# 03 进度看板与交接卡 · 合璧字幕 HebiSubs

## 阶段看板

| 阶段 | 状态 | 开始 | 完成 | 产出 |
|---|---|---|---|---|
| P0 准备 | ✅ 完成 | 2026-10-15 | 2026-10-15 | 仓库、CLAUDE.md、文档 v0.1、api-notes（MP V3 开发要点 / 本机环境）、最小空插件 v0.0.1（实机冒烟通过） |
| P1 研读海拉鲁 | ⬜ 未开始 | | | |
| P2 接口实测 | ⬜ 未开始 | | | |
| P3 需求定稿 + 架构 | ⬜ 未开始 | | | |
| P4 MVP | ⬜ 未开始 | | | |
| P5 自动化 | ⬜ 未开始 | | | |
| P6 合成 | ⬜ 未开始 | | | |
| P7 扩展 | ⬜ 未开始 | | | |

## P0 任务清单

- [x] 立项：方案、命名、文档体系（C00）
- [x] 建本地文件夹 `D:\code\hebi-subs`，放入初始骨架
- [x] `git init` + 首次提交；建 GitHub 私有仓库并推送
- [x] VS Code 安装 Claude Code 扩展并登录；确认读到 CLAUDE.md（任务 B/C 会话即在 VS Code 扩展中运行，CLAUDE.md 已自动加载）
- [x] 海拉鲁移入项目内 `_reference\hailulu`（D012）
- [x] 配置 `.claude/settings.local.json`：禁止编辑 `_reference`（D012）
- [x] 回答开放问题 1：MP V3 部署方式 → Windows 原生（D013）
- [x] 确认 MP V3 本地插件开发/加载方式（官方 V3 开发指南）→ 产出 `docs/api-notes/mp-v3-plugin.md`（文档 + 源码核实，待实机冒烟）
- [x] 摸清本机 MP 环境：安装目录、Python 版本、配置文件位置、日志位置、插件安装目录 → 产出 `docs/api-notes/mp-local-env.md`（MP v3.0.7 / Python 3.14.7）
- [x] 冒烟测试：最小空插件 `hebisubs` 被本机 MP V3 识别并加载（P0 验收）→ 2026-10-15 实机通过：市场发现、安装、启用、热重载均正常

## 交接卡模板

> 关闭对话或 Claude Code 会话前填写，追加到下方「交接记录」最上面。

```
### 交接 YYYY-MM-DD · <对话/会话名>
- 阶段：Px
- 完成：
- 决定：（新增决策写入 02-decisions，这里只写编号）
- 未完成 / 下一步：
- 卡点与风险：
- 需要更新的文档：
- 下个对话开场白：继续合璧字幕项目，当前阶段 Px，读 03-progress 最新交接卡后开始：<目标>
```

## 交接记录

### 交接 2026-10-15 · P0 冒烟实机验证与收尾
- 阶段：P0 → 完成
- 完成：用户按 `app.env` 写入 `PLUGIN_LOCAL_REPO_PATHS=D:\code\hebi-subs`、`PLUGIN_AUTO_RELOAD=true`、`DEBUG=true` 并重启 MP；插件市场发现「合璧字幕」，安装后日志「加载成功，启用状态=False」，启用后「启用状态=True」；改 `.py` 后约 1 秒内自动热重载生效（测试文字已撤回，未提交）。数据目录核实为 `<SRV>\config\plugins\HebiSubs`。结论已回填 mp-v3-plugin.md §7/§8、mp-local-env.md §9、D013 状态、CLAUDE.md
- 决定：无新增（D013 状态更新为实机通过）
- 未完成 / 下一步：开 C11「P1 研读海拉鲁」；P0 遗留小项（不阻塞）：图标换自有（mp-v3-plugin §8 #8）、DEBUG 下有无旧导入警告（#9）、监听 `_reference/` 的性能影响（#6）、热重载两轮的原因（#11）、插件日志文件名（mp-local-env §9 #4）
- 卡点与风险：热重载一次改动触发两轮 stop/init，后续加事件订阅、定时服务时必须幂等，避免重复注册；MP 侧当前开着 `DEBUG=true`，日志会更多，P1 期间可按需关掉
- 需要更新的文档：无（本次已更新）
- 下个对话开场白：继续合璧字幕项目，当前阶段 P1，读 03-progress 最新交接卡后开始：研读海拉鲁字幕插件（subtitlemanualupload）的整体结构与字幕源实现

### 交接 2026-10-15 · P0 任务 C 最小空插件
- 阶段：P0
- 完成：新建根目录 `package.v3.json`（键 `HebiSubs`，v0.0.1，`system_version >=3.0.0`）与 `plugins.v3/hebisubs/__init__.py`（6 个必需方法空实现 + 启用开关；`init_plugin` 打印「【合璧字幕】HebiSubs v0.0.1 加载成功，启用状态=…，数据目录=…」）；只读核对本机 v3.0.7 的 `app.sdk.plugin._PluginBase`、`app.sdk.logging.logger` 存在；用 MP 自带 Python 3.14.7 做语法解析通过
- 决定：无新增
- 未完成 / 下一步：用户在 MP 侧操作——备份并修改 `app.env`（`PLUGIN_LOCAL_REPO_PATHS=D:\code\hebi-subs`、`PLUGIN_AUTO_RELOAD=true`、`DEBUG=true`）→ 重启 → 插件市场安装「合璧字幕」→ 启用 → 查日志；可选热重载验证。通过后勾选 P0 冒烟项，并把结论回填 mp-v3-plugin.md §8（#3 配置是否需重启、#6 监听 `_reference` 的影响、#8 图标、#9 导入警告）与 mp-local-env.md §9（#1、#3 数据目录、#4 插件日志文件名）
- 卡点与风险：图标暂借官方仓 `chinesesubfinder.png` 的 URL（占位）；`app.env` 中 Windows 反斜杠路径能否被正确解析未实测；MP 会递归监听整个仓库（含 `_reference/`）
- 需要更新的文档：实机验证后更新上述两份 api-notes、本文件看板（P0 → 完成）、CLAUDE.md 目录表「P0 核实」字样
- 下个对话开场白：继续合璧字幕项目，当前阶段 P0，读 03-progress 最新交接卡后开始：根据我的实机冒烟结果回填文档并收尾 P0

### 交接 2026-10-15 · C00 立项
- 阶段：P0
- 完成：确定自写插件方案；命名合璧字幕 HebiSubs；建立文档体系（00–03、CLAUDE.md）；对话分工
- 决定：D001–D010
- 未完成 / 下一步：完成 P0 任务清单；然后开 C11「P1 研读海拉鲁」
- 卡点与风险：MP V3 部署方式未知；V3 插件目录与加载方式需按官方 V3 指南核实
- 需要更新的文档：无
- 下个对话开场白：继续合璧字幕项目，当前阶段 P0，读 03-progress 最新交接卡后开始：完成 P0 环境搭建
