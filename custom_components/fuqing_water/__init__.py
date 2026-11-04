"""福清水务 Home Assistant 集成"""
import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_ENTRY_ID,
    CONF_CARD_NO,
    DOMAIN,
    SERVICE_REFRESH_HISTORY,
)

PLATFORMS = ["sensor", "button"]

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """YAML 不参与配置，仅通过 UI 添加。"""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """设置配置条目。"""
    hass.data.setdefault(DOMAIN, {})

    # 启动延迟注入历史统计任务（供能源面板使用）
    async def async_auto_inject():
        await asyncio.sleep(10)
        try:
            from .sensor import _import_water_history_to_statistics

            await _import_water_history_to_statistics(hass, entry)
        except Exception as e:
            _LOGGER.warning("自动注入历史统计失败（可通过按钮/服务补救）: %s", e)

    entry.async_create_background_task(
        hass, async_auto_inject(), f"{DOMAIN}_history_inject_{entry.entry_id}"
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if not hass.services.has_service(DOMAIN, SERVICE_REFRESH_HISTORY):
        hass.services.async_register(
            DOMAIN, SERVICE_REFRESH_HISTORY, _async_handle_refresh_history
        )

    return True


async def _async_handle_refresh_history(call: ServiceCall) -> None:
    """服务：手动刷新历史统计数据（可选 entry_id 限定单个实例）。"""
    hass = call.hass
    entry_id = call.data.get(ATTR_ENTRY_ID)
    entries = hass.config_entries.async_entries(DOMAIN)
    if entry_id:
        entries = [e for e in entries if e.entry_id == entry_id]
        if not entries:
            _LOGGER.warning("未找到配置条目 %s，无法刷新历史统计", entry_id)
            return

    from .sensor import _import_water_history_to_statistics

    for entry in entries:
        _LOGGER.info("用户触发: 刷新历史统计数据（%s）", entry.data.get(CONF_CARD_NO))
        try:
            await _import_water_history_to_statistics(hass, entry)
            _LOGGER.info("历史统计数据刷新完成（%s）", entry.data.get(CONF_CARD_NO))
        except Exception as e:
            _LOGGER.error(
                "刷新历史统计数据失败（%s）: %s", entry.data.get(CONF_CARD_NO), e
            )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """卸载配置条目。"""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        remaining = [
            e for e in hass.config_entries.async_entries(DOMAIN) if e.entry_id != entry.entry_id
        ]
        if not remaining:
            hass.data.pop(DOMAIN, None)
            hass.services.async_remove(DOMAIN, SERVICE_REFRESH_HISTORY)
    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """配置条目迁移（当前无历史版本需迁移）。"""
    _LOGGER.info("福清水务: 迁移 config entry 从 version %s", config_entry.version)
    return True


async def async_token_expired_notification(hass: HomeAssistant, entry_id: str) -> None:
    """Token 过期通知"""
    try:
        await hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": "⚠️ 福清水务 Token 已过期",
                "message": "福清水务集成的 Token 已失效，数据将停止更新。\n\n"
                "请从福清水务微信小程序重新抓包获取 Token，然后点击下方按钮更新：\n\n"
                "[重新配置 →](/config/integrations/integration/fuqing_water)\n\n"
                "路径：设置 → 设备与服务 → 福清水务 → 重新配置",
                "notification_id": f"fuqing_water_token_expired_{entry_id}",
            },
            blocking=True,
        )
        _LOGGER.warning("福清水务: Token过期通知已发送")
    except Exception as e:
        _LOGGER.warning("福清水务: 发送Token过期通知失败: %s", e)
