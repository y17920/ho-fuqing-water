# CODEBUDDY.md This file provides guidance to CodeBuddy when working with code in this repository.

## Commands

This is a Home Assistant (HA) custom integration; it has no dedicated build system, linter config, or test suite checked in. The project is developed inside a running HA instance.

Repository layout (HACS-publishable): the integration lives in `custom_components/fuqing_water/`; the repo root holds only `hacs.json`, `README.md`, `CHANGELOG.md`, `LICENSE`, `.github/workflows/{validate,release}.yml` and this file. Publish target: `https://github.com/y17920/ho-fuqing-water`. When bumping the version in `manifest.json`, add a matching section to `CHANGELOG.md`.

Releases: `hacs.json` sets `zip_release: true` + `filename: fuqing_water.zip`, so HACS installs from the Release asset, not from the repo snapshot (a tag without a Release/asset means no update for users). Every version must therefore be published as a GitHub Release whose asset is `fuqing_water.zip` built from `custom_components/` (root of the zip is `custom_components/fuqing_water/...`). `.github/workflows/release.yml` does this automatically on `v*` tag push and fails when the tag differs from the `manifest.json` version.

- **Syntax check**: `python -m compileall custom_components/fuqing_water` compiles all `.py` files and reports syntax errors without running HA. Useful as a fast sanity check after edits.

- **Lint (optional)**: `ruff check .` (after `pip install ruff`) surfaces style and import issues. There is no committed `ruff`/`pyproject` config, so treat its output as advisory.

- **Load into Home Assistant**: copy or symlink `custom_components/fuqing_water` into `<config>/custom_components/fuqing_water` (HACS does this automatically), restart HA (or reload Core), then add the integration via Settings → Devices & Services. This is the real "run" step; there is no standalone runtime.

- **Run Home Assistant**: `hass --config <config_dir>` (or `python -m homeassistant --config <config_dir>`) starts HA pointed at a test config, allowing live testing of config flow, sensors, and services. Requires a valid `token` + `card_no` (抓包 from the 福清水务 WeChat mini-program).

- **Single test**: there is no test framework or single-test runner. Validate behavior by exercising the config flow in the UI and checking the generated sensors, the refresh button, and the `fuqing_water.refresh_history` service. Check HA logs for the integration's `_LOGGER` output.

## Architecture

### What it is

`fuqing_water` is a Home Assistant custom integration (`domain = "fuqing_water"`, 福清水务) that polls a single water utility's billing API and exposes water-usage/billing data as entities. It targets one water account (户号, `card_no`) per config entry. `manifest.json` declares `integration_type: "device"` and `iot_class: "cloud_polling"`; `config_flow: true` means users add/configure it entirely through the HA UI (no `configuration.yaml` setup). There are no Python package requirements (`requirements: []`); the only external dependency is `aiohttp`, which ships with HA.

### File map and responsibilities

- `const.py` — all shared constants: API URL, fixed request params, water pricing tiers, config/option keys, error codes, status strings.
- `api.py` — `FuqingWaterAPI`, the only network layer; builds the request body and parses responses.
- `sensor.py` — the core: sensor type catalog, the data coordinator, sensor entities, and the statistics-injection pipeline.
- `button.py` — a single manual-refresh `ButtonEntity`.
- `config_flow.py` — `ConfigFlow` (initial + reconfigure) and `OptionsFlow` (poll interval).
- `__init__.py` — integration entry point, platform forwarding, service registration, and token-expiry notification.
- `services.yaml` / `strings.json` / `translations/zh-Hans.json` — service definition and Chinese UI strings for the config flow.

### Lifecycle and wiring

`async_setup` is a no-op returning `True` (UI-config-only integration). The real work starts in `async_setup_entry` (`__init__.py`), which:

1. Creates `hass.data[DOMAIN][entry.entry_id]` to hold per-entry state.
2. Forwards setup to two platforms via `async_forward_entry_setups(entry, ["sensor", "button"])`.
3. Schedules a delayed task (`async_auto_inject`) that waits 10 s then calls `_import_water_history_to_statistics` to backfill energy-panel history on startup.
4. Registers the `fuqing_water.refresh_history` service, which re-runs the same statistics injection on demand.

`async_unload_entry` unloads both platforms and pops the per-entry data. `async_migrate_entry` is a stub.

### The coordinator is the single source of truth

The heart of the integration is `FuqingWaterDataUpdateCoordinator` (a `DataUpdateCoordinator`) in `sensor.py`. One coordinator exists per config entry, stored under `hass.data[DOMAIN][entry.entry_id]["coordinator"]`, with `update_interval` set from the `poll_hours` option (default 1, clamped 1–24). Both the sensor and button platforms look up this coordinator by `entry.entry_id`, so the button and all sensors share the same fetch/refresh cycle.

`async_setup_entry` in `sensor.py` builds the coordinator, calls `async_config_entry_first_refresh()`, then instantiates one `FuqingWaterSensor` per key in the `SENSOR_TYPES` dict (30+ sensors) plus the single refresh button. Each sensor's `native_value` simply reads `self.coordinator.data[sensor_id]`, so the whole data model is a flat dict of strings/floats produced once per refresh.

### Data flow of one refresh

`_async_update_data` (in the coordinator) is the main pipeline:

1. Fetch current-year bills via `self.api.get_bills(self.card_no)`.
2. Parse them with `_parse_bills`, which normalizes each bill into a canonical dict keyed by `billing_month` (`feeMonth` "2026/08" → "202608"), dedupes by month, and sorts descending. All numeric API fields are strings, so `_to_float` is applied defensively everywhere.
3. Take the newest bill as the "current" values (readings, usage, amount, fee breakdown, meter dates).
4. On first refresh only (`_history_init_done` flag guarded by an `asyncio.Lock`), backfill history year-by-year: `_init_billing_history_from_api` loops from the current year down to `EARLIEST_HISTORY_YEAR` (2022), calling `get_bills` per year, skipping empty years and surviving failed years, with a 0.5 s sleep between requests to avoid rate limiting. Results are merged with any previously stored history (API wins per month) and persisted.
5. Compute derived stats: monthly average, percent-vs-average, cumulative usage/cost (summing history in chronological order).
6. Apply anti-regression fallback from `_last_good`: if the current month has no bill yet, keep the previous non-zero usage/cumulative values instead of dropping to 0.
7. Estimate current-month usage by linear extrapolation from days elapsed.
8. Compute tiered pricing: `_tiered_water_cost` / `_tiered_total_cost` implement Fuqing's three-tier residential pricing (0–25 m³ @ 2.20, 25–30 m³ @ 3.30, >30 m³ @ 4.40 yuan) plus a flat sewage fee (0.95 yuan/m³). Thresholds/prices live in `const.py`.
9. Set `integration_status` (`normal` / `token_expired` / `network_error`), and on `token_expired` fire a one-time persistent notification (deduplicated by `_token_expired_notified` flag).

Sensors also use `RestoreEntity`: `async_added_to_hass` restores the last known state so entities don't flash `unknown` on restart, and `CUMULATIVE_SENSORS` keep their restored value when a fresh value is `None`/`<= 0`.

### History persistence and statistics injection

Billing history is persisted in HA's `Store` under key `fuqing_water_history_{card_no}` (`_load_billing_history` / `_save_billing_history`). This store is the durable record that both the coordinator (for averages/cumulatives) and the statistics injector read from.

`_import_water_history_to_statistics` is the most intricate multi-system piece and is invoked from three places: the startup auto-inject task, the `refresh_history` service, and the refresh button's `async_press`. It has two independent halves:

- **Official API path**: uses `homeassistant.components.recorder.statistics.async_add_external_statistics` to register two long-term statistics (monthly water usage in m³, monthly water cost in CNY) with `statistic_id` `fuqing_water:{card_no}_monthly_water_usage` / `..._monthly_water_cost`. Bill months are shifted back one month (a "202608" bill counts as a statistic point at 2026-07-01) to align the meter-reading period with the preceding calendar month.

- **Direct SQLite path** ("ported from 温州版"): writes cumulative values directly into HA's recorder database (`home-assistant_v2.db`) tables `statistics_meta` and `statistics`, for the `water_history_cumulative` and `total_water_cost` entities. It resolves entity IDs via the entity registry (unique_id → entity_id), creates metadata rows if missing, detects changes and skips the write when nothing changed, gap-fills monthly points up to the current month with flat cumulative values, and does a full delete-and-rewrite when anything changed. This runs on the executor thread (`async_add_executor_job`) with `BEGIN IMMEDIATE` and WAL mode.

Because this integration writes the recorder DB directly, be careful when editing this function: it bypasses HA's normal statistics APIs and must stay schema-compatible with the recorder tables, and the change-detection logic exists specifically to avoid redundant DB writes on every refresh.

### API client quirks

`FuqingWaterAPI` in `api.py` talks to `POST http://fqswwt.fjfqwater.com/iwatermgr/invoice/list.json` with `application/x-www-form-urlencoded` and a single `requestPara` field containing a URL-encoded JSON string. The JSON is built **manually** (`_build_request_para`) rather than via `json.dumps` because the server uses fastjson strict parsing that requires `startMonth`/`endMonth` to be the bare literal `null` (no quotes). The fixed params in `const.py.FIXED_REQUEST_PARAMS` (e.g. `isOpen`, `type`, `systemcode`, `waterCorpId`, `clientType: "iOS"`) and a mobile WeChat `User-Agent`/`Referer` header set are required for the request to be accepted.

Error handling distinguishes three outcomes: `FuqingWaterTokenExpiredError` (HTTP 401/403, HTML error page, or business status 401/403/10001/10002/10003), generic `FuqingWaterAPIError` (network, timeout, parse, or other business status), and the benign `status == -115` case (no bills for that year) which silently returns `[]` so history backfill can skip a year without aborting.

### Configuration

`config_flow.py` defines `VERSION = 1` and two steps:

- `user` — collect `token` + `card_no`, validate by calling `FuqingWaterAPI(token).validate(card_no)` (fetch current-year bills), enforce uniqueness per card number, and create the entry.
- `reconfigure` — collect a new `token` only, validate it against the existing `card_no`, then `async_update_reload_and_abort` with the updated token. This is the flow users follow when the token expires.

`OptionsFlow` stores `poll_hours` (validated 1–24) in the entry's options. Note that `sensor.py` re-reads `poll_hours` at setup time and clamps it, so changing options takes effect on reload.

### Conventions to preserve

- Domain is the `DOMAIN` constant; don't hardcode `"fuqing_water"`.
- Entity `unique_id`s follow `{DOMAIN}_{card_no}_{sensor_id}`; devices are grouped by `identifiers={(DOMAIN, card_no)}`.
- All numeric handling goes through `_to_float` (API returns strings).
- The tiered-price math and thresholds are policy constants in `const.py`; update them there, not inline.
- Logging uses each module's `_LOGGER` with Chinese messages; keep it for consistency with the user-facing tone.
