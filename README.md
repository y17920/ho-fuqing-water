# 福清水务 Home Assistant 集成

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![version](https://img.shields.io/badge/version-1.3.3-blue.svg)](https://github.com/y17920/ho-fuqing-water/releases)
[![Validate](https://github.com/y17920/ho-fuqing-water/actions/workflows/validate.yml/badge.svg)](https://github.com/y17920/ho-fuqing-water/actions/workflows/validate.yml)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Changelog](https://img.shields.io/badge/changelog-CHANGELOG.md-blue.svg)](CHANGELOG.md)

福清市自来水（福清水务）账单查询的 Home Assistant 自定义集成。通过抓包获取的 Token 轮询官方接口，将用水量、账单金额、缴费状态、阶梯水价等信息接入 HA，并支持注入历史数据到**能源面板**。

## 功能特性

- **基础信息**：户名、用水地址、水费户号
- **账单数据**：本期/上期读数、本期用水量、账单金额、已缴金额、滞纳金、缴费状态
- **水费明细**：基本水费、污水费、水价单价
- **抄表信息**：上期/本期抄表日期、抄表周期、账单月份
- **阶梯水价**：一/二/三阶水价、污水处理费、阶梯阈值、当前阶梯、预估本月账单
- **统计分析**：历史月均用水、与均值对比（%）、预估月用水量、累计用水量、累计水费
- **历史回溯**：首次加载自动回溯 2022 年至今的历年账单，本地持久化保存
- **能源面板**：注入月度用水量 / 月度水费长期统计，可在能源面板中使用
- **Token 过期提醒**：Token 失效时自动发送持久通知，并支持 UI 内一键重新配置
- **手动刷新**：提供 "立即刷新" 按钮与 `fuqing_water.refresh_history` 服务

## 安装

仓库地址：<https://github.com/y17920/ho-fuqing-water>

### 方式一：HACS（推荐）

1. HACS → 集成 → 右上角菜单 → 自定义存储库
2. 仓库地址填写 `https://github.com/y17920/ho-fuqing-water`，类别选择 `Integration`
3. 搜索并安装「福清水务」，重启 Home Assistant

HACS 安装/升级时下载的是最新 GitHub Release 中的 `fuqing_water.zip` 附件。

### 方式二：手动安装

1. 在 [Releases](https://github.com/y17920/ho-fuqing-water/releases) 下载最新的 `fuqing_water.zip` 并解压（zip 根目录就是集成文件：`__init__.py`、`manifest.json` 等）
2. 将解压出的全部文件放入 `<HA 配置目录>/custom_components/fuqing_water/`
3. 重启 Home Assistant

最终目录结构应为：

```
config/
└── custom_components/
    └── fuqing_water/
        ├── __init__.py
        ├── api.py
        ├── button.py
        ├── config_flow.py
        ├── const.py
        ├── manifest.json
        ├── sensor.py
        ├── services.yaml
        ├── strings.json
        └── translations/
            └── zh-Hans.json
```

### 仓库结构（开发者）

```
ho-fuqing-water/
├── custom_components/
│   └── fuqing_water/          # 集成本体（HACS 只打包此目录）
├── .github/workflows/
│   ├── validate.yml           # HACS + hassfest 校验
│   └── release.yml            # 打 tag 时打包并发布 Release 附件
├── hacs.json                  # HACS 发布元数据
├── CHANGELOG.md               # 版本更新日志
├── LICENSE
└── README.md
```

本地校验（可选，需要 Python 环境）：

```bash
python -m compileall custom_components/fuqing_water
```

推送后 GitHub Actions 会自动运行 HACS 与 hassfest 校验。

### 发布新版本

HACS 通过 `hacs.json` 的 `zip_release` 下载 GitHub Release 附件 `fuqing_water.zip`，因此**每个版本都必须以 GitHub Release 的形式发布**，仅打 tag 用户收不到更新。

1. 修改 `custom_components/fuqing_water/manifest.json` 的 `version`（如 `1.3.3`）
2. 在 [`CHANGELOG.md`](CHANGELOG.md) 中新增对应版本小节，并更新其中的对比链接
3. 提交后打 tag 并推送：

```bash
git tag v1.3.3
git push origin v1.3.3
```

`Release` 工作流会自动校验 tag 与 `manifest.json` 版本一致，将 `custom_components/fuqing_water` 打包成 `fuqing_water.zip` 并创建（或更新）对应 Release。

手动发布时同样必须上传 `fuqing_water.zip`。注意 HACS 会把 zip 直接解压到 `config/custom_components/fuqing_water/`，因此 **zip 根目录必须就是集成本身**（`manifest.json` 在根上），不能再套 `fuqing_water/` 或 `custom_components/` 一层：

```bash
cd custom_components/fuqing_water && zip -r ../../fuqing_water.zip . && cd ../..
gh release create v1.3.3 fuqing_water.zip --title v1.3.3 --generate-notes
```

## 配置

1. 打开福清水务微信小程序，登录并查看水费账单
2. 使用抓包工具（如 Stream / Charles / mitmproxy）抓取 `fqswwt.fjfqwater.com` 的请求，获取其中的 `token` 参数
3. 在 HA 中进入 **设置 → 设备与服务 → 添加集成**，搜索「福清水务」
4. 填入 **Token** 与 **水费户号**，提交后集成会自动校验

> 每个户号只能添加一次。如需添加多个户号，重复上述步骤即可。

### 选项设置

在集成详情页进入「配置」，可设置 **轮询间隔（小时）**，范围 1–24，默认 1 小时。

## Token 过期处理

福清水务的 Token 有有效期。过期后：

- 集成状态传感器会变为 `token_expired`（密钥过期），数据停止更新
- HA 会发送一次持久通知提醒

**解决方法**：重新抓包获取新 Token，然后点击通知中的链接，或进入 **设置 → 设备与服务 → 福清水务 → 重新配置**，粘贴新 Token 即可，无需删除重建集成。

## 实体列表

| 实体 | 说明 | 单位 |
|------|------|------|
| 户名 | 用水户名 | - |
| 用水地址 | 用水地址 | - |
| 上期读数 | 上期水表读数 | m³ |
| 本期读数 | 本期水表读数 | m³ |
| 本期用水量 | 本期用水量 | m³ |
| 账单金额 | 本期账单金额 | CNY |
| 已缴金额 | 已缴纳金额 | CNY |
| 滞纳金 | 滞纳金 | CNY |
| 缴费状态 | 销帐 / 欠费等 | - |
| 基本水费 | 基本水费金额 | CNY |
| 污水费 | 污水处理费金额 | CNY |
| 水价单价 | 账单中的单价 | CNY/m³ |
| 一阶水价 / 二阶水价 / 三阶水价 | 阶梯单价（政策固定值） | CNY/m³ |
| 污水处理费 | 污水单价（政策固定值） | CNY/m³ |
| 一阶阈值 / 二阶阈值 | 阶梯分界水量 | m³ |
| 当前阶梯 | 根据本期用水量判断 | - |
| 预估本月账单 | 按阶梯水价计算 | CNY |
| 上期抄表日期 / 本期抄表日期 | 抄表日期 | - |
| 抄表周期 / 账单月份 | 抄表周期与账单月 | - |
| 历史月均用水 | 历史账单平均用水量 | m³ |
| 与均值对比 | 本期相对历史均值的偏差 | % |
| 预估月用水量 | 按已过天数线性外推 | m³ |
| 水表历史累计 | 历史累计用水量 | m³ |
| 累计水费 | 历史累计水费 | CNY |
| 集成状态 | 正常 / 密钥过期 / 网络异常 / API错误 | - |
| 最后更新时间 | 最后一次成功拉取时间 | - |
| 立即刷新（按钮） | 手动触发刷新 + 统计注入 | - |

## 服务

### `fuqing_water.refresh_history`

手动触发历史账单统计注入，用于修复能源面板数据。

```yaml
service: fuqing_water.refresh_history
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `entry_id` | 否 | 配置条目 ID（集成实例）；留空则刷新所有福清水务实例 |

## 能源面板

集成会自动向 HA recorder 注入两组长期统计：

| statistic_id | 说明 | 单位 |
|--------------|------|------|
| `fuqing_water:{户号}_monthly_water_usage` | 历史月度用水量 | m³ |
| `fuqing_water:{户号}_monthly_water_cost` | 历史月度水费 | CNY |

在 **设置 → 仪表盘 → 能源** 中添加「水 Consumption」，选择上述统计即可。

> 说明：账单月份会向前偏移一个月作为统计时间点（例如 2026 年 8 月账单记为 2026-07-01），以匹配实际用水周期。
> 统计注入会在集成加载 10 秒后自动执行一次，之后由刷新按钮或 `refresh_history` 服务触发。

## 阶梯水价说明

福清居民生活用水按**月**计量，阶梯水价如下（内置固定值，见 `const.py`）：

| 阶梯 | 用水量 | 单价 |
|------|--------|------|
| 第一阶梯 | 0–25 m³（含） | 2.20 元/m³ |
| 第二阶梯 | 25–30 m³（含） | 3.30 元/m³ |
| 第三阶梯 | 30 m³ 以上 | 4.40 元/m³ |

污水处理费：0.95 元/m³（不参与阶梯，按实际用水量计收）。

> 预估账单基于上述政策价计算，可能与实际账单存在差异（如含水表维护费、滞纳金等），仅供参考。

## 数据存储

- 历史账单保存在 HA 的 `.storage/` 中，key 为 `fuqing_water_history_{户号}`
- 首次加载时从当前年份逐年回溯到 2022 年；无数据的年份会自动跳过
- 新拉取的账单会与本地历史合并，同月份以接口数据为准

## 故障排查

| 现象 | 可能原因与处理 |
|------|----------------|
| 配置时报「Token 无效或户号无数据」 | Token 失效 / 户号填写有误 / 该户号当年无账单 |
| 配置时报「网络异常」 | 无法访问 `fqswwt.fjfqwater.com`，检查网络或稍后重试 |
| 集成状态为「密钥过期」 | 重新抓包并重新配置 Token |
| 能源面板无数据 | 调用 `fuqing_water.refresh_history` 服务手动注入，或检查历史账单是否 ≥ 2 条 |
| 当月用水量为 0 | 当月尚未出账，集成会保持上次有效值并保持为 0 直至新账单生成 |

日志关键字（搜索 `fuqing_water` 可定位）：

- `自动注入历史统计失败`
- `统计注入失败`
- `历史账单回溯完成`
- `Token已过期`

## 已知限制

- 只支持查询账单，不支持缴费
- Token 需手动抓包，且会过期
- 接口为 HTTP 明文，且需模拟微信 UA
- 统计数据依赖历史账单条数，新装水表首月数据较少

## 免责声明

本集成非官方实现，仅用于个人学习和家庭自用。接口来自福清水务微信公众号/小程序，可能随时变更导致功能失效。

## 版本

当前版本 **1.3.3**，完整变更记录见 [CHANGELOG.md](CHANGELOG.md)。

## 许可证

[MIT](LICENSE)
