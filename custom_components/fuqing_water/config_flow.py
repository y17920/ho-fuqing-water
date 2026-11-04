"""福清水务配置流程

- 初始配置：粘贴 token + 户号，实测校验后创建集成
- 重新配置（reconfigure）：token 过期后更新 token
- 选项流程：轮询间隔设置
"""
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, OptionsFlow, ConfigEntry
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .api import (
    FuqingWaterAPI,
    FuqingWaterAPIError,
    FuqingWaterTokenExpiredError,
)
from .const import (
    DOMAIN,
    CONF_TOKEN,
    CONF_CARD_NO,
    CONF_POLL_HOURS,
    DEFAULT_POLL_HOURS,
    ERROR_CANNOT_CONNECT,
    ERROR_INVALID_AUTH,
    ERROR_UNKNOWN,
    STEP_USER,
    STEP_RECONFIGURE,
)

_LOGGER = logging.getLogger(__name__)


class FuqingWaterConfigFlow(ConfigFlow, domain=DOMAIN):

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry):
        return FuqingWaterOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """初始配置：粘贴 token + 户号"""
        errors = {}
        schema = vol.Schema(
            {
                vol.Required(CONF_TOKEN): str,
                vol.Required(CONF_CARD_NO): str,
            }
        )

        if user_input is not None:
            token = user_input.get(CONF_TOKEN, "").strip()
            card_no = user_input.get(CONF_CARD_NO, "").strip()

            if not token or not card_no:
                errors["base"] = ERROR_INVALID_AUTH
            else:
                try:
                    bills = await FuqingWaterAPI(token).validate(card_no)
                    _LOGGER.info(
                        "福清水务配置校验成功: 户号=%s, 当前年份账单 %s 条",
                        card_no,
                        len(bills),
                    )
                    await self.async_set_unique_id(f"fuqing_water_{card_no}")
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=f"福清水务 - {card_no}",
                        data={
                            CONF_TOKEN: token,
                            CONF_CARD_NO: card_no,
                        },
                    )
                except FuqingWaterTokenExpiredError as e:
                    _LOGGER.error("福清水务配置校验失败（Token无效）: %s", e)
                    errors["base"] = ERROR_INVALID_AUTH
                except FuqingWaterAPIError as e:
                    _LOGGER.error("福清水务配置校验失败（网络/接口异常）: %s", e)
                    errors["base"] = ERROR_CANNOT_CONNECT
                except Exception as e:
                    _LOGGER.exception("福清水务配置校验未知异常: %s", e)
                    errors["base"] = ERROR_UNKNOWN

        return self.async_show_form(
            step_id=STEP_USER,
            data_schema=schema,
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """重新配置：token 过期后更新 token"""
        errors = {}
        reconfigure_entry = self._get_reconfigure_entry()
        card_no = reconfigure_entry.data.get(CONF_CARD_NO, "")

        schema = vol.Schema(
            {
                vol.Required(CONF_TOKEN): str,
            }
        )

        if user_input is not None:
            token = user_input.get(CONF_TOKEN, "").strip()
            if not token:
                errors["base"] = ERROR_INVALID_AUTH
            else:
                try:
                    await FuqingWaterAPI(token).validate(card_no)
                    _LOGGER.info("福清水务重新配置成功: 户号=%s", card_no)
                    return self.async_update_reload_and_abort(
                        reconfigure_entry,
                        data_updates={CONF_TOKEN: token},
                    )
                except FuqingWaterTokenExpiredError as e:
                    _LOGGER.error("福清水务重新配置失败（Token无效）: %s", e)
                    errors["base"] = ERROR_INVALID_AUTH
                except FuqingWaterAPIError as e:
                    _LOGGER.error("福清水务重新配置失败（网络/接口异常）: %s", e)
                    errors["base"] = ERROR_CANNOT_CONNECT
                except Exception as e:
                    _LOGGER.exception("福清水务重新配置未知异常: %s", e)
                    errors["base"] = ERROR_UNKNOWN

        return self.async_show_form(
            step_id=STEP_RECONFIGURE,
            data_schema=schema,
            errors=errors,
            description_placeholders={"card_no": card_no},
        )


class FuqingWaterOptionsFlow(OptionsFlow):
    """选项流程：轮询间隔设置"""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors = {}

        if user_input is not None:
            poll_hours = int(user_input.get(CONF_POLL_HOURS, DEFAULT_POLL_HOURS))
            if not 1 <= poll_hours <= 24:
                errors["base"] = "invalid_poll_hours"
            else:
                return self.async_create_entry(title="", data={CONF_POLL_HOURS: poll_hours})

        current = self.config_entry.options.get(
            CONF_POLL_HOURS,
            self.config_entry.data.get(CONF_POLL_HOURS, DEFAULT_POLL_HOURS),
        )

        schema = vol.Schema(
            {
                vol.Required(CONF_POLL_HOURS, default=current): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=24)
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )
