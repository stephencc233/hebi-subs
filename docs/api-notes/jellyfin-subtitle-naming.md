# Jellyfin 外挂字幕命名与子目录识别（P2-D P2-jellyfin-naming）

> 日期：2026-10-16 ｜ 最终采集 08:49:50 AM ｜ 方法：隔离测试库实测 + 官方文档 + v12.1 源码 + 客户端截图
> 脚本：`scripts/jellyfin_naming_probe.py`（build / refresh / collect）｜ 报告：`tests/fixtures/jellyfin/_probe-report.json` ｜ 截图：`tests/fixtures/jellyfin/*.png`
> 测试库：`tests/jellyfin-lib/Movies/`（已 gitignore，可用脚本重建），Jellyfin 媒体库 HebiTest
> 回答：01-requirements F6.6（两份双语怎么命名）、F6.7（原包放影片子文件夹会不会被误读）；**本文只给依据和方案对比，决定留给 C12**
> 置信度：**高** = 实测且与源码一致；**中** = 实测或源码只有一方；**低** = 推断

## §0 结论速览

1. **只认视频同目录、以「视频名 + `.`」开头的文件**。子文件夹里的字幕一律不识别（`Subs/`、`subtitles/`、`.hebisubs/`、`hebisubs-archive/`、两层嵌套都试过）；`Some.Release-GRP.chs.srt` 这种不以视频名开头的、`Hebi Test A - CMCT.zh.srt` 这种视频名后面不是 `.` 的，也都不识别。（高）
2. **视频名之后按 `.` 切段，从后往前解析**：能识别成语言的**最后一段**作为语言；`default`、`forced` / `foreign`、`sdh` / `cc` / `hi` 是标志；**其余段按原顺序用 `.` 拼起来作为标题**。所以 `.CMCT.zh` 和 `.zh.CMCT` 的结果完全一样（标题都是 CMCT，语言都是 zho）。（高）
3. **客户端列表里显示的就是服务器给的 DisplayTitle**，格式为 `标题 - 语言 - [默认/强制的/听力障碍] - 格式 - 外部`。JMP 截图与 API 返回逐条一致。**能用来区分两份字幕的只有「标题」**：标题、语言、格式都相同时，列表里两行一模一样。实测中把 A21 当成 A20 点错了（`A-06`）。（高）
4. **语言码**：`zh` / `chi` / `zho` / `Chinese` → `zho`，显示为「Chinese」；`zh-CN` / `zh-Hans` → 「Chinese (Simplified)」；`zh-Hant` → 「Chinese (Traditional)」；`chs`、`cht`、`chi&eng`、`简体&英文` **都不是语言**，会变成标题，语言显示为「未定义」。（高）
5. **自动选字幕按语言码整串匹配**：本机用户设置是 Smart 模式、首选语言 `zho`。服务器只会自动选中 Language **恰好等于 `zho`** 的字幕；`zh-hans` / `zh-cn` 匹配不上。多条匹配时，优先选带 `.default` 的；两条都带 `.default` 时选 Index 小的（A43 胜过 A40）。（高：源码 + A / B 两部影片的实测结果一致）
6. **编码不是问题**：UTF-8、GBK、Big5、UTF-16 LE 四种编码，服务器转出的文本和 JMP 的显示都正确。（高）
7. **新发现：缺少 `[Script Info]` 节头的 ASS 会被静默跳过**。CMCT 的 4 个 ASS（真实样本里去重后 15 个 ASS 中的 4 个）都直接以 `Title:` 开头，ffprobe 报 `Invalid data`，Jellyfin 就不列出这个字幕，也没有任何提示。**只在开头补一行 `[Script Info]` 就能正常识别和渲染**（B08）。落盘前必须做格式校验或修复。（高）
8. **两种双语 ASS 排列在 JMP（libass）里都能正常渲染**：同一事件内上下排（SWTYBLZ），按 Style 分成两组事件（CMCT 补节头后）。ASS 的 `Title:` 不会覆盖文件名里的标题（A30、B06）。（高）
9. **F6.7**：`Subs/`（不分大小写）和所有以 `.` 开头的目录在 Jellyfin 内置忽略名单里，**整个目录不会进媒体库**；其他名字的子目录（`subtitles/`、`hebisubs-archive/`）会被建成 **Folder 条目**，影片目录本身也会跟着变成 Folder 条目。它们不会被当成影片、extras 或字幕，但会出现在库的条目里。zip 包在任何位置都不会被读取。（高）

## §1 环境与方法

| 项 | 值 |
|---|---|
| 服务器 | Jellyfin Server **12.1.0**（`/System/Info/Public`），Windows 原生，`D:\jellyfin\Server`，自带 ffmpeg / ffprobe |
| 客户端 | Jellyfin Media Player（桌面端，mpv / libass），只截了这一个客户端 |
| 媒体库 | HebiTest：电影类型，路径 `tests/jellyfin-lib/Movies`；元数据下载器、图片获取器、Nfo 保存器、实时监控全部关闭（报告 `library.library_options`）。实测 Jellyfin **没有往测试目录写入任何文件** |
| 用户偏好 | SubtitleMode = **Smart**，SubtitleLanguagePreference = **zho**，RememberSubtitleSelections = true（报告 `user_subtitle_preferences`） |
| 测试视频 | ffmpeg 生成：3 分钟，640×360 深灰底，H.264 + 静音 AAC；音轨**没有语言标记**，所以 Smart 模式一定会选字幕 |
| 字幕内容 | 每个自造字幕只有一条 0:00.5–3:00 的事件：`变体 Axx：<后缀>` + 简体（Big5 用繁体）测试短语 + 英文。真实双语 ASS 取自 fixtures 的 zip，写成 UTF-8 BOM；时间轴整体前移，以最早的英文台词为锚点挪到 0:05，并在顶部加一行变体标签 |
| 流程 | `build` → 用户建库 → `refresh`（只对 HebiTest 发 FullRefresh，先校验库名和路径）→ `collect`（只读 GET）→ JMP 截图核对。第二轮只加了 B08 |
| API 备注 | 用 API Key 调 `/Items/{id}` **必须带 `userId`**，否则返回 HTTP 400；不带设备配置的 `PlaybackInfo` 不返回 DeliveryMethod / DeliveryUrl（报告里是 null） |

## §2 官方文档要点（2026-10-16 抓取）

出处：jellyfin.org 的 Movies 页（<https://jellyfin.org/docs/general/server/media/movies/>）；External Files 页是前端渲染的，抓到的是空页，所以改读文档仓库的源文件 `jellyfin/jellyfin.org` → `docs/general/server/media/_video-external-streams.md`、`_video-external-extras.md`（master 分支）。页面上没有标注对应哪个服务器版本，下面是否适用于 12.1.0 以 §3 源码和 §4 实测为准。

- 外挂字幕 / 音轨通过**文件名后缀**添加；一个文件可以带多个标志，用 `.` 分隔。示例：`Film.default.srt`、`Film.default.en.forced.ass`、`Film.en.sdh.srt`、`Film.English Commentary.en.mp3`。
- 标志：`default`；`forced` 或 `foreign`；`sdh` / `cc` / `hi`（听力障碍）。`hi` 和印地语代码冲突：单独出现时算印地语，和其他语言码一起出现时算听力障碍标志。
- 不能解析成语言或标志的文字会成为流的**标题**，除非文件自身的元数据里已经有标题。
- extras 子目录名（`behind the scenes`、`deleted scenes`、`interviews`、`scenes`、`samples`、`shorts`、`featurettes`、`clips`、`other`、`extras`、`trailers`、`theme-music`、`backdrops`）和后缀 `-trailer` 等：文档没有提到「子文件夹里的字幕」。
- `VIDEO_TS` / `BDMV` 不支持外挂字幕。

## §3 源码规则（jellyfin/jellyfin `v12.1`，commit `ee91c75`；GPL-2.0，只记规则，引用 ≤5 行）

| 规则 | 出处 | 要点 |
|---|---|---|
| 在哪找 | `MediaBrowser.Providers/MediaInfo/MediaInfoResolver.cs` `GetExternalFiles` | 只列 `video.ContainingFolderPath` 下的文件，再加上内部元数据目录（`GetInternalMetadataPath`，是服务器自己的数据目录）。**不递归子目录** |
| 怎么匹配 | 同上 | 文件名（去扩展名）要以视频文件名（去扩展名）开头，**不区分大小写**，并且下一个字符必须是分隔符 `.`，或者两者完全相同（不带任何后缀） |
| 扩展名 | `Emby.Naming/Common/NamingOptions.cs` `SubtitleFileExtensions` | `.ass .mks .sami .smi .srt .ssa .sub .sup .vtt`（另外 `.idx` 单独处理） |
| 切段与解析 | `Emby.Naming/ExternalFiles/ExternalPathParser.cs` `ParseFile` | 分隔符只有 `.`；从最后一段往前逐段判断：default → forced/foreign → 语言（`FindLanguageInfo`，**只取第一次命中，也就是最靠后的那段**）→ hi 冲突处理 → 听力障碍标志 → 其余段原样拼进标题 |
| 标志判断 | 同上，第 86、94 行 | default、forced/foreign 用的是 **`Contains`（子串匹配）**：`currentSliceWithoutSeparator.Contains(s, OrdinalIgnoreCase)`。所以标题段里只要含有 `default`、`forced`、`foreign`，就会被当成标志吃掉（例如 `ForeignFilm`）。听力障碍标志是整段相等 |
| 语言值 | 同上，第 107–109 行 | 找到的文化名里带 `-` 就存文化名（`zh-cn`、`zh-hans`），否则存三字母 ISO 码（`zho`） |
| 文件内元数据优先 | `MediaInfoResolver.cs` `MergeMetadata` | ffprobe 读到的流本身有 Title / Language 时，以文件内的为准；SRT / ASS 实测不提供（A30、B06），`.mks` 等容器可能会提供（未测） |
| ffprobe 失败 | `GetExternalStreamsAsync` | 抛异常时只写一条错误日志然后 `continue`，**这个字幕不会出现**（B05） |
| 自动选字幕 | `Emby.Server.Implementations/Library/MediaStreamSelector.cs` | 排序：外挂 → IsDefault → 非强制且语言匹配 → …；Smart 模式下，如果音轨语言不在偏好列表里，取第一条语言匹配的。匹配函数是 `preferredLanguages.Contains(language, OrdinalIgnoreCase)`，**整串比较** |
| 忽略目录 | `Emby.Server.Implementations/Library/IgnorePatterns.cs` | 不区分大小写的 glob，包括 `**/subs`、`**/subs/**`、`**/.*`、`**/metadata/**`、`**/extrafanart/**`、`**/sample/*` 等 |

与官方文档一致；文档没有写「只扫同目录」和「标志是子串匹配」这两点，以源码为准。

## §4 A 目录结果：命名（API 字段 + JMP 显示）

`Hebi Test A` 目录下有 28 个变体，同时存在，识别出 27 个。「显示」一列是 API 的 DisplayTitle，和 JMP 列表逐字一致（截图 `A-01`、`A-02`、`A-04`、`A-05`）。Language 是 API 原值。

| 变体 | 文件名后缀 | Index | Language | Title | 显示（DisplayTitle） | 说明 |
|---|---|---|---|---|---|---|
| A01 | `.srt`（无后缀） | 19 | — | — | 未定义 - SUBRIP - 外部 | |
| A02 | `.zh` | 25 | zho | — | Chinese - SUBRIP - 外部 | ⚠ A02 / A03 / A04 / A13 四行显示相同 |
| A03 | `.chi` | 3 | zho | — | Chinese - SUBRIP - 外部 | |
| A04 | `.zho` | 26 | zho | — | Chinese - SUBRIP - 外部 | |
| A05 | `.chs` | 6 | — | chs | chs - 未定义 - SUBRIP - 外部 | 不是语言码，变成了标题 |
| A06 | `.cht` | 7 | — | cht | cht - 未定义 - SUBRIP - 外部 | 同上 |
| A07 | `.zh-CN` | 21 | zh-cn | — | Chinese (Simplified) - SUBRIP - 外部 | 不能匹配 `zho` 偏好 |
| A08 | `.zh-Hans` | 22 | zh-hans | — | Chinese (Simplified) - SUBRIP - 外部 | 同上；和 A07 显示相同 |
| A09 | `.zh-Hant` | 23 | zh-hant | — | Chinese (Traditional) - SUBRIP - 外部 | |
| A10 | `.chi&eng` | 4 | — | chi&eng | chi&eng - 未定义 - SUBRIP - 外部 | 海拉鲁写法：没有语言 |
| A11 | `.简体&英文` | 1 | — | 简体&英文 | 简体&英文 - 未定义 - SUBRIP - 外部 | |
| A12 | `.eng` | 16 | eng | — | English - SUBRIP - 外部 | |
| A13 | `.Chinese` | 5 | zho | — | Chinese - SUBRIP - 外部 | 英文全称也能识别 |
| A20 | `.CMCT.zh` | 15 | zho | CMCT | CMCT - Chinese - SUBRIP - 外部 | ⚠ A20 / A21 / A26 三行显示相同 |
| A21 | `.zh.CMCT` | 24 | zho | CMCT | CMCT - Chinese - SUBRIP - 外部 | 标题放在语言后面，结果和 A20 一样 |
| A22 | `.简英-CMCT.zh` | 2 | zho | 简英-CMCT | 简英-CMCT - Chinese - SUBRIP - 外部 | 中文标题可用 |
| A23 | `.1 CMCT 简英.zh` | 0 | zho | 1 CMCT 简英 | 1 CMCT 简英 - Chinese - SUBRIP - 外部 | 空格可用；排在 Index 0 |
| A24 | `.Hebi.CMCT.zh` | 18 | zho | Hebi.CMCT | Hebi.CMCT - Chinese - SUBRIP - 外部 | 标题里的点会保留 |
| A25 | `.CMCT.zh-Hans` | 10 | zh-hans | CMCT | CMCT - Chinese (Simplified) - SUBRIP - 外部 | |
| A26 | `.CMCT.chi` | 8 | zho | CMCT | CMCT - Chinese - SUBRIP - 外部 | |
| A27 | `.SWTYBLZ.zh.ass` | 20 | zho | SWTYBLZ | SWTYBLZ - Chinese - ASS - 外部 | 和 A20 一起看：两份可以区分 |
| A28 | `.CMCT.zh.ass` | 11 | zho | CMCT | CMCT - Chinese - ASS - 外部 | 只靠格式（ASS / SUBRIP）区分 |
| A29 | ` - CMCT.zh.srt` | — | — | — | **未识别** | 视频名后面不是 `.` |
| A30 | `.FileTitle.zh.ass`（Script Info 里写了 `Title: 脚本内标题`） | 17 | zho | FileTitle | FileTitle - Chinese - ASS - 外部 | 标题取自文件名 |
| A40 | `.CMCT.zh.default` | 12 | zho | CMCT | CMCT - Chinese - 默认 - SUBRIP - 外部 | IsDefault=true |
| A41 | `.CMCT.zh.forced` | 13 | zho | CMCT | CMCT - Chinese - 强制的 - SUBRIP - 外部 | IsForced=true |
| A42 | `.CMCT.zh.sdh` | 14 | zho | CMCT | CMCT - Chinese - 听力障碍 - SUBRIP - 外部 | IsHearingImpaired=true |
| A43 | `.CMCT.default.zh` | 9 | zho | CMCT | CMCT - Chinese - 默认 - SUBRIP - 外部 | 标志放在语言前也行 |

**客户端核对**（JMP）：
- 开始播放时**自动选中 A43**（`A-03`），与 API 的 `DefaultSubtitleStreamIndex=9` 一致：Smart 模式 + 偏好 `zho`，A40 和 A43 都带 default、语言都是 zho，选了 Index 小的。
- **列表顺序**：关闭 → 强制（A41）→ 默认（A43、A40）→ 其余按 Index（`A-04`）。详情页下拉框的顺序也一样（`A-01`）。
- Index 的顺序看起来是按文件名排的，但中文标题（`简体&英文`、`简英-CMCT`）排在拉丁字母前面、数字后面，具体比较规则**不确定**。数字前缀（A23 的 `1 …`）确实能让它排到最前。
- **区分失败的实例**：在列表里点「CMCT - Chinese - SUBRIP - 外部」，本来想选 A20，播出来的是 **A21**（`A-06`）；再点另一行同名的才是 A20（`A-08`）。
- A20、A25、A27 的渲染正常（`A-08`、`A-09`、`A-07`）。

## §5 B 目录结果：子文件夹 + 编码 + 渲染

### 5.1 根目录：编码与真实双语

「服务器文本」= `GET /Videos/{id}/{msId}/Subtitles/{index}/0/Stream.{srt|ass}` 返回的文本里能不能找到变体标签和测试短语。

| 变体 | 文件 | 识别 | 显示 | 服务器文本 | JMP 显示 |
|---|---|---|---|---|---|
| B01 | `.UTF8.zh.srt`（UTF-8 无 BOM） | 是 | UTF8 - Chinese - SUBRIP - 外部 | 标签 ✓ 短语 ✓ | 正确（`B-08`） |
| B02 | `.GBK.zh.srt` | 是 | GBK - Chinese - SUBRIP - 外部 | 标签 ✓ 短语 ✓ | 正确（`B-05`） |
| B03 | `.BIG5.zh-Hant.srt`（繁体文本） | 是 | BIG5 - Chinese (Traditional) - SUBRIP - 外部 | 标签 ✓ 短语 ✓ | 正确（`B-03`） |
| B04 | `.UTF16.zh.srt`（UTF-16 LE BOM） | 是 | UTF16 - Chinese - SUBRIP - 外部 | 标签 ✓ 短语 ✓ | 正确（`B-07`） |
| B05 | `.CMCT.zh.ass`（真实，缺 `[Script Info]`） | **否** | — | — | 列表里没有（`B-02`） |
| B06 | `.SWTYBLZ.zh.ass`（真实，同一事件 `中文\N英文`，`Title: YYeTs`） | 是 | SWTYBLZ - Chinese - ASS - 外部 | 标签 ✓ | 中文在上、英文在下，样式正常（`B-06`） |
| B07 | `Some.Release-GRP.chs.srt` | **否** | — | — | — |
| B08 | `.CMCT-fixed.zh.ass`（B05 只补一行节头） | 是 | CMCT-fixed - Chinese - ASS - 外部 | 标签 ✓ | 片头特效字和中英两行都正常（`B-01`、`B-04`） |

- 开始播放时自动选中 **B08**（Index 1，`zho`），**没有选 Index 0 的 B03**（`zh-hant`）：和 §3「整串匹配」一致（`B-01`）。
- B05 的原因：ffmpeg 的 ASS 识别要求文件以 `[Script Info]` 开头，CMCT 的文件直接以 `Title:` 开头（去掉 BOM 后）。用 Jellyfin 自带的 ffprobe 扫了全部真实样本（解包到 scratchpad，没有写进仓库）：**CMCT 的 4 个 ASS（简体、英文、简体&英文、英文&简体；两个源字节相同）全部失败**，其余 11 个 ASS / SSA 和全部 SRT（包括 GBK、UTF-16）都成功。
- B06 的 `Title: YYeTs` 没有覆盖文件名里的标题 SWTYBLZ：ffprobe 不把 ASS 的 Script Info Title 当成流的标题。

### 5.2 子文件夹（F6.7）

| 子目录 | 变体 | 内容 | 字幕识别 | 库条目 |
|---|---|---|---|---|
| `Subs/` | B11–B13 | zip、`Hebi Test B.Subs.zh.srt`、包里的原名 srt | 全部否 | **无**（忽略名单 `**/subs`） |
| `subtitles/` | B21–B23 | 同上 | 全部否 | **Folder 条目** `…/Hebi Test B/subtitles` |
| `.hebisubs/` | B31–B33 | 同上 | 全部否 | **无**（忽略名单 `**/.*`） |
| `hebisubs-archive/` | B41–B43、B45 | 同上，另有两层嵌套 `CMCT-pack/inner/` | 全部否 | **Folder 条目**：本目录、`CMCT-pack`、`CMCT-pack/inner` |

- 子目录里有不在忽略名单上的目录时，`Hebi Test B` 自己也成了 Folder 条目；只有视频和字幕的 `Hebi Test A` 不会。两部影片都正常识别为 Movie，extras（SpecialFeatures）都是 0。
- 这些 Folder 条目会出现在 API 的递归结果里（报告 `items`）。**没有核实**：它们在客户端的「电影」视图或「文件夹」视图里会不会显示出来（本次没有截库列表）；子目录里放了视频会发生什么（我们不会放）。
- zip 在任何位置都不会被读取（不在字幕扩展名名单里）。

## §6 F6.6 命名方案对比（交 C12 决定）

所有方案都要遵守的硬约束（来自 §3、§4）：
- 文件名必须是 `<视频文件名去扩展名>.<…>.<ext>`，放在视频同目录；
- 标题段不能含 `default`、`forced`、`foreign` 子串，不能整段等于 `cc`、`hi`、`sdh`，也不能整段是语言码（否则会被当成标志或语言）；最好也不含 `.`（含点虽然能保留，但每一段都会被单独解析一次，风险更大）；
- ASS 落盘前保证以 `[Script Info]` 开头（§0 #7）。

| | 方案 1：标题 + `zh` | 方案 2：标题 + `zh-Hans` | 方案 3：海拉鲁式 `chi&eng` |
|---|---|---|---|
| 文件名示例 | `Movie.1 简英 CMCT.zh.default.ass`、`Movie.2 简英 SWTYBLZ.zh.ass` | `Movie.1 简英 CMCT.zh-Hans.default.ass`、`Movie.2 简英 SWTYBLZ.zh-Hans.ass` | `Movie.chi&eng.ass`、`Movie.SWTYBLZ.chi&eng.ass` |
| JMP 显示 | `1 简英 CMCT - Chinese - 默认 - ASS - 外部` / `2 简英 SWTYBLZ - Chinese - ASS - 外部` | `1 简英 CMCT - Chinese (Simplified) - 默认 - ASS - 外部` / … | `chi&eng - 未定义 - ASS - 外部` / `SWTYBLZ.chi&eng - 未定义 - ASS - 外部` |
| 两份能否区分 | 能（靠标题） | 能（靠标题），并且明确标出「简体」 | 能，但第一份没有来源信息 |
| 自动选中（Smart + 偏好 zho） | **能**：Language=zho；带 `.default` 的那份优先 | **不能**：Language=zh-hans ≠ zho，只能手动选（除非用户把偏好改成能匹配的值，**不确定** UI 是否提供） | **不能**：没有语言 |
| 顺序可控 | 能：Index 按文件名排，数字前缀排在最前；`.default` 那份在列表里也置顶 | 同左 | 弱 |
| 对 Jellyfin 版本的依赖 | 低：`zh` → `zho` 和标题段是长期规则（文档示例、单元测试都有） | 中：语言值保留文化名（`zh-hans`）是新版逻辑（v12.1 源码第 107 行），旧版行为**未测** | 低，但本来就识别不出语言 |
| 与 F1.4「已有字幕判定」的配合 | 我们自己的文件一眼能认出（标题段可以带固定标记）；别的工具看 `.zh.` 会当作中文单语 | 同左；`zh-Hans` 在其他工具里能不能识别**不确定** | 与海拉鲁的命名一样，同一个包会被它当成同一个语言后缀；没有语言，其他工具也认不出 |
| 风险 | 显示「Chinese」，看不出是双语，要靠标题写明「简英」；标题会受 §6 硬约束的限制 | 自动选择失效，对日常观看的影响最大 | 「未定义」不好看，自动选择失效 |

补充说明：
- 华语片只要简中（F6.8、D017）时，方案 1 的标题可以写成「简中 …」，规则不变。
- 第二份要不要加 `.default`：不加。两份都带 `.default` 时只有 Index 小的会被选中，第二个标志没有作用，反而在列表里多占一个置顶位置（A40 / A43）。
- 标题里的「简英」可以根据合成结果换成「简英合成」等，让用户看出来源；长度建议短一些（JMP 列表宽度有限，`A-04` 里最长的一行已经接近边缘）。

## §7 F6.7 建议（交 C12 决定）

| 选项 | Jellyfin 影响 | 其他考虑 |
|---|---|---|
| A1 子文件夹 `Subs/` | 被内置忽略名单跳过：不识别字幕、不产生条目（高） | 名字很通用，用户自己或其他工具可能也在用（Plex 等会不会读 `Subs/` **不确定**）；「Subs/ 被忽略」这条规则写在源码里，没写进文档，以后版本可能会变 |
| A2 子文件夹 `.hebisubs/` | 被 `**/.*` 忽略：不识别、不产生条目（高） | 名字是我们自己的，不会和别人冲突；Windows 资源管理器里仍然能看到（没有设置隐藏属性）；MP 整理 / 刮削时会不会碰这个目录**不确定**（P5 验证） |
| A3 子文件夹 `subtitles/`、`hebisubs-archive/` 等普通名字 | 不识别字幕，但**会产生 Folder 条目** | 库里会多出条目，不推荐 |
| B 媒体库之外的集中存档目录（按影片目录镜像） | 完全不受影响 | 影片改名或移动后存档关联会断，需要在存档里记录影片标识；占用空间不在影片目录里，备份策略不同 |

倾向（仅供参考）：如果要放在影片目录里，**`.hebisubs/` 比 `Subs/` 更稳**（我们自己的名字，又落在通配的点目录规则上）；如果更看重「影片目录保持干净」，选 B。两种都能满足 Jellyfin 不误读。

## §8 不确定项与后续

| # | 项 | 怎么补 |
|---|---|---|
| 1 | 只测了 JMP；Web、Android / TV 客户端的列表和渲染没测（DisplayTitle 由服务器生成，推测一致） | 需要时在 Web 端看一眼即可 |
| 2 | Jellyfin 旧版本（10.8 / 10.9 / 10.10）对 `zh-Hans`、子串标志的行为 | 用户实际只用 12.1.0，暂不需要 |
| 3 | Index 的排序规则（中文标题为什么排在拉丁字母前面） | 不影响方案：要控制顺序就用数字前缀 |
| 4 | 首选语言能不能设成 `zh-Hans` 之类的值，让方案 2 也能自动选中 | 看用户设置页的语言下拉；源码在 `UserConfiguration` / 前端 |
| 5 | `.hebisubs/`、`Subs/` 在 MP 整理、刮削时的行为 | P5 实机 |
| 6 | Folder 条目在客户端「电影」/「文件夹」视图里会不会显示 | 只影响 A3，A3 本来就不推荐；需要时打开 HebiTest 库截一张 |
| 7 | `.mks` 等容器字幕自带 Title / Language 时会覆盖文件名（源码如此） | 我们只写 srt / ass，不受影响 |

## §9 对 P3 / P4 的输入

1. **落盘命名函数**的输入：视频文件名（去扩展名）、序号、标题（来源 / 制作组）、语言码（固定 `zh`，或由 C12 决定）、是否 default、扩展名。生成后要做 3 项检查：前缀加 `.` 的规则；标题段不含标志子串、不是语言码；同目录不重名（F6.5，不覆盖）。
2. **ASS 校验 / 修复**：去掉 BOM 和空行后，第一行不是 `[Script Info]` 就补上；有条件时用 ffprobe 跑一遍（MP 环境里有没有 ffprobe **不确定**，P2-E / P5 再看）。这一条要加进 F5.x 或 F6.x。
3. **编码**：Jellyfin 能读 GBK / Big5 / UTF-16，所以写入 UTF-8 不是 Jellyfin 的硬性要求；但为了其他播放器和合成流程，仍建议统一写 UTF-8（03-archive-pain3 §8.3 #1）。
4. **F1.4「已有合格字幕」判定**：用和 Jellyfin 相同的匹配规则（同目录、前缀 + `.`），子目录里的不算。语言不能只看文件名：`chs` / `cht` / `chi&eng` 在 Jellyfin 里是「未定义」，文件名语言标记本来就不可信（archive-tools §0 #7）。
5. **测试**：`_matrix.json` + `_probe-report.json` 可以作为 P4「命名解析」单元测试的期望值（实现一个与 Jellyfin 等价的解析函数，用 A 组变体做断言）。
6. 原包存档如果选 A1 / A2，存档目录名做成配置项，默认值由 C12 定。
