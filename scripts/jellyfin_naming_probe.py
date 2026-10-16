"""
Jellyfin 外挂字幕命名与子目录识别探针（P2-D P2-jellyfin-naming）

用途：
    给 F6.6（两份双语字幕怎么命名才能区分）和 F6.7（原包放影片子文件夹会不会被误读）提供实测依据：
      1. build   在 tests/jellyfin-lib/Movies/ 下生成两部测试影片（Hebi Test A / B）和一组字幕变体：
                 A = 命名矩阵（语言码、标题段位置、default / forced / sdh 标志）；
                 B = 子文件夹（Subs/、subtitles/、.hebisubs/、hebisubs-archive/ 里放 zip 和 srt）
                     + 编码（UTF-8 / GBK / Big5 / UTF-16）+ 两份真实双语 ASS（从 fixtures 的 zip 只读取出）；
                 每个字幕的台词写明自己是哪个变体，客户端里一眼能认出来；同时写 _matrix.json。
      2. refresh 只刷新名为 HebiTest、且路径全部位于 tests/jellyfin-lib 下的媒体库（FullRefresh），轮询到流数量稳定。
      3. collect 只读：读出每部影片的外挂字幕流（Path、Language、Title、DisplayTitle、IsExternal、IsDefault、
                 IsForced、IsHearingImpaired、Codec），并逐条下载服务器转出的字幕文本，检查变体标签和测试短语
                 能不能找到（判断服务器端编码解得对不对）；输出报告和 Markdown 表。
    这是探针脚本，不是插件代码；P3/P4 定命名规则时参考结论，不直接复用。

适用情况：
    - Jellyfin 与本仓库在同一台 Windows 上（媒体库直接指向 tests/jellyfin-lib/Movies）。
    - 只写 tests/jellyfin-lib/（已 gitignore）和 tests/fixtures/jellyfin/_probe-report.json；fixtures 的 zip 只读。
    - Jellyfin API：除了对 HebiTest 库的 Refresh，全部是 GET；Refresh 之前先校验库名和路径。
    - 凭据只从环境变量 JELLYFIN_URL / JELLYFIN_API_KEY 读：先读进程环境，读不到再读当前用户的环境变量
      （注册表 HKCU\\Environment，VS Code 早于变量设置启动时进程里没有）。不打印、不落盘，报告里不写服务器地址。

如何使用（用仓库 .venv 的解释器，-I 隔离模式）：
    .venv\\Scripts\\python.exe -I scripts\\jellyfin_naming_probe.py build --ffmpeg D:\\jellyfin\\Server\\ffmpeg.exe
    （在 Jellyfin 控制台建好 HebiTest 库之后）
    .venv\\Scripts\\python.exe -I scripts\\jellyfin_naming_probe.py refresh
    .venv\\Scripts\\python.exe -I scripts\\jellyfin_naming_probe.py collect
    输出：
        tests/jellyfin-lib/Movies/Hebi Test A|B/      测试影片与字幕（不提交）
        tests/jellyfin-lib/_matrix.json              变体清单（不提交）
        tests/fixtures/jellyfin/_probe-report.json   实测报告（提交；路径相对仓库，无 URL / token）

依赖：
    标准库：urllib.request（调 Jellyfin REST API）、winreg（读用户级环境变量）、zipfile（读 fixtures 字幕包、
            生成测试 zip）、subprocess（调用 ffmpeg 生成测试视频）、re（ASS 时间轴平移）、json / argparse / pathlib / datetime
    外部程序：ffmpeg（用 Jellyfin 自带的那份，只在 build 时生成 3 分钟的空白测试视频）
"""

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

# ---------------------------------------------------------------- 路径与常量

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
LIBRARY_ROOT = REPOSITORY_ROOT / "tests" / "jellyfin-lib"          # 测试媒体库根（已 gitignore）
MOVIES_ROOT = LIBRARY_ROOT / "Movies"                               # Jellyfin 的 HebiTest 库指向这里
BUILD_CACHE_DIR = LIBRARY_ROOT / "_build"                           # 生成的空白视频缓存（不在 Movies 下，Jellyfin 看不到）
MATRIX_PATH = LIBRARY_ROOT / "_matrix.json"
REPORT_PATH = REPOSITORY_ROOT / "tests" / "fixtures" / "jellyfin" / "_probe-report.json"
FIXTURE_ARCHIVES_DIR = REPOSITORY_ROOT / "tests" / "fixtures" / "archives"

LIBRARY_NAME = "HebiTest"
MOVIE_A = "Hebi Test A"
MOVIE_B = "Hebi Test B"
VIDEO_SECONDS = 180

# 测试文本：简体短语用于 UTF-8 / GBK / UTF-16，繁体短语用于 Big5（Big5 编不了简体字）
SIMPLIFIED_PHRASE = "简体测试：检查编码与显示，骨门直说"
TRADITIONAL_PHRASE = "繁體測試：檢查編碼與顯示，臺灣說話"
ENGLISH_PHRASE = "English line: the quick brown fox"

# 两份真实双语 ASS（manifest 里 chs+eng 的两种排列方式）
REAL_BILINGUAL_SOURCES = {
    "CMCT": {
        "archive": "assrt/The.Shawshank.Redemption.1994.BluRay.1080p.x264.AC3-CMCT.zip",
        "member_suffix": ".简体&英文.ass",
        "layout": "separate-events（按 Style 分中、英两组事件）",
    },
    "SWTYBLZ": {
        "archive": "subhd/The.Shawshank.Redemption.1994.2160p.BluRay.x265.10bit.SDR.DTS-HD.MA.5.1-SWTYBLZ.zip",
        "member_suffix": ".zh.ass",
        "layout": "same-event（同一事件 中文\\N英文）",
    },
}


def now_text():
    """当前时刻，12 小时制带 AM/PM（项目日志规范）。"""
    return datetime.datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")


def relative_to_repository(path):
    """报告里统一写相对仓库的 / 分隔路径，不暴露本机目录结构以外的信息。"""
    try:
        return Path(path).resolve().relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError:
        return str(path)


def ensure_inside_library(path):
    """写文件前的护栏：目标必须在 tests/jellyfin-lib/ 里，否则直接退出。"""
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(LIBRARY_ROOT.resolve()):
        sys.exit(f"拒绝写入测试库以外的路径：{resolved}")
    return resolved


# ---------------------------------------------------------------- 变体矩阵

def build_variant_matrix():
    """
    返回变体清单。每个变体：id、目录（A/B）、相对影片目录的路径、类型、编码、要看什么。
    类型：srt / ass（自造）、ass-script-title（自造，Script Info 带 Title）、real-ass（真实双语）、zip（测试包）。
    """
    variants = []

    def add(variant_id, movie, relative_path, kind, purpose, encoding="utf-8", **extra):
        variants.append({
            "id": variant_id, "movie": movie, "relative_path": relative_path, "kind": kind,
            "encoding": encoding, "purpose": purpose, **extra,
        })

    a = MOVIE_A
    # A：语言码
    add("A01", a, f"{a}.srt", "srt", "不带任何后缀")
    add("A02", a, f"{a}.zh.srt", "srt", "ISO 639-1")
    add("A03", a, f"{a}.chi.srt", "srt", "ISO 639-2/B")
    add("A04", a, f"{a}.zho.srt", "srt", "ISO 639-2/T")
    add("A05", a, f"{a}.chs.srt", "srt", "非标准码 chs（海拉鲁写法）")
    add("A06", a, f"{a}.cht.srt", "srt", "非标准码 cht（海拉鲁写法）")
    add("A07", a, f"{a}.zh-CN.srt", "srt", "BCP 47 地区")
    add("A08", a, f"{a}.zh-Hans.srt", "srt", "BCP 47 简体书写")
    add("A09", a, f"{a}.zh-Hant.srt", "srt", "BCP 47 繁体书写")
    add("A10", a, f"{a}.chi&eng.srt", "srt", "双语组合（海拉鲁写法）")
    add("A11", a, f"{a}.简体&英文.srt", "srt", "双语组合（真实字幕包写法）")
    add("A12", a, f"{a}.eng.srt", "srt", "对照组：英文")
    add("A13", a, f"{a}.Chinese.srt", "srt", "语言英文全称")
    # A：标题段位置
    add("A20", a, f"{a}.CMCT.zh.srt", "srt", "标题在语言前")
    add("A21", a, f"{a}.zh.CMCT.srt", "srt", "标题在语言后")
    add("A22", a, f"{a}.简英-CMCT.zh.srt", "srt", "中文标题")
    add("A23", a, f"{a}.1 CMCT 简英.zh.srt", "srt", "带空格和序号的标题")
    add("A24", a, f"{a}.Hebi.CMCT.zh.srt", "srt", "标题里有点")
    add("A25", a, f"{a}.CMCT.zh-Hans.srt", "srt", "标题 + BCP 47")
    add("A26", a, f"{a}.CMCT.chi.srt", "srt", "标题 + 639-2/B")
    add("A27", a, f"{a}.SWTYBLZ.zh.ass", "ass", "与 A20 组成两份双语：同语言、不同标题")
    add("A28", a, f"{a}.CMCT.zh.ass", "ass", "与 A20 只差扩展名")
    add("A29", a, f"{a} - CMCT.zh.srt", "srt", "视频名后接 ' - ' 而不是 '.'")
    add("A30", a, f"{a}.FileTitle.zh.ass", "ass-script-title", "ASS 的 Script Info 带 Title，看谁覆盖谁",
        script_title="脚本内标题")
    # A：标志
    add("A40", a, f"{a}.CMCT.zh.default.srt", "srt", "default 在语言后")
    add("A41", a, f"{a}.CMCT.zh.forced.srt", "srt", "forced 在语言后")
    add("A42", a, f"{a}.CMCT.zh.sdh.srt", "srt", "sdh 在语言后")
    add("A43", a, f"{a}.CMCT.default.zh.srt", "srt", "default 在语言前（与 A40 同时带 default）")

    b = MOVIE_B
    # B：根目录编码与真实双语
    add("B01", b, f"{b}.UTF8.zh.srt", "srt", "UTF-8 无 BOM", encoding="utf-8")
    add("B02", b, f"{b}.GBK.zh.srt", "srt", "GBK", encoding="gbk")
    add("B03", b, f"{b}.BIG5.zh-Hant.srt", "srt", "Big5（繁体文本）", encoding="big5")
    add("B04", b, f"{b}.UTF16.zh.srt", "srt", "UTF-16 LE 带 BOM", encoding="utf-16")
    add("B05", b, f"{b}.CMCT.zh.ass", "real-ass", "真实双语 ASS：" + REAL_BILINGUAL_SOURCES["CMCT"]["layout"],
        encoding="utf-8-sig", source_key="CMCT")
    add("B06", b, f"{b}.SWTYBLZ.zh.ass", "real-ass", "真实双语 ASS：" + REAL_BILINGUAL_SOURCES["SWTYBLZ"]["layout"]
        + "；Script Info 有 Title: YYeTs", encoding="utf-8-sig", source_key="SWTYBLZ")
    add("B07", b, "Some.Release-GRP.chs.srt", "srt", "根目录、文件名不以视频名开头")
    # 第二轮补充：CMCT 原文件缺 [Script Info] 节头，ffprobe 报 Invalid data，Jellyfin 静默跳过（B05）；
    # B08 只在开头补一行节头，其余与 B05 相同
    add("B08", b, f"{b}.CMCT-fixed.zh.ass", "real-ass", "同 B05，只在开头补 [Script Info] 节头",
        encoding="utf-8-sig", source_key="CMCT", prepend_script_info=True)
    # B：子文件夹（F6.7）
    subfolders = [(1, "Subs", "Subs"), (2, "subtitles", "subtitles"),
                  (3, ".hebisubs", "dot-hebisubs"), (4, "hebisubs-archive", "hebisubs-archive")]
    for number, folder, tag in subfolders:
        add(f"B{number}1", b, f"{folder}/pkg-{tag}.zip", "zip", f"{folder}/ 里的 zip 包",
            member_name=f"Pack.Release-GRP.{tag}.chs.srt")
        add(f"B{number}2", b, f"{folder}/{b}.{tag}.zh.srt", "srt", f"{folder}/ 里以视频名开头的 srt")
        add(f"B{number}3", b, f"{folder}/Pack.Release-GRP.{tag}.chs.srt", "srt", f"{folder}/ 里包内原名的 srt")
    add("B45", b, f"hebisubs-archive/CMCT-pack/inner/{b}.deep.zh.srt", "srt", "两层嵌套目录、以视频名开头")
    return variants


def variant_label(variant):
    """字幕里显示的变体标签：变体号 + 文件名去掉视频名前缀后的部分。"""
    file_name = Path(variant["relative_path"]).name
    movie = variant["movie"]
    shown = file_name[len(movie):] if file_name.startswith(movie) else file_name
    folder = str(Path(variant["relative_path"]).parent).replace("\\", "/")
    if folder != ".":
        shown = f"{folder}/{shown}"
    prefix = "變體" if variant["encoding"] == "big5" else "变体"
    return f"{prefix} {variant['id']}：{shown}"


def variant_phrase(variant):
    return TRADITIONAL_PHRASE if variant["encoding"] == "big5" else SIMPLIFIED_PHRASE


# ---------------------------------------------------------------- 字幕内容生成

def make_srt_text(label, phrase):
    """单条 0:00.5–3:00 的 SRT：任何时间点切过来都能看到变体标签。"""
    return (f"1\r\n00:00:00,500 --> 00:03:00,000\r\n{label}\r\n{phrase} / {ENGLISH_PHRASE}\r\n\r\n")


def make_ass_text(label, phrase, script_title=None):
    """最小 ASS：一个 Default 样式、一条覆盖全片的事件；可选 Script Info 的 Title。"""
    title_line = f"Title: {script_title}\r\n" if script_title else ""
    return (
        "[Script Info]\r\n"
        f"{title_line}"
        "ScriptType: v4.00+\r\nPlayResX: 640\r\nPlayResY: 360\r\n\r\n"
        "[V4+ Styles]\r\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding\r\n"
        "Style: Default,Microsoft YaHei,26,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,2,1,"
        "2,20,20,20,1\r\n\r\n"
        "[Events]\r\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\r\n"
        f"Dialogue: 0,0:00:00.50,0:03:00.00,Default,,0,0,0,,{label}\\N{phrase}\\N{ENGLISH_PHRASE}\r\n"
    )


ASS_TIME_PATTERN = re.compile(r"^(\d+):(\d{2}):(\d{2})\.(\d{2})$")


def ass_time_to_seconds(text):
    match = ASS_TIME_PATTERN.match(text.strip())
    hours, minutes, seconds, centiseconds = (int(group) for group in match.groups())
    return hours * 3600 + minutes * 60 + seconds + centiseconds / 100


def seconds_to_ass_time(value):
    centiseconds_total = max(0, round(value * 100))
    hours, remainder = divmod(centiseconds_total, 360000)
    minutes, remainder = divmod(remainder, 6000)
    seconds, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


def shift_real_ass(text, label, anchor_target_seconds=5.0):
    """
    把真实双语 ASS 的时间轴整体前移：以开始时间最早的含英文对话为锚，挪到 anchor_target_seconds
    （取最早而不是文件里第一条：CMCT 这类按 Style 分组的文件先排完全部中文事件再排英文），
    让 3 分钟的测试视频里能看到双语台词；结束时间 ≤0 的事件丢掉。
    再在 [Events] 的 Format 行后插一条顶部（\\an8）标签，写明变体和平移量。
    """
    lines = text.splitlines()
    tag_pattern = re.compile(r"\{[^}]*\}")
    anchor_seconds = None
    style_name = None
    for line in lines:
        if line.startswith("Style:") and style_name is None:
            style_name = line.split(":", 1)[1].split(",", 1)[0].strip()
        if line.startswith("Dialogue:"):
            fields = line.split(",", 9)
            if re.search(r"[A-Za-z]{3,}", tag_pattern.sub("", fields[9])):
                start_seconds = ass_time_to_seconds(fields[1])
                anchor_seconds = start_seconds if anchor_seconds is None else min(anchor_seconds, start_seconds)
    shift = max(0.0, anchor_seconds - anchor_target_seconds)

    output_lines = []
    in_events = False
    for line in lines:
        if line.strip().lower() == "[events]":
            in_events = True
        if line.startswith("Dialogue:"):
            fields = line.split(",", 9)
            start = ass_time_to_seconds(fields[1]) - shift
            end = ass_time_to_seconds(fields[2]) - shift
            if end <= 0:
                continue
            fields[1], fields[2] = seconds_to_ass_time(start), seconds_to_ass_time(end)
            line = ",".join(fields)
        output_lines.append(line)
        if in_events and line.startswith("Format:"):
            output_lines.append(
                f"Dialogue: 9,0:00:00.00,0:03:00.00,{style_name},,0,0,0,,"
                f"{{\\an8\\fs14}}{label}（时间轴前移 {shift:.2f} 秒）")
            in_events = False
    return "\r\n".join(output_lines) + "\r\n", shift


def read_real_bilingual_ass(source_key):
    """从 fixtures 的 zip 里只读取出真实双语 ASS（两个包都是 UTF-8 BOM，成员名有 UTF-8 标志或纯 ASCII）。"""
    source = REAL_BILINGUAL_SOURCES[source_key]
    with zipfile.ZipFile(FIXTURE_ARCHIVES_DIR / source["archive"]) as archive:
        for info in archive.infolist():
            if info.filename.endswith(source["member_suffix"]):
                return archive.read(info).decode("utf-8-sig"), info.filename
    sys.exit(f"fixtures 里找不到 {source_key} 的双语 ASS")


# ---------------------------------------------------------------- build

def make_blank_video(ffmpeg_path):
    """用 ffmpeg 生成 3 分钟、640x360、深灰底、5 fps 的 H.264 + 静音 AAC mkv，只生成一次。"""
    output = ensure_inside_library(BUILD_CACHE_DIR / f"blank-{VIDEO_SECONDS}s.mkv")
    if output.exists():
        return output
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg_path, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"color=c=0x303030:s=640x360:r=5:d={VIDEO_SECONDS}",
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
        "-t", str(VIDEO_SECONDS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "30", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "32k", "-shortest", str(output),
    ]
    subprocess.run(command, check=True)
    return output


def write_variant(variant, movie_dir):
    """按变体类型生成文件；返回写入记录（路径、字节数、额外信息）。"""
    target = ensure_inside_library(movie_dir / variant["relative_path"])
    target.parent.mkdir(parents=True, exist_ok=True)
    label = variant_label(variant)
    phrase = variant_phrase(variant)
    record = {"label": label, "phrase": phrase}

    if variant["kind"] == "srt":
        target.write_bytes(make_srt_text(label, phrase).encode(variant["encoding"]))
    elif variant["kind"] in ("ass", "ass-script-title"):
        target.write_bytes(make_ass_text(label, phrase, variant.get("script_title")).encode(variant["encoding"]))
    elif variant["kind"] == "real-ass":
        original_text, member_name = read_real_bilingual_ass(variant["source_key"])
        if variant.get("prepend_script_info") and not original_text.lstrip().startswith("[Script Info]"):
            original_text = "[Script Info]\r\n" + original_text
            record["script_info_header_added"] = True
        shifted_text, shift = shift_real_ass(original_text, label)
        target.write_bytes(shifted_text.encode("utf-8-sig"))
        record.update({"source_archive": REAL_BILINGUAL_SOURCES[variant["source_key"]]["archive"],
                       "source_member": member_name, "shift_seconds": round(shift, 2)})
        record["phrase"] = None  # 真实字幕只检查标签
    elif variant["kind"] == "zip":
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(variant["member_name"], make_srt_text(label, phrase).encode("utf-8"))
    else:
        raise ValueError(variant["kind"])
    record["path"] = relative_to_repository(target)
    record["bytes"] = target.stat().st_size
    return record


def command_build(arguments):
    ffmpeg_path = arguments.ffmpeg or shutil.which("ffmpeg")
    if not ffmpeg_path or not Path(ffmpeg_path).exists():
        sys.exit("找不到 ffmpeg，请用 --ffmpeg 指定（例如 Jellyfin 自带的 D:\\jellyfin\\Server\\ffmpeg.exe）")
    blank_video = make_blank_video(ffmpeg_path)

    variants = build_variant_matrix()
    for movie in (MOVIE_A, MOVIE_B):
        movie_dir = ensure_inside_library(MOVIES_ROOT / movie)
        movie_dir.mkdir(parents=True, exist_ok=True)
        video_path = ensure_inside_library(movie_dir / f"{movie}.mkv")
        if not video_path.exists():
            shutil.copyfile(blank_video, video_path)

    for variant in variants:
        variant.update(write_variant(variant, MOVIES_ROOT / variant["movie"]))
        print(f"  {variant['id']:<4} {variant['bytes']:>7} B  {variant['path']}")

    MATRIX_PATH.write_text(json.dumps({"generated_at": now_text(), "variants": variants},
                                      ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[{now_text()}] 生成 {len(variants)} 个变体；视频 {blank_video.stat().st_size} B；"
          f"矩阵 {relative_to_repository(MATRIX_PATH)}")


# ---------------------------------------------------------------- Jellyfin API（只读 + HebiTest 刷新）

def read_credential(name):
    """先读进程环境变量，读不到再读当前用户的环境变量（HKCU\\Environment）。值只在内存里用。"""
    value = os.environ.get(name)
    if not value and sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                value, _ = winreg.QueryValueEx(key, name)
        except OSError:
            value = None
    if not value:
        sys.exit(f"环境变量 {name} 未设置")
    return value


class JellyfinClient:
    """最小 REST 客户端：token 只放在 Authorization 头里，错误信息只带路径不带主机和 token。"""

    def __init__(self):
        self.base_url = read_credential("JELLYFIN_URL").rstrip("/")
        self.api_key = read_credential("JELLYFIN_API_KEY")

    def request(self, method, path, params=None, want_json=True):
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, method=method)
        request.add_header("Authorization", f'MediaBrowser Token="{self.api_key}"')
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read()
                status = response.status
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"{method} {path} → HTTP {error.code}") from None
        except urllib.error.URLError as error:
            raise RuntimeError(f"{method} {path} → {error.reason}") from None
        if not want_json:
            return status, body
        return json.loads(body) if body else None

    def get(self, path, params=None):
        return self.request("GET", path, params)


def find_test_library(client):
    """找到 HebiTest 库并校验它的所有路径都在 tests/jellyfin-lib 下；不满足就退出（护栏）。"""
    folders = client.get("/Library/VirtualFolders")
    matches = [folder for folder in folders if folder.get("Name") == LIBRARY_NAME]
    if len(matches) != 1:
        sys.exit(f"没有找到唯一的媒体库 {LIBRARY_NAME}（现有：{[folder.get('Name') for folder in folders]}）")
    library = matches[0]
    locations = library.get("Locations") or []
    library_root = os.path.normcase(str(LIBRARY_ROOT.resolve()))
    for location in locations:
        if not os.path.normcase(str(Path(location).resolve())).startswith(library_root):
            sys.exit(f"{LIBRARY_NAME} 的路径不在 tests/jellyfin-lib 下，拒绝操作：{location}")
    if not locations:
        sys.exit(f"{LIBRARY_NAME} 没有配置路径")
    return library


def list_library_movies(client, library_id):
    result = client.get("/Items", {"ParentId": library_id, "Recursive": "true", "IncludeItemTypes": "Movie",
                                   "Fields": "MediaStreams,Path"})
    return result.get("Items", [])


def command_refresh(arguments):
    client = JellyfinClient()
    library = find_test_library(client)
    library_id = library["ItemId"]
    client.request("POST", f"/Items/{library_id}/Refresh", {
        "Recursive": "true", "MetadataRefreshMode": "FullRefresh", "ImageRefreshMode": "Default",
        "ReplaceAllMetadata": "false", "ReplaceAllImages": "false"}, want_json=False)
    print(f"[{now_text()}] 已请求刷新 {LIBRARY_NAME}（FullRefresh，递归），开始轮询")

    started = time.monotonic()
    previous_signature = None
    stable_rounds = 0
    while time.monotonic() - started < arguments.timeout:
        time.sleep(5)
        movies = list_library_movies(client, library_id)
        signature = tuple(sorted((movie.get("Path", ""), len(movie.get("MediaStreams") or [])) for movie in movies))
        stable_rounds = stable_rounds + 1 if signature == previous_signature and movies else 0
        previous_signature = signature
        summary = ", ".join(f"{Path(path).stem}:{count} 流" for path, count in signature) or "暂无影片"
        print(f"  {time.monotonic() - started:5.0f}s  {summary}")
        if stable_rounds >= 2 and time.monotonic() - started >= 15:
            print(f"[{now_text()}] 流数量连续稳定，刷新完成")
            return
    print(f"[{now_text()}] 超时 {arguments.timeout}s，结果可能不完整")


# ---------------------------------------------------------------- collect

STREAM_FIELDS = ["Index", "Type", "Codec", "Language", "Title", "DisplayTitle", "IsExternal", "IsDefault",
                 "IsForced", "IsHearingImpaired", "IsTextSubtitleStream", "SupportsExternalStream",
                 "LocalizedDefault", "LocalizedForced", "LocalizedExternal", "LocalizedHearingImpaired",
                 "LocalizedUndefined", "DeliveryMethod"]


def strip_query(url):
    """DeliveryUrl 可能带 api_key 之类的查询串，落盘前去掉。"""
    return url.split("?", 1)[0] if url else url


def fetch_server_subtitle(client, item_id, media_source_id, stream, variant):
    """GET 服务器转出的字幕文本，检查变体标签 / 测试短语是否完整（判断服务器端编码有没有解对）。"""
    extension = "ass" if (stream.get("Codec") or "").lower() in ("ass", "ssa") else "srt"
    path = f"/Videos/{item_id}/{media_source_id}/Subtitles/{stream['Index']}/0/Stream.{extension}"
    try:
        status, body = client.request("GET", path, want_json=False)
    except RuntimeError as error:
        return {"error": str(error)}
    text = body.decode("utf-8", errors="replace")
    label = variant["label"] if variant else None
    phrase = variant.get("phrase") if variant else None
    first_line = next((line for line in text.splitlines()
                       if ("变体" in line or "變體" in line or "\ufffd" in line)), None)
    return {
        "format": extension, "http_status": status, "bytes": len(body),
        "has_bom": body.startswith(b"\xef\xbb\xbf"),
        "label_found": (label in text) if label else None,
        "phrase_found": (phrase in text) if phrase else None,
        "replacement_chars": text.count("\ufffd"),
        "label_line": first_line[:200] if first_line else None,
    }


def command_collect(arguments):
    client = JellyfinClient()
    public_info = client.get("/System/Info/Public")
    library = find_test_library(client)
    library_id = library["ItemId"]
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))["variants"]
    variants_by_path = {os.path.normcase(str((REPOSITORY_ROOT / variant["path"]).resolve())): variant
                        for variant in matrix}

    # 库里所有条目（任何类型）：看子文件夹有没有被当成影片、文件夹或 extras
    all_items = client.get("/Items", {"ParentId": library_id, "Recursive": "true", "Fields": "Path"}).get("Items", [])
    items_report = [{"name": item.get("Name"), "type": item.get("Type"), "is_folder": item.get("IsFolder"),
                     "path": relative_to_repository(item["Path"]) if item.get("Path") else None}
                    for item in all_items]

    # 当前管理员的字幕偏好（解释默认选中哪条）；不记用户名
    users = client.get("/Users")
    admin = next((user for user in users if (user.get("Policy") or {}).get("IsAdministrator")), users[0])
    configuration = admin.get("Configuration") or {}
    user_preferences = {key: configuration.get(key) for key in
                        ("SubtitleMode", "SubtitleLanguagePreference", "PlayDefaultAudioTrack",
                         "RememberSubtitleSelections", "AudioLanguagePreference")}

    rows = []
    seen_paths = set()
    movies_report = []
    for movie in list_library_movies(client, library_id):
        # 用 API Key 调用时 /Items/{id} 必须带 userId（不带返回 HTTP 400，12.1.0 实测）
        item = client.get(f"/Items/{movie['Id']}", {"userId": admin["Id"], "Fields": "MediaStreams,MediaSources,Path"})
        media_source = (item.get("MediaSources") or [{}])[0]
        media_source_id = media_source.get("Id")
        try:
            playback = client.get(f"/Items/{movie['Id']}/PlaybackInfo", {"userId": admin["Id"]})
            playback_streams = {stream["Index"]: stream
                                for stream in (playback.get("MediaSources") or [{}])[0].get("MediaStreams", [])}
            default_subtitle_index = (playback.get("MediaSources") or [{}])[0].get("DefaultSubtitleStreamIndex")
        except RuntimeError as error:
            playback_streams, default_subtitle_index = {}, f"PlaybackInfo 失败：{error}"
        try:
            special_features = client.get(f"/Items/{movie['Id']}/SpecialFeatures", {"userId": admin["Id"]})
            special_feature_paths = [relative_to_repository(feature.get("Path", "")) for feature in special_features]
        except RuntimeError as error:
            special_feature_paths = f"读取失败：{error}"

        movies_report.append({
            "name": item.get("Name"), "path": relative_to_repository(item.get("Path", "")),
            "stream_count": len(item.get("MediaStreams") or []),
            "default_subtitle_stream_index": default_subtitle_index,
            "special_features": special_feature_paths,
        })
        for stream in item.get("MediaStreams") or []:
            if stream.get("Type") != "Subtitle":
                continue
            normalized_path = os.path.normcase(str(Path(stream["Path"]).resolve())) if stream.get("Path") else None
            variant = variants_by_path.get(normalized_path)
            if normalized_path:
                seen_paths.add(normalized_path)
            row = {"variant": variant["id"] if variant else None, "movie": item.get("Name"),
                   "path": relative_to_repository(stream["Path"]) if stream.get("Path") else None}
            row.update({field: stream.get(field) for field in STREAM_FIELDS if field in stream})
            playback_stream = playback_streams.get(stream.get("Index"), {})
            row["playback_delivery_method"] = playback_stream.get("DeliveryMethod")
            row["playback_delivery_url"] = strip_query(playback_stream.get("DeliveryUrl"))
            if stream.get("IsExternal"):
                row["server_text"] = fetch_server_subtitle(client, movie["Id"], media_source_id, stream, variant)
            rows.append(row)

    missing = [variant["id"] for path, variant in variants_by_path.items() if path not in seen_paths]
    report = {
        "generated_at": now_text(),
        "server": {"product": public_info.get("ProductName"), "version": public_info.get("Version")},
        "library": {"name": library["Name"], "collection_type": library.get("CollectionType"),
                    "locations": [relative_to_repository(location) for location in library.get("Locations", [])],
                    "library_options": {key: (library.get("LibraryOptions") or {}).get(key) for key in
                                        ("EnableRealtimeMonitor", "SaveLocalMetadata", "SaveSubtitlesWithMedia",
                                         "MetadataSavers", "DisabledSubtitleFetchers", "SubtitleFetcherOrder")}},
        "user_subtitle_preferences": user_preferences,
        "items": items_report,
        "movies": movies_report,
        "subtitle_streams": rows,
        "not_recognized": missing,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print_tables(report, matrix)
    print(f"[{now_text()}] 报告：{relative_to_repository(REPORT_PATH)}")


def print_tables(report, matrix):
    """终端打印 Markdown 表：每个变体一行，没被识别的也列出来。"""
    rows_by_variant = {row["variant"]: row for row in report["subtitle_streams"] if row.get("variant")}
    print(f"\nJellyfin {report['server']['version']}；用户字幕偏好：{report['user_subtitle_preferences']}")
    for movie in report["movies"]:
        print(f"- {movie['name']}：{movie['stream_count']} 个流，默认字幕 Index={movie['default_subtitle_stream_index']}，"
              f"extras={movie['special_features']}")
    print(f"- 库内条目：{[(item['type'], item['path']) for item in report['items']]}")
    print("\n| 变体 | 文件 | 识别 | Index | Language | Title | DisplayTitle | Def | Forced | HI | Codec | 服务器文本 |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for variant in matrix:
        row = rows_by_variant.get(variant["id"])
        file_name = variant["relative_path"]
        if not row:
            print(f"| {variant['id']} | `{file_name}` | 否 | | | | | | | | | |")
            continue
        server_text = row.get("server_text") or {}
        if "error" in server_text:
            server_summary = server_text["error"]
        else:
            server_summary = (f"标签{'✓' if server_text.get('label_found') else '✗'}"
                              + ("" if server_text.get("phrase_found") is None
                                 else f" 短语{'✓' if server_text.get('phrase_found') else '✗'}")
                              + (f" �×{server_text['replacement_chars']}" if server_text.get("replacement_chars") else ""))
        print(f"| {variant['id']} | `{file_name}` | 是 | {row.get('Index')} | {row.get('Language')} | {row.get('Title')} | "
              f"{row.get('DisplayTitle')} | {row.get('IsDefault')} | {row.get('IsForced')} | "
              f"{row.get('IsHearingImpaired')} | {row.get('Codec')} | {server_summary} |")
    unmatched = [row for row in report["subtitle_streams"] if not row.get("variant")]
    for row in unmatched:
        print(f"| ? | `{row.get('path')}` | 内嵌/未知 | {row.get('Index')} | {row.get('Language')} | {row.get('Title')} | "
              f"{row.get('DisplayTitle')} | | | | {row.get('Codec')} | |")


# ---------------------------------------------------------------- 入口

def main():
    parser = argparse.ArgumentParser(description="Jellyfin 外挂字幕命名与子目录识别探针")
    subcommands = parser.add_subparsers(dest="command", required=True)
    build_parser = subcommands.add_parser("build", help="生成测试影片与字幕变体")
    build_parser.add_argument("--ffmpeg", help="ffmpeg 可执行文件路径")
    refresh_parser = subcommands.add_parser("refresh", help="刷新 HebiTest 库并等待完成")
    refresh_parser.add_argument("--timeout", type=int, default=180)
    subcommands.add_parser("collect", help="只读收集外挂字幕流并输出报告")
    arguments = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    {"build": command_build, "refresh": command_refresh, "collect": command_collect}[arguments.command](arguments)


if __name__ == "__main__":
    main()
