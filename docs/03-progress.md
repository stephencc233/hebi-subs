# 03 进度看板与交接卡 · 合璧字幕 HebiSubs

## 阶段看板

| 阶段 | 状态 | 开始 | 完成 | 产出 |
|---|---|---|---|---|
| P0 准备 | ✅ 完成 | 2026-10-15 | 2026-10-15 | 仓库、CLAUDE.md、文档 v0.1、api-notes（MP V3 开发要点 / 本机环境）、最小空插件 v0.0.1（实机冒烟通过） |
| P1 研读海拉鲁 | 🟡 进行中 | 2026-10-15 | | study-hailulu/README 研读规则、01-module-map、02-search-pain12、03-archive-pain3 |
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

## P1 任务清单

> 研读规则见 `docs/study-hailulu/README.md`；笔记编号与任务对应（01=S1 … 04=S4）。

- [x] S1 P1-1-module-map：模块地图 + 研读规则 → `study-hailulu/01-module-map.md`
- [x] S2 P1-2-search-pain12：痛点①SubHD 不按下载量排序、②不显示制作组 → `study-hailulu/02-search-pain12.md`
- [x] S3 P1-3-archive-pain3：痛点③整包（压缩包）无法处理 → `study-hailulu/03-archive-pain3.md`
- [ ] S4 P1-4-auto-chain：整理完成 → 识别 → 搜索 → 下载 → 解包 → 落盘的完整链路 → `04-*.md`
- [ ] C11 复盘：claude.ai 阶段对话评审 P1 笔记，提炼借鉴/避免清单

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

### 交接 2026-10-15 · P1-3-archive-pain3
- 阶段：P1（S3 完成）
- 完成：`study-hailulu/03-archive-pain3.md`：下载→解包→预览→写入时序图（标每步 bytes / 临时文件 / 路径）、A 压缩格式 / B 包内多文件 / C 剧集三张证据链表、手动上传 vs 在线下载对比、写入命名·覆盖·编码·繁转简位置表、根因、对合璧字幕解包模块与 Windows 依赖选型的启示、P2 验证清单 10 条；`01-module-map.md` §7 #3 #4 标为已答 / 部分回答。读 20 个文件（超出规则约 15 个，超出部分各只读 15–90 行），`_reference` 无改动；可选的 rarfile 文档查询与 `tar --version` 未做（未获同意）
- 决定：无新增（§8 是建议，留 P3 定稿）
- 主要发现：①根因是**平台假设**：rar/7z 都只认文件名恰为 `unar` 的外部程序（`upload_session.py:136-189`），默认路径 `/usr/bin/unar`，自动安装靠 `sh`+`apt-get`，Windows 原生装了 `unar.exe` 也认不出；7z 无 py7zr / 7z.exe 替代；rar 的 rarfile 兜底仍需外部工具（不确定）。②手动上传与在线下载共用同一解包入口，无本质差异。③多文件包：目录拍平、内层压缩包静默跳过、zip GBK 文件名不做 cp437 回转、纯中文 ASS 可能被判成中英双语、Big5 解码分支走不到、写入不转 UTF-8。④命名 `视频名.语言后缀.ext`，同语言同格式只能一份，与 F6.1「2 份双语」冲突；会覆盖（一次性备份 `.mp-timeline-bk`）；原包写入后随会话删除，不保留
- 未完成 / 下一步：S4 P1-4-auto-chain（`auto_transfer.py:302 handle_transfer_complete` → 队列 → `auto_transfer_processor.py:51/282` → `auto_transfer_write.py:114`；同时答 01 §7 #5–#7）
- 卡点与风险：rarfile 行为、Windows `tar.exe`（libarchive）对 RAR5/7z 的支持、py7zr 在 Python 3.14 + Windows 的 wheel 均未验证，影响 P3 依赖选型；7-Zip 默认不加 PATH，探测需查固定安装路径
- 需要更新的文档：无（本次已更新 03 笔记、01、本文件）；P3 定解包模块与 F6.6/F6.7 时参考 03 §8、§9
- 下个对话开场白：继续合璧字幕项目，当前阶段 P1，读 03-progress 最新交接卡后开始：S4 P1-4-auto-chain，按 study-hailulu/README 研读规则整理整理完成→识别→搜索→下载→解包→落盘的完整自动链路

### 交接 2026-10-15 · P1-2-search-pain12
- 阶段：P1（S2 完成）
- 完成：`study-hailulu/02-search-pain12.md`：链路时序图、下载量 / 制作组两张 5 层证据链表、ASSRT 字段取用附表、根因归类、对合璧字幕的数据模型与排序层级建议、P2 实测清单（SubHD 11 条、ASSRT 4 条）；`01-module-map.md` 更正前端排序键、§7 #1 #2 标为已答。读了 15 个文件（`language.py`、`request_helpers.py` 只读各一个函数），`_reference` 无改动
- 决定：无新增（§6 是建议，留 P3 定稿）
- 主要发现：①② 都属于**没实现**，下载量和制作组从源站解析起就没进入数据流，不是「解析了又丢掉」；SubHD 只用正则抓 `/a/{sid}` 链接的锚文本，周围约 1,000 字符的文本只拿来猜语言和格式；排序是相关性设计（源优先级 → 身份 → 语言 → 匹配分 → **标题倒序**），会打乱站点原顺序；前后端两套排序键顺序不一致；ASSRT 只请求 15 条，也没读下载量 / 评分 / 发布类字段
- 未完成 / 下一步：S3 P1-3-archive-pain3（需要用户先补充「整包无法处理」的症状）
- 卡点与风险：SubHD 列表页是否有下载数、制作组，是不是 JS 渲染，只能在 P2 确认；如果只在详情页，每条多一次请求，和低频访问约束冲突；§4 里的 ASSRT 字段名凭印象写的（不确定）
- 需要更新的文档：无（本次已更新 02、01、本文件）；P3 定稿数据模型时参考 02 §6
- 下个对话开场白：继续合璧字幕项目，当前阶段 P1，读 03-progress 最新交接卡后开始：S3 P1-3-archive-pain3，按 study-hailulu/README 研读规则定位整包（压缩包）无法处理的原因；症状：<补充>

### 交接 2026-10-15 · P1-1-module-map
- 阶段：P1（S1 完成）
- 完成：README 新增「研读规则」6 条；`01-module-map.md`：参考仓 `8146218`、插件 v1.2.7；14 个子包 / 63 个实质模块的地图（职责、关键类/函数、调用方）；前端组件职责；Mermaid 子包调用图（A 在线 / B 上传 / C 自动三条主线）；三痛点嫌疑文件；依赖说明。只分段读了约 6 个文件，`_reference` 无改动
- 决定：无新增
- 主要发现：①② 结果模型 `OnlineSubtitleResult` 根本没有下载量、制作组字段，排序键也不含下载量；③ 三条主线共用 `upload_session.extract_subtitle_files`，rar/7z 依赖外部程序（默认 `/usr/bin/unar`、RAR 依赖模式默认 none），Windows 原生下大概率缺工具（推测）；海拉鲁带 SubHD 验证码自动识别，与 D004 相反，不借鉴
- 未完成 / 下一步：S2 P1-2-search-pain12（从 `providers/subhd.py`、`models.py`、`service.py:154`、`matcher.py` 入手）
- 卡点与风险：S3 需要用户补充「整包无法处理」的具体症状；架构靠 `owner.services` + 委托方法注入，只看 import 会漏调用关系，S4 需读 `runtime/service_factories.py` 与 `shell_helpers.py`
- 需要更新的文档：无（本次已更新 README、01-module-map、本文件）
- 下个对话开场白：继续合璧字幕项目，当前阶段 P1，读 03-progress 最新交接卡后开始：S2 P1-2-search-pain12，按 study-hailulu/README 研读规则定位 SubHD 不按下载量排序、不显示制作组的原因

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
