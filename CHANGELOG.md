# 更新日志

本项目的所有重要变更都会记录在此文件中，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

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

[Unreleased]: https://github.com/y17920/ho-fuqing-water/compare/v1.3.0...HEAD
[1.3.0]: https://github.com/y17920/ho-fuqing-water/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/y17920/ho-fuqing-water/releases/tag/v1.2.0
