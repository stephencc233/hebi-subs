# 本机 MoviePilot 环境 · 合璧字幕 HebiSubs

> 用途：P0 任务 B，记录本机 MoviePilot V3（Windows 原生）的版本、路径、配置开关、日志、插件目录与端口，供冒烟测试和后续调试查阅。
> 查看日期：2026-10-15。全程**只读**（经用户授权），未修改 `D:\MoviePilot` 下任何文件。
> 密钥类配置（Token、密码、Cookie、代理）只记录“键存在”，不记录值。
> 下文 `<MP>` = `D:\MoviePilot`，`<SRV>` = `D:\MoviePilot\server\MoviePilot-V3`。

## 速查

| 项目 | 值 |
|---|---|
| MP 版本 | **v3.0.7**（前端 v3.0.7），源码提交 `e2e6ff0`（2026-09-21），分支 `v3` |
| Python | **3.14.7**（CPython），解释器 `<MP>\runtime\venv\Scripts\python.exe` |
| MP 主配置 | `<SRV>\config\app.env` |
| 启动器配置 | `<MP>\config\app.ini` |
| 本地插件开发开关 | `PLUGIN_LOCAL_REPO_PATHS`、`PLUGIN_AUTO_RELOAD`、`DEV`、`DEBUG` **均未设置**（取默认值） |
| MP 日志 | `<SRV>\config\logs\moviepilot.log`；插件日志 `<SRV>\config\logs\plugins\<插件id小写>.log` |
| 插件运行目录 | `<SRV>\app\plugins\<插件id小写>\` |
| Web 访问 | `http://localhost:3000`（nginx）；后端 API 端口 3001 |

---

## 1. 目录布局

| 路径 | 内容 |
|---|---|
| `<MP>\MoviePilot-V3.exe` | 启动器（托盘程序），负责拉起 nginx 与后端 |
| `<MP>\config\` | **启动器**配置：`app.ini`、`nginx.conf`、`common.conf`、`category.yaml` |
| `<MP>\logs\` | 启动器日志（目前只有 `shutdown.log`） |
| `<MP>\mp-web\` | 前端静态文件（nginx 提供） |
| `<MP>\runtime\` | 自带运行时：`Python3.14.7\`、`venv\`、`Nginx\`、`Git\`、`uv\` |
| `<MP>\tmp\` | 启动器临时目录 |
| `<SRV>\` | MP 后端源码（git 仓库），含 `app\`、`version.py`、`pyproject.toml`、`uv.lock` |
| `<SRV>\config\` | **MP 自身**配置与数据目录：`app.env`、`user.db`（SQLite）、`logs\`、`plugins\`、`cache\`、`temp\`、`cookies\`、`database_backup\`、`plugin_transactions\` |

命令：`Get-ChildItem D:\MoviePilot`（两层）、`Get-ChildItem <SRV>`、`Get-ChildItem <SRV>\config`

## 2. 版本

- `<SRV>\version.py`：`APP_VERSION = 'v3.0.7'`、`FRONTEND_VERSION = 'v3.0.7'`
- `git -C <SRV> log -1`：`e2e6ff0dc467fe13ceb9dba8e32573edbf352d86`，2026-09-21，分支 `v3`
- 启动器 `app.ini`：`auto_update_on_start=False`，即不会随启动自动更新，版本会一直停在 v3.0.7，除非手动更新

**与任务 A 笔记的差异**：[mp-v3-plugin.md](mp-v3-plugin.md) 依据的是 MP v3 分支 2026-10-15 的源码（`63c8c0d`），本机源码比它早约 3 周。我在本机源码里逐项核对了任务 A 用到的能力：

| 能力 | 本机 v3.0.7 | 位置 |
|---|---|---|
| `PLUGIN_LOCAL_REPO_PATHS` / `PLUGIN_AUTO_RELOAD` / `DEV` / `DEBUG` 配置项 | ✅ 有 | `<SRV>\app\runtime\config.py` L779 / L775 / L201 / L199 |
| 插件热重载监控 | ✅ 有 | `<SRV>\app\runtime\extensions\plugin\monitor.py` |
| `EventType.TransferComplete` / `SubtitleTransferComplete` | ✅ 有 | `<SRV>\app\schemas\types.py` L205 / L209 |
| `app.sdk.events` 的 `snapshot_event_data`、`TransferResultContractData` | ✅ 有 | `<SRV>\app\sdk\events.py` |
| `app.sdk.scheduler.add_plugin_once_job()` | ❌ **无**（该模块只导出 `update_plugin_job`、`remove_plugin_job` 等） | `<SRV>\app\sdk\scheduler.py` |

## 3. Python

- 版本：`python.exe --version` → `Python 3.14.7`
- 解释器（MP 后端实际用的 venv）：`D:\MoviePilot\runtime\venv\Scripts\python.exe`
- `pyvenv.cfg`：`home = D:\MoviePilot\runtime\Python3.14.7`，`implementation = CPython`，`uv = 0.12.5`，`include-system-site-packages = false`
- 正在运行的进程里，`runtime\Python3.14.7\python.exe` 和 `runtime\venv\Scripts\python.exe` 各有 2 个；后端端口 3001 由 `runtime\Python3.14.7\python.exe`（pid 18732）监听。推测是 venv 启动器拉起的基础解释器子进程（Windows venv 的常见行为），实际加载的依赖仍是 venv 里的
- 对本项目的意义：插件依赖装在这个 venv 中；本地跑语法检查 / 单测时应使用这个解释器（[mp-v3-plugin.md §5.5](mp-v3-plugin.md)）

## 4. 配置文件与开关现状

### 4.1 配置目录如何确定

本机源码 `<SRV>\app\runtime\config.py` 中 `CONFIG_PATH` 的取值顺序：
1. 设置了 `CONFIG_DIR` → 用它
2. 在 Docker 中 → `/config`
3. 冻结打包（frozen）→ 可执行文件同级的 `config`
4. 其余情况 → `ROOT_PATH/config`

本机没有设置 `CONFIG_DIR`（`app.env` 和环境变量中都没有），后端用 venv 里的 python 运行源码，不属于 frozen，所以走第 4 种：**`<SRV>\config\`**。实际看到的 `user.db`、日志、插件数据都在这个目录，与推断一致。

### 4.2 MP 主配置 `<SRV>\config\app.env`

现有键（只列键名）：`GITHUB_TOKEN`、`SUPERUSER`、`API_TOKEN`、`COOKIECLOUD_KEY`、`COOKIECLOUD_PASSWORD`、`COOKIECLOUD_ENABLE_LOCAL`、`MODULE_ENABLE`、`PROXY_HOST`、`MOVIE_RENAME_FORMAT`、`TV_RENAME_FORMAT`、`SUBSCRIBE_SEARCH`、`SEARCH_MULTIPLE_NAME`、`SUBSCRIBE_RSS_INTERVAL`、`PLUGIN_MARKET`（约 80 个第三方插件仓库地址）。

### 4.3 与插件开发相关的开关

| 键 | 当前值 | 来源 / 说明 |
|---|---|---|
| `PLUGIN_LOCAL_REPO_PATHS` | **未设置**（默认 `None`） | `app.env` 无此键；用户/系统/进程环境变量也没有 |
| `PLUGIN_AUTO_RELOAD` | **未设置**（默认 `False`） | 同上 |
| `DEV` | **未设置**（默认 `False`） | 同上 |
| `DEBUG` | **未设置**（默认 `False`） | 同上；启动器 `app.ini` 中有 `debug_log=True`，它和 `DEBUG` 是什么关系**不确定** |
| `CONFIG_DIR` | 未设置 | 见 4.1 |

### 4.4 启动器配置 `<MP>\config\app.ini`（非敏感项）

`run_version=MoviePilot-V3`、`nginx_port=3000`、`backend_port=3001`、`auto_update_on_start=False`、`force_update_resources=True`、`auto_start_services=True`、`debug_log=True`、`shutdown_timeout_sec=30`。另有 `github_token`、`proxy_type`、`proxy_host`、`proxy_port`，值未记录。

命令：用 `Select-String` 只匹配指定键；只列键名；`[Environment]::GetEnvironmentVariable(键, Process|User|Machine)`。

## 5. 日志

| 日志 | 路径 | 备注 |
|---|---|---|
| MP 主日志 | `<SRV>\config\logs\moviepilot.log` | 按大小滚动（约 5MB 一份），旧日志为 `.1`、`.2`… |
| 插件日志 | `<SRV>\config\logs\plugins\<插件id小写>.log` | 每个插件一份，同样会滚动；本项目的日志预计为 `hebisubs.log`（**推测**） |
| 启动器日志 | `<MP>\logs\shutdown.log` | 只记录退出过程 |

目前共 34 个日志文件。只看了文件名、大小和修改时间，没有读日志内容。

## 6. 插件目录

- **运行目录**：`<SRV>\app\plugins\<插件id小写>\`。目前装了 30 个插件，包括 autobackup、autosignin、autosubtitle、brushflow、chinesesubfinder、cloudstrm、iyuuautoseed、p115strmhelper、subtitleassistant、subtitlemanualupload 等。本地开发时 MP 会把 `D:\code\hebi-subs\plugins.v3\hebisubs\` 复制到 `<SRV>\app\plugins\hebisubs\`（[mp-v3-plugin.md §5.2](mp-v3-plugin.md)）
- **数据目录**（**推测**，即 `get_data_path()` 返回的目录）：`<SRV>\config\plugins\<PluginID>\`。现在有 AutoBackup、CloudStrm、p115strmhelper、SubtitleAssistant、SubtitleManualUpload，目录名保留了大小写
- **已装的字幕类插件**（与本项目功能重叠）：`chinesesubfinder`、`subtitleassistant`、`subtitlemanualupload`（即海拉鲁字幕大师）、`autosubtitle`

## 7. 端口与进程

| 进程 | 路径 | 监听 |
|---|---|---|
| MoviePilot-V3（启动器） | `<MP>\MoviePilot-V3.exe` | — |
| nginx ×2 | `<MP>\runtime\Nginx\nginx.exe` | `0.0.0.0:3000`（Web） |
| python ×4 | `runtime\Python3.14.7\python.exe` ×2、`runtime\venv\Scripts\python.exe` ×2 | `0.0.0.0:3001`（后端） |

- 浏览器访问：`http://localhost:3000`
- 端口与 `app.ini` 的 `nginx_port`、`backend_port` 一致
- 两个端口都监听 `0.0.0.0`，局域网内的其他设备也能访问
- 查看时 MP 正在运行

命令：`Get-Process` 筛选路径以 `D:\MoviePilot\` 开头的进程；`Get-NetTCPConnection -State Listen` 按这些进程 ID 过滤。

## 8. 对任务 C（冒烟测试）的影响

1. **启用本地插件源**：在 `<SRV>\config\app.env` 中加入
   `PLUGIN_LOCAL_REPO_PATHS=D:\code\hebi-subs` 和 `PLUGIN_AUTO_RELOAD=true`（建议同时加 `DEBUG=true`，用于看旧导入警告），然后通过启动器重启 MP。
   - 这一步要改 MP 配置并重启，**先备份 `app.env`，等用户确认后再做**
   - 能否改在 Web“设定”页里设置、改完是否必须重启，都**不确定**；先按改 `app.env` 加重启的方式来
2. **版本兼容**：`package.v3.json` 中 `system_version: ">=3.0.0"` 能满足本机 v3.0.7。不要用 `add_plugin_once_job`；确实需要时先用 `getattr` 判断是否存在。
3. **验收时看的日志**：`<SRV>\config\logs\moviepilot.log`，关键字为 `HebiSubs` / `hebisubs`，以及热重载提示“检测到本地插件 … Python 文件变化”。
4. **与已装字幕插件可能冲突（P3 再处理）**：海拉鲁 `subtitlemanualupload` 等插件也会在整理完成后写字幕，同一部影片可能被重复处理，同名字幕文件可能互相覆盖。冒烟测试只验证插件能加载，不受影响。
5. **监听范围**：`PLUGIN_LOCAL_REPO_PATHS` 指向仓库根，会让 MP 递归监听 `_reference\` 等全部子目录，影响见 [mp-v3-plugin.md §8](mp-v3-plugin.md) 第 6 项。

## 9. 不确定项

| # | 问题 | 验证方式 |
|---|---|---|
| 1 | 启动器 `debug_log=True` 和 MP 的 `DEBUG` 是什么关系 | 任务 C 中观察日志级别，或查启动器说明 |
| 2 | `PLUGIN_LOCAL_REPO_PATHS` 等能否在 Web 设置页修改、修改后是否需要重启 | 任务 C：改 `app.env` + 重启的方式**已验证可用**；Web 设置页与免重启未测 |
| 3 | ~~插件数据目录是否就是 `<SRV>\config\plugins\<PluginID>\`~~ | **已核实**（任务 C）：`get_data_path()` = `D:\MoviePilot\server\MoviePilot-V3\config\plugins\HebiSubs`，保留类名大小写，首次调用时宿主自动创建 |
| 4 | 本项目插件日志文件名是否为 `hebisubs.log` | 任务 C：日志记录器名为 `hebisubs`（日志行前缀 `hebisubs - `），文件名推测为 `hebisubs.log`，未直接查看 |
| 5 | 后端两种 python 进程的父子关系 | 不影响开发，暂不深究 |
