# Windows 原生解包工具链与字幕包样本（P2-C P2-archive-tools）

> 日期：2026-10-16 ｜ 方法：离线实测（只有 py7zr 的 wheel 查询和安装联网，均经用户确认）；最终运行 02:33:18 AM
> 脚本：`scripts/archive_probe.py` ｜ 报告：`tests/fixtures/archives/_probe-report.json` ｜ 正确答案：`tests/fixtures/archives/manifest.json`
> 回答：`study-hailulu/03-archive-pain3.md` §9 #2–#7、#10（见 §7）；D015 定稿输入（§6）
> 样本：`tests/fixtures/archives/{subhd,assrt}/` 共 13 个文件（`other/` 不存在）；缺的格式由脚本在 `tests/tmp/` 临时合成（用户决定），不计入样本统计
> 置信度：**高** = 实测且多个样本一致；**中** = 实测但样本少或只有合成样本；**低** = 推断

## §0 结论速览

1. **7-Zip（7z.exe 26.03）全能**：真实样本 12 个包（zip 9、RAR4 3）、合成的 7z / 嵌套包，全部能列出、能解开、中文名正确。唯一的失败是**不带扩展字段的 Big5 文件名 zip**：7z 按系统代码页（936）解码，名字被解错。（高）
2. **Windows 自带 tar.exe（bsdtar 3.8.4 / libarchive 3.8.4）不能解常规 7z**：报错 `LZMA codec is unsupported`。只有「仅存储 + 关闭头压缩」的 7z 能读，现实中基本不存在。zip、RAR4 都能解，但 zip 中文名同样依赖系统代码页，Big5 名的 zip **解包直接失败**（`Invalid empty pathname`）。（高）
3. **py7zr 1.1.4 在 Python 3.14 + Windows 上可用**：9 个包全部有现成 wheel（`cp314-win_amd64` / `abi3` / 纯 Python），装进 `.venv` 后 7z（LZMA2、仅存储、嵌套内层）都能解，中文名正确。（高）
4. **zip 文件名要自己回转，不能交给 7z / tar**：真实样本中 GBK 文件名、没有 UTF-8 标志的成员 **14/24**（不含目录项）。本机代码页恰好是 936，7z / tar 才碰巧解对；英文系统或 Big5 名一定解错。「标志位 → 0x7075 Unicode 路径字段 → cp437 还原字节后按常用字比例在 utf-8 / gb18030 / big5 中选」这套方法，在 26 个真实名字 + 8 个合成名字上**全部判对**。（高；Big5 只有合成样本：中）
5. **RAR4 文件名不依赖代码页**：3 个 RAR4 包的 4 个成员，文件头都带 Unicode 名标志（0x200）。（高；RAR5 没有样本，见 §8）
6. **扩展名不可信**：ASSRT「肖申克…4K适配HDR.zip」实为 RAR4。散装的「…简中.ass」内容是 SSA v4。（高）
7. **文件名里的语言标记不可信，必须看对话正文**：`02访谈_cht.ass` 正文是简体（与 chs 版只差字体名）；`…SWTYBLZ.zh.ass` 实为中英双语；REDANDY / usury / 肥内 三个文件名没有任何语言标记。（高）
8. **包里不只有正片**：28 个字幕里有导演评论 1 个、花絮 / 预告 6 个、分段（cd1 / cd2）4 个。挑选环节必须识别 `content_scope`。（高，样本小）
9. **D015 推荐**（§6）：zip 用标准库并自己回转文件名；rar / 7z 主力用 7-Zip；rar 的备用是 tar.exe，7z 的备用是 py7zr；**建议引入 py7zr 作为 7z 的备用依赖**；不用 rarfile、unar。

## §1 工具探测

| 工具 | 位置 / 来源 | 版本命令输出 | 说明 |
|---|---|---|---|
| 7z.exe | `D:\Scoop\shims\7z.exe`（用户 PATH 上的 Scoop shim）→ 实体 `D:\Scoop\apps\7zip\current\7z.exe` | `7-Zip 26.03 (x64) … 2026-09-03`（`7z i` 首行） | shim 和实体各运行一次，都可用；Program Files、(x86)、`%LOCALAPPDATA%\Programs`、Chocolatey 下都没有 |
| tar.exe | `C:\WINDOWS\system32\tar.exe` | `bsdtar 3.8.4 - libarchive 3.8.4 zlib/1.2.5.f-ipp cng/2.0 libb2/bundled` | 版本行里**没有 liblzma / bz2 / zstd**，与 7z 失败对得上 |
| UnRAR / WinRAR | — | — | 本机没有 |
| py7zr | 仓库 `.venv`（2026-10-16 经用户确认安装） | `py7zr 1.1.4`（Python 3.14.7） | 依赖：brotli 1.2.0、inflate64 1.0.4、pybcj 1.0.8、pyppmd 1.3.1（均 cp314-win_amd64）；pycryptodomex 3.24.1、psutil 7.2.2（abi3）；multivolumefile 0.2.3、texttable 1.7.1（纯 Python）。**依赖里没有 pyzstd**（推测 3.14 用标准库 `compression.zstd`，不确定） |
| 系统代码页 | 注册表 `Nls\CodePage` / `GetACP()` | ACP = OEMCP = **936** | 决定 7z / tar 怎么解码 zip 里没有 UTF-8 标志的文件名 |

**MP 运行环境**（只读列 `D:\MoviePilot\runtime\venv\Lib\site-packages` 的目录名，经用户同意）：有 `rarfile 4.5`（单文件 `rarfile.py`，大概率是海拉鲁的 requirements 装进来的，推测）、`chardet 7.6.0`、`charset_normalizer 3.5.1`；**没有 py7zr**。

**MP 进程能不能找到 7z**：`D:\Scoop\shims` 在**用户 PATH**，不在系统 PATH。MP 托盘程序从用户会话启动，应该继承用户 PATH（推测，未查进程环境）。如果改成以服务或其他账户运行，就找不到了 → 探测清单必须包含 Scoop 位置，并允许在配置里填路径。

## §2 能力矩阵

四个字母依次是：能列出 / 列出的名字对 / 能解开 / 落盘的名字对；`-` = 不适用（zipfile 只测 zip，py7zr 只测 7z）。「名字对」以正确名称为准：zip 用 §3 的回转结果，RAR / 7z 用 7z `-sccUTF-8` 的列表，再人工核对；合成样本的正确名称是已知的，6 个合成包全部复核一致。

### 2.1 真实样本（12 个包，内容一致 = 各工具解出的文件 sha256 集合相同）

| 包（真实格式） | 7z | tar | zipfile | 内容一致 |
|---|---|---|---|---|
| 9 个 zip（GBK 名 4 个，其中 TJUPT 带 0x7075；UTF-8 标志 2 个，即两个源的 CMCT；纯 ASCII 名 3 个） | YYYY | YYYY | YYYY | 是 |
| 3 个 RAR4（含扩展名为 .zip 的 1 个） | YYYY | YYYY | - | 是 |

### 2.2 合成样本（`--with-synthetic`，只测能力，不提交）

| 合成包 | 内容 | 7z | tar | py7zr | zipfile |
|---|---|---|---|---|---|
| `synthetic-lzma2.7z` | 7z / LZMA2，中文名，子目录 | YYYY | **nnnn** `LZMA codec is unsupported` | YYYY | - |
| `synthetic-copy.7z` | 7z 仅存储 + 关闭头压缩（`-mx=0 -mhc=off`） | YYYY | YYYY | YYYY | - |
| `synthetic-gbk-names-7z.zip` | 7z 写的 GBK 名（`-mcu=off -mcp=936`），**附带 0x7075 字段** | YYYY | YYYY | - | YYYY |
| `synthetic-big5-names-7z.zip` | 7z 写的 Big5 名（`-mcp=950`），附带 0x7075 字段 | YYYY | YYYY | - | YYYY |
| `synthetic-gbk-names-raw.zip` | 标准库写的 GBK 原始字节名，**没有扩展字段**（与真实 GBK 包一致） | YYYY | YYYY | - | YYYY |
| `synthetic-big5-names-raw.zip` | 同上，Big5 名，含第二字节 0x5C 的「功」「許」 | **YnYn** 名字成乱码 | **YnYn** 名字乱码、解包失败 | - | YYYY |
| `synthetic-nested.zip` | UTF-8 名外层 zip，内含 1 个字幕 + 内层 zip + 内层 7z | YYYY | YYYY | - | YYYY |
| └ 内层 `inner.7z` | 深度 1 | YYYY | nnnn | YYYY | - |
| └ 内层 `inner.zip` | 深度 1（即 GBK raw 包） | YYYY | YYYY | - | YYYY |

解读：
- tar 失败的原因是 libarchive 编译时没带 LZMA，不是 7z 容器读不了。仅存储的 7z 能读，但 7z 默认会用 LZMA 压缩文件头，现实中的 7z 包 tar 一律读不了。
- 7z / tar 在 GBK 包上「对」，是因为系统代码页是 936。Big5 raw 包同时证明了两点：**代码页一换就错**，以及**0x7075 字段可以掩盖这个问题**（7-Zip 自己写的包带这个字段，所以没暴露）。真实样本里只有 SubHD TJUPT 包带 0x7075。
- tar 的列表输出按系统 ANSI 代码页编码（脚本记录为 `mbcs`），不是 UTF-8。7z 要加 `-sccUTF-8`，否则控制台输出按 OEM 代码页编码。

## §3 zip 文件名回转（验证结论）

算法（`scripts/archive_probe.py` 的 `decode_zip_member_name`，P4 照此实现）：

1. 有 UTF-8 标志（`flag_bits & 0x800`）→ 直接用。真实样本：CMCT 包。
2. 有 **0x7075 Info-ZIP Unicode Path** 扩展字段，并且字段里的 CRC32 等于原始名字节的 CRC32 → 用字段里的 UTF-8 名。真实样本：TJUPT 包。
3. 否则用 `orig_filename.encode("cp437")` 还原原始字节（cp437 覆盖 0–255，可以无损还原）。**必须用 `orig_filename`**：Windows 上 `ZipInfo` 构造时会把 `\` 换成 `/`，而 Big5 的第二字节可能是 0x5C。合成器第一版就踩了这个坑，写出的包已经坏了。
4. 依次试 utf-8 / gb18030 / big5，按以下规则打分：
   - 有替换字符、私用区字符或控制字符 → 0 分；
   - utf-8 严格解码成功 → 1 分；
   - gb18030 → 汉字落在 **GB2312** 里的比例；big5 → 汉字落在 Big5 里的比例。
   - 选分数最高的；**平分时选 gb18030**。
5. 全是 0 分 → 标为 `undecidable`，转人工，或参考同一包里其他成员的结果，不要静默返回乱码。
6. 解码之后再把 `\` 统一成 `/`，这个顺序不能反。

实测：

| 样本 | 名字数 | 结果 | 分数特征 |
|---|---|---|---|
| 真实 GBK 名，无 0x7075（3 个包） | 14 | 全部选 gb18030，正确 | 10 个名字 **gb18030 = big5 = 1.0**（GBK 字节当 Big5 也能解出常用繁体字），靠平分规则选对；4 个名字 big5 = 0 |
| 真实 0x7075（TJUPT） | 1 | 用字段；猜测结果也是 gb18030，与字段一致 | — |
| 真实 UTF-8 标志 / ASCII | 9 | 直接用 | — |
| 合成 GBK（7z 版、raw 版） | 4 | gb18030，正确 | 同样是 1.0 平分 |
| 合成 Big5（7z 版、raw 版） | 4 | big5，正确（含 0x5C 的「功」「許」） | gb18030 = 0（出现私用区字符） |

**弱点**（中）：GBK 和 Big5 常常同分，只能靠「平分选 GBK」，所以短的 Big5 名如果第二字节都 ≥ 0xA1，可能被误判成 GBK（样本里没有出现）。P4 的改进方向：按包投票（同一个包的名字编码基本一致）；可以把包内字幕正文的编码检测结果作为旁证；或者参考 MP 已有的 `charset_normalizer`，但它对短文本准不准**不确定**。

## §4 样本统计（真实样本按 sha256 去重：12 个；CMCT 包两个源字节相同，去掉 1 个）

| 项 | 结果 |
|---|---|
| 真实格式 | zip 8、RAR4 3、散装字幕 1；**7z 0、RAR5 0** |
| 扩展名与内容不符 | 1（`.zip` 实为 RAR4）；散装 `.ass` 实为 SSA 另计 |
| zip 成员名编码（不含目录项，24 个） | GBK（无标志、无 0x7075）14、UTF-8 标志 6、ASCII 3、0x7075 字段 1 → 需要回转的占 **58%** |
| RAR4 成员名 | 4/4 带 Unicode 标志 |
| 包内有子目录 | 1/11（CMCT：一层目录） |
| 包内有内层压缩包 | 0/11 |
| 字幕文件数 | 28 个（manifest 共 34 条，含重复包里的 6 条）；非字幕成员 1 个（`字幕说明.txt`，GBK） |
| 单包最多字幕数 | 8（Anitafayer：正片 + 访谈 + 2 段预告，各有简 / 繁） |
| 字幕编码 | UTF-8 带 BOM 19、GBK（gb18030）5、UTF-16 LE 带 BOM 2、UTF-8 无 BOM 1、纯 ASCII 1；**Big5 0** |
| 格式 | ass 14、srt 13、ssa 1（扩展名是 .ass） |
| 语言（manifest，按正文判断） | chs 16、cht 4、eng 3、chs+eng 5（cht 4 = 01 正片、03 / 04 预告、肥内；`02访谈_cht` 算在 chs 里） |
| 双语形式（字幕级） | 单语 23；同一事件内 `中文\N英文` 2（REDANDY、SWTYBLZ）；中英分成两组事件 3（CMCT 两个 ass 按 Style 分，CMCT srt 是同时间轴的两个条目） |
| 双语形式（包级） | 无外语 8；只有单文件双语 2；只有简中、英文分开的文件 1（IMBT cd1/cd2）；两种都有 1（CMCT） |
| 内容范围 | 正片 17、分段 4、花絮 / 预告 6、导演评论 1 |

**限制**：样本只有 3 部电影、12 个包。7z、RAR5、嵌套压缩包、Big5、剧集季包都**没有真实样本**，比例只能说明「这些情况确实存在」，不能代表总体分布。

**纯中文 ASS 误判验证**（海拉鲁 03 §3 缺陷 ①）：只抽对话正文（ASS 取 `Dialogue` 第 10 个字段，去掉 `{…}` 标签）后，所有纯中文 ASS 的拉丁行数是 0–1 行（占比 < 0.1%）；把文件头也算进去才会把它们判成双语。**结论：只看对话正文就能避免这个缺陷**（高）。简繁用约 90 对常用简繁不同字统计，样本里两类的命中分别是「简 2000+ / 繁 0」和「简 0 / 繁 2000+」，区分非常清楚（高；短字幕上的效果未测）。

## §5 manifest.json 字段

每个包一条，包里每个字幕文件一条。语言**按对话正文判断，不看 ASS 文件头和文件名**。由探针草稿加人工逐条核对得出，34 条全部为 `high`。

| 字段 | 取值 | 说明 |
|---|---|---|
| `archive` / `sha256` | 相对 `tests/fixtures/archives/` 的路径 / 文件 sha256 | 散装字幕也算一个「包」，`true_format = loose`，`member_path = null` |
| `true_format` / `extension_matches` | zip / rar4 / rar5 / 7z / loose；布尔或 null | 按魔数判断 |
| `duplicate_of` | null 或首次出现的包路径 | 字节完全相同（CMCT），统计时去重 |
| `bilingual_form` | none / single-file / separate-files / single-file+separate-files | 包级双语形式 |
| `non_subtitle_members` | 包内路径列表 | 如 `字幕说明.txt` |
| `member_path` | 正确解码后的包内路径（`/` 分隔） | P4 测回转结果用 |
| `name_encoding` | utf8-flag / unicode-path-extra / gb18030 / ascii / rar-unicode | 成员名的来源 |
| `encoding` | utf-8-sig / utf-8 / ascii / gb18030 / utf-16-le-bom | 字幕正文编码 |
| `format` | ass / ssa / srt | 按内容判断 |
| `language` | chs / cht / eng / chs+eng | `+` 连接，中文在前 |
| `bilingual` / `bilingual_layout` | 布尔；same-event / separate-events / null | 单文件双语的排列方式 |
| `content_scope` / `part` | feature / extra / commentary / part；cd1 / cd2 / null | 正片、花絮、导评、分段 |
| `confidence` / `note` | high / medium / low；中文备注 | 备注写清判断依据和陷阱 |

用户抽查的 5 条（2026-10-16 确认）：`02访谈_cht.ass`（实为 chs）、WiKi.rar `肥内提供中字.srt`（cht，UTF-16）、`4K适配HDR.zip` 里的 REDANDY.ass（RAR4，chs+eng same-event）、CMCT `导评字幕.srt`（commentary）、IMBT `cd1…eng.srt`（eng，part，混入一行 GBK）。

## §6 D015 最终推荐（交 C12 定稿）

**推荐方案**

| 格式 | 主力 | 备用 | 都没有时 |
|---|---|---|---|
| zip | **标准库 zipfile**，按 §3 自己回转文件名，逐个成员写盘（不用 `extractall`） | 不需要 | — |
| rar（RAR4 / RAR5） | **7z.exe** | **tar.exe**（Win10 1803 起系统自带，零安装） | 报「需要安装 7-Zip」 |
| 7z | **7z.exe** | **py7zr**（插件依赖） | 报「需要安装 7-Zip」 |

**探测顺序**（每个候选都要实际运行一次才算可用：7z 运行 `7z i`，tar 运行 `tar --version` 并检查输出含 libarchive；不比较文件名）：

1. 插件配置里填的路径
2. `shutil.which("7z" / "7za" / "7zz")`
3. `%ProgramFiles%\7-Zip\7z.exe`、`%ProgramFiles(x86)%\7-Zip\7z.exe`
4. Scoop：`%SCOOP%`、`~\scoop` 下的 `apps\7zip\current\7z.exe`（本机 Scoop 装在 `D:\Scoop`，靠第 2 步的 PATH 找到；不要写死盘符）
5. Chocolatey：`C:\ProgramData\chocolatey\bin\7z.exe`
6. tar：`shutil.which("tar")`，或固定位置 `%SystemRoot%\System32\tar.exe`
7. py7zr：`importlib.util.find_spec`

结果展示在界面上，格式如「rar：7-Zip 26.03（D:\Scoop\…）／7z：py7zr 1.1.4（备用）」。

**理由**
1. 7z.exe 是唯一在 zip / RAR4 / 7z 上都通过的外部工具，一个程序覆盖全部格式（§2）。
2. zip 不交给 7z / tar：它们按系统代码页解文件名，**中文 Windows 上碰巧对，换个环境就错**，遇到 Big5 名 tar 甚至解不开（§2.2）。标准库加回转在全部样本上正确，还能拿到原始字节和判断依据（§3）。
3. tar.exe 零安装，能解 RAR4，适合作 rar 的备用；但它**解不了常规 7z**，不能作为 7z 的备用（§2.2）。
4. **建议引入 py7zr**，只作 7z 的备用：它是 7z 唯一的零外部安装方案，且 cp314 wheel 齐全（§1）。代价是插件 requirements 会带进 9 个包（含 psutil、pycryptodomex），MP 升级 Python 时要有对应的 wheel。真实样本里 7z 是 0/12，所以也可以选择不引入、只提示安装 7-Zip。这是取舍，交 C12 决定。我的倾向是引入，并且导入失败时自动降级为「提示安装 7-Zip」，不影响插件加载。
5. 不用 rarfile：MP 环境里虽然有 rarfile 4.5，但它读取压缩成员时仍要调外部工具（据 03 §2 的记忆，未实测），价值等于直接调 7z / tar。不用 unar：没有必要，海拉鲁就是因为绑死 unar 才出的问题。

**调用细节**（P4 照做）
- 7z 列表：`7z l -slt -ba -sccUTF-8 <包>`。目录项的判断：zip / rar 看 `Folder = +`，**7z 格式没有 Folder 字段，看 `Attributes` 是否以 `D` 开头**（脚本第一版在这里出过错）。
- 7z 解包：`7z x -y -bd -sccUTF-8 -o<目录> <包>`。解包前先用列表做路径穿越检查；落盘后的文件名由 Python 用 Unicode API 读取。
- tar：`tar -tf` / `tar -xf <包> -C <目录>`。列表输出按 ANSI 代码页解码。
- 不经过 shell，参数用列表传递；中文路径直接传，实测没有问题。

## §7 回答 03 §9

| # | 问题 | 结论 |
|---|---|---|
| 2 | rarfile 是否需要外部工具 | **未实测**（D015 不用 rarfile）；MP 里装的是 rarfile 4.5 |
| 3 | MP 环境里有没有 rarfile / py7zr / charset 检测库 | rarfile 4.5、chardet 7.6.0、charset_normalizer 3.5.1 有；py7zr 没有（§1） |
| 4 | tar.exe 的版本，能否解 RAR5 / 7z / 中文名 | libarchive 3.8.4；7z（LZMA）不能；中文名依赖代码页，Big5 名的 zip 解包失败；RAR4 能解；**RAR5 没有样本，未测** |
| 5 | py7zr 在 3.14 + Windows 上有没有 wheel | 有，已装进 `.venv` 实测可用（§1） |
| 6 | 7-Zip 装好后 MP 进程能否找到 | 本机是 Scoop 安装，只在用户 PATH 上；MP 能找到是推测（§1） |
| 7 | 真实字幕包的分布 | §4 |
| 10 | 季包字幕数会不会超过 100 | **本次答不了**：没有剧集样本，电影包最多 8 个字幕 |

## §8 不确定项与后续

| # | 项 | 怎么补 |
|---|---|---|
| 1 | RAR5 没有真实样本（7-Zip 不能创建 RAR），7z / tar 对 RAR5 的支持只来自文档记忆 | 以后下载到 RAR5 包时放进 `tests/fixtures/archives/other/`，重跑探针 |
| 2 | 7z 真实样本为 0 | 同上 |
| 3 | MP 进程的 PATH 是否包含用户 PATH | P5 实机时在插件里记录 `shutil.which("7z")` |
| 4 | GBK / Big5 平分时判断短名字的可靠性 | P4 加按包投票，并补 Big5 真实样本 |
| 5 | 剧集季包规模（03 §9 #10） | P7 剧集阶段 |
| 6 | py7zr 是否引入 | C12 决定（§6 理由 4） |
| 7 | charset_normalizer 对短文件名 / 字幕正文的判断效果 | P4 可选对比 |

## §9 对 P3 / P4 的输入

1. 解包模块输入原包路径，输出清单。清单每项包括：包内路径（解码后）、原始名字节、名字来源（`name_encoding`）、大小、sha256；解包目录**保留目录结构**。
2. 编码检测顺序：BOM（含 UTF-16）→ 严格 UTF-8 → gb18030 / big5 按常用字比例取高者。没有 BOM 时不猜 UTF-16。英文文件里也可能混进一行 GBK（IMBT cd1）。
3. 语言判定只看对话正文。简繁按特征字比例判断。双语排列有 3 种：同一事件上下排、按 Style 分开的两组事件、SRT 同时间轴的两个条目。挑选和合成都要能识别这 3 种。
4. 挑选前先分出 `content_scope`：「导评 / commentary」「花絮 / 访谈 / 预告 / trailer」等词出现在文件名、目录名或包内 txt 里；`cd1 / cd2` 是分段，需要整套拼接或转人工。
5. 文件名里的语言标记只作弱参考，正文判断优先（§0 #7）。
6. manifest.json 是 P4 单测的正确答案：解包、名字回转、编码、语言、双语形式、内容范围都按它断言。
