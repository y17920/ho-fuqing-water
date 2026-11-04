"""福清水务集成常量"""

# 平台
DOMAIN = "fuqing_water"
PLATFORM_NAME = "福清水务"

# API配置
BASE_URL = "http://fqswwt.fjfqwater.com/iwatermgr/invoice/list.json"
API_TIMEOUT = 30

# requestPara 固定参数（实测验证，fastjson 严格解析，startMonth/endMonth 必须为 null 字面量）
FIXED_REQUEST_PARAMS = {
    "isOpen": 2,
    "type": 1,
    "startMonth": None,
    "endMonth": None,
    "systemcode": "GD",
    "accountType": "XJ",
    "waterCorpId": 3,
    "UNID": "",
    "areaId": 0,
    "appVersion": "1.0.2",
    "clientType": "iOS",
    "htmlVersion": "1.0.4",
    "apiType": "JSAPI",
}

# 历史账单回溯最早年份：从当前年开始逐年回溯到此年份为止；
# 无数据年份跳过继续（不中断），请求失败同样跳过
EARLIEST_HISTORY_YEAR = 2022

# 福清居民生活用水阶梯水价（按月计量）
# 第一水量：每户每月 0-25 吨（含25吨）2.20 元/吨
# 第二水量：每户每月 25-30 吨（含30吨）3.30 元/吨
# 第三水量：每户每月 30 吨以上 4.40 元/吨
TIER_PRICE_1 = 2.20
TIER_PRICE_2 = 3.30
TIER_PRICE_3 = 4.40
TIER_THRESHOLD_1 = 25  # 一阶上限（含）
TIER_THRESHOLD_2 = 30  # 二阶上限（含）

# 居民生活污水处理费（元/立方米，不参与阶梯）
SEWAGE_UNIT_PRICE = 0.95

# 配置键
CONF_TOKEN = "token"
CONF_CARD_NO = "card_no"

# Options 键
CONF_POLL_HOURS = "poll_hours"
DEFAULT_POLL_HOURS = 1

# ConfigFlow Step IDs
STEP_USER = "user"
STEP_RECONFIGURE = "reconfigure"

# 服务
SERVICE_REFRESH_HISTORY = "refresh_history"
ATTR_ENTRY_ID = "entry_id"

# 错误码
ERROR_CANNOT_CONNECT = "cannot_connect"
ERROR_INVALID_AUTH = "invalid_auth"
ERROR_UNKNOWN = "unknown"

# 集成状态定义
INTEGRATION_STATUS = {
    "normal": "正常",
    "token_expired": "密钥过期",
    "network_error": "网络异常",
    "api_error": "API错误",
}
