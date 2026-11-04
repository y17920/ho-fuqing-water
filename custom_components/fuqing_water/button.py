"""福清水务手动刷新按钮"""
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_CARD_NO

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """设置按钮实体"""
    card_no = entry.data[CONF_CARD_NO]
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator = entry_data.get("coordinator")

    if coordinator is None:
        _LOGGER.error("福清水务: 未找到 coordinator，按钮设置失败")
        return

    async_add_entities([FuqingWaterRefreshButton(coordinator, entry, card_no)])


class FuqingWaterRefreshButton(CoordinatorEntity, ButtonEntity):
    """手动刷新按钮（触发 coordinator 刷新 + 历史统计注入）"""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry: ConfigEntry, card_no: str):
        super().__init__(coordinator)
        self.entry = entry
        self.card_no = card_no
        self._attr_unique_id = f"{DOMAIN}_{card_no}_refresh"
        self._attr_name = "立即刷新"
        self._attr_icon = "mdi:refresh"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.card_no)},
            name=f"福清水务 - {self.card_no}",
            manufacturer="福清水务",
            model="智能水表",
        )

    async def async_press(self) -> None:
        """按钮按下：刷新数据 + 注入历史统计"""
        _LOGGER.info("福清水务: 用户触发手动刷新（户号=%s）", self.card_no)
        await self.coordinator.async_request_refresh()
        try:
            from .sensor import _import_water_history_to_statistics

            await _import_water_history_to_statistics(self.hass, self.entry)
        except Exception as e:
            _LOGGER.warning("刷新历史统计失败: %s", e)
