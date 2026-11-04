# 更新日志

本项目的所有重要变更都会记录在此文件中，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [1.3.4] - 2026-11-04

### 新增

- 零用水月份补零：抓包确认某月 0 用水时接口不返回该月账单，新增 `_fill_missing_months` 把历史区间内缺失的月份按 0 用水补齐（仅在内存中参与月均、累计与统计注入，不写回 Storage，也不会被当作最新账单）

### 修复

- 历史月均 `history_avg_usage` 与 `usage_vs_avg` 因零用水月份未计入分母而偏高
- 能源面板长期统计在零用水月份出现断月：外部统计现在为该月输出 `state=0`、累计 `sum` 持平的数据点；SQLite 直写的累计曲线同样补齐平段数据点

## [1.3.3] - 2026-11-04

### 修复

- Release 附件 `fuqing_water.zip` 改为扁平结构（`manifest.json`、`__init__.py` 位于 zip 根目录）：HACS 会把 zip 直接解压到 `config/custom_components/fuqing_water/`，旧版 zip 内多套了一层 `fuqing_water/` 会导致安装后目录多一级、集成无法加载
- `Release` 工作流新增 zip 结构校验，根目录缺少 `manifest.json` / `__init__.py` / `const.py` 时直接失败，避免再次发布错误结构的附件

## [1.3.2] - 2026-11-04

### 修复

- `hacs.json` 最低支持版本由 `2026.11.0` 降为 `2024.11.0`，避免旧版 HA 在 HACS 中被「需要更高版本」拦截
- 统计元数据改为按当前 HA 支持的字段构造：旧版本没有 `StatisticMeanType` 时自动省略 `mean_type` / `unit_class`，不再整段跳过外部统计注入

## [1.3.1] - 2026-11-04

### 变更

- 发布方式改为 GitHub Release 附件：`hacs.json` 启用 `zip_release` 并指定 `filename: fuqing_water.zip`，HACS 安装/升级时下载 Release 中的 zip，而非仓库源码快照
- 新增 `Release` 工作流（`.github/workflows/release.yml`）：推送 `v*` tag 时校验 tag 与 `manifest.json` 版本一致，打包 `custom_components/fuqing_water` 为 `fuqing_water.zip` 并创建/更新 Release 附件

## [1.3.0] - 2026-11-04

### 新增

- 仓库调整为 HACS 可发布结构：集成代码迁入 `custom_components/fuqing_water/`，根目录新增 `hacs.json`、`LICENSE`、`.gitignore`
- 新增 GitHub Actions 校验工作流（`hacs/action` + `home-assistant/actions/hassfest`）
- 新增品牌图片 `custom_components/fuqing_water/brand/{icon,logo}.png`

### 变更

- `manifest.json`：`documentation` / `issue_tracker` 指向 `https://github.com/y17920/ho-fuqing-water`，`codeowners` 改为 `@y17920`，移除非规范字段 `authors`，版本升至 `1.3.0`
- `fuqing_water.refresh_history` 服务改为全局注册一次，`entry_id` 变为可选参数：留空刷新全部实例，指定则只刷新对应实例
- 卸载集成时只清理当前配置条目的数据，最后一个实例卸载后才注销服务
- 启动时的历史统计注入改用 `entry.async_create_background_task`，避免阻塞 HA 关闭
- 选项流程改用 `self.config_entry`，移除已废弃的构造函数传入 entry 写法
- 配置流程以 `DOMAIN` 常量替代硬编码域名
- `strings.json` 与 `translations/zh-Hans.json` 补全 `title`、重新配置的 `{card_no}` 占位符与 `invalid_poll_hours` 错误文案
- `services.yaml` 补充 `entry_id` 字段定义

### 修复

- 多户号场景下，后添加的实例会覆盖先前注册的 `refresh_history` 服务
- 卸载单个实例会误删其他实例的 `hass.data` 数据
- Token 过期通知中的链接指向已失效的配置流跳转地址，现指向「设置 → 设备与服务 → 福清水务」

## [1.2.0]

### 新增

- 阶梯水价计算（0–25 / 25–30 / >30 m³ 三档 + 污水处理费），新增当前阶梯、预估本月账单等传感器
- 历史账单自动回溯至 2022 年，结果持久化到 HA `Store`
- 直接写入 recorder SQLite（`statistics_meta` / `statistics`），补全实体累计统计
- 通过 `async_add_external_statistics` 注入月度用水量 / 月度水费长期统计，支持能源面板
- Token 过期持久通知与 UI 内重新配置流程（reconfigure）
- 适配 HA 2026.11 统计 API（`StatisticMetaData.unit_class`）

[Unreleased]: https://github.com/y17920/ho-fuqing-water/compare/v1.3.3...HEAD
[1.3.3]: https://github.com/y17920/ho-fuqing-water/compare/v1.3.2...v1.3.3
[1.3.2]: https://github.com/y17920/ho-fuqing-water/compare/v1.3.1...v1.3.2
[1.3.1]: https://github.com/y17920/ho-fuqing-water/compare/v1.3.0...v1.3.1
[1.3.0]: https://github.com/y17920/ho-fuqing-water/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/y17920/ho-fuqing-water/releases/tag/v1.2.0
