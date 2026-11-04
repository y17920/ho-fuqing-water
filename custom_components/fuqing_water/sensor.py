"""福清水务传感器 - 完整版

功能：
- 完整版传感器集（本期/上期读数、用水量、账单金额、水费明细、缴费状态、
  抄表日期、户名地址、历史月均、累计用水量、累计水费等）
- 首次初始化并发抓取近 2 年历史账单，合并去重后存 Storage
- 当月未出账兜底：用水量/累计值保持上次有效值（RestoreEntity + 缓存）
- 统计注入：async_add_external_statistics 官方 API，支持能源面板
"""
import asyncio
import logging
from datetime import timedelta, datetime
from typing import Any, Dict, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.helpers.restore_state import RestoreEntity

try:
    from homeassistant.components.sensor import SensorEntity
    from homeassistant.components.sensor.const import SensorStateClass
except ImportError:
    from homeassistant.helpers.entity import Entity as SensorEntity

    class SensorStateClass:
        MEASUREMENT = "measurement"
        TOTAL = "total"
        TOTAL_INCREASING = "total_increasing"

from .api import FuqingWaterAPI, FuqingWaterAPIError, FuqingWaterTokenExpiredError
from .const import (
    DOMAIN,
    CONF_TOKEN,
    CONF_CARD_NO,
    CONF_POLL_HOURS,
    DEFAULT_POLL_HOURS,
    EARLIEST_HISTORY_YEAR,
    INTEGRATION_STATUS,
    TIER_PRICE_1,
    TIER_PRICE_2,
    TIER_PRICE_3,
    TIER_THRESHOLD_1,
    TIER_THRESHOLD_2,
    SEWAGE_UNIT_PRICE,
)

_LOGGER = logging.getLogger(__name__)

SENSOR_TYPES = {
    # 账户信息
    "client_name": {
        "name": "户名",
        "icon": "mdi:account",
        "unit": None,
    },
    "account_address": {
        "name": "用水地址",
        "icon": "mdi:home-map-marker",
        "unit": None,
    },
    # 最新账单
    "last_reading": {
        "name": "上期读数",
        "icon": "mdi:counter",
        "unit": "m³",
        "state_class": SensorStateClass.TOTAL_INCREASING,
    },
    "current_reading": {
        "name": "本期读数",
        "icon": "mdi:counter",
        "unit": "m³",
        "state_class": SensorStateClass.TOTAL_INCREASING,
    },
    "water_used": {
        "name": "本期用水量",
        "icon": "mdi:water",
        "unit": "m³",
        "device_class": "water",
        "state_class": SensorStateClass.TOTAL,
    },
    "bill_amount": {
        "name": "账单金额",
        "icon": "mdi:receipt",
        "unit": "CNY",
        "device_class": "monetary",
        "state_class": SensorStateClass.TOTAL,
    },
    "received_amount": {
        "name": "已缴金额",
        "icon": "mdi:cash-check",
        "unit": "CNY",
        "device_class": "monetary",
        "state_class": SensorStateClass.TOTAL,
    },
    "late_fee": {
        "name": "滞纳金",
        "icon": "mdi:cash-remove",
        "unit": "CNY",
        "device_class": "monetary",
        "state_class": SensorStateClass.TOTAL,
    },
    "fee_state": {
        "name": "缴费状态",
        "icon": "mdi:checkbox-marked-circle",
        "unit": None,
    },
    # 水费明细
    "basics_fee": {
        "name": "基本水费",
        "icon": "mdi:currency-cny",
        "unit": "CNY",
        "device_class": "monetary",
        "state_class": SensorStateClass.TOTAL,
    },
    "sewage_fee": {
        "name": "污水费",
        "icon": "mdi:recycle",
        "unit": "CNY",
        "device_class": "monetary",
        "state_class": SensorStateClass.TOTAL,
    },
    "unit_price": {
        "name": "水价单价",
        "icon": "mdi:currency-cny",
        "unit": "CNY/m³",
        "state_class": SensorStateClass.MEASUREMENT,
    },
    # 阶梯水价（福清居民生活用水，按月计量，为固定政策值）
    "water_price_step1": {
        "name": "一阶水价",
        "icon": "mdi:numeric-1-box",
        "unit": "CNY/m³",
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "water_price_step2": {
        "name": "二阶水价",
        "icon": "mdi:numeric-2-box",
        "unit": "CNY/m³",
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "water_price_step3": {
        "name": "三阶水价",
        "icon": "mdi:numeric-3-box",
        "unit": "CNY/m³",
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "water_price_sewage": {
        "name": "污水处理费",
        "icon": "mdi:recycle",
        "unit": "CNY/m³",
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "price_threshold1": {
        "name": "一阶阈值",
        "icon": "mdi:stairs-up",
        "unit": "m³",
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "price_threshold2": {
        "name": "二阶阈值",
        "icon": "mdi:stairs-up",
        "unit": "m³",
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "current_step": {
        "name": "当前阶梯",
        "icon": "mdi:stairs",
        "unit": None,
    },
    "estimated_bill_amount": {
        "name": "预估本月账单",
        "icon": "mdi:calculator",
        "unit": "CNY",
        "device_class": "monetary",
        "state_class": SensorStateClass.TOTAL,
    },
    # 抄表日期
    "last_read_date": {
        "name": "上期抄表日期",
        "icon": "mdi:calendar",
        "unit": None,
    },
    "current_read_date": {
        "name": "本期抄表日期",
        "icon": "mdi:calendar",
        "unit": None,
    },
    "meter_cycle": {
        "name": "抄表周期",
        "icon": "mdi:calendar-range",
        "unit": None,
    },
    "billing_month": {
        "name": "账单月份",
        "icon": "mdi:calendar-month",
        "unit": None,
    },
    # 统计与预警
    "history_avg_usage": {
        "name": "历史月均用水",
        "icon": "mdi:history",
        "unit": "m³",
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "usage_vs_avg": {
        "name": "与均值对比",
        "icon": "mdi:percent",
        "unit": "%",
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "estimated_monthly_usage": {
        "name": "预估月用水量",
        "icon": "mdi:chart-line",
        "unit": "m³",
        "device_class": "water",
        "state_class": SensorStateClass.TOTAL,
    },
    # 能源面板专用
    "water_history_cumulative": {
        "name": "水表历史累计",
        "icon": "mdi:water",
        "unit": "m³",
        "device_class": "water",
        "state_class": SensorStateClass.TOTAL_INCREASING,
    },
    "total_water_cost": {
        "name": "累计水费",
        "icon": "mdi:cash-multiple",
        "unit": "CNY",
        "device_class": "monetary",
        "state_class": SensorStateClass.TOTAL,
    },
    # 诊断
    "integration_status": {
        "name": "集成状态",
        "icon": "mdi:heart-pulse",
        "unit": None,
    },
    "last_update_time": {
        "name": "最后更新时间",
        "icon": "mdi:clock-outline",
        "unit": None,
    },
}

CUMULATIVE_SENSORS = ("water_history_cumulative", "total_water_cost", "water_used")


def _to_float(value: Any, default: float = 0.0) -> float:
    """字符串型数值安全转 float"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _tiered_water_cost(usage: float) -> float:
    """阶梯水费（不含污水费）

    福清居民阶梯（按月）：0-25 吨 2.20 元，25-30 吨 3.30 元，30 吨以上 4.40 元
    """
    if usage <= 0:
        return 0.0
    step1 = min(usage, TIER_THRESHOLD_1)
    step2 = max(0.0, min(usage, TIER_THRESHOLD_2) - TIER_THRESHOLD_1)
    step3 = max(0.0, usage - TIER_THRESHOLD_2)
    return step1 * TIER_PRICE_1 + step2 * TIER_PRICE_2 + step3 * TIER_PRICE_3


def _tiered_total_cost(usage: float) -> float:
    """阶梯总费用 = 阶梯水费 + 污水处理费（0.95 元/m³，不参与阶梯）"""
    if usage <= 0:
        return 0.0
    return _tiered_water_cost(usage) + usage * SEWAGE_UNIT_PRICE


def _calc_current_step(usage: float) -> int:
    """根据本期用水量判断当前所处阶梯"""
    if usage <= 0:
        return 1
    if usage <= TIER_THRESHOLD_1:
        return 1
    if usage <= TIER_THRESHOLD_2:
        return 2
    return 3


class FuqingWaterDataUpdateCoordinator(DataUpdateCoordinator):
    """福清水务数据更新协调器（单户号）"""

    def __init__(self, hass: HomeAssistant, entry_id: str, token: str, card_no: str, poll_hours: int):
        self.api = FuqingWaterAPI(token)
        self._entry_id = entry_id
        self.card_no = card_no
        self.poll_hours = poll_hours
        # 历史初始化标志
        self._history_init_done = False
        self._history_init_lock = asyncio.Lock()
        # Token 过期通知标志
        self._token_expired_notified = False
        # 上次有效缓存（防当月未出账回退）
        self._last_good: Dict[str, Any] = {}
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=poll_hours),
        )

    def _get_history_store(self):
        """获取历史账单 Storage 实例（延迟初始化）"""
        try:
            from homeassistant.helpers.storage import Store

            return Store(
                hass=self.hass,
                version=1,
                key=f"{DOMAIN}_history_{self.card_no}",
            )
        except Exception as e:
            _LOGGER.error("创建历史 Store 失败（%s）: %s", self.card_no, e)
            return None

    async def _load_billing_history(self) -> list:
        """从 HA Storage 加载历史账单"""
        try:
            store = self._get_history_store()
            if store is None:
                return []
            data = await store.async_load()
            return data if isinstance(data, list) else []
        except Exception:
            return []

    async def _save_billing_history(self, history: list) -> None:
        """保存历史账单到 Storage"""
        try:
            store = self._get_history_store()
            if store is None:
                return
            await store.async_save(history)
        except Exception as e:
            _LOGGER.error("保存历史记录失败（%s）: %s", self.card_no, e)

    @staticmethod
    def _parse_bills(bills: list) -> list:
        """标准化账单列表：提取关键字段 + 去重 + 排序（月份降序）"""
        history = []
        for bill in bills:
            # feeMonth 格式 "2026/08" → "202608"
            fee_month = str(bill.get("feeMonth", "") or "").replace("/", "")
            if len(fee_month) != 6:
                continue
            history.append(
                {
                    "billing_month": fee_month,
                    "water_used": _to_float(bill.get("practicalWater")),
                    "bill_amount": _to_float(bill.get("feeMoney")),
                    "received_amount": _to_float(bill.get("receivedMoney")),
                    "basics_fee": _to_float(bill.get("basicsFeeMoney")),
                    "sewage_fee": _to_float(bill.get("sewageFeeMoney")),
                    "unit_price": _to_float(bill.get("basicsFeeUnitPrice")),
                    "last_reading": _to_float(bill.get("preto")),
                    "current_reading": _to_float(bill.get("thisto")),
                    "last_read_date": str(bill.get("preCopyDate", "") or ""),
                    "current_read_date": str(bill.get("thisCopyDate", "") or ""),
                    "meter_cycle": str(bill.get("copyMeterCycle", "") or ""),
                    "fee_state": str(bill.get("feeStateStr", "") or ""),
                    "late_fee": _to_float(bill.get("lateFee")),
                    "fee_id": str(bill.get("feeId", "") or ""),
                }
            )
        # 去重（按 billing_month）
        seen = set()
        unique = []
        for h in history:
            if h["billing_month"] not in seen:
                seen.add(h["billing_month"])
                unique.append(h)
        # 月份降序
        unique.sort(key=lambda x: x["billing_month"], reverse=True)
        return unique

    async def _init_billing_history_from_api(self) -> list:
        """首次初始化：逐年回溯抓取历史账单，合并去重

        逻辑：从当前年开始逐年往前请求到 EARLIEST_HISTORY_YEAR（2022 年）；
        无数据年份（status=-115）跳过继续，不中断；请求失败记录后同样继续；
        有数据的年份全部收集入库
        """
        now = datetime.now()
        all_bills = []
        fetched_years = []  # 有数据的年份
        empty_years = []  # 无数据的年份（跳过）
        error_years = []  # 请求失败的年份

        for year in range(now.year, EARLIEST_HISTORY_YEAR - 1, -1):
            try:
                bills = await self.api.get_bills(self.card_no, str(year))
            except Exception as e:
                _LOGGER.warning("抓取 %s 年账单失败，跳过继续: %s", year, e)
                error_years.append(year)
            else:
                if bills:
                    all_bills.extend(bills)
                    fetched_years.append(year)
                else:
                    # status=-115（该年份无账单数据），跳过继续往前追
                    empty_years.append(year)
                    _LOGGER.info("  %s 年无账单数据，跳过继续向前", year)
            await asyncio.sleep(0.5)  # 防限流

        _LOGGER.info(
            "福清水务：历史账单回溯完成（%s），范围 %s-%s；"
            "有数据年份 %s，无数据年份 %s，失败年份 %s，原始账单 %s 条",
            self.card_no,
            EARLIEST_HISTORY_YEAR,
            now.year,
            fetched_years,
            empty_years,
            error_years,
            len(all_bills),
        )

        parsed = self._parse_bills(all_bills)

        # 与已有历史合并（保留旧数据，API 数据覆盖同月份）
        existing = await self._load_billing_history()
        if existing:
            existing_map = {
                h.get("billing_month"): h for h in existing if h.get("billing_month")
            }
            for h in parsed:
                existing_map[h["billing_month"]] = h
            merged = list(existing_map.values())
            merged.sort(key=lambda x: x["billing_month"], reverse=True)
            result = merged
            _LOGGER.info(
                "  与已有历史合并完成: 共 %s 条（API 新增 %s 条）",
                len(result),
                len(parsed),
            )
        else:
            result = parsed
            _LOGGER.info(
                "  历史账单初始化完成，共 %s 条（抓取年份: %s）",
                len(result),
                fetched_years,
            )

        if result:
            await self._save_billing_history(result)

        return result

    def _make_card_result(self) -> dict:
        """生成默认数据结构"""
        result = {
            "client_name": "未知",
            "account_address": "未知",
            "last_reading": 0,
            "current_reading": 0,
            "water_used": 0,
            "bill_amount": 0,
            "received_amount": 0,
            "late_fee": 0,
            "fee_state": "未知",
            "basics_fee": 0,
            "sewage_fee": 0,
            "unit_price": 0,
            # 阶梯水价（政策固定值）
            "water_price_step1": TIER_PRICE_1,
            "water_price_step2": TIER_PRICE_2,
            "water_price_step3": TIER_PRICE_3,
            "water_price_sewage": SEWAGE_UNIT_PRICE,
            "price_threshold1": TIER_THRESHOLD_1,
            "price_threshold2": TIER_THRESHOLD_2,
            "current_step": 1,
            "estimated_bill_amount": 0,
            "last_read_date": "未知",
            "current_read_date": "未知",
            "meter_cycle": "未知",
            "billing_month": "未知",
            "history_avg_usage": 0,
            "usage_vs_avg": 0,
            "estimated_monthly_usage": 0,
            "water_history_cumulative": 0,
            "total_water_cost": 0,
            "integration_status": "unknown",
            "last_update_time": "未知",
        }
        return result

    async def _async_update_data(self) -> dict:
        """更新数据"""
        result = self._make_card_result()
        token_expired = False
        api_error = False
        current_bills = []

        # 1. 拉取当前年份账单
        try:
            current_bills = await self.api.get_bills(self.card_no)
        except FuqingWaterTokenExpiredError as e:
            _LOGGER.error("Token已过期: %s", e)
            token_expired = True
        except FuqingWaterAPIError as e:
            _LOGGER.error("获取账单失败: %s", e)
            api_error = True

        # 2. 解析账单数据
        parsed = self._parse_bills(current_bills)
        if parsed:
            latest = parsed[0]
            result["billing_month"] = latest["billing_month"]
            result["last_reading"] = latest["last_reading"]
            result["current_reading"] = latest["current_reading"]
            result["water_used"] = latest["water_used"]
            result["bill_amount"] = latest["bill_amount"]
            result["received_amount"] = latest["received_amount"]
            result["late_fee"] = latest["late_fee"]
            result["fee_state"] = latest["fee_state"]
            result["basics_fee"] = latest["basics_fee"]
            result["sewage_fee"] = latest["sewage_fee"]
            result["unit_price"] = latest["unit_price"]
            result["last_read_date"] = latest["last_read_date"] or "未知"
            result["current_read_date"] = latest["current_read_date"] or "未知"
            result["meter_cycle"] = latest["meter_cycle"] or "未知"
            # 户名/地址从原始账单提取
            if current_bills:
                raw = current_bills[0]
                result["client_name"] = str(raw.get("clientName", "") or "未知")
                result["account_address"] = str(raw.get("accountAddress", "") or "未知")

        # 3. 历史初始化（首次或覆盖不足时）
        history = await self._load_billing_history()
        if not self._history_init_done:
            async with self._history_init_lock:
                if not self._history_init_done:
                    try:
                        init_history = await self._init_billing_history_from_api()
                        if init_history:
                            history = init_history
                            self._history_init_done = True
                    except Exception as e:
                        _LOGGER.warning("初始化历史账单失败（可稍后重试）: %s", e)

        # 4. 统计计算（历史均值、与均值对比、累计值）
        if history:
            total_usage = sum(_to_float(h.get("water_used")) for h in history)
            avg = round(total_usage / len(history), 2) if history else 0
            result["history_avg_usage"] = avg
            current_usage = result.get("water_used", 0)
            if avg > 0:
                result["usage_vs_avg"] = round((current_usage - avg) / avg * 100, 1)

            # 累计值（历史已按月份降序，正序累加）
            cumul = 0.0
            cumul_cost = 0.0
            for h in sorted(history, key=lambda x: x["billing_month"]):
                cumul += _to_float(h.get("water_used"))
                cumul_cost += _to_float(h.get("bill_amount"))
            result["water_history_cumulative"] = round(cumul, 1)
            result["total_water_cost"] = round(cumul_cost, 2)

        # 5. 当月未出账兜底：用水量/累计值保持上次有效值（防回退）
        prev = self._last_good
        if prev:
            if result["water_used"] <= 0 and prev.get("water_used", 0) > 0:
                result["water_used"] = prev["water_used"]
                _LOGGER.debug("当月未出账，用水量保持上次值: %s m³", prev["water_used"])
            if (
                result["water_history_cumulative"] <= 0
                and prev.get("water_history_cumulative", 0) > 0
            ):
                result["water_history_cumulative"] = prev["water_history_cumulative"]
            if result["total_water_cost"] <= 0 and prev.get("total_water_cost", 0) > 0:
                result["total_water_cost"] = prev["total_water_cost"]

        # 6. 预估月用水量（按当月已过天数线性外推）
        now = datetime.now()
        if now.day > 0 and result["water_used"] > 0:
            import calendar

            days_in_month = calendar.monthrange(now.year, now.month)[1]
            result["estimated_monthly_usage"] = round(
                result["water_used"] / now.day * days_in_month, 2
            )

        # 7. 阶梯水价计算（福清居民阶梯，污水费固定 0.95 元/m³）
        usage_now = result["water_used"]
        result["current_step"] = _calc_current_step(usage_now)
        result["water_price_step1"] = TIER_PRICE_1
        result["water_price_step2"] = TIER_PRICE_2
        result["water_price_step3"] = TIER_PRICE_3
        result["water_price_sewage"] = SEWAGE_UNIT_PRICE
        result["price_threshold1"] = TIER_THRESHOLD_1
        result["price_threshold2"] = TIER_THRESHOLD_2
        result["estimated_bill_amount"] = round(_tiered_total_cost(usage_now), 2)

        # 8. 状态判断
        if token_expired:
            result["integration_status"] = "token_expired"
            if not self._token_expired_notified:
                self._token_expired_notified = True
                try:
                    from . import async_token_expired_notification

                    await async_token_expired_notification(self.hass, self._entry_id)
                except Exception as e:
                    _LOGGER.error("发送Token过期通知失败: %s", e)
        elif api_error:
            result["integration_status"] = "network_error"
        else:
            result["integration_status"] = "normal"
            # 缓存本次成功数据（防回退用）
            self._last_good = {
                "water_used": result["water_used"],
                "water_history_cumulative": result["water_history_cumulative"],
                "total_water_cost": result["total_water_cost"],
            }

        result["last_update_time"] = now.strftime("%Y-%m-%d %H:%M:%S")

        _LOGGER.info(
            "福清水务数据更新完成: 户号=%s, 状态=%s, 本期用水=%s m³, 账单=¥%s",
            self.card_no,
            result["integration_status"],
            result["water_used"],
            result["bill_amount"],
        )

        return result


class FuqingWaterSensor(RestoreEntity, CoordinatorEntity, SensorEntity):
    """福清水务传感器"""

    def __init__(
        self,
        coordinator: FuqingWaterDataUpdateCoordinator,
        entry: ConfigEntry,
        sensor_id: str,
        card_no: str,
    ):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.entry = entry
        self.sensor_id = sensor_id
        self.card_no = card_no
        self._attr_has_entity_name = True
        self._restored_state = None

        sensor_cfg = SENSOR_TYPES.get(sensor_id, {})
        self._attr_device_class = sensor_cfg.get("device_class")
        self._attr_state_class = sensor_cfg.get("state_class")

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN}_{self.card_no}_{self.sensor_id}"

    @property
    def name(self) -> str:
        return SENSOR_TYPES[self.sensor_id]["name"]

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, self.card_no)},
            "name": f"福清水务 - {self.card_no}",
            "manufacturer": "福清水务",
            "model": "智能水表",
        }

    @property
    def native_value(self):
        """返回传感器状态值"""
        if not self.coordinator.data:
            return self._restored_state
        value = self.coordinator.data.get(self.sensor_id)

        # current_step 显示为"第X阶梯"
        if self.sensor_id == "current_step" and isinstance(value, int):
            return f"第{value}阶梯"

        # 累计值防回退：值无效时使用恢复状态
        if self.sensor_id in CUMULATIVE_SENSORS:
            if value is None or value <= 0:
                if self._restored_state is not None:
                    return self._restored_state

        return value

    @property
    def native_unit_of_measurement(self) -> str | None:
        return SENSOR_TYPES[self.sensor_id].get("unit")

    @property
    def icon(self) -> str | None:
        base_icon = SENSOR_TYPES[self.sensor_id].get("icon")
        # 当前阶梯根据阶梯级别显示不同图标
        if self.sensor_id == "current_step" and self.coordinator.data:
            step = self.coordinator.data.get("current_step", 1)
            if step == 1:
                return "mdi:numeric-1-box-outline"
            elif step == 2:
                return "mdi:numeric-2-box-outline"
            return "mdi:numeric-3-box-outline"
        # 缴费状态动态图标
        if self.sensor_id == "fee_state" and self.coordinator.data:
            state = str(self.coordinator.data.get("fee_state", ""))
            if "销帐" in state or "已缴" in state:
                return "mdi:check-circle"
            elif "欠" in state:
                return "mdi:alert-circle"
        return base_icon

    @property
    def extra_state_attributes(self) -> dict:
        """额外状态属性"""
        data = self.coordinator.data or {}
        raw_status = data.get("integration_status", "unknown")
        attrs = {
            "card_no": self.card_no,
            "last_update": self.coordinator.last_update_success,
            "integration_status": raw_status,
            "integration_status_cn": INTEGRATION_STATUS.get(raw_status, raw_status),
        }
        if raw_status == "token_expired":
            attrs["操作指引"] = "请在集成配置中重新粘贴 Token"
        return attrs

    @property
    def available(self) -> bool:
        """传感器可用性 - token 过期时仍显示（状态为 token_expired）"""
        if not self.coordinator.data:
            return self.coordinator.last_update_success
        return True

    async def async_added_to_hass(self):
        """添加到 HA - 恢复上次状态避免 unknown 间隙"""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in (None, "unknown", "unavailable"):
            try:
                self._restored_state = float(last_state.state)
            except (ValueError, TypeError):
                self._restored_state = last_state.state
        if self.coordinator.data is not None or self._restored_state is not None:
            self.async_write_ha_state()


async def _import_water_history_to_statistics(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """注入历史统计（async_add_external_statistics 官方 API，支持能源面板）"""
    card_no = entry.data.get(CONF_CARD_NO)
    if not card_no:
        return

    store = None
    try:
        from homeassistant.helpers.storage import Store

        store = Store(hass=hass, version=1, key=f"{DOMAIN}_history_{card_no}")
    except Exception as e:
        _LOGGER.error("创建历史 Store 失败: %s", e)
        return

    try:
        data = await store.async_load()
        history = data if isinstance(data, list) else []
    except Exception:
        history = []

    if len(history) < 2:
        _LOGGER.info("历史账单数据不足（%s 条），跳过统计注入", len(history))
        return

    history.sort(key=lambda b: str(b.get("billing_month", "")))

    try:
        from homeassistant.components.recorder.statistics import (
            async_add_external_statistics,
            StatisticMetaData,
        )

        try:
            # HA 2026.11 起统计元数据改用 mean_type 枚举，旧版本没有该定义
            from homeassistant.components.recorder.statistics import (
                StatisticMeanType,
            )
        except ImportError:
            StatisticMeanType = None  # type: ignore[assignment,misc]

        def _build_meta(**kwargs: Any) -> StatisticMetaData:
            """丢弃当前 HA 版本不支持的字段（unit_class / mean_type 等）"""
            allowed = getattr(StatisticMetaData, "__annotations__", {})
            return cast(
                StatisticMetaData, {k: v for k, v in kwargs.items() if k in allowed}
            )

        usage_stats = []
        cost_stats = []
        cumulative = 0.0
        cumulative_cost = 0.0
        for bill in history:
            bm = str(bill.get("billing_month", "") or "")
            if len(bm) != 6:
                continue
            year, month = int(bm[:4]), int(bm[4:6])
            if year < 2020 or year > 2035 or month < 1 or month > 12:
                continue
            # 账单月份对齐：用水发生在上月末~本月末，统计点取上月1日（与温州一致）
            month -= 1
            if month == 0:
                month = 12
                year -= 1
            from datetime import timezone

            start = datetime(year, month, 1, tzinfo=timezone.utc)
            water_amt = _to_float(bill.get("water_used"))
            bill_amt = _to_float(bill.get("bill_amount"))
            cumulative += water_amt
            cumulative_cost += bill_amt
            usage_stats.append(
                {
                    "start": start,
                    "state": water_amt,
                    "sum": cumulative,
                    "min": water_amt,
                    "max": water_amt,
                    "mean": 0.0,
                    "mean_weight": 0.0,
                    "last_reset": start,
                }
            )
            cost_stats.append(
                {
                    "start": start,
                    "state": bill_amt,
                    "sum": cumulative_cost,
                    "min": bill_amt,
                    "max": bill_amt,
                    "mean": 0.0,
                    "mean_weight": 0.0,
                    "last_reset": start,
                }
            )

        mean_type = StatisticMeanType.NONE if StatisticMeanType is not None else None

        if usage_stats:
            async_add_external_statistics(
                hass,
                _build_meta(
                    has_mean=False,
                    has_sum=True,
                    name=f"历史月度用水量-{card_no}",
                    source=DOMAIN,
                    statistic_id=f"{DOMAIN}:{card_no}_monthly_water_usage",
                    unit_of_measurement="m³",
                    unit_class="volume",
                    mean_type=mean_type,
                ),
                usage_stats,
            )
        if cost_stats:
            async_add_external_statistics(
                hass,
                _build_meta(
                    has_mean=False,
                    has_sum=True,
                    name=f"历史月度水费-{card_no}",
                    source=DOMAIN,
                    statistic_id=f"{DOMAIN}:{card_no}_monthly_water_cost",
                    unit_of_measurement="CNY",
                    unit_class=None,
                    mean_type=mean_type,
                ),
                cost_stats,
            )
        _LOGGER.info("外部统计注入完成（%s）", card_no)
    except ImportError:
        _LOGGER.warning("recorder 组件不可用，跳过外部统计注入")
    except Exception as e:
        _LOGGER.error("统计注入失败: %s", e)

    # === 第二部分: SQLite 直写（历史账单逐月写入实体统计表，移植自温州版） ===
    import sqlite3
    import time as time_mod
    from datetime import timezone

    stats_data = []
    cumulative = 0.0
    cumulative_cost = 0.0
    for bill in history:
        bm = str(bill.get("billing_month", "") or "")
        if len(bm) != 6:
            continue
        year, month = int(bm[:4]), int(bm[4:6])
        if year < 2020 or year > 2035 or month < 1 or month > 12:
            continue
        # 账单月份对齐：统计点取上月1日（与外部统计注入一致）
        month -= 1
        if month == 0:
            month = 12
            year -= 1
        cumulative += _to_float(bill.get("water_used"))
        cumulative_cost += _to_float(bill.get("bill_amount"))
        start_ts = datetime(year, month, 1, tzinfo=timezone.utc).timestamp()
        stats_data.append((start_ts, round(cumulative, 3), round(cumulative_cost, 3)))

    if not stats_data:
        return

    # gap-fill：补齐统计点到当前月（累计值持平），保证当月也有数据点
    last_dt = datetime.fromtimestamp(stats_data[-1][0], tz=timezone.utc)
    now_dt = datetime.now()
    fill_year, fill_month = last_dt.year, last_dt.month
    while True:
        fill_month += 1
        if fill_month > 12:
            fill_month = 1
            fill_year += 1
        if fill_year > now_dt.year or (
            fill_year == now_dt.year and fill_month > now_dt.month
        ):
            break
        fill_ts = datetime(fill_year, fill_month, 1, tzinfo=timezone.utc).timestamp()
        stats_data.append((fill_ts, stats_data[-1][1], stats_data[-1][2]))

    db_path = hass.config.path("home-assistant_v2.db")
    now_ts = time_mod.time()

    # 通过 entity_registry 查找传感器实体 ID（unique_id → entity_id）
    entity_data = []
    try:
        from homeassistant.helpers import entity_registry as er

        reg = er.async_get(hass)
    except Exception:
        reg = None
    targets = (
        ("water_history_cumulative", "m³", "水表历史累计", "usage"),
        ("total_water_cost", "CNY", "累计水费", "cost"),
    )
    for sensor_type, unit, cname, key in targets:
        uid = f"{DOMAIN}_{card_no}_{sensor_type}"
        if reg:
            try:
                eid = reg.async_get_entity_id("sensor", DOMAIN, uid)
                if eid:
                    entity_data.append((eid, unit, cname, key))
            except Exception:
                pass

    if not entity_data:
        _LOGGER.info("未找到累计传感器实体，跳过 SQLite 直写（%s）", card_no)
        return

    def _do_inject():
        conn = None
        try:
            conn = sqlite3.connect(db_path, timeout=10)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("BEGIN IMMEDIATE")

            # 统计元数据不存在则创建
            for eid, eunit, cname, _key in entity_data:
                conn.execute(
                    "INSERT OR IGNORE INTO statistics_meta "
                    "(statistic_id, source, unit_of_measurement, has_mean, has_sum, name) "
                    "VALUES (?, ?, ?, 0, 1, ?)",
                    (eid, DOMAIN, eunit, cname),
                )

            # 变化检测：无变化则跳过写入，避免重复写库
            changed = False
            for eid, _unit, _cname, key in entity_data:
                row = conn.execute(
                    "SELECT id FROM statistics_meta WHERE statistic_id = ?", (eid,)
                ).fetchone()
                if row is None:
                    changed = True
                    break
                existing = dict(
                    conn.execute(
                        "SELECT start_ts, sum FROM statistics WHERE metadata_id = ? ORDER BY start_ts",
                        (row[0],),
                    ).fetchall()
                )
                wanted = {
                    d[0]: (d[1] if key == "usage" else d[2])
                    for d in stats_data
                    if (d[1] if key == "usage" else d[2]) > 0
                }
                if set(existing) != set(wanted) or any(
                    abs(existing.get(ts, 0) - val) > 0.001 for ts, val in wanted.items()
                ):
                    changed = True
                    break

            if not changed:
                conn.rollback()
                _LOGGER.info("SQLite 直写：数据无变化，跳过（%s）", card_no)
                return

            # 有变化则全量重写
            for eid, _unit, _cname, _key in entity_data:
                row = conn.execute(
                    "SELECT id FROM statistics_meta WHERE statistic_id = ?", (eid,)
                ).fetchone()
                if row:
                    conn.execute("DELETE FROM statistics WHERE metadata_id = ?", (row[0],))

            for ts, cumul_usage, cumul_cost in stats_data:
                for eid, _unit, _cname, key in entity_data:
                    val = cumul_usage if key == "usage" else cumul_cost
                    if val <= 0:
                        continue
                    row = conn.execute(
                        "SELECT id FROM statistics_meta WHERE statistic_id = ?", (eid,)
                    ).fetchone()
                    if row:
                        conn.execute(
                            "INSERT INTO statistics (metadata_id, start_ts, state, sum, min, max, mean, last_reset_ts, created_ts) "
                            "VALUES (?, ?, ?, ?, ?, ?, 0.0, ?, ?)",
                            (row[0], ts, val, val, val, val, ts, now_ts),
                        )

            conn.commit()
            _LOGGER.info(
                "SQLite 直写完成（%s）：每实体 %s 条月度统计", card_no, len(stats_data)
            )
        except sqlite3.Error as e:
            _LOGGER.error("SQLite 直写失败: %s", e)
            if conn:
                conn.rollback()
        except Exception as e:
            _LOGGER.error("SQLite 直写意外错误: %s", e)
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()

    await hass.async_add_executor_job(_do_inject)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """设置传感器"""
    token = entry.data[CONF_TOKEN]
    card_no = entry.data[CONF_CARD_NO]

    poll_hours = entry.options.get(CONF_POLL_HOURS, DEFAULT_POLL_HOURS)
    try:
        poll_hours = max(1, min(24, int(poll_hours)))
    except (TypeError, ValueError):
        poll_hours = DEFAULT_POLL_HOURS

    coordinator = FuqingWaterDataUpdateCoordinator(hass, entry.entry_id, token, card_no, poll_hours)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "card_no": card_no,
    }

    await coordinator.async_config_entry_first_refresh()

    entities = [
        FuqingWaterSensor(coordinator, entry, sensor_id, card_no)
        for sensor_id in SENSOR_TYPES
    ]
    async_add_entities(entities)
