"""福清水务API客户端

接口契约（实测验证）：
- 请求: POST http://fqswwt.fjfqwater.com/iwatermgr/invoice/list.json
  Content-Type: application/x-www-form-urlencoded
  body: requestPara=<URL编码的JSON字符串>
- requestPara 中 startMonth/endMonth 必须为不带引号的 null（fastjson 严格解析）
- 响应: {"count":null,"data":[账单列表],"status":200,"message":null,...}
- 账单数值字段均为字符串，解析时需统一 float() 容错
"""
import asyncio
import logging
from typing import Any

import aiohttp

from .const import BASE_URL, FIXED_REQUEST_PARAMS, API_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class FuqingWaterAPIError(Exception):
    """福清水务API异常"""

    def __init__(self, message: str, code: int = -1):
        self.message = message
        self.code = code
        super().__init__(self.message)


class FuqingWaterTokenExpiredError(FuqingWaterAPIError):
    """Token过期/无效异常 - 集成可据此设置 token_expired 状态"""


class FuqingWaterAPI:
    """福清水务API客户端（需 Token 初始化）"""

    def __init__(self, token: str):
        self.token = token
        self._headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
            "MicroMessenger/8.0.49(0x18003123) NetType/WIFI Language/zh_CN",
            "Referer": "http://fqswwt.fjfqwater.com/",
            "Origin": "http://fqswwt.fjfqwater.com",
        }

    def _build_request_para(self, card_no: str, year_num: str) -> str:
        """构建 requestPara JSON 字符串

        注意：手动构建 JSON（startMonth/endMonth 必须为 null 字面量，不带引号）
        """
        params = dict(FIXED_REQUEST_PARAMS)
        params["cardNos"] = str(card_no)
        params["yearNum"] = str(year_num)
        params["token"] = str(self.token)
        items = []
        for key, value in params.items():
            if value is None:
                items.append(f'"{key}":null')
            elif isinstance(value, bool):
                items.append(f'"{key}":{str(value).lower()}')
            elif isinstance(value, (int, float)):
                items.append(f'"{key}":{value}')
            else:
                items.append(f'"{key}":"{value}"')
        return "{" + ",".join(items) + "}"

    async def _request(self, card_no: str, year_num: str) -> list:
        """发送 API 请求，返回账单列表"""
        request_para = self._build_request_para(card_no, year_num)
        timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    BASE_URL,
                    data={"requestPara": request_para},
                    headers=self._headers,
                ) as response:
                    if response.status == 401 or response.status == 403:
                        raise FuqingWaterTokenExpiredError(
                            f"HTTP {response.status} - Token已失效"
                        )

                    raw_text = await response.text()

                    # 服务器异常时可能返回 HTML 错误页
                    stripped = raw_text.strip()
                    if stripped.startswith("<!doctype") or stripped.startswith("<html"):
                        _LOGGER.error(
                            "福清水务接口返回 HTML 错误页 (HTTP %s)，Token 可能已失效",
                            response.status,
                        )
                        raise FuqingWaterTokenExpiredError(
                            "接口返回异常页面，Token可能已失效"
                        )
                    if response.status != 200:
                        raise FuqingWaterAPIError(
                            f"HTTP {response.status}", response.status
                        )

                    import json as _json

                    try:
                        data = _json.loads(stripped)
                    except (ValueError, TypeError) as e:
                        _LOGGER.error("福清水务接口响应 JSON 解析失败: %s", e)
                        raise FuqingWaterAPIError("响应解析失败", -3) from e

                    status = data.get("status")
                    message = data.get("message") or "API error"

                    # -115: 指定年份无账单数据（实测返回 {"status":-115,"data":null,"message":null}）
                    # 属正常情况（如新水表往年无记录），静默返回空列表
                    if status == -115:
                        _LOGGER.debug(
                            "福清水务接口无数据 (status=-115): 户号=%s 年份=%s",
                            card_no,
                            year_num,
                        )
                        return []

                    # status != 200 视为业务失败（token 无效时通常返回非 200）
                    if status != 200:
                        _LOGGER.error(
                            "福清水务接口错误: %s (status=%s)", message, status
                        )
                        # 401/403 或明确提示 token 相关错误视为 Token 失效
                        if status in (401, 403, 10001, 10002, 10003):
                            raise FuqingWaterTokenExpiredError(str(message), status)
                        raise FuqingWaterAPIError(str(message), status)

                    bills = data.get("data")
                    return bills if isinstance(bills, list) else []

        except (FuqingWaterAPIError, FuqingWaterTokenExpiredError):
            raise
        except aiohttp.ClientError as e:
            _LOGGER.error("网络错误: %s", e)
            raise FuqingWaterAPIError(f"Network error: {e}", -1) from e
        except asyncio.TimeoutError as e:
            _LOGGER.error("请求超时")
            raise FuqingWaterAPIError("Request timeout", -2) from e

    async def get_bills(self, card_no: str, year_num: str | None = None) -> list:
        """获取指定户号、指定年份的账单列表

        Args:
            card_no: 水费户号
            year_num: 年份（如 "2026"），默认当前年份

        Returns:
            账单列表（按月份降序），字段为字符串型数值
        """
        from datetime import datetime

        if not year_num:
            year_num = str(datetime.now().year)
        return await self._request(card_no, year_num)

    async def validate(self, card_no: str) -> list:
        """校验 token + 户号有效性（配置流程使用）

        返回当前年份账单列表；空列表视为户号无数据
        """
        return await self.get_bills(card_no)
