# SubHD 页面结构实测（P2-A P2-subhd-probe）

> 日期：2026-10-16 ｜ 方法：离线解析用户手动保存的网页（2026-10-15 夜间 11:37 PM–11:56 PM 保存），**本次联网请求 0 次**
> 脚本：`scripts/subhd_parse_probe.py` ｜ 结果：`tests/fixtures/subhd/parsed/` ｜ 回答：`study-hailulu/02-search-pain12.md` §7.1 #1–#11、`05-p1-review.md` §2 #3
> 置信度：**高** = 3 部影片样本一致，且 raw 与 rendered / 截图互相印证；**中** = 样本支持但有例外或样本少；**低** = 推断，未实测

## §0 结论速览

1. **列表页已经有痛点①②要的全部字段，而且都是服务器直接给出的**：下载量、上传时间（ISO）、发布人、来源类型（官方字幕 / 原创翻译 / 其他来源）、语言、格式、大小、字幕组（有才显示），全在 raw HTML 里；6 个页面的 raw 和 rendered 逐字段对比完全一致，JS 只把时间的**显示文字**改成访问者本地时区。（置信度：高）
2. **SubHD 没有「评分」**，只有「支持」点赞数（列表页大于 0 才显示，详情页总是显示）。`rating` 对 SubHD 恒为 null，点赞数放 `raw_extra.like_count`。（高）
3. **字幕组和视频压制组是两回事**：字幕组是可选的 `/zu/{id}` 徽章（样本去重后 54 条，其中 8 条有）；发布名末尾的 `-CMCT`、`-usury` 是视频压制组。（高）
4. **影片页 `/d/{豆瓣ID}` 比搜索页更适合当主入口**：一页列出该片全部字幕（肖申克 36 条，搜索页要翻 2 页），只包含本片，带「下载次数」列，默认排序接近按下载量降序。搜索页是模糊匹配，会混进别的影片（「下北阳光灿烂的日子」）。（高；影片页是否分页：中）
5. **详情页 `/a/{sid}` 只在下载前才需要访问**：它额外提供包内文件清单、字幕组、发布人累计上传数和预览接口。候选排序不需要它。（高）
6. 下载流程是 `POST /api/sub/prepare-download {sid}` → JSON `{success, url:"/down/…"}` → 跳转到 `/down/…`。用户手动下载的 7 个包**全程没出现验证码**。（结构：高；验证码触发条件：低）

## §1 fixtures 清单

raw = Chrome `view-source:` 页面另存（源码包在 `<td class="line-content">` 里并转义，脚本先「解包」还原）；rendered = 浏览器保存的完整网页（JS 执行后的 DOM，相对链接被改写成绝对地址）。URL 取自文件头 `<!-- saved from url=… -->`；canonical 只有影片页和详情页有，搜索页没有，三类页面都没有 og:url。

| 影片（豆瓣 ID） | 文件 | 页面类型 | URL（saved-from） | canonical |
|---|---|---|---|---|
| 秋刀鱼之味（1294433） | `秋刀鱼之味-search.{raw,rendered}.html` + `.png` | 搜索页 | `https://subhd.tv/search/秋刀鱼之味` | 无 |
| | `秋刀鱼之味-movie.{raw,rendered}.html` | 影片页 | `https://subhd.tv/d/1294433` | `https://subhd.me/d/1294433` |
| | `秋刀鱼之味-sub1.raw.html` | 字幕详情 | `https://subhd.tv/a/86CifR` | `https://subhd.me/a/86CifR` |
| | `秋刀鱼之味-sub2.raw.html` | 字幕详情 | `https://subhd.tv/a/pQnWmk` | 同左域名规则 |
| 肖申克的救赎（1292052） | `肖申克的救赎-search.{raw,rendered}.html` + `.png` | 搜索页（第 1 页 / 共 2 页） | `https://subhd.tv/search/肖申克的救赎` | 无 |
| | `肖申克的救赎-movie.{raw,rendered}.html` | 影片页 | `https://subhd.tv/d/1292052` | `https://subhd.me/d/1292052` |
| | `肖申克的救赎-sub1.raw.html` | 字幕详情 | `https://subhd.tv/a/M39aTn` | `https://subhd.me/a/M39aTn` |
| | `肖申克的救赎-sub2.raw.html` | 字幕详情 | `https://subhd.tv/a/OyueLJ` | 同上规则 |
| 阳光灿烂的日子（1291875） | `阳光灿烂的日子-search.{raw,rendered}.html` + `.png` | 搜索页 | `https://subhd.tv/search/阳光灿烂的日子` | 无 |
| | `阳光灿烂的日子-movie.{raw,rendered}.html` | 影片页 | `https://subhd.tv/d/1291875` | `https://subhd.me/d/1291875` |
| | `阳光灿烂的日子-sub1.raw.html` | 字幕详情 | `https://subhd.tv/a/PuFOmN` | 同上规则 |
| | `阳光灿烂的日子-sub2.raw.html` | 字幕详情 | `https://subhd.tv/a/n0sjMq` | 同上规则 |

附属资源：`*_files/` 只提交一份 `秋刀鱼之味-search.rendered_files/subhd.js.download`（6 份哈希相同，站点前端脚本 `subhd.js?v=20260714-1`）。其余是 bootstrap / jquery / css / 海报，外加两个第三方脚本：`saved_resource`（aizhantj 统计）和 `v4bc…`（Cloudflare RUM 信标）。这些用 `.gitignore` 排除，文件留在本地。

下文引用的行号 = view-source 行号（raw 文件里 `td.line-number` 的值，也等于解包后源码的行号）。

## §2 海拉鲁假设 #1–#7 核对

| # | 假设 | 结论 | 证据 | 对设计的影响 | 置信度 |
|---|---|---|---|---|---|
| 1 | 根地址 `https://subhd.tv` | **部分成立** | 页面从 `subhd.tv` 保存，但 canonical 指向 `subhd.me`；页头横幅写着备用域名（见下方片段 A） | 根地址做成配置项，默认 `subhd.tv`，备选 `subhd.me`、`subhd.one`；页面内链都是相对路径，换域名不影响解析 | 高 |
| 2 | 搜索页 `{root}/search/{关键词}`，GET，静态 HTML 有结果 | **成立**（IMDb 号搜索**未验证**） | saved-from 即此形式；raw 里直接有结果卡片；分页是 `/search/{关键词}/{页码}`，每页 20 条 | 搜索页可直接请求解析；`/search/tt…` 能否命中要等联网验证 | 高（IMDb：低） |
| 3 | 搜索页里影片链接 `<a href="/d/{数字}">`，锚文本或 `img alt` 是片名 | **成立**（片名在 `img alt` 里，锚文本为空） | 片段 B | 用卡片的 `/d/{ID}` 做身份过滤（搜索是模糊匹配，见 §3.4） | 高 |
| 4 | 详情页 `{root}/d/{豆瓣 ID}`，条目 ID = 豆瓣 ID | **成立** | 影片页链到 `movie.douban.com/subject/1292052`（L117），海报路径 `poster/douban/1292052_600.webp` | 有豆瓣 ID 就能直接请求影片页，省掉搜索；MP 的 mediainfo 是否带豆瓣 ID 留给 P3 | 高 |
| 5 | 字幕链接 `<a href="/a/{sid}">`，搜索页和详情页结构相同 | **部分成立** | 链接形式成立（54 个 sid 全是 6 位字母数字）；但搜索页是卡片 `div.bg-white.shadow-sm.rounded-3.mb-4`（每张卡片 2 个 `/a/` 链接），影片页是表格行 `div.row.pt-2.mb-2`（每行 1 个），**结构不同** | 两种页面各写一个解析器（脚本中的 `parse_search_page` / `parse_movie_page`）；按 sid 去重 | 高 |
| 6 | 语言、格式信息在字幕链接前 700 / 后 300 字符内 | **部分成立** | 从 `</a>` 结束处往后数 300 字符：搜索页每张卡片的第 2 个链接（发布名）能覆盖标签区，第 1 个（片名）不能；影片页 36 行里有 8 行覆盖不到，恰好是有字幕组徽章的 8 行（徽章把标签区往后推了）；前 700 字符没有吃进上一条的标签（0 次） | 用 DOM 按卡片 / 行取标签，不用字符窗口 | 中 |
| 7 | 详情页有 `href=".../down/{sid}"` 下载按钮或 `data-sid` 属性 | **部分成立**：有 `data-sid`，**没有** `/down/` 链接 | 片段 C；`/down/…` 地址由接口动态返回（§5） | 下载要先 POST 接口拿 URL，不能直接拼 `/down/{sid}`（是否也能用未验证） | 高 |

片段 A（`肖申克的救赎-search.raw.html` L31，页头横幅）：
```html
网站可能被墙，请记住以下域名：<span class="text-danger fw-bold f14">subhd.me subhd.one</span>
```
片段 B（`肖申克的救赎-search.raw.html` L91–94）：
```html
<a href='/d/1292052'>
  <div class="pics">
    <img class="rounded-start" src="https://img.subhd.me/poster/douban/1292052_600.webp" alt="肖申克的救赎 The Shawshank Redemption">
```
片段 C（`肖申克的救赎-sub1.raw.html` L217–220）：
```html
<button type="button"
        class="btn btn-danger down subtitle-prepare-download"
        data-sid="M39aTn"
        data-loading-text="处理中…"
```

## §3 #8–#11：字段在哪、是不是服务器给出

### 3.1 字段位置表

「raw 有」= 服务器直接给出；「rendered 有」= JS 执行后仍在。逐字段对比结果见 `parsed/_compare_raw_vs_rendered.json`：6 对页面所有字段的非空条数和取值全部一致。

| 字段（D014） | 搜索页卡片（选择器） | 影片页行（选择器） | 详情页（选择器） | raw 有 | rendered 有 | 结论 | 置信度 |
|---|---|---|---|---|---|---|---|
| `download_count` 下载量 | `div.pt-2.text-secondary.f12` 里 `svg.bi-download` 后面的 `span` | `div.text-end.text-secondary`（列头「下载次数」） | `div.subtitle-metadata-stats` 第 2 个 `span` | ✅ | ✅ | 服务器直接给出；三处数值一致 | 高 |
| `release_group` 字幕组 | 可选的 `div.float-end > a[href^="/zu/"]` | 可选的 `span.rounded-3 > a[href^="/zu/"]`（跟在标题后面） | 可选的 `a[href^="/zu/"]`（「片源版本」块内） | ✅ | ✅ | 独立元素，不混在标题里；**没有就是真的没有**（null） | 高 |
| `uploader` 发布人 | `div.pt-1.f12` 里「发布人 `a.fw-bold[href^="/u/"]`」 | `a[href^="/u/"]`（列头「上传人」） | `div.subtitle-publisher-row a.fw-bold[href^="/u/"]` + 「总共发布过字幕 N 条」 | ✅ | ✅ | 服务器直接给出；详情页多一个头像链接（无头像时里面是首字母），不能取它的文字 | 高 |
| `upload_time` 上传时间 | `time[datetime]`（ISO，UTC） | `time[datetime]` | `div.subtitle-metadata-stats time[datetime]` | ✅ | ✅（显示文字变了） | `datetime` 属性服务器直接给出；显示文字被页面内联脚本（`time[data-local-time]`）改成本地时区：raw `03-15 20:53` → rendered `03-15 16:53` | 高 |
| `rating` 评分 | 无；只有点赞数 `span.p-1.text-danger > span.align-baseline`（大于 0 才显示） | 同左 | 无；点赞按钮 `button.subtitle-rating-button span.upv`（总是显示，可以是 0） | — | — | **SubHD 没有评分**，`rating` = null；点赞数放 `raw_extra.like_count`，列表页缺失 ≈ 0（`86CifR` 列表无徽章，详情 `upv=0`） | 高 |
| `source_type` 来源类型 | `span.rounded.p-1.text-white`（背景色区分） | 同左 | `div.subtitle-metadata-tags` 里同样的 span | ✅ | ✅ | 样本里只出现 3 种：官方字幕（`#00a3ff`）、原创翻译（`#28a745`）、其他来源（`#6c757d`）；没有「机翻 / AI 校对」 | 高（种类是否齐全：中） |
| `language_tags` 语言 | `span.p-1.fw-bold`（含「双语」） | 同左 | 同左 | ✅ | ✅ | 取值见过：双语、简体、繁体、英语、法语、德语、其它 | 高 |
| `format` 格式 | `span.p-1.text-secondary` | 同左 | 同左 | ✅ | ✅ | 可以有多个：SRT、ASS、SSA、SUP（图形字幕） | 高 |
| `title` | `div.view-text a`（发布名；卡片大标题是片名，放 `raw_extra.movie_title`） | `div.view-text a` | `div.subtitle-edition`（「片源版本」） | ✅ | ✅ | — | 高 |
| 大小（raw_extra） | `svg.bi-file-earmark-fill` 后面的 `span` | **无** | stats 第 1 个 `span` | ✅ | ✅ | 文字形式如 `153k` | 高 |
| 评论数（raw_extra） | `span.p-1.text-primary`（含 `svg.bi-chat`，大于 0 才显示） | 同左 | — | ✅ | ✅ | — | 高 |
| 包内文件清单（raw_extra） | 无 | 无 | `a.subtitle-file-name[data-filename]` + `span.subtitle-file-size` | ✅ | 未保存 rendered | 下载前就能看到包里有哪些文件（语言、格式、目录）；预览接口 `data-preview-url="/api/sub/preview/{sid}"` | 高 |

片段 D（`肖申克的救赎-search.raw.html` L128–136，搜索页卡片统计行，已去掉 svg）：
```html
<span class="align-text-top me-3">1932</span>
<span class="align-text-top me-3"><time datetime="2026-03-15T20:53:15.000Z" data-local-time="relative">03-15 20:53</time></span>
发布人 <a class="fw-bold text-dark" href='/u/字幕Robot' target='_blank'>字幕Robot</a>
```
片段 E（`肖申克的救赎-movie.raw.html` L176、L179、L210）：
```html
<div class="px-3 py-2 text-end">下载次数</div>
<div class="px-3 py-2 text-end">上传人</div>
<div class="px-3 py-2 text-end text-secondary">49824</div>
```

**结论（回答 05 §2 #3）**：下载量和制作组**不只在详情页**，列表页就有，而且是服务器直接给出。F4.1 / F4.2 不需要逐条请求详情页，「低频约束」与候选展示之间的冲突不存在。

### 3.2 列表页默认排序（截图核对）

| 页面 | 默认顺序 | 证据 | 置信度 |
|---|---|---|---|
| 搜索页 | **按上传时间降序** | 3 个搜索页的 `upload_time` 序列都严格降序；3 张截图卡片顺序与 raw 完全一致（例：秋刀鱼 2025-10-25 → 2022-01-13 → 2021-02-23 → 2015-06-22）；混进来的别片放在它自己的时间位置 | 高 |
| 影片页 | 「默认排序」**接近按下载量降序，但不严格** | 秋刀鱼 0 处逆序；肖申克 35 对相邻里 3 处逆序（第 2 名 `58rXMQ` 6202 排在 20709 前面）；阳光 12 对里 2 处。规则不确定（可能是缓存的下载数，或者有置顶） | 中 |

### 3.3 排序和分页参数

| 页面 | 参数 | 证据 | 置信度 |
|---|---|---|---|
| 搜索页 | 分页 `/search/{关键词}/{页码}`，**每页 20 条**；`h4` 里有「共 N 条 当前第 N 页」；**没有排序参数** | `肖申克的救赎-search.raw.html` L82、L1319 | 高 |
| 影片页 | 排序下拉：默认 `/d/{ID}`、按时间 `/d/{ID}?order=time`；**没看到分页**（36 条一页列完） | `肖申克的救赎-movie.raw.html` L161–162 | 排序：高；条目很多时是否分页：中（样本最多 36 条） |
| 搜索联想 | `subhd.js` L250 `fetch("/searchD/" + 关键词)`，返回 JSON 联想列表（未调用） | `subhd.js.download` | 低（只看到代码） |

### 3.4 搜索页 vs 影片页

| 项 | 搜索页 | 影片页 |
|---|---|---|
| 范围 | 关键词模糊匹配，会混进别的影片（阳光 14 条里有 1 条属于 `/d/2148784` 下北阳光灿烂的日子） | 只有本片 |
| 条数 | 每页 20 条，要翻页（肖申克 36 条 = 2 页） | 一页列完（肖申克 36 条） |
| 字段 | 多了大小 | 没有大小 |
| 条目集合 | 肖申克：两页合计 36 条 = 影片页 36 条；阳光：去掉别片后 13 条 = 影片页 13 条 | — |

**对设计的影响**：Provider 流程建议为「拿到豆瓣 ID → 直接请求影片页（1 次）；没有豆瓣 ID → 搜索页 1 次，用卡片的 `/d/{ID}` 选出本片 → 请求影片页」。搜索页只用来**找 ID**，不靠它翻页取候选。（中，P3 定）

## §4 解析脚本与输出

- 用法：`.venv\Scripts\python.exe -I scripts\subhd_parse_probe.py tests\fixtures\subhd --compare-raw-rendered --out-dir tests\fixtures\subhd\parsed`
- 只用标准库：`HTMLParser` 建最小 DOM 树 → 按页面类型（URL 路径）选解析器 → 输出 D014 字段；拿不到输出 null。
- 输出：每个输入文件一个 JSON（共 18 个）+ `_compare_raw_vs_rendered.json`。列表页 `candidates[]`，详情页 `detail`。
- **null 与 0**：输出里所有的 0 都是站点**显示出来的 0**（`gb5jsH`、`AeFTDs` 下载数为 0；详情页点赞 `upv=0`），不是缺省值；缺失一律是 null（例：没有字幕组的 `release_group`、影片页的 `size_text`、列表页没有徽章时的 `like_count`）。
- 一致性：详情页与列表页对同一 sid 的 D014 字段**完全一致**（6 个 sid 交叉核对）。

输出样例（`肖申克的救赎-movie.raw.json`，第 3 条，节选）：
```json
{"title": "The.Shawshank.Redemption.1994.BluRay.1080p.x264.AC3-CMCT", "sid": "M39aTn",
 "detail_url": "https://subhd.tv/a/M39aTn", "download_count": 20709, "release_group": "CMCT字幕组",
 "uploader": "101eagle", "upload_time": "2017-07-28T16:32:17.000Z", "rating": null,
 "source_type": "原创翻译", "language_tags": ["双语", "简体", "英语"], "format": ["SRT", "ASS"], "source_rank": 3}
```

## §5 下载流程（只描述，未触发）与转人工

### 5.1 结构

1. 详情页按钮 `button.btn.down.subtitle-prepare-download[data-sid]`（片段 C）。页面上**没有 form，没有 csrf token，没有验证码元素**（6 个详情页 grep `csrf` / `captcha` / `geetest` / `<form` 均为 0）。
2. `subhd.js` L334–410：点击后 `POST /api/sub/prepare-download`，`Content-Type: application/json`，请求体 `{"sid": "<sid>"}`；成功响应要求 `data.success === true` 且 `data.url` 以 `/down/` 开头，然后 `window.location.href = data.url`；失败就 `alert(data.msg)`。
   ```js
   url: "/api/sub/prepare-download",
   data: JSON.stringify({ sid: subtitleId }),
   if (!data || data.success !== true || typeof data.url !== "string" || data.url.indexOf("/down/") !== 0) {
   ```
3. `/down/…` 返回的内容未观察到。按用户的手动下载结果推断是直接返回文件：6 个压缩包 + 1 个裸 `.ass`，可见**下载结果不一定是压缩包**。（低）
4. 其他接口（只看到代码，未调用）：点赞 `POST /api/sub/rating`、预览 `GET /api/sub/preview/{sid}`、搜索联想 `GET /searchD/{关键词}`。

### 5.2 验证码观察与 D004 转人工场景

用户观察：2026-10-15 夜间手动下载 7 个文件，**全程没出现验证码**。所以验证码在哪一步、以什么形式出现，目前**没有实测依据**。以下判定规则是推断（置信度：低），P4 实现时要做成「拿不准就转人工」：

| 场景 | 判定依据（推断） | 处理 |
|---|---|---|
| prepare-download 返回 `success !== true` | 响应里有 `msg` | 记录 msg；含「验证 / 人机 / 频繁」等字样 → 转人工 |
| `data.url` 不以 `/down/` 开头 | 前端也把它当失败处理 | 转人工 |
| `/down/…` 返回的是 HTML 而不是文件 | `Content-Type: text/html`，或魔数不是 zip / rar / 7z / 文本字幕 | 当作验证码或拦截页 → 转人工（通知 + 投喂目录），**不尝试识别** |
| HTTP 403 / 429 / 503，或 Cloudflare 挑战页 | 状态码，或页面里有 `cdn-cgi` / `challenge` | 熔断 SubHD（F8.2），转人工 |
| 列表页 / 影片页本身返回挑战页 | 解析不到卡片或行，且不是「共 0 条」 | 同上 |

## §6 请求预算

每部影片（HTTP 层按请求计数，F8.2）：

| 方案 | 请求数 | 能拿到 |
|---|---|---|
| A. 已知豆瓣 ID → 影片页 | **1** | 全部候选的 D014 字段（缺大小） |
| B. 搜索页 → 影片页 | **2** | 同上；搜索页只用来找豆瓣 ID |
| C. 只用搜索页（翻页） | ⌈N/20⌉（肖申克 2 次） | 有大小，但会混进别片，要翻页 |
| D. 列表 + 前 N 条详情页 | 1~2 + N | 加上包内文件清单、发布人累计上传数 |
| 下载 1 个字幕 | +2（prepare-download + `/down/`） | — |

**建议**（中，P3 定稿）：
1. 候选展示和打分只用列表请求（A 或 B），**不访问详情页**。
2. 只对最终选中的 Top 2 下载；包内文件清单可以在下载后直接从压缩包读，所以详情页默认不请求。只有在「两个候选打平、要靠包内文件判断语言」时才请求，并按 sid 缓存。
3. 自动处理单部影片的典型开销：2（列表）+ 2×2（下载）= **6 次**。历史库批量扫描仍不走 SubHD（01 非功能需求，🔶）。

## §7 字幕包登记（只登记，未解包）

格式按文件头魔数判断（只读前 16 字节）。sid 按发布名与页面对应。

| 文件 | 大小（字节） | 魔数格式 | 对应 sid / 页面 | 备注 |
|---|---|---|---|---|
| `An.Autumn.Afternoon.1962.1080p.Bluray.x264-usury.zip` | 34,707 | zip | `pQnWmk`（秋刀鱼 sub2） | 详情页列出 1 个文件 |
| `An.Autumn.Afternoon.1962.720p.BluRay.x264-WiKi.rar` | 67,911 | **RAR4**（`Rar!\x1a\x07\x00`） | `86CifR`（秋刀鱼 sub1） | 详情页列出 2 个文件（原版中字 + 「简体化」版），P2-C 测 rar 用 |
| `In.the.Heat.of.the.Sun.1994.CHINESE.1080p.BluRay.x264.DTS-NOGRP 官方简体字幕.zip` | 44,334 | zip | `QRJs0A`（阳光搜索页第 6 条；没保存详情页） | 文件名带空格和中文 |
| `The.Shawshank.Redemption.1994.2160p.BluRay.x265.10bit.SDR.DTS-HD.MA.5.1-SWTYBLZ.zip` | 72,708 | zip | `OyueLJ`（肖申克 sub2） | 详情页列出 1 个 `.zh.ass`，但标签写「双语 简体 英语」 |
| `The.Shawshank.Redemption.1994.BluRay.1080p.x264.AC3-CMCT.zip` | 417,458 | zip（UTF-8 文件名标志位已设置） | `M39aTn`（肖申克 sub1） | 详情页列出 6 个文件，带子目录，含「导评字幕」 |
| `阳光灿烂的日子.In.the.Heat.of.the.Sun.1994.1080p.WEB-DL.H264.AAC-TJUPT.zip` | 42,460 | zip | `PuFOmN`（阳光 sub1） | 详情页列出 1 个文件 |
| `阳光灿烂的日子.In.the.Heat.of.the.Sun.1994.CHINESE.1080p.BluRay.x265-VXT.简中.ass` | 189,944 | **裸 ASS**（UTF-8 BOM） | `eVhMw6`（阳光搜索页第 1 条） | 下载结果不是压缩包 |

另：`hebi-subs-starter.zip`（项目初始骨架，不是字幕包）已移出 fixtures，不提交。

## §8 对设计的影响与遗留问题

对 P3 的输入：
1. **D014 字段对 SubHD 的取值**：`download_count`、`upload_time`、`uploader`、`source_type`、`language_tags`、`format`、`source_rank` 列表页全有；`release_group` 有就填、没有就 null；`rating` 恒为 null，候选模型可增加 `like_count`（或放 `raw_extra`）。（高）
2. **来源类型映射**：SubHD 的「官方字幕 / 原创翻译 / 其他来源」要映射到 F4.2 的分类；「其他来源」占多数（去重 54 条里 36 条；官方字幕、原创翻译各 9 条），对应「转载 / 未知」。「机翻 / AI 校对」SubHD 不标，只能靠标题关键词推断，并标注是推断值。（中）
3. **字幕组 ≠ 视频压制组**：模型里分开存（`release_group` 与 `video_release_group`）；后者用于 F2.2 片源版本匹配。（高）
4. **身份过滤**：搜索结果必须按 `/d/{豆瓣ID}` 过滤；有豆瓣 ID 就直接走影片页。（高）
5. **时间统一用 `datetime` 属性**（UTC ISO），不要解析显示文字。（高）
6. **下载结果要按魔数分流**：zip / rar / 7z / 裸字幕文件都可能出现（接 P2-C、F5.1）。（高）
7. **`source_rank` 取哪种页面的顺序**：搜索页是时间序、影片页接近下载量序，两者不同；建议以影片页顺序为准，并记录 `query` / 页面类型。（中）

遗留（需要联网验证，本次未做）：
- `/search/tt{IMDb号}` 能否直接命中影片（假设 #2 后半）。
- 影片页字幕很多时是否分页；`?order=time` 的效果；「默认排序」的确切规则。
- `/down/…` 的真实响应、验证码出现的条件和形式（D004 转人工规则要据此校准）。
- 直接 GET `/down/{sid}` 是否可用（海拉鲁的旧假设）。
