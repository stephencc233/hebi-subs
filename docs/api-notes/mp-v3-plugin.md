# MP V3 插件开发要点 · 合璧字幕 HebiSubs

> 用途：P0 任务 A 的研读笔记，整理 MoviePilot V3 插件的目录、生命周期、事件、页面/API、本地开发方式，供后续编码直接查阅。
> 读取日期：2026-10-15。只写结论与出处，不含插件实现代码。
> 标注约定：**不确定** = 文档未写明、源码也未能完全确认；**推测** = 依据源码推断，待实机验证。

## 0. 来源清单

| 简称 | 来源 | 版本 |
|---|---|---|
| 主指南 | `jxxghp/MoviePilot-Plugins` [docs/Plugin_Development.md][PD]（wiki 入口 https://wiki.movie-pilot.org/plugindev 指向此仓库） | main @ `59c77e8`（2026-10-15） |
| 仓库指南 | 同仓库 [docs/Repository_Guide.md][RG] | 同上 |
| API 专题 | 同仓库 [docs/V3_API_Response_Adaptation.md][API] | 同上 |
| 迁移专题 | 同仓库 [docs/V3_Plugin_Adaptation.md][ADP]（只扫读，本项目是新插件） | 同上 |
| 联邦指南 | `jxxghp/MoviePilot-Frontend` [docs/module-federation-guide.md][FED]（v3 分支，只记要点） | v3（2026-10-15） |
| 宿主源码 | `jxxghp/MoviePilot`（默认分支 `v3`），具体文件见各节链接 | v3 @ `63c8c0d`（2026-10-15） |
| 参考实现 | `_reference/hailulu/plugins.v3/`（本地只读，只看结构） | 本地快照 |

主指南末尾声明：文档与运行时不一致时，以 V3 宿主代码和测试为准（[PD §14][PD-14]）。因此本笔记对时效性强的点（事件字段、本地仓库、热重载）都对照了宿主源码。

---

## 1. 目录结构、package.v3.json、最小骨架

### 1.1 目录与命名规则（[PD §2][PD-2]、[RG §2][RG-2]）

```text
<插件仓库根>/
├── package.v3.json            # V3 市场索引
├── plugins.v3/
│   └── <插件类名小写>/
│       ├── __init__.py        # 插件主类必须定义在这里
│       ├── pyproject.toml     # 有额外 Python 依赖时
│       ├── README.md          # 推荐
│       └── dist/assets/       # 仅 Vue 联邦模式：前端构建产物
└── tests/v3/<插件类名小写>/   # 测试放这里，不要放进插件目录
```

硬性对应关系：
- 主类名 = 插件 ID（如 `HebiSubs`）；目录名 = 类名小写（`hebisubs`）；`package.v3.json` 的键 = 插件 ID。
- 测试不能放在插件目录内，否则安装/同步时会被一起复制到运行目录（[PD §2][PD-2]）。
- 新插件不要写进 `plugins/` 或 `plugins.v2/`（[PD §2][PD-2]）。

### 1.2 package.v3.json 字段（[PD §4][PD-4]、[RG §3.4][RG-34]）

| 字段 | 含义 | 本项目取值建议 |
|---|---|---|
| 键名 | 插件 ID，等于主类名 | `HebiSubs` |
| `name` | 展示名 | 合璧字幕 |
| `description` | 简介 | — |
| `labels` | 标签，英文逗号分隔 | 如 `字幕,双语` |
| `version` | 版本，必须与类属性 `plugin_version` 一致 | `0.0.1` 起 |
| `icon` | 图标文件名或完整 HTTP URL | 第三方插件用完整 URL 更稳（见 §8 不确定项） |
| `author` / `author_url` | 作者 | — |
| `level` | 插件市场可见权限级别 | 1 |
| `system_version` | 可安装的主程序版本范围（pip 约束语法）；V3 新合同插件必须 `>=3.0.0` | `>=3.0.0`（用到较新 SDK 能力时再上调） |
| `history` | 更新日志，当前版本置顶，按语义版本降序 | — |
| `release` | 是否用 GitHub Release 压缩包分发；**Vue 联邦插件必须 `true`**（[PD §8.3][PD-83]） | 本地开发阶段不需要 |

版本三处同步：类 `plugin_version`、索引 `version`、`history` 首条（[PD §12][PD-12]、[RG §6.3][RG-63]）。

### 1.3 最小骨架（字段清单，非代码）

依据 [PD §4 最小可运行插件][PD-4] 与基类源码 [`app/sdk/plugin/base.py`][SRC-BASE]：

- 导入：`_PluginBase` 从 `app.sdk.plugin` 导入（主指南写法）。
- 类属性：`plugin_name`、`plugin_desc`、`plugin_icon`、`plugin_version`、`plugin_author`、`author_url`、`plugin_config_prefix`（如 `hebisubs_`）、`plugin_order`、`auth_level`。
  - 基类源码本身只声明了 `plugin_name` / `plugin_desc` / `plugin_order` / `is_clone`（[base.py L39-46][SRC-BASE-ATTR]），其余属性由宿主加载器读取；以主指南示例为准全部写上。
- 必须实现 6 个抽象方法：`init_plugin(config)`、`get_state()`、`get_api()`、`get_form()`、`get_page()`、`stop_service()`（见 §2）。
- 最小实现的形态：`get_api` 返回空列表；`get_form` 返回「Vuetify 组件 JSON 列表 + 默认配置 dict」二元组（至少一个 `VSwitch` 绑定 `enabled`）；`get_page` 返回组件列表或 `None`；`get_state` 返回 `_enabled`。

---

## 2. 生命周期

### 2.1 方法清单（[PD §5][PD-5]、[base.py][SRC-BASE]）

| 方法 | 必须 | 调用时机 / 职责 |
|---|---|---|
| `init_plugin(config)` | ✅ | 插件加载、保存配置、重载时调用；读取配置并建立运行状态。**必须允许重复调用** |
| `get_state()` | ✅ | 返回是否启用；宿主据此决定是否注册服务等 |
| `get_api()` | ✅ | 返回 API 声明列表，没有则 `[]`（§4.1） |
| `get_form()` | ✅ | 返回配置页（§4.2） |
| `get_page()` | ✅ | 返回详情页，没有则 `None` 或 `[]` |
| `stop_service()` | ✅ | 停用/重载/卸载时调用；取消任务、关闭线程/客户端，**可重复、安全** |
| `get_command()` | 可选（静态方法） | 注册远程命令，通常走 `EventType.PluginAction`（[PD §9.1][PD-91]） |
| `get_service()` | 可选 | 注册定时/周期服务：`id`（稳定唯一）、`name`、`trigger`、`func`、`kwargs`（[PD §9.3][PD-93]） |
| `get_render_mode()` | 可选（静态方法） | 默认 `("vuetify", None)`；Vue 模式返回 `("vue", "dist/assets")` |
| `get_dashboard()` / `get_dashboard_meta()` | 可选 | 仪表板 |
| `get_sidebar_nav()` | 可选 | Vue 插件侧栏全页入口 |
| `get_actions()` / `get_agent_tools()` | 可选 | 工作流动作 / Agent 工具 |
| `get_module()` / `get_auth_providers()` / `get_media_source()` / `get_agent_pets()` | 可选 | 高级扩展，本项目暂不涉及 |
| `get_database_models()` / `get_database_migrations()` | 可选 | 插件自有表的声明式建表 / Alembic 迁移（源码有，主指南示例用的是 `ensure_table()` 手动建表写法，两者并存）（[base.py L284-307][SRC-BASE-DB]） |

### 2.2 基类提供的常用工具方法（[PD §7][PD-71]、[base.py][SRC-BASE]）

| 方法 | 用途 |
|---|---|
| `update_config(dict)` / `get_config()` | 读写本插件配置（不要直接改宿主配置文件） |
| `save_data(key, value)` / `get_data(key)` / `del_data(key)`（及 `async_` 变体） | 小型可序列化状态 |
| `get_data_path()` | 插件独立数据目录，报告/缓存文件写这里 |
| `post_message(...)` | 发通知 |

### 2.3 生命周期纪律（与本项目直接相关）

- 模块导入期、类定义期不得启动任务、访问网络、连数据库；资源在 `init_plugin()` 中按配置建立（[PD §5.2][PD-52]）。
- **运行数据不能写回插件源码目录**：插件更新/本地同步时源码目录会被整体替换（[PD §7.2][PD-72]；源码 `sync_local` 先删后拷，见 §5.3）。
- “立即运行一次”、事件后延迟执行等一次性任务用 `app.sdk.scheduler.add_plugin_once_job()`，不要自建 `BackgroundScheduler`；停用时用 `remove_plugin_once_job()` 取消（[PD §9.3][PD-93]）。⚠ 本机 v3.0.7 没有这个接口；**2026-10-16 本机已升级到 v3.1.5，`app/sdk/scheduler.py` 已导出 `add_plugin_once_job`**（§9.0）。`system_version` 仍写 `>=3.0.0` 时，调用前仍要用 `getattr` 判断。
- 插件 ID 用 `self.__class__.__name__` 取得，不硬编码（虚拟分身会改类名）（[PD §7.1][PD-71]）。
- 宿主接口优先从 `app.sdk.*` 导入（`config`/`events`/`logging`/`network`/`services`…）；新插件**禁止**用 `app.core.*`、`app.helper.*`、`app.utils.*`、`app.sdk._legacy`（[PD §6][PD-6]）。
- HTTP：`app.sdk.network.AsyncRequestUtils` 基于 HTTPX2，网络错误默认返回 `None`，需要区分失败时传 `raise_exception=True`；4xx/5xx 不自动抛（[PD §7.6][PD-76]）。

---

## 3. 事件订阅与「整理完成」事件

### 3.1 订阅方式（[PD §9.1][PD-91]、[app/sdk/events.py][SRC-SDKEV]）

- 用 `app.sdk.events.eventmanager` 的 `register(EventType.Xxx)` 装饰插件实例方法，方法接收一个 `Event` 参数，数据在 `event.event_data`。
- `EventType` 从 `app.schemas.types` 导入（公开稳定入口，[PD §6][PD-6]）。
- `app.sdk.events` 还导出 `snapshot_event_data()` 和若干契约模型（含 `TransferResultContractData`），可把原始 payload 按登记契约解析成 Pydantic 快照（[app/runtime/event/snapshot.py][SRC-SNAP]）。

### 3.2 事件名（源码核实，[app/schemas/types.py L189-268][SRC-TYPES]）

| 枚举 | 值 | 中文名 | 触发对象 |
|---|---|---|---|
| `EventType.TransferComplete` | `transfer.complete` | 整理完成 | **主媒体文件**整理成功 |
| `EventType.TransferFailed` | `transfer.failed` | 整理失败 | 媒体文件整理失败 |
| `EventType.SubtitleTransferComplete` | `transfer.subtitle.complete` | 字幕整理完成 | **字幕文件**整理成功（如种子自带字幕） |
| `EventType.SubtitleTransferFailed` | `transfer.subtitle.failed` | 字幕整理失败 | — |
| `EventType.AudioTransferComplete` / `AudioTransferFailed` | `transfer.audio.*` | 音频整理完成/失败 | — |
| `EventType.MetadataScrape` | `metadata.scrape` | 刮削元数据 | 整理成功后发送（[settlement.py][SRC-SETTLE]） |

分派逻辑见 [settlement.py `_durable_transfer_event` L190-213][SRC-SETTLE-KIND] 与 [`_publish_transfer_result` L323-343][SRC-SETTLE-PUB]：
- 成功时按文件类型三选一：主媒体 → `TransferComplete`；字幕 → `SubtitleTransferComplete`；音频 → `AudioTransferComplete`。
- **`transferinfo.target_item` 为 `None`（静默跳过、沿用旧成功终态）时不发完成事件**（[L511-515][SRC-SETTLE-SKIP]）。
- 推测：一次整理任务对应一个源文件，所以**剧集是每集发一次**，不是整季一次（待实机验证）。

### 3.3 TransferComplete 的 event_data 字段

payload 构造：[settlement.py `_transfer_result_payload` L173-188][SRC-SETTLE-PAYLOAD]；契约模型：[app/schemas/event.py `TransferResultContractData` L409-419][SRC-EV-CONTRACT]、`TransferResultEventData` [L1126-1136][SRC-EV-DATA]。

| 字段 | 类型（源码） | 含义 | 对本项目的用途 |
|---|---|---|---|
| `fileitem` | `FileItem` | 整理前的源文件 | 下载目录里的原文件，不是目标 |
| `meta` | `MetaBase`（契约快照为 `MetaSnapshot`） | 文件名解析结果（标题、年份、季集、制作组等） | 季/集号、发布组 |
| `mediainfo` | `MediaInfo`（契约快照为 `MediaSnapshot`） | 识别后的媒体信息 | 标题、年份、TMDB/IMDb 等，搜字幕用 |
| `transferinfo` | `TransferInfo` | 整理结果 | **影片最终落盘位置**在这里 |
| `downloader` | `str \| None` | 下载器名称 | — |
| `download_hash` | `str \| None` | 下载任务 hash | — |
| `transfer_history_id` | `int \| None` | 整理历史记录 ID | 去重 / 关联历史 |
| `idempotency_key` | `str \| None` | 宿主生成的幂等键 | 防重复处理 |

`TransferInfo` 主要字段（[app/schemas/transfer.py L163-201][SRC-TI]）：

| 字段 | 含义 |
|---|---|
| `success` | 是否成功 |
| `fileitem` | 整理的源文件 |
| `target_diritem` | 目标目录项（媒体根目录） |
| `target_item` | **目标文件项**（`FileItem`，`.path` 为整理后视频完整路径，`.storage` 为存储类型，`local` 即本地盘） |
| `transfer_type` | 整理方式（复制/移动/硬链接等） |
| `file_list` / `file_list_new` | 处理的源文件清单 / 目标文件清单（路径字符串列表） |
| `file_count` / `total_size` | 文件数 / 总大小 |
| `need_scrape` / `need_notify` / `message` / `fail_list` | 刮削、通知、错误信息 |

`FileItem` 关键字段（[app/schemas/file.py][SRC-FILE]）：`path`、`storage`（默认 `local`）、`name`、`basename`、`extension`、`size`、`modify_time`、`type`（file/dir）。

**数据形态：不确定。** 发送处传的是普通 `dict`，值为 Pydantic/业务对象；但海拉鲁的处理函数同时兼容「dict / 对象」和「`transferinfo` 为对象或 dict」两种情况，说明在某些路径（推测：持久化事件重放）下值可能已被序列化。编码时建议：读取字段同时兼容属性和键；或用 `snapshot_event_data()` 拿 `TransferResultContractData` 快照（字段已校验，但 `meta`/`mediainfo` 是快照类型，不是原对象）。

---

## 4. get_api、get_form/get_page、依赖声明

### 4.1 get_api（[PD §9.2][PD-92]、[API §1-2][API-1]）

- 每项字段：`path`、`endpoint`（绑定方法）、`methods`、`auth`、`summary`（可加 `description`、`response_model`）。
- 最终路径：`/api/v1/plugin/<PluginID>/<path>`。
- `auth`：插件页面调用用 `bear`；外部系统调用用 `apikey`；除非确属公开接口，不设匿名。
- 返回格式：插件路由**不经过**宿主统一响应包装，可直接返回业务模型，或显式返回 `{success, message, data}` 三段式 envelope；二选一并声明 `response_model`，不要用 `response_model=None` 隐藏结构；业务数据不要塞进 `message`（[API §1][API-1]、[API §2][API-2]）。
- 文件、图片、SSE、HTML 等原生响应单独处理（[API §7][API]）。
- `/api/v2` 已移除，统一 `/api/v1`。

### 4.2 get_form / get_page：两种渲染模式（[PD §8][PD-81]、[RG §5.2][RG]）

| 模式 | 声明 | 形态 | 适用 |
|---|---|---|---|
| Vuetify JSON（默认） | 不实现或返回 `("vuetify", None)` | `get_form()` 返回「组件 JSON 列表 + 默认配置」；`get_page()` 返回组件 JSON；`props.model` 绑定配置字段，`props.show` 条件显示，支持 `{{ }}` 表达式 | 配置表单、轻量详情页 |
| Vue 联邦 | `get_render_mode()` 返回 `("vue", "dist/assets")` | `get_form()`/`get_page()` 第一项返回 `None`；前端组件构建后放 `dist/assets/`，暴露 `./Page`、`./Config` 等 | 复杂交互、侧栏全页 |

Vue 模式额外约束（[PD §8.3][PD-83]、[FED][FED]）：不得打包 Vuetify/MDI 全局样式；共享依赖 `generate: false`；需 Node 前端工程与 `yarn build`；索引需 `release: true`。
→ 本项目 MVP 建议先用 **Vuetify JSON 模式**，避免引入前端构建链（结论供 P3 架构参考，非决策）。

小差异：基类 docstring 写的默认 Vue 产物路径是 `dist/asserts`（拼写），主指南示例与海拉鲁都显式返回 `dist/assets`（[base.py L100-105][SRC-BASE-RENDER]）——显式写 `dist/assets` 即可。

### 4.3 依赖声明（[PD §7.5][PD-75]、[RG §6.2][RG]）

- V3 插件：插件目录放 `pyproject.toml`，依赖写 `[project].dependencies`，`dynamic = ["version"]`；不提交 `uv.lock`；不在代码中执行 pip/uv。
- `requirements.txt` 只用于 V1/V2 历史插件。
- 依赖装入宿主共享环境：只声明宿主没有的包、设合理版本范围、不得降级核心依赖（否则安装被拒），可选能力延迟导入。
- 需额外包索引时用 `tool.uv.index` / `tool.uv.sources`（[RG §6.2][RG]）。
- 主指南示例 `requires-python = ">=3.14"`，推测 MP V3 运行在 Python 3.14（本机版本留给任务 B 核实）。

---

## 5. 本地开发

### 5.1 相关配置（[PD §3][PD-3]、源码 [app/runtime/config.py][SRC-CFG]）

| 配置 | 默认 | 作用 | 出处 |
|---|---|---|---|
| `PLUGIN_LOCAL_REPO_PATHS` | `None` | 本地插件仓库目录，**多个用英文逗号 `,` 分隔** | [config.py L710-711][SRC-CFG-LOCAL] |
| `PLUGIN_AUTO_RELOAD` | `False` | 插件热加载（监听文件变化自动同步并重载） | [config.py L706-707][SRC-CFG-RELOAD] |
| `DEV` | `False` | 开发模式；文档称与 `PLUGIN_AUTO_RELOAD` 二选一即可让本地构建产物同步 | [config.py L200-201][SRC-CFG-DEV]、[RG §7.2][RG-72] |
| `DEBUG` | `False` | 显示旧导入兼容警告和更多调试信息 | [PD §3][PD-3] |

本项目设置值：`PLUGIN_LOCAL_REPO_PATHS=D:\code\hebi-subs`（仓库根，即 `package.v3.json` 所在目录）、`PLUGIN_AUTO_RELOAD=true`、开发期 `DEBUG=true`。**这些配置写在哪里（Windows 原生版的 env 文件 / 系统设置页）属于任务 B，未核实。**

### 5.2 本地仓库的发现与安装（源码，推测为主）

- 宿主读取本地仓库根下 `package.v3.json`，按 `plugins.v3/<id小写>/` 找源码；候选来源标记为 `local://<PluginID>?version=v3`（[source.py L23-32][SRC-SRC-LOCAL]；安装日志“从 package.{v}.json 中找到适用于当前版本的插件”，[package.py L881][SRC-PKG-881]）。
- 本地仓库插件会合并进**插件市场列表**，从界面上点安装（[catalog.py L506-515][SRC-CAT]）。
- 同一插件同时有本地与在线来源时，未显式选源则**优先本地**（“当前使用本地插件”，[source.py L520-560][SRC-SRC-SELECT]）。本项目插件名不与官方冲突，无影响。
- 安装 = 先做兼容性检查（`system_version` 等），再把 `plugins.v3/hebisubs/` **复制**到宿主运行目录 `app/plugins/hebisubs/`，忽略 `__pycache__`、`*.pyc`、`.DS_Store`、`node_modules`；源目录与运行目录相同会被拒绝（[package.py L1145-1215][SRC-PKG-INSTALL]、[L204][SRC-PKG-IGNORE]）。
- 结论：宿主自己做复制，**我们不需要也不应手动往 `app/plugins/` 写文件**——与 CLAUDE.md 约定一致。

### 5.3 热重载流程（[app/runtime/extensions/plugin/monitor.py L144-262][SRC-MON]）

1. 开启 `PLUGIN_AUTO_RELOAD` 后，宿主用 `watchfiles` 同时监听运行目录和所有本地仓库根目录（递归）。
2. 本地仓库内某插件的 **`.py` 文件**变化 → 用仓库内容**整目录替换**运行副本（`sync_local`：先删运行目录再拷贝，失败回滚，[package.py L2489-2515][SRC-PKG-SYNC]）→ 重载该插件。
3. 联邦构建产物（`remoteEntry.js` 等）变化 → 只同步不重载，刷新页面即可。
4. `pyproject.toml` 等依赖清单变化走单独分支 `_handle_dependency_manifest_change`（具体行为未细读，**不确定**）。
5. 同一插件 2 秒内刚同步过的变化会被忽略（防抖）；`__pycache__` 变化被忽略。

### 5.4 Windows 原生运行

- **官方未提及** Windows 原生环境的特别说明（主指南、仓库指南、FAQ 索引均无）。
- 文档命令都是 POSIX 写法（`../MoviePilot/.venv/bin/python`）；Windows 对应 `.venv\Scripts\python.exe`——推测，以本机安装方式为准（任务 B）。
- 源码层面：路径处理统一用 `pathlib`，并显式拒绝含 `\` 的**市场远程文件路径**（[package.py L1267-1275][SRC-PKG-PATH]）；这只影响在线下载，本地复制走 `shutil.copytree`，推测不受影响。
- `PLUGIN_LOCAL_REPO_PATHS` 用逗号分隔，Windows 盘符路径 `D:\code\hebi-subs` 不含逗号，推测可直接用。

### 5.5 调试与验收（[PD §11][PD-113]）

- 语法：`python -m compileall plugins.v3/hebisubs`（用宿主解释器）。
- 测试放 `tests/v3/hebisubs/`，用宿主虚拟环境运行，按 `app.plugins.hebisubs` 生产命名空间导入（[PD §11.2][PD]）。⚠ 本项目现有约定是 `tests/`，P3 定架构时需对齐。
- 真实加载检查：市场能发现并安装；启用/停用/重载不残留后台资源；`DEBUG=true` 无旧导入警告；API/服务/命令/页面只注册一次（[PD §11.3][PD-113]）。

---

## 6. 海拉鲁 V3 插件结构观察（只读，仅描述）

参考仓根目录 `LICENSE` 为 **GPL-3.0**（只看了文件头）。GPL 允许学习，但复制其代码会使本项目受 GPL 约束；继续执行“只学思路、不复制代码”。是否据此更新 CLAUDE.md 第 4 条由用户决定。

| 观察点 | `subtitlemanualupload`（海拉鲁字幕大师 1.2.7） | `autosubv3`（AI 字幕 4.0.1） |
|---|---|---|
| 索引 | `package.v3.json` 键 `SubtitleManualUpload`，`system_version >=3.0.0`，`release: true`，`icon` 用完整 URL，带 `author_url` | 键 `AutoSubv3`，同上；`level: 2` |
| 入口 `__init__.py` | 约 390 行，只做组装：类属性 + 生命周期方法，业务拆到 `api/`、`matching/`、`online_subtitles/`、`runtime/` 等子包 | 约 400 行，同样拆 `core/`、`pipeline/`、`tasks/`、`storage/` 等子包 |
| 渲染模式 | Vue 联邦（有 `src/`、`dist/`、`vite.config.js`），并实现 `get_sidebar_nav()` | Vue 联邦（`./Page`、`./Config` 暴露） |
| 扩展点 | `get_actions()`、`get_agent_tools()`、`get_command()` | `get_command()` |
| 事件 | 订阅 `EventType.TransferComplete` | 订阅 `EventType.TransferComplete`，从 `transferinfo.file_list_new` 取目标文件，兼容 dict/对象两种形态 |
| 依赖 | 插件目录用 `requirements.txt`（**与 V3 指南的 `pyproject.toml` 要求不一致**），另带 `wheels/` 预编译包 | `requirements.txt` |
| 导入 | `_PluginBase` 从 `app.plugins` 导入（兼容旧路径），其余用 `app.sdk.*` | 同左 |
| 配置前缀 | `plugin_config_prefix` 带下划线结尾 | 不带下划线 |

可借鉴的思路：入口文件保持薄、业务分子包（契合本项目“核心逻辑与 MP 接口层分离”）；事件处理对 payload 形态做防御。不跟随的做法：`requirements.txt`、从 `app.plugins` 导入基类。

---

## 7. 对本项目的结论

1. **D013 成立**（文档 + 源码核实；**2026-10-15 本机 v3.0.7 实机冒烟通过**：市场发现、安装、启用、热重载均正常）：仓库根 `D:\code\hebi-subs` 放 `package.v3.json`，插件放 `plugins.v3/hebisubs/`，MP 设 `PLUGIN_LOCAL_REPO_PATHS` 指向仓库根 + `PLUGIN_AUTO_RELOAD=true`；MP 从插件市场看到并安装，之后改 `.py` 自动同步重载。
2. 命名定死：主类 `HebiSubs` → 插件 ID `HebiSubs` → 目录 `hebisubs` → 索引键 `HebiSubs` → 配置前缀建议 `hebisubs_`。
3. 自动触发入口：订阅 `EventType.TransferComplete`，用 `transferinfo.target_item.path`（或 `file_list_new`）定位影片落盘路径；`mediainfo`/`meta` 提供搜字幕所需的标题、年份、季集。另可关注 `SubtitleTransferComplete`（种子自带字幕被整理时触发），P3 再决定是否使用。
4. 运行数据（字幕原包存档、缓存、状态）只能放 `get_data_path()` / `save_data()`，不能放插件目录（会被同步覆盖）。
5. 依赖用 `pyproject.toml`；HTTP 优先 `AsyncRequestUtils`。
6. **P0 冒烟测试（任务 C）需要准备**：`package.v3.json`（`HebiSubs` 条目，`system_version >=3.0.0`）+ `plugins.v3/hebisubs/__init__.py`（6 个必需方法的空实现 + 一个启用开关）；MP 侧加两项配置并重启（需用户确认）；验收看市场是否出现、能否安装启用、改代码后日志是否出现“检测到本地插件 HebiSubs Python 文件变化”。

建议后续文档同步（本次不改，由用户确认）：CLAUDE.md 目录表 `plugins.v3/hebisubs/` 一行的“P0 核实”可改为“已核实”；测试目录约定是否改为 `tests/v3/hebisubs/`。

---

## 8. 不确定项 / 待实机验证

| # | 问题 | 现状 | 验证方式 |
|---|---|---|---|
| 1 | `TransferComplete` 的 `event_data` 及 `transferinfo` 是对象还是已序列化的 dict | 源码发送 dict+对象；海拉鲁两种都兼容，**不确定** | 冒烟后加日志打印类型 |
| 2 | 剧集整理是否每集发一次 `TransferComplete` | 推测每个主媒体文件一次 | 实机整理一部剧看日志 |
| 3 | Windows 原生版 `PLUGIN_LOCAL_REPO_PATHS` 等配置写在哪里、改后是否需重启 | **已核实位置**：`D:\MoviePilot\server\MoviePilot-V3\config\app.env`，目前未设置；是否需要重启待任务 C 验证。**任务 C 实机**：写入 `app.env`（`D:\code\hebi-subs` 反斜杠写法、不加引号）+ 重启后生效；不重启能否生效未测 | [mp-local-env.md §4](mp-local-env.md) |
| 4 | 本机 MP 版本是否 ≥ 本笔记所读源码（v3 @ `63c8c0d`） | **已核实**：本机 v3.0.7（`e2e6ff0`，2026-09-21），更旧；本笔记用到的能力中只缺 `add_plugin_once_job`。**2026-10-16 P3-A 发现本机已升级到 v3.1.5（`99ee18d`，2026-10-13），已有该接口**（§9.0） | [mp-local-env.md §2](mp-local-env.md) |
| 5 | 本机 Python 版本（指南示例 `>=3.14`） | **已核实**：3.14.7 | [mp-local-env.md §3](mp-local-env.md) |
| 6 | `watchfiles` 递归监听整个仓库，含 `_reference/`（大量文件）是否影响 MP 性能 | **不确定** | 冒烟时观察 CPU/日志；如有影响再评估把参考仓移出或 MP 侧过滤 |
| 7 | 只改 `package.v3.json`（如版本号）是否触发同步 | 源码只对 `.py`、联邦产物、依赖清单处理，推测**不触发**，需在界面手动更新/重装 | 实机 |
| 8 | `icon` 只写文件名时，第三方本地插件从哪里取图 | **不确定**（官方插件图标在官方仓 `icons/`） | 冒烟先用完整 URL 或官方已有图标名 |
| 9 | 主指南写 `from app.sdk.plugin import _PluginBase`，海拉鲁用 `from app.plugins import _PluginBase` | 两者都能用（后者走兼容层），按主指南 | 冒烟开 `DEBUG=true` 看是否有兼容警告 |
| 10 | 声明式建表 `get_database_models()` 与主指南 `ensure_table()` 哪个是推荐做法 | 源码两者并存，**不确定** | 需要自有表时（P4+）再查 |
| 11 | 热重载为何一次改动触发两轮「stop_service → init_plugin」 | **任务 C 实机观察**：改一行 `.py` 后约 1 秒内连续两轮，间隔约 60ms。推测是仓库与运行目录各触发一次、防抖未覆盖，**不确定**。影响：`init_plugin`/`stop_service` 必须幂等，后台任务不能重复注册 | 需要时看 MP 主日志里的同步提示行 |

---

## 9. mediainfo 字段核实（P3-A，2026-10-16）

> 方法：只读本机 MP 源码静态核实，未运行 MP 代码，未改 MP 文件。下文路径相对 `<SRV>\app\`（`<SRV>` = `D:\MoviePilot\server\MoviePilot-V3`），**行号以本机 v3.1.5（`99ee18d`）为准**，与 §0–§8 引用的 GitHub `63c8c0d` 不同。
> 回答：F2.1（识别身份要哪些 ID）、F6.8（华语片判定依据）、03 P2 遗留表「MP mediainfo 有无豆瓣 ID / 原始语言」。

### 9.0 本机版本变化

本机 MP 已从 P0 时的 v3.0.7（`e2e6ff0`）升级到 **v3.1.5**（`version.py`；git `99ee18d`，2026-10-13）。Python 仍是 3.14.7。`app/sdk/scheduler.py` 现在导出 `add_plugin_once_job`（L4、L20）。详见 [mp-local-env.md §2](mp-local-env.md)。

### 9.1 结论速览

1. 4 个字段**都在** `MediaInfo` 上，字段名：`douban_id`、`imdb_id`、`original_language`、`origin_country` / `production_countries`（另有 `spoken_languages`、`languages`）。（高）
2. **事件里拿得到**：TransferComplete 的 payload 放的是整理任务里原来的 `MediaInfo` 对象（没有调 `clear()`）；契约快照 `MediaSnapshot` 就是 `app.schemas.context.MediaInfo`，这几个字段都保留。（高）
3. **按本机默认识别源 TMDb：`imdb_id`、`original_language`、`production_countries`、`spoken_languages` 有值，`douban_id` 为空**。`douban_id` 只在识别源是豆瓣时才填，或者是插件自己去匹配豆瓣。（高；`origin_country` 对电影是否有值：不确定，见 9.2）
4. **历史扫描**：整理历史只存主身份（`media_source` + `media_id`，即 TMDb ID）和标题、年份，**没有 IMDb、豆瓣、语言、地区**。要拿到完整字段，需要用 `media_id` 让 MP 再识别一次（`ChainBase.recognize_media`），或者读 MP 刮削出的 NFO（只有 IMDb ID 和出品国家，没有语言）。（高）

### 9.2 字段表

| 需要的信息 | `MediaInfo` 字段（领域对象 `domain/context.py`） | 事件快照类型（`schemas/context.py`） | TMDb 识别时 | 豆瓣识别时 | 依据 |
|---|---|---|---|---|---|
| TMDb ID | `tmdb_id: int`（L1617）；主身份 `media_source` / `media_id`（L1595、L1597） | `tmdb_id: int`（L297） | 有，`media_source=themoviedb`、`media_id` = TMDb ID | 只有 MP 补查 TMDb 时才有 | `projection/tmdb.py` L121–126 |
| IMDb ID | `imdb_id: str`（L1618） | `imdb_id: str`（L298） | **有**：来自 TMDb 详情的 `external_ids.imdb_id`，详情请求固定带 `append_to_response=…external_ids` | 豆瓣投影不填 | `domain/projection/tmdb.py` L130–133；`modules/themoviedb/tmdbapi.py` L1046–1054（电影）、L1167–1174（剧集） |
| 豆瓣 ID | `douban_id: str`（L1621） | `douban_id: str`（L301） | **空**：TMDb 投影不设置，详情里也没有同名键 | 有，等于豆瓣主 ID | `domain/projection/douban.py` L155–157 |
| 原始语言 | `original_language: str`（L1628），ISO 639-1，如 `zh`、`cn`、`ja` | `original_language: str`（L310） | **有**：TMDb 的 `original_language` | 只在为空时补：豆瓣 `languages` 第一项映射成代码 | `projection/tmdb.py` L140–141；`projection/douban.py` L123–143、L165 |
| 出品国家 / 地区 | `production_countries: list`（L1703），元素 `{iso_3166_1, name}` | `list[MediaCountry]`（L379；`MediaCountry` L192–197） | **有**：TMDb 详情的同名键，由 `fill_missing` 按名字拷过来 | 只在为空时补：豆瓣 `countries` → `{id: 名称, name: 名称}`，**没有 ISO 代码** | `projection/tmdb.py` L173；`projection/mapping.py` L46–60（`fill_missing`：详情里与 `MediaInfo` 同名的空字段都补上）；`projection/douban.py` L229–232 |
| 原产国 | `origin_country: list[str]`（L1697），ISO 3166-1 代码 | `list[str]`（L373） | 剧集有；电影是否有取决于 TMDb 电影详情是否返回 `origin_country`（**不确定**，P4 实机看一次事件） | 无 | 同上（`fill_missing`） |
| 对白语言 | `spoken_languages: list`（L1705），元素 `{iso_639_1, english_name, name}`；`languages: list`（L1687，剧集用） | `list[MediaLanguage]`（L381；L200–205）、`list[str]`（L363） | 有（`fill_missing`） | 无 | 同上 |

注意：
- 领域对象上 `tmdb_id` 等字段的注释写着「数据源返回的辅助 ID，仅作为元数据输出，不参与通用身份传递或持久化」（`domain/context.py` L1616）。MP 自己认的身份是 `media_source` + `media_id`。
- `MediaInfo.clear()`（L1964）会清空 `production_countries`、`spoken_languages`、`names` 等列表。整理流程只对**给队列界面用的深拷贝**调用它（`application/transfer/jobs.py` L285–287），事件 payload 用的是 `task.mediainfo` 原对象（`chain/transfer/settlement.py` L174–188 `_transfer_result_payload`）。识别命中 MP 本地缓存时，对象是否完整：**不确定**，P4 / P5 实机打印一次事件确认。
- 本机识别源：`runtime/config.py` L374 `RECOGNIZE_SOURCE` 默认 `"themoviedb"`，`app.env` 里没有覆盖。

### 9.3 事件里的形态

| 层 | 内容 | 位置 |
|---|---|---|
| 发送 | payload 是 dict，`mediainfo` 值为领域对象 `app.domain.context.MediaInfo` | `chain/transfer/settlement.py` L174–188 |
| 插件兼容模型 | `TransferResultEventData.mediainfo: Any` | `schemas/event.py` L1126–1136 |
| 契约快照 | `TransferResultContractData.mediainfo: MediaSnapshot`；`MediaSnapshot` = `schemas.context.MediaInfo`（或 `MusicInfo`）。转换时先调对象的 `to_dict()`（领域 `to_dict` 只把 `tmdb_info` / `douban_info` 原始详情置空，其余字段保留，L1939–1962） | `schemas/event.py` L14、L27–52、L409–419 |

→ 插件读 `mediainfo.imdb_id`、`.original_language`、`.production_countries` 都可以，用原对象或用 `snapshot_event_data()` 快照都行；`douban_id` 在本机配置下应当视为「通常为空」。

### 9.4 历史扫描怎么拿同样的信息（插件只能用 `app.sdk.*`）

| 途径 | 能拿到什么 | 代价 / 限制 | 位置 |
|---|---|---|---|
| ① 整理历史 `app.sdk.queries.list_transfer_history(filters)` | `TransferHistorySnapshot`：`media_source`、`media_id`、`title`、`year`、`type`、`seasons`、`episodes`、`src`、`dest`、`date`… **没有 IMDb、豆瓣、语言、地区**。筛选可以按 `dest`（精确）或 `text`（标题 / 路径包含）查 | 只读、本地数据库，无网络；只覆盖经过 MP 整理的文件 | `sdk/queries.py` L212–237；`schemas/query.py` L264–300（快照）、L364–385（筛选） |
| ② 再识别 `ChainBase.recognize_media(media_source=…, media_id=…)` | 完整 `MediaInfo`（同 9.2 TMDb 那一列） | 插件自建一个继承 `app.sdk.chain.ChainBase` 的类调用；会访问 TMDb（MP 有识别缓存，`cache=True`） | `sdk/chain.py` L3–5；`chain/_recognition.py` L656–666 |
| ③ 豆瓣 ID：`ChainBase.match_doubaninfo(name, imdbid=…, year=…)` | 豆瓣详情 dict（含 `id`） | 访问豆瓣；按需调用，不适合批量（频率风险） | `chain/base.py` L278–292。（MP 内部的 TMDb→豆瓣身份转换 `MediaChain.convert_media_identity`，`chain/media/projection.py` L392，没有通过 `app.sdk` 导出） |
| ④ 读 NFO：`app.sdk.media.NfoReader` | MP 用 TMDb 刮削的 NFO 里有 `<tmdbid>`、`<uniqueid type="tmdb/imdb">`、`<imdbid>`、`<country>`（出品国家**名称**，没有代码），**没有原始语言和豆瓣 ID** | 只读本地文件；NFO 可能由 Jellyfin 等别的工具写，字段不一定一样 | `sdk/media.py` L29、L56；`domain/scraper.py` L12–26；`modules/themoviedb/scraper.py` L252–271、L317–320 |

### 9.5 对需求和架构的影响

1. **F2.1 身份**：自动触发直接用事件里的 `media_source` / `media_id`（TMDb）、`imdb_id`、`title` / `en_title` / `original_title` / `names`、`year`。历史扫描先查整理历史 ①，按 `dest` 拿到 TMDb ID，再按需走 ② 补全；没有整理记录的文件读 NFO ④，再不行才按文件名识别。（高）
2. **SubHD 影片页 `/d/{豆瓣ID}`（subhd §3）拿不到现成豆瓣 ID**：本机识别源是 TMDb，`douban_id` 通常为空。要么用 ③ 由 IMDb ID + 标题 + 年份匹配豆瓣（多一次豆瓣请求，结果可以缓存到插件数据），要么走 SubHD 搜索页（模糊，会混进别片）。这个取舍留给 C13 / P3-B。（高）
3. **F6.8 华语片判定**：可用 `original_language ∈ {zh, cn}`（TMDb 把粤语标成 `cn`，**不确定**，待查样本），加上 `production_countries` / `origin_country` 含 CN / HK / TW 做辅助。两个字段在 TMDb 识别下都有值；历史扫描要走 ②。NFO 只有国家名、没有语言，不够判定。（中）
4. P5 实机时打印一次 TransferComplete 的 `mediainfo` 关键字段，确认 9.2 里两个「不确定」：电影的 `origin_country`、识别缓存命中时对象是否完整。

<!-- 链接定义 -->
[PD]: https://github.com/jxxghp/MoviePilot-Plugins/blob/59c77e86dc4fe486a751ffb14829ddb70e2f2fca/docs/Plugin_Development.md
[PD-2]: https://github.com/jxxghp/MoviePilot-Plugins/blob/59c77e86dc4fe486a751ffb14829ddb70e2f2fca/docs/Plugin_Development.md#2-v3-新插件放在哪里
[PD-3]: https://github.com/jxxghp/MoviePilot-Plugins/blob/59c77e86dc4fe486a751ffb14829ddb70e2f2fca/docs/Plugin_Development.md#3-准备开发环境
[PD-4]: https://github.com/jxxghp/MoviePilot-Plugins/blob/59c77e86dc4fe486a751ffb14829ddb70e2f2fca/docs/Plugin_Development.md#4-最小可运行插件
[PD-5]: https://github.com/jxxghp/MoviePilot-Plugins/blob/59c77e86dc4fe486a751ffb14829ddb70e2f2fca/docs/Plugin_Development.md#5-_pluginbase-生命周期
[PD-52]: https://github.com/jxxghp/MoviePilot-Plugins/blob/59c77e86dc4fe486a751ffb14829ddb70e2f2fca/docs/Plugin_Development.md#52-常用可选扩展点
[PD-6]: https://github.com/jxxghp/MoviePilot-Plugins/blob/59c77e86dc4fe486a751ffb14829ddb70e2f2fca/docs/Plugin_Development.md#6-使用稳定的宿主接口
[PD-71]: https://github.com/jxxghp/MoviePilot-Plugins/blob/59c77e86dc4fe486a751ffb14829ddb70e2f2fca/docs/Plugin_Development.md#71-配置读写
[PD-72]: https://github.com/jxxghp/MoviePilot-Plugins/blob/59c77e86dc4fe486a751ffb14829ddb70e2f2fca/docs/Plugin_Development.md#72-结构化数据与文件
[PD-75]: https://github.com/jxxghp/MoviePilot-Plugins/blob/59c77e86dc4fe486a751ffb14829ddb70e2f2fca/docs/Plugin_Development.md#75-第三方依赖
[PD-76]: https://github.com/jxxghp/MoviePilot-Plugins/blob/59c77e86dc4fe486a751ffb14829ddb70e2f2fca/docs/Plugin_Development.md#76-异步-http-客户端
[PD-81]: https://github.com/jxxghp/MoviePilot-Plugins/blob/59c77e86dc4fe486a751ffb14829ddb70e2f2fca/docs/Plugin_Development.md#81-vuetify-json-模式
[PD-83]: https://github.com/jxxghp/MoviePilot-Plugins/blob/59c77e86dc4fe486a751ffb14829ddb70e2f2fca/docs/Plugin_Development.md#83-联邦组件-css-不得污染主程序
[PD-91]: https://github.com/jxxghp/MoviePilot-Plugins/blob/59c77e86dc4fe486a751ffb14829ddb70e2f2fca/docs/Plugin_Development.md#91-远程命令与事件
[PD-92]: https://github.com/jxxghp/MoviePilot-Plugins/blob/59c77e86dc4fe486a751ffb14829ddb70e2f2fca/docs/Plugin_Development.md#92-插件-api
[PD-93]: https://github.com/jxxghp/MoviePilot-Plugins/blob/59c77e86dc4fe486a751ffb14829ddb70e2f2fca/docs/Plugin_Development.md#93-定时服务
[PD-113]: https://github.com/jxxghp/MoviePilot-Plugins/blob/59c77e86dc4fe486a751ffb14829ddb70e2f2fca/docs/Plugin_Development.md#113-真实加载检查
[PD-12]: https://github.com/jxxghp/MoviePilot-Plugins/blob/59c77e86dc4fe486a751ffb14829ddb70e2f2fca/docs/Plugin_Development.md#12-发布插件
[PD-14]: https://github.com/jxxghp/MoviePilot-Plugins/blob/59c77e86dc4fe486a751ffb14829ddb70e2f2fca/docs/Plugin_Development.md#14-遇到问题时看哪里
[RG]: https://github.com/jxxghp/MoviePilot-Plugins/blob/59c77e86dc4fe486a751ffb14829ddb70e2f2fca/docs/Repository_Guide.md
[RG-2]: https://github.com/jxxghp/MoviePilot-Plugins/blob/59c77e86dc4fe486a751ffb14829ddb70e2f2fca/docs/Repository_Guide.md#2-目录结构
[RG-34]: https://github.com/jxxghp/MoviePilot-Plugins/blob/59c77e86dc4fe486a751ffb14829ddb70e2f2fca/docs/Repository_Guide.md#34-常用字段
[RG-63]: https://github.com/jxxghp/MoviePilot-Plugins/blob/59c77e86dc4fe486a751ffb14829ddb70e2f2fca/docs/Repository_Guide.md#63-维护版本一致性
[RG-72]: https://github.com/jxxghp/MoviePilot-Plugins/blob/59c77e86dc4fe486a751ffb14829ddb70e2f2fca/docs/Repository_Guide.md#72-vue-远程组件
[API]: https://github.com/jxxghp/MoviePilot-Plugins/blob/59c77e86dc4fe486a751ffb14829ddb70e2f2fca/docs/V3_API_Response_Adaptation.md
[API-1]: https://github.com/jxxghp/MoviePilot-Plugins/blob/59c77e86dc4fe486a751ffb14829ddb70e2f2fca/docs/V3_API_Response_Adaptation.md#1-宿主-api-与插件-api-的边界
[API-2]: https://github.com/jxxghp/MoviePilot-Plugins/blob/59c77e86dc4fe486a751ffb14829ddb70e2f2fca/docs/V3_API_Response_Adaptation.md#2-哪些响应需要套-envelope
[ADP]: https://github.com/jxxghp/MoviePilot-Plugins/blob/59c77e86dc4fe486a751ffb14829ddb70e2f2fca/docs/V3_Plugin_Adaptation.md
[FED]: https://github.com/jxxghp/MoviePilot-Frontend/blob/v3/docs/module-federation-guide.md
[SRC-BASE]: https://github.com/jxxghp/MoviePilot/blob/63c8c0d71a12358f92e1e3056b2c79edb2931279/app/sdk/plugin/base.py
[SRC-BASE-ATTR]: https://github.com/jxxghp/MoviePilot/blob/63c8c0d71a12358f92e1e3056b2c79edb2931279/app/sdk/plugin/base.py#L39-L46
[SRC-BASE-RENDER]: https://github.com/jxxghp/MoviePilot/blob/63c8c0d71a12358f92e1e3056b2c79edb2931279/app/sdk/plugin/base.py#L99-L105
[SRC-BASE-DB]: https://github.com/jxxghp/MoviePilot/blob/63c8c0d71a12358f92e1e3056b2c79edb2931279/app/sdk/plugin/base.py#L284-L307
[SRC-SDKEV]: https://github.com/jxxghp/MoviePilot/blob/63c8c0d71a12358f92e1e3056b2c79edb2931279/app/sdk/events.py
[SRC-SNAP]: https://github.com/jxxghp/MoviePilot/blob/63c8c0d71a12358f92e1e3056b2c79edb2931279/app/runtime/event/snapshot.py
[SRC-TYPES]: https://github.com/jxxghp/MoviePilot/blob/63c8c0d71a12358f92e1e3056b2c79edb2931279/app/schemas/types.py#L189-L268
[SRC-SETTLE]: https://github.com/jxxghp/MoviePilot/blob/63c8c0d71a12358f92e1e3056b2c79edb2931279/app/chain/transfer/settlement.py
[SRC-SETTLE-PAYLOAD]: https://github.com/jxxghp/MoviePilot/blob/63c8c0d71a12358f92e1e3056b2c79edb2931279/app/chain/transfer/settlement.py#L173-L188
[SRC-SETTLE-KIND]: https://github.com/jxxghp/MoviePilot/blob/63c8c0d71a12358f92e1e3056b2c79edb2931279/app/chain/transfer/settlement.py#L190-L213
[SRC-SETTLE-PUB]: https://github.com/jxxghp/MoviePilot/blob/63c8c0d71a12358f92e1e3056b2c79edb2931279/app/chain/transfer/settlement.py#L323-L343
[SRC-SETTLE-SKIP]: https://github.com/jxxghp/MoviePilot/blob/63c8c0d71a12358f92e1e3056b2c79edb2931279/app/chain/transfer/settlement.py#L509-L515
[SRC-EV-CONTRACT]: https://github.com/jxxghp/MoviePilot/blob/63c8c0d71a12358f92e1e3056b2c79edb2931279/app/schemas/event.py#L409-L419
[SRC-EV-DATA]: https://github.com/jxxghp/MoviePilot/blob/63c8c0d71a12358f92e1e3056b2c79edb2931279/app/schemas/event.py#L1126-L1136
[SRC-TI]: https://github.com/jxxghp/MoviePilot/blob/63c8c0d71a12358f92e1e3056b2c79edb2931279/app/schemas/transfer.py#L163-L201
[SRC-FILE]: https://github.com/jxxghp/MoviePilot/blob/63c8c0d71a12358f92e1e3056b2c79edb2931279/app/schemas/file.py#L13-L75
[SRC-CFG]: https://github.com/jxxghp/MoviePilot/blob/63c8c0d71a12358f92e1e3056b2c79edb2931279/app/runtime/config.py
[SRC-CFG-DEV]: https://github.com/jxxghp/MoviePilot/blob/63c8c0d71a12358f92e1e3056b2c79edb2931279/app/runtime/config.py#L199-L201
[SRC-CFG-RELOAD]: https://github.com/jxxghp/MoviePilot/blob/63c8c0d71a12358f92e1e3056b2c79edb2931279/app/runtime/config.py#L706-L707
[SRC-CFG-LOCAL]: https://github.com/jxxghp/MoviePilot/blob/63c8c0d71a12358f92e1e3056b2c79edb2931279/app/runtime/config.py#L710-L711
[SRC-SRC-LOCAL]: https://github.com/jxxghp/MoviePilot/blob/63c8c0d71a12358f92e1e3056b2c79edb2931279/app/application/plugin/source.py#L23-L32
[SRC-SRC-SELECT]: https://github.com/jxxghp/MoviePilot/blob/63c8c0d71a12358f92e1e3056b2c79edb2931279/app/application/plugin/source.py#L520-L560
[SRC-CAT]: https://github.com/jxxghp/MoviePilot/blob/63c8c0d71a12358f92e1e3056b2c79edb2931279/app/application/plugin/catalog.py#L506-L515
[SRC-PKG-881]: https://github.com/jxxghp/MoviePilot/blob/63c8c0d71a12358f92e1e3056b2c79edb2931279/app/adapters/system/plugin/package.py#L881
[SRC-PKG-IGNORE]: https://github.com/jxxghp/MoviePilot/blob/63c8c0d71a12358f92e1e3056b2c79edb2931279/app/adapters/system/plugin/package.py#L204
[SRC-PKG-INSTALL]: https://github.com/jxxghp/MoviePilot/blob/63c8c0d71a12358f92e1e3056b2c79edb2931279/app/adapters/system/plugin/package.py#L1145-L1215
[SRC-PKG-PATH]: https://github.com/jxxghp/MoviePilot/blob/63c8c0d71a12358f92e1e3056b2c79edb2931279/app/adapters/system/plugin/package.py#L1260-L1286
[SRC-PKG-SYNC]: https://github.com/jxxghp/MoviePilot/blob/63c8c0d71a12358f92e1e3056b2c79edb2931279/app/adapters/system/plugin/package.py#L2489-L2515
[SRC-MON]: https://github.com/jxxghp/MoviePilot/blob/63c8c0d71a12358f92e1e3056b2c79edb2931279/app/runtime/extensions/plugin/monitor.py#L144-L262
