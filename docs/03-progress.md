# 03 进度看板与交接卡 · 合璧字幕 HebiSubs

## 阶段看板

| 阶段 | 状态 | 开始 | 完成 | 产出 |
|---|---|---|---|---|
| P0 准备 | ✅ 完成 | 2026-10-15 | 2026-10-15 | 仓库、CLAUDE.md、文档 v0.1、api-notes（MP V3 开发要点 / 本机环境）、最小空插件 v0.0.1（实机冒烟通过） |
| P1 研读海拉鲁 | ✅ 完成 | 2026-10-15 | 2026-10-16 | study-hailulu 01–05（模块地图、痛点①②、痛点③、自动链路、复盘）；01-requirements v0.2；D014–D017 |
| P2 接口实测 | 🟡 进行中 | 2026-10-16 | | |
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
- [x] S4 P1-4-auto-chain：整理完成 → 识别 → 搜索 → 下载 → 解包 → 落盘的完整链路 → `study-hailulu/04-auto-chain.md`
- [x] C11 复盘：claude.ai 阶段对话评审 P1 笔记，提炼借鉴/避免清单 → `study-hailulu/05-p1-review.md`

## P2 任务清单

> 顺序：P2-A → P2-B → P2-C → P2-D → C12 复盘。P2-E（MP 事件实测）推迟到 P5。输入见 `study-hailulu/05-p1-review.md` §6。

- [x] P2-A P2-subhd-probe：SubHD 页面结构（离线解析手动保存的 HTML）→ `api-notes/subhd.md` + `scripts/subhd_parse_probe.py`
- [x] P2-B P2-assrt-probe：ASSRT API 字段、分页、限额 → `api-notes/assrt.md` + `scripts/assrt_probe.py`
- [x] P2-C P2-archive-tools：Windows 解包工具链 + 字幕包样本统计与真值标注 → `api-notes/archive-tools.md` + `scripts/archive_probe.py` + `tests/fixtures/archives/manifest.json`
- [ ] P2-D P2-jellyfin-naming：Jellyfin 外挂字幕命名与子目录识别 → `api-notes/jellyfin-subtitle-naming.md`
- [ ] C12 复盘：claude.ai 阶段对话定 F6.6 / F6.7、D015 定稿，确认进入 P3

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

### 交接 2026-10-16 · P2-archive-tools
- 阶段：P2（P2-C 完成）
- 完成：`scripts/archive_probe.py`（标准库 + subprocess；工具候选清单逐个运行版本命令；魔数判格式含 RAR4/RAR5；zip 成员名「UTF-8 标志 → 0x7075 → cp437 还原字节按常用字比例选 utf-8/gb18030/big5」回转；7z / tar / py7zr / zipfile 四列能力矩阵；RAR4 Unicode 名标志解析；字幕正文统计；`--with-synthetic` 在 `tests/tmp` 合成 7z / GBK / Big5 / 嵌套样本；样本 sha256 前后比对）；`tests/fixtures/archives/_probe-report.json`；`manifest.json`（13 个包 34 条，人工逐条核对，用户抽查 5 条通过）；`api-notes/archive-tools.md` §0–§9。py7zr 1.1.4 经用户确认装进仓库 `.venv`（9 个包）；只读查看了 MP site-packages。联网仅 py7zr 的 wheel 查询与安装；临时目录已清理
- 决定：无新增编号；**D015 定稿建议**见 archive-tools.md §6：zip 标准库 + 自己回转；rar / 7z 主力 7z.exe；rar 备用 tar.exe、7z 备用 py7zr；倾向引入 py7zr（导入失败降级为提示装 7-Zip）；不用 rarfile / unar
- 主要发现：①7-Zip 26.03 在全部真实样本和合成样本上通过，唯一失败是无扩展字段的 Big5 名 zip（按系统代码页 936 解错）；本机 7z 只在用户 PATH（Scoop），Program Files 没有；②系统 tar.exe（libarchive 3.8.4）**解不了常规 7z**（`LZMA codec is unsupported`），Big5 名 zip 解包失败，zip / RAR4 可以；③7z / tar 在中文 zip 名上「对」只是因为代码页恰好是 936，真实样本 58% 的 zip 成员名是无标志 GBK → zip 必须自己回转；回转在 26 个真实名 + 8 个合成名上全对，GBK/Big5 常同分要靠「平分选 GBK」；Windows 上必须用 `orig_filename`（0x5C 陷阱）；④RAR4 4/4 成员带 Unicode 名；⑤文件名语言标记不可信（`02访谈_cht` 实为简体、`.zh.ass` 实为中英、`.ass` 实为 SSA）；⑥包里有导评、花絮、cd1/cd2 分段，挑选要识别 `content_scope`；⑦只看对话正文后纯中文 ASS 拉丁行 ≤1，海拉鲁缺陷 ① 可避免；简繁特征字区分清楚；⑧MP 环境已有 rarfile 4.5、chardet、charset_normalizer，无 py7zr
- 未完成 / 下一步：P2-D P2-jellyfin-naming（Jellyfin 外挂字幕命名与子目录识别）
- 卡点与风险：RAR5、7z、Big5、嵌套包、季包都没有真实样本（只有合成或缺口）；MP 进程能否通过用户 PATH 找到 Scoop 的 7z 是推测；`.venv` 现在有 py7zr，MP 环境没有
- 需要更新的文档：C12 复盘时——D015 改为生效（按 archive-tools.md §6，含 py7zr 去留）；01 F5.1 补「zip 不交给外部工具、文件名自己回转；tar.exe 只作 rar 备用」，F5.2 补「content_scope（正片 / 花絮 / 导评 / 分段）识别」与「文件名语言标记只作弱参考」；03 §9 #2–#7 标为已答（#10 待剧集）；知识库镜像同步 03
- 下个对话开场白：继续合璧字幕项目，当前阶段 P2，读 03-progress 最新交接卡后开始：P2-D P2-jellyfin-naming，实测 Jellyfin 外挂字幕命名与子目录识别

### 交接 2026-10-16 · P2-assrt-probe
- 阶段：P2（P2-B 完成）
- 完成：`scripts/assrt_probe.py`（标准库 urllib；token 只从环境变量读，用 `Authorization: Bearer` + `add_unredirected_header` 传，URL 不含 token，落盘前再替换为 `***`；统一限速客户端，16 秒间隔、每次运行 ≤40 次；`--dry-run` 打印请求清单、`--resume` 复用已保存响应续跑、`--run-tag` 区分运行）；3 次运行共 42 次请求（r1 12 次被 509 截停、r2 首次 1 次因脚本 bug 丢响应、r2 11 次被下载超时截停、r3 18 次完成）；`tests/fixtures/assrt/` 官方文档原文 + 原始 JSON + 3 份运行日志；`tests/fixtures/archives/assrt/` 6 个字幕包；`api-notes/assrt.md` §0–§8；02 §4、§7.2 标为已答；fixtures 与日志中 token 命中 0 处
- 决定：无新增编号（设计建议在 assrt.md §5.2、§8，留 P3 定）
- 主要发现：①search 只有轻字段（`vote_score`、`upload_time`、可选 `release_site` / `lang`），**下载量 `down_count`、发布人 / 来源 `producer`、包内文件 `filelist` 只在 detail**；②**本账号配额 5 次/分钟**（文档写 20），4 秒间隔连发第 12 次返回 HTTP 509，16 秒间隔稳定；③`cnt` 上限 15，`cnt=50` 时前 2 条混入无 `id` 的内部记录（接口 bug）；`pos` 是条目偏移；无总数字段；无结果时 `subs` 是 `{}`；④`lang` = `{langlist:{langchs,langcht,langeng,langdou}, desc}`，`langdou` = 双语，但 47% 条目没有 `lang`，「英 简」可能是分开的单语文件；⑤不支持 IMDb 搜索，全文模糊匹配会混进别片；默认按上传时间降序；⑥下载链接 ≤17 分钟过期（HTTP 492 → `/download/failed/`），刷新 detail 即可；`filelist` 每个文件有单独下载链接；扩展名不可信（.zip 实为 RAR4）；⑦与 SubHD：肖申克 CMCT 包字节相同，确认重叠 3 条；同包下载量 ASSRT 明显少于 SubHD，跨源不能直接比
- 未完成 / 下一步：P2-C P2-archive-tools（Windows 解包工具链 + 字幕包样本统计与真值标注；ASSRT 新增 2 个 RAR4、4 个 zip 样本，其中一个扩展名与内容不符）
- 卡点与风险：配额语义只是推断（令牌桶式回补？下载与 `user/quota` 是否计数？）；r1 的 509 响应体没保存；`filelist=1` / `is_file` / `no_muxer` / `sub/similar` 未测；`upload_time` 时区、`vote_score` 量纲、链接确切有效期未知
- 需要更新的文档：C12 复盘时——01-requirements 非功能需求「ASSRT 初始 20 次/分钟」改为以账号实际配额为准（本账号 5 次/分钟），F8.2 限速默认值据此设；D014 字段细节带入 assrt.md §4（`vote_score=0` → 无、`release_site="个人"` → 无、上传时间时区统一）；F5.1 补「扩展名不可信」样例；知识库镜像同步 03
- 下个对话开场白：继续合璧字幕项目，当前阶段 P2，读 03-progress 最新交接卡后开始：P2-C P2-archive-tools，实测 Windows 解包工具链并统计字幕包样本

### 交接 2026-10-16 · P2-subhd-probe
- 阶段：P2（P2-A 完成）
- 完成：仓库根建 `.venv`（MP 自带 Python 3.14.7 的 venv，未装任何包，后续 P2 共用）；整理 fixtures（starter.zip 移出；`*_files` 只提交一份 `subhd.js`，其余用 .gitignore 排除）；`scripts/subhd_parse_probe.py`（标准库 HTMLParser 建 DOM，先解包 view-source 另存页，解析搜索页 / 影片页 / 详情页，输出 D014 字段，拿不到为 null；`--compare-raw-rendered` 逐字段对比）；`tests/fixtures/subhd/parsed/` 共 18 个 JSON + 1 份对比；`api-notes/subhd.md` §0–§8。全程联网 0 次
- 决定：无新增编号（设计建议在 subhd.md §6、§8，留 P3 定）
- 主要发现：①列表页（搜索页 / 影片页）就有下载量、上传时间（ISO）、发布人、来源类型、语言、格式、可选字幕组，**全部服务器直接给出**（raw 与 rendered 逐字段一致），05 §2 #3 的请求预算冲突不存在；②**SubHD 没有评分**，只有「支持」点赞数；③字幕组 `/zu/` ≠ 视频压制组（发布名末尾 `-XXX`）；④影片页 `/d/{豆瓣ID}` 一页列出全部字幕、只含本片、默认排序接近下载量降序；搜索页模糊匹配会混进别片、按时间降序、每页 20 条；⑤下载 = `POST /api/sub/prepare-download {sid}` → `/down/…`；详情页有包内文件清单；⑥域名 subhd.tv / subhd.me / subhd.one 并存；⑦海拉鲁假设 #1 #5 #6 #7 部分成立，#2 #3 #4 成立
- 未完成 / 下一步：P2-B P2-assrt-probe（ASSRT API 字段、分页、限额）
- 卡点与风险：验证码在哪一步出现**没有实测依据**（用户 7 次手动下载都没遇到），转人工规则（subhd.md §5.2）是推断；`/search/tt…`、影片页分页、`?order=time`、`/down/` 响应都需要联网验证，本次没做；`.venv` 依赖 MP 的基础解释器，MP 升级 Python 后要重建
- 需要更新的文档：C12 复盘时把 subhd.md §8 #1–#3（`rating` 恒为 null、来源类型映射、字幕组与视频压制组分开）带进 D014 字段细节；知识库镜像同步 03
- 下个对话开场白：继续合璧字幕项目，当前阶段 P2，读 03-progress 最新交接卡后开始：P2-B P2-assrt-probe，实测 ASSRT API 字段、分页与限额

### 交接 2026-10-16 · C11 P1 复盘
- 阶段：P1 → 完成
- 完成：评审 study-hailulu 01–04，三个痛点根因成立；修正 3 处（自动触发身份以事件 mediainfo 为主、历史扫描才读 NFO；语言判定未验证前不据此跳过；SubHD 详情页请求预算）；借鉴 9 条 / 避免 10 条 → `study-hailulu/05-p1-review.md`；01-requirements 升 v0.2；CLAUDE.md 第 4 条改为 GPL-3.0（D016）
- 决定：D014（候选模型与排序层级）、D015（解包方向，拟定）、D016（GPL 只学思路）、D017（华语片也处理，只需简中）
- 未完成 / 下一步：Claude Code 提交本次文档改动；按 P2 任务清单顺序执行 P2-A → P2-D
- 卡点与风险：SubHD 列表页若没有下载量 / 制作组，F4.1/F4.2 需要详情页请求，与低频约束冲突；P2-E 推迟到 P5，事件形态与热重载两轮仍未实测
- 需要更新的文档：无（本次已更新 01、02、03、CLAUDE.md、study-hailulu/README、05、api-notes/README；知识库镜像已同步 01–03）
- 下个对话开场白：继续合璧字幕项目，当前阶段 P2，读 03-progress 最新交接卡后开始：P2-A SubHD 页面结构探测

### 交接 2026-10-15 · P1-4-auto-chain
- 阶段：P1（S4 完成，S1–S4 全部完成）
- 完成：`study-hailulu/04-auto-chain.md`：端到端时序图（每步标文件:行号，搜索 / 解包引用 02、03）、各步要点表、TransferComplete 字段对照表（2a）、Q1–Q5 逐项回答（2b）、借鉴 5 条 / 避免 5 条、给 P3 的架构输入 10 项、P2 待验证 6 条；README「笔记」补了 01–04 目录和一句话结论；`01-module-map.md` §7 #5–#7 标为已答。范围内读了 15 个文件；范围外用 Grep + 小段读取确认了 5 处（`target_normalizers`、`config_runtime`、`subtitle_language`、`shell_helpers`、`subtitle_writer`，合计约 100 行），`_reference` 无改动
- 决定：无新增（§4 是建议，留 P3 定稿）
- 主要发现：①事件只入队、后台单线程处理；路径**只看 `transferinfo.file_list_new`**（兜底的 `target_path` 在 V3 里不存在，推测是旧版遗留），`target_item`、`idempotency_key`、`transfer_history_id` 都没用到；外层 `event_data` 必须是 dict，内层用 `event_value` 同时兼容键和属性。②识别 = 事件 mediainfo/meta + 文件名集数 + TMDb 详情补别名，不读 NFO、不用 IMDb；候选过分数线（≥20）后按服务排序依次试前 5 个，第一个写成功就停。③幂等三层：300 秒内存去重（签名含父目录 mtime）→ 活跃任务去重 → 「已有任意中文字幕就跳过」；队列、结果不持久化，stop 是软停，热重载时 pending 任务会丢、可能出现双 worker（推测）。④限速每源 5 次/分钟，但一次 search 只记 1 次、下载不计。⑤只写中文字幕（外语转 AI）；「匹配历史」是扫描磁盘的快照（`match_history_cache.json`），没有来源和失败记录；失败只在内存任务表（≤200 条）和日志里
- 未完成 / 下一步：**回 C11（claude.ai）做 P1 复盘**：评审 01–04 笔记，提炼借鉴 / 避免清单，然后进入 P2
- 卡点与风险：§5 的 6 条需要实机验证（事件实际形态、重复事件、热重载是新实例还是同一实例、剧集事件间隔、ffprobe 是否可用、刮削与事件的先后），其中 #1 #2 #4 #6 要整理一部测试影片，必须你同意并指定测试目录；04 的行号基于 `8146218`
- 需要更新的文档：无（本次已更新 04、README、01、本文件）；P3 定事件适配层、任务表、落盘历史时参考 04 §4
- 下个对话开场白：继续合璧字幕项目，当前阶段 P1，读 03-progress 最新交接卡后开始：C11 P1 复盘，评审 study-hailulu 01–04 笔记，提炼借鉴 / 避免清单并确认进入 P2

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
