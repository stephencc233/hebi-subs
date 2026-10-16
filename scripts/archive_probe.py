"""
字幕包解包工具链探针（P2-C P2-archive-tools）

用途：
    在 Windows 原生环境下实测解包工具链，并统计真实字幕包的特征，供 D015 定稿和 P4 写测试用：
      1. 探测外部工具（7-Zip、Windows 自带 tar.exe）和 Python 包（py7zr），每个候选实际运行一次确认可用；
      2. 对每个样本：用魔数判断真实格式（RAR4 / RAR5 也区分）、zip 成员名有没有 UTF-8 标志、
         成员数、目录层级、有没有内层压缩包；
      3. 每个工具 × 每个包：能不能列出、能不能解开、解出的中文文件名对不对、解出的内容是否一致；
      4. zip 文件名回转：没有 UTF-8 标志的成员名先按 cp437 编回原始字节，再依次试 utf-8 / gb18030 / big5；
      5. 每个字幕文件：编码、格式、对话正文里的文字统计（简 / 繁 / 英 / 日）、双语形式，打印前几行对话供人工核对。
    这是探针脚本，不是插件代码；P4 写解包模块时参考结论，不直接复用。

适用情况：
    - 离线运行，不联网；样本只读（开头和结尾各算一次 sha256 比对）。
    - 解包只写 tests/tmp/archive_probe/（已 gitignore），结束时默认删除。
    - --with-synthetic 会用 7z.exe 在同一个临时目录里合成样本库里缺少的格式
      （7z、GBK / Big5 文件名 zip、嵌套压缩包），只测工具能力，不计入样本统计。

如何使用（用仓库 .venv 的解释器，-I 隔离模式）：
    .venv\\Scripts\\python.exe -I scripts\\archive_probe.py --samples tests\\fixtures\\archives --with-synthetic
    .venv\\Scripts\\python.exe -I scripts\\archive_probe.py --samples tests\\fixtures\\archives --keep-tmp   保留解包目录
    输出：
        终端：工具探测、能力矩阵、每个字幕文件的统计与前几行对话
        tests/fixtures/archives/_probe-report.json   完整报告（路径相对仓库，提交作为证据）
        tests/tmp/manifest.draft.json               标注草稿（自动推断，人工核对后写成 manifest.json，不提交）
        若 tests/fixtures/archives/manifest.json 已存在，样本统计中的语言 / 双语部分以它为准

依赖：
    标准库：zipfile（读写 zip、取成员原始名）、struct / zlib（解析 zip 扩展字段、校验 CRC32）、
            subprocess（调用 7z.exe / tar.exe）、hashlib（sha256）、
            shutil（找可执行文件、删除临时目录）、re / unicodedata（对话正文统计）、json / argparse / pathlib / datetime
    外部程序（可选，找不到就跳过对应列）：7-Zip 的 7z.exe、Windows 自带 tar.exe（bsdtar / libarchive）
    Python 包（可选）：py7zr（只用于 7z 格式）
"""

import argparse
import ctypes
import datetime
import hashlib
import importlib.util
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import unicodedata
import zipfile
import zlib
from pathlib import Path

# ---------------------------------------------------------------- 路径与常量

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SAMPLES_DIR = REPOSITORY_ROOT / "tests" / "fixtures" / "archives"
TMP_ROOT = REPOSITORY_ROOT / "tests" / "tmp" / "archive_probe"
REPORT_PATH = DEFAULT_SAMPLES_DIR / "_probe-report.json"
DRAFT_MANIFEST_PATH = REPOSITORY_ROOT / "tests" / "tmp" / "manifest.draft.json"
MANIFEST_PATH = DEFAULT_SAMPLES_DIR / "manifest.json"

SUBTITLE_EXTENSIONS = {".ass", ".ssa", ".srt", ".vtt", ".sub", ".idx", ".sup", ".smi"}
SUBPROCESS_TIMEOUT_SECONDS = 120
DIALOGUE_PREVIEW_LINES = 8
MAX_NESTING_DEPTH = 2  # 内层压缩包最多再解两层（与 01 F5.2 一致）

# 压缩格式魔数（文件开头字节）；RAR4 与 RAR5 的签名只差第 7 字节
ARCHIVE_MAGIC_TABLE = [
    (b"Rar!\x1a\x07\x01\x00", "rar5"),
    (b"Rar!\x1a\x07\x00", "rar4"),
    (b"7z\xbc\xaf\x27\x1c", "7z"),
    (b"PK\x03\x04", "zip"),
    (b"PK\x05\x06", "zip"),  # 空 zip
    (b"\x1f\x8b", "gzip"),
]
EXTENSION_TO_FORMAT = {".zip": "zip", ".rar": "rar", ".7z": "7z", ".gz": "gzip"}

# 常用简繁不同字对（只收两边写法不同、且不会在另一方单独出现的字），用于按对话正文判断简体 / 繁体
SIMPLIFIED_TRADITIONAL_PAIRS = (
    "这這 说說 们們 来來 时時 会會 对對 过過 还還 没沒 个個 为為 让讓 话話 见見 点點 现現 开開 关關 "
    "听聽 问問 谁誰 东東 车車 长長 门門 间間 发發 经經 样樣 钱錢 爱愛 买買 卖賣 头頭 脸臉 给給 认認 "
    "记記 讲講 请請 谢謝 应應 该該 从從 无無 与與 当當 实實 进進 远遠 运運 动動 国國 学學 书書 写寫 "
    "语語 读讀 识識 电電 题題 觉覺 亲親 妈媽 岁歲 两兩 难難 吗嗎 饭飯 欢歡 气氣 军軍 战戰 机機 线線 "
    "场場 处處 帮幫 别別 带帶 万萬 却卻 将將 华華 乐樂 么麼 杀殺 灯燈 马馬 鱼魚 鸟鳥"
)
SIMPLIFIED_ONLY_CHARS = {pair[0] for pair in SIMPLIFIED_TRADITIONAL_PAIRS.split()}
TRADITIONAL_ONLY_CHARS = {pair[1] for pair in SIMPLIFIED_TRADITIONAL_PAIRS.split()}

ENGLISH_WORD_PATTERN = re.compile(r"[A-Za-z]{2,}")
ASS_OVERRIDE_TAG_PATTERN = re.compile(r"\{[^}]*\}")
SRT_TIMECODE_PATTERN = re.compile(r"^\s*\d{1,2}:\d{2}:\d{2}[,.]\d{1,3}\s*-->")


def now_12h() -> str:
    """当前本地时刻，12 小时制带 AM/PM（CLAUDE.md 代码规范）。"""
    return datetime.datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")


def relative_to_repository(path: Path) -> str:
    """报告里只写相对仓库根的路径（临时目录也一样），不暴露本机绝对路径。"""
    try:
        return path.resolve().relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError:
        return str(path)


def sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file_handle:
        for block in iter(lambda: file_handle.read(1 << 16), b""):
            digest.update(block)
    return digest.hexdigest()


def snapshot_fixture_hashes(samples_dir: Path) -> dict:
    """样本目录下所有文件的 sha256（除脚本自己写的报告），用于确认运行前后样本没被改动。"""
    return {
        relative_to_repository(path): sha256_of_file(path)
        for path in sorted(samples_dir.rglob("*"))
        if path.is_file() and path.name not in {"_probe-report.json", "manifest.json"}
    }


def windows_code_pages() -> dict:
    """系统 ANSI / OEM 代码页：决定 7z、tar 怎么解码 zip 里没有 UTF-8 标志的文件名（ctypes 调 kernel32）。"""
    try:
        return {"ansi": ctypes.windll.kernel32.GetACP(), "oem": ctypes.windll.kernel32.GetOEMCP()}
    except (AttributeError, OSError):
        return {"ansi": None, "oem": None}


def run_command(arguments: list, working_dir: Path | None = None) -> dict:
    """运行外部命令（不经过 shell），stdout / stderr 按字节返回，由调用方决定怎么解码。"""
    try:
        completed = subprocess.run(
            [str(argument) for argument in arguments],
            cwd=working_dir,
            capture_output=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )
        return {"returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"returncode": None, "stdout": b"", "stderr": str(error).encode("utf-8", "replace")}


def decode_console_bytes(raw: bytes) -> tuple:
    """外部程序输出：先试严格 UTF-8，失败再按系统 ANSI 代码页（本机 cp936）解码；返回 (文本, 用的编码)。"""
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("mbcs", errors="replace"), "mbcs"


def short_error(raw: bytes) -> str:
    text, _ = decode_console_bytes(raw)
    return " ".join(text.split())[:300]


# ---------------------------------------------------------------- 1. 工具探测


def sevenzip_candidate_paths() -> list:
    """7-Zip 候选清单：环境变量 → PATH → 常见安装位置。只收集路径，是否可用由实际运行决定。"""
    candidates = []
    configured = os.environ.get("HEBISUBS_7Z_PATH")
    if configured:
        candidates.append(("env HEBISUBS_7Z_PATH", configured))
    for program_name in ("7z", "7za", "7zz"):
        found = shutil.which(program_name)
        if found:
            candidates.append((f"PATH:{program_name}", found))
    common_roots = [
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
    ]
    for root in common_roots:
        candidates.append(("Program Files", str(Path(root) / "7-Zip" / "7z.exe")))
    scoop_roots = [os.environ.get("SCOOP"), str(Path.home() / "scoop"), r"D:\Scoop", r"C:\Scoop"]
    for root in filter(None, scoop_roots):
        candidates.append(("Scoop", str(Path(root) / "apps" / "7zip" / "current" / "7z.exe")))
    candidates.append(("Chocolatey", r"C:\ProgramData\chocolatey\bin\7z.exe"))
    # 去重（保留第一次出现的来源）
    seen, unique = set(), []
    for source, candidate in candidates:
        key = os.path.normcase(os.path.abspath(candidate))
        if key not in seen:
            seen.add(key)
            unique.append((source, candidate))
    return unique


def discover_archive_tools() -> dict:
    """探测全部候选，每个都实际运行版本命令；返回 {tools: 可用工具, candidates: 全部候选的检测记录}。"""
    candidate_records, tools = [], {}

    for source, candidate in sevenzip_candidate_paths():
        record = {"tool": "7z", "source": source, "path": candidate, "exists": Path(candidate).is_file()}
        if record["exists"]:
            result = run_command([candidate, "i"])
            first_line = next((line for line in decode_console_bytes(result["stdout"])[0].splitlines() if line.strip()), "")
            record.update(returncode=result["returncode"], version=first_line.strip())
            record["usable"] = result["returncode"] == 0 and "7-Zip" in first_line
            if record["usable"] and "7z" not in tools:
                tools["7z"] = {"path": candidate, "version": first_line.strip(), "source": source}
        candidate_records.append(record)

    tar_path = shutil.which("tar")
    record = {"tool": "tar", "source": "PATH:tar", "path": tar_path, "exists": bool(tar_path)}
    if tar_path:
        result = run_command([tar_path, "--version"])
        version_line = decode_console_bytes(result["stdout"])[0].strip()
        record.update(returncode=result["returncode"], version=version_line)
        record["usable"] = result["returncode"] == 0 and "libarchive" in version_line
        if record["usable"]:
            tools["tar"] = {"path": tar_path, "version": version_line, "source": "PATH:tar"}
    candidate_records.append(record)

    record = {"tool": "py7zr", "source": "import", "path": None, "exists": importlib.util.find_spec("py7zr") is not None}
    if record["exists"]:
        import py7zr  # 只在探测到时导入；没装就整列跳过

        record.update(version=py7zr.__version__, usable=True)
        tools["py7zr"] = {"path": None, "version": py7zr.__version__, "source": "import"}
    candidate_records.append(record)

    tools["zipfile"] = {"path": None, "version": f"Python {sys.version.split()[0]} 标准库", "source": "stdlib"}
    return {"tools": tools, "candidates": candidate_records}


# ---------------------------------------------------------------- 2. 魔数判格式


def detect_archive_format(path: Path) -> str:
    """看文件开头字节判断真实格式；不是压缩包时按内容猜字幕类型（loose-*）。"""
    with open(path, "rb") as file_handle:
        head = file_handle.read(64)
    for magic, format_name in ARCHIVE_MAGIC_TABLE:
        if head.startswith(magic):
            return format_name
    return "loose"


def extension_matches_format(path: Path, true_format: str) -> bool | None:
    expected = EXTENSION_TO_FORMAT.get(path.suffix.lower())
    if expected is None:
        return None if true_format == "loose" else False
    if expected == "rar":
        return true_format in {"rar4", "rar5"}
    return expected == true_format


# ---------------------------------------------------------------- 3. zip 文件名回转


def is_in_gb2312(character: str) -> bool:
    """能用 GB2312 编码（两字节都 ≥0xA1）= 简体常用字表里的字；GBK 扩展区的生僻字不算。"""
    try:
        return len(character.encode("gb2312")) == 2
    except UnicodeEncodeError:
        return False


def is_in_big5(character: str) -> bool:
    try:
        return len(character.encode("big5")) == 2
    except UnicodeEncodeError:
        return False


def score_decoded_name(text: str, encoding: str) -> float:
    """解码结果像不像正常文本，分数 0–1。

    规则：有替换字符 / 私用区 / 控制字符 → 0；纯 ASCII → 1；
    其余看汉字落在该编码「常用字表」里的比例（gb18030 → GB2312，big5 → Big5），utf-8 能严格解出就给 1。
    关键点：GBK 字节被当成 Big5 往往也能「解码成功」，所以不能只看成功与否；
    Big5 的第二字节有 0x40–0x7E，当成 GBK 解会落进 GBK 扩展区（不在 GB2312 里），比例就会掉下来。
    """
    if any(ch == "\ufffd" or 0xE000 <= ord(ch) <= 0xF8FF or unicodedata.category(ch) == "Cc" for ch in text):
        return 0.0
    han_characters = [ch for ch in text if "\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf"]
    if not han_characters:
        return 1.0 if all(ord(ch) < 0x80 for ch in text) else 0.5
    if encoding == "utf-8":
        return 1.0
    checker = is_in_gb2312 if encoding == "gb18030" else is_in_big5
    return sum(1 for ch in han_characters if checker(ch)) / len(han_characters)


def parse_zip_extra_fields(extra: bytes) -> dict:
    """zip 扩展字段：{header_id: 数据}。0x7075 = Info-ZIP Unicode Path（版本 1 字节 + 原始名 CRC32 4 字节 + UTF-8 名）。"""
    fields, offset = {}, 0
    while offset + 4 <= len(extra):
        header_id, size = struct.unpack_from("<HH", extra, offset)
        fields[header_id] = extra[offset + 4: offset + 4 + size]
        offset += 4 + size
    return fields


def decode_zip_member_name(info: zipfile.ZipInfo) -> dict:
    """成员名回转：返回原始字节、扩展字段、各候选解码与分数、最终选择。

    优先级：UTF-8 标志（flag 0x800）→ 0x7075 Unicode 路径字段（CRC 与原始名一致才信）→ 回转猜测。
    zipfile 对没有 UTF-8 标志的名字一律按 cp437 解码；cp437 覆盖 0–255 全部字节，
    所以 orig_filename.encode("cp437") 能无损还原原始字节。
    注意要用 orig_filename：Windows 上 ZipInfo 构造时会把 '\\' 换成 '/'，而 Big5 的第二字节可能正是 0x5C。
    """
    extra_fields = parse_zip_extra_fields(info.extra)
    base = {"utf8_flag": bool(info.flag_bits & 0x800), "extra_field_ids": [hex(key) for key in extra_fields]}
    if base["utf8_flag"]:
        raw = info.orig_filename.encode("utf-8")
        return {**base, "raw_hex": raw.hex(), "candidates": {}, "heuristic_choice": None,
                "chosen_encoding": "utf8-flag", "decoded": info.orig_filename.replace("\\", "/")}
    raw = info.orig_filename.encode("cp437")
    if all(byte < 0x80 for byte in raw):
        return {**base, "raw_hex": raw.hex(), "candidates": {}, "heuristic_choice": None,
                "chosen_encoding": "ascii", "decoded": raw.decode("ascii").replace("\\", "/")}
    unicode_path = None
    if 0x7075 in extra_fields and len(extra_fields[0x7075]) > 5:
        field = extra_fields[0x7075]
        if struct.unpack_from("<I", field, 1)[0] == zlib.crc32(raw):
            unicode_path = field[5:].decode("utf-8", errors="replace")
    candidates = {}
    for encoding in ("utf-8", "gb18030", "big5"):
        try:
            text = raw.decode(encoding)
            candidates[encoding] = {"text": text, "score": round(score_decoded_name(text, encoding), 3)}
        except UnicodeDecodeError:
            candidates[encoding] = {"text": None, "score": 0.0}
    # 选择顺序：utf-8 严格成功优先；否则取分数最高的，分数相同时 gb18030 优先（简中样本占多数）
    if candidates["utf-8"]["score"] == 1.0:
        heuristic_choice = "utf-8"
    else:
        heuristic_choice = max(("gb18030", "big5"), key=lambda name: (candidates[name]["score"], name == "gb18030"))
    heuristic_text = (candidates[heuristic_choice]["text"] or info.orig_filename).replace("\\", "/")
    # 回转猜测结果单独保留（heuristic_choice），用于在带 0x7075 的合成样本上也能检验猜测算法
    if unicode_path is not None:
        return {**base, "raw_hex": raw.hex(), "candidates": candidates, "heuristic_choice": heuristic_choice,
                "heuristic_matches_unicode_path": heuristic_text == unicode_path.replace("\\", "/"),
                "chosen_encoding": "unicode-path-extra", "decoded": unicode_path.replace("\\", "/")}
    if candidates[heuristic_choice]["score"] == 0.0:
        # 三种都不像正常文本：标为无法判断（P4 应转人工或按整包其他成员投票），不静默返回乱码
        return {**base, "raw_hex": raw.hex(), "candidates": candidates, "heuristic_choice": None,
                "chosen_encoding": "undecidable", "decoded": info.orig_filename.replace("\\", "/")}
    return {**base, "raw_hex": raw.hex(), "candidates": candidates, "heuristic_choice": heuristic_choice,
            "chosen_encoding": heuristic_choice, "decoded": heuristic_text}


def read_rar4_name_flags(path: Path) -> list:
    """RAR4 文件头逐块读：HEAD_TYPE 0x74 = 文件头，HEAD_FLAGS 0x200 = 文件名带 Unicode 编码（不依赖系统代码页）。

    块结构：CRC(2) TYPE(1) FLAGS(2) SIZE(2)；文件头里 PACK_SIZE 在 +7，NAME_SIZE 在 +26，
    FLAGS 0x100 时有 8 字节高位大小，名字从 +32（或 +40）开始。只读标志，不解压。
    """
    data, flags_found, position = path.read_bytes(), [], 7
    while position + 7 <= len(data):
        _, header_type, header_flags, header_size = struct.unpack_from("<HBHH", data, position)
        if header_type == 0x73:  # 主头
            position += header_size
        elif header_type == 0x74:  # 文件头
            pack_size = struct.unpack_from("<I", data, position + 7)[0]
            flags_found.append(bool(header_flags & 0x200))
            position += header_size + pack_size
        else:
            break
    return flags_found


def path_is_unsafe(member_path: str) -> bool:
    """路径穿越 / 绝对路径检查：有盘符、以 / 开头或含 .. 段就拒绝解包。"""
    normalized = member_path.replace("\\", "/")
    return normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized) is not None or ".." in normalized.split("/")


# ---------------------------------------------------------------- 4. 各工具的列表与解包


def list_files_on_disk(root: Path) -> dict:
    """解包目录里的全部文件：{相对路径(NFC): sha256}。"""
    return {
        unicodedata.normalize("NFC", path.relative_to(root).as_posix()): sha256_of_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def sevenzip_list(tool_path: str, archive: Path) -> dict:
    """7z l -slt：-sccUTF-8 让控制台输出强制为 UTF-8（否则按 OEM 代码页输出，中文会乱码）。"""
    result = run_command([tool_path, "l", "-slt", "-ba", "-sccUTF-8", archive])
    entries, current = [], {}
    for line in result["stdout"].decode("utf-8", errors="replace").splitlines():
        if not line.strip():
            if current:
                entries.append(current)
                current = {}
            continue
        key, separator, value = line.partition(" = ")
        if separator:
            current[key.strip()] = value
    if current:
        entries.append(current)
    # 目录项：zip / rar 用 Folder = +，7z 格式没有 Folder 字段，要看 Attributes 以 D 开头
    files = [entry["Path"].replace("\\", "/") for entry in entries
             if "Path" in entry and entry.get("Folder") != "+" and not entry.get("Attributes", "").startswith("D")]
    return {"ok": result["returncode"] == 0 and bool(entries), "files": files,
            "error": None if result["returncode"] == 0 else short_error(result["stderr"] or result["stdout"])}


def sevenzip_extract(tool_path: str, archive: Path, output_dir: Path) -> dict:
    result = run_command([tool_path, "x", "-y", "-bd", "-sccUTF-8", f"-o{output_dir}", archive])
    return {"ok": result["returncode"] == 0,
            "error": None if result["returncode"] == 0 else short_error(result["stderr"] or result["stdout"])}


def tar_list(tool_path: str, archive: Path) -> dict:
    result = run_command([tool_path, "-tf", archive])
    text, used_encoding = decode_console_bytes(result["stdout"])
    files = [line.replace("\\", "/") for line in text.splitlines() if line.strip() and not line.endswith(("/", "\\"))]
    return {"ok": result["returncode"] == 0 and bool(files), "files": files, "stdout_encoding": used_encoding,
            "error": None if result["returncode"] == 0 else short_error(result["stderr"])}


def tar_extract(tool_path: str, archive: Path, output_dir: Path) -> dict:
    result = run_command([tool_path, "-xf", archive, "-C", output_dir])
    return {"ok": result["returncode"] == 0, "error": None if result["returncode"] == 0 else short_error(result["stderr"])}


def zipfile_list(archive: Path) -> dict:
    try:
        with zipfile.ZipFile(archive) as zip_file:
            files = [decode_zip_member_name(info)["decoded"] for info in zip_file.infolist() if not info.is_dir()]
        return {"ok": True, "files": files, "error": None}
    except (zipfile.BadZipFile, OSError) as error:
        return {"ok": False, "files": [], "error": str(error)}


def zipfile_extract(archive: Path, output_dir: Path) -> dict:
    """用回转后的名字逐个成员写盘（不用 extractall，它会用 cp437 乱码名）。"""
    try:
        with zipfile.ZipFile(archive) as zip_file:
            for info in zip_file.infolist():
                if info.is_dir():
                    continue
                decoded = decode_zip_member_name(info)["decoded"]
                if path_is_unsafe(decoded):
                    return {"ok": False, "error": f"不安全的成员路径：{decoded}"}
                target = output_dir / decoded
                target.parent.mkdir(parents=True, exist_ok=True)
                with zip_file.open(info) as source, open(target, "wb") as destination:
                    shutil.copyfileobj(source, destination)
        return {"ok": True, "error": None}
    except (zipfile.BadZipFile, OSError, NotImplementedError) as error:
        return {"ok": False, "error": str(error)}


def py7zr_list(archive: Path) -> dict:
    import py7zr

    try:
        with py7zr.SevenZipFile(archive, mode="r") as seven_zip:
            files = [entry.filename.replace("\\", "/") for entry in seven_zip.list() if not entry.is_directory]
        return {"ok": True, "files": files, "error": None}
    except Exception as error:  # py7zr 的异常类型较多，探针里统一记录
        return {"ok": False, "files": [], "error": f"{type(error).__name__}: {error}"}


def py7zr_extract(archive: Path, output_dir: Path) -> dict:
    import py7zr

    try:
        with py7zr.SevenZipFile(archive, mode="r") as seven_zip:
            seven_zip.extractall(path=output_dir)
        return {"ok": True, "error": None}
    except Exception as error:
        return {"ok": False, "error": f"{type(error).__name__}: {error}"}


def tool_supports_format(tool_name: str, true_format: str) -> bool:
    """哪些组合要测：zipfile 只测 zip，py7zr 只测 7z，7z / tar 全测。"""
    if tool_name == "zipfile":
        return true_format == "zip"
    if tool_name == "py7zr":
        return true_format == "7z"
    return true_format != "loose"


def run_tool_matrix(tools: dict, archive: Path, true_format: str, expected_files: list, work_dir: Path) -> dict:
    """每个工具：列出 → 安全检查 → 解开 → 比较落盘文件名与正确名称。"""
    expected_set = {unicodedata.normalize("NFC", name) for name in expected_files}
    results = {}
    for tool_name, tool_info in tools.items():
        if not tool_supports_format(tool_name, true_format):
            results[tool_name] = {"status": "不适用"}
            continue
        output_dir = work_dir / tool_name
        output_dir.mkdir(parents=True, exist_ok=True)
        if tool_name == "7z":
            listing = sevenzip_list(tool_info["path"], archive)
        elif tool_name == "tar":
            listing = tar_list(tool_info["path"], archive)
        elif tool_name == "zipfile":
            listing = zipfile_list(archive)
        else:
            listing = py7zr_list(archive)
        unsafe = [name for name in listing["files"] if path_is_unsafe(name)]
        if unsafe:
            results[tool_name] = {"status": "拒绝解包", "unsafe_paths": unsafe}
            continue
        if tool_name == "7z":
            extraction = sevenzip_extract(tool_info["path"], archive, output_dir)
        elif tool_name == "tar":
            extraction = tar_extract(tool_info["path"], archive, output_dir)
        elif tool_name == "zipfile":
            extraction = zipfile_extract(archive, output_dir)
        else:
            extraction = py7zr_extract(archive, output_dir)
        on_disk = list_files_on_disk(output_dir)
        listed_set = {unicodedata.normalize("NFC", name) for name in listing["files"]}
        results[tool_name] = {
            "list_ok": listing["ok"],
            "list_names_ok": listing["ok"] and listed_set == expected_set,
            "extract_ok": extraction["ok"] and bool(on_disk),
            "disk_names_ok": set(on_disk) == expected_set,
            "files_on_disk": len(on_disk),
            "disk_names": sorted(on_disk) if set(on_disk) != expected_set else None,
            "listed_names": sorted(listed_set) if listed_set != expected_set else None,
            "content_sha256": sorted(on_disk.values()),
            "list_error": listing.get("error"),
            "extract_error": extraction.get("error"),
            "stdout_encoding": listing.get("stdout_encoding"),
        }
    # 各工具解出的内容是否一致（与文件名无关：比较 sha256 多重集合）
    content_sets = {name: result["content_sha256"] for name, result in results.items()
                    if result.get("extract_ok")}
    distinct = {tuple(values) for values in content_sets.values()}
    for result in results.values():
        result.pop("content_sha256", None)
    return {"by_tool": results, "content_consistent": len(distinct) <= 1, "tools_compared": sorted(content_sets)}


# ---------------------------------------------------------------- 5. 字幕内容分析


def detect_text_encoding(raw: bytes) -> tuple:
    """字幕文件编码：BOM → 严格 UTF-8 → gb18030 / big5 按常用字比例取高者。返回 (编码名, 文本)。

    不靠「解码成不成功」区分 GBK 和 Big5（Big5 字节当 GB18030 解几乎总能成功），
    而是看解出来的汉字落在 GB2312 / Big5 常用字表里的比例。没有 BOM 时不猜 UTF-16。
    """
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig", raw[3:].decode("utf-8", errors="replace")
    if raw.startswith(b"\xff\xfe"):
        return "utf-16-le-bom", raw[2:].decode("utf-16-le", errors="replace")
    if raw.startswith(b"\xfe\xff"):
        return "utf-16-be-bom", raw[2:].decode("utf-16-be", errors="replace")
    try:
        return "utf-8", raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    scores = {}
    for encoding, checker in (("gb18030", is_in_gb2312), ("big5", is_in_big5)):
        text = raw.decode(encoding, errors="replace")
        han = [ch for ch in text if "\u4e00" <= ch <= "\u9fff"]
        replacement_ratio = text.count("\ufffd") / max(len(text), 1)
        common_ratio = sum(1 for ch in han if checker(ch)) / max(len(han), 1)
        scores[encoding] = (common_ratio - replacement_ratio * 10, text)
    chosen = max(scores, key=lambda name: scores[name][0])
    return chosen, scores[chosen][1]


def detect_subtitle_format(text: str) -> str:
    head = text[:4000].lower()
    if "[script info]" in head or "[v4+ styles]" in head or "[v4 styles]" in head:
        return "ass" if ("v4.00+" in head or "[v4+ styles]" in head) else "ssa"
    if head.lstrip().startswith("webvtt"):
        return "vtt"
    if "-->" in head:
        return "srt"
    return "unknown"


def extract_dialogue_events(text: str, subtitle_format: str) -> list:
    """只取对话正文：每个事件 = {style, lines}。ASS 取 Dialogue 第 10 个字段，去掉 {…} 标签，按 \\N 拆行；
    矢量绘图（\\p1 等）整条跳过；SRT 跳过序号和时间轴行。不看 ASS 文件头（Style 名、字体名会冒充英文）。"""
    events = []
    if subtitle_format in {"ass", "ssa"}:
        for line in text.splitlines():
            if not line.startswith("Dialogue:"):
                continue
            fields = line[len("Dialogue:"):].split(",", 9)
            if len(fields) < 10:
                continue
            body = fields[9]
            if re.search(r"\\p[1-9]", body):
                continue
            body = ASS_OVERRIDE_TAG_PATTERN.sub("", body).replace("\\n", "\\N").replace("\\h", " ")
            lines = [part.strip() for part in body.split("\\N") if part.strip()]
            if lines:
                events.append({"style": fields[3].strip(), "lines": lines})
    else:
        for block in re.split(r"\r?\n\s*\r?\n", text):
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            lines = [line for line in lines if not line.isdigit() and not SRT_TIMECODE_PATTERN.match(line)]
            lines = [re.sub(r"<[^>]+>", "", line) for line in lines]
            lines = [line for line in lines if line]
            if lines:
                events.append({"style": None, "lines": lines})
    return events


def classify_text_line(line: str) -> str:
    """一行对话的主要文字：han / latin / kana / hangul / other。"""
    counts = {"han": 0, "latin": 0, "kana": 0, "hangul": 0}
    for ch in line:
        if "\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf":
            counts["han"] += 1
        elif "\u3040" <= ch <= "\u30ff":
            counts["kana"] += 1
        elif "\uac00" <= ch <= "\ud7af":
            counts["hangul"] += 1
        elif ch.isascii() and ch.isalpha():
            counts["latin"] += 1
    if counts["kana"] >= 2:
        return "kana"
    if counts["hangul"] >= 2:
        return "hangul"
    if counts["han"] >= 1 and counts["han"] * 3 >= counts["latin"]:
        return "han"
    if len(ENGLISH_WORD_PATTERN.findall(line)) >= 1:
        return "latin"
    return "other"


def analyze_subtitle_bytes(raw: bytes) -> dict:
    """编码、格式、对话统计、建议语言标签与双语形式（建议值，manifest 以人工核对为准）。"""
    encoding, text = detect_text_encoding(raw)
    subtitle_format = detect_subtitle_format(text)
    events = extract_dialogue_events(text, subtitle_format)
    all_lines = [line for event in events for line in event["lines"]]
    line_kinds = [classify_text_line(line) for line in all_lines]
    kind_counts = {kind: line_kinds.count(kind) for kind in ("han", "latin", "kana", "hangul", "other")}
    han_text = "".join(line for line, kind in zip(all_lines, line_kinds) if kind == "han")
    simplified_hits = sum(1 for ch in han_text if ch in SIMPLIFIED_ONLY_CHARS)
    traditional_hits = sum(1 for ch in han_text if ch in TRADITIONAL_ONLY_CHARS)

    # 同一事件里既有汉字行又有拉丁行 → 同事件上下排的双语
    mixed_events = sum(
        1 for event in events
        if {"han", "latin"} <= {classify_text_line(line) for line in event["lines"]}
    )
    # 按 Style 统计主要文字（ASS 常见「中文样式 + 英文样式」分开的双语）
    style_kinds = {}
    for event in events:
        for line in event["lines"]:
            style_kinds.setdefault(event["style"], {}).setdefault(classify_text_line(line), 0)
            style_kinds[event["style"]][classify_text_line(line)] += 1

    total = max(len(all_lines), 1)
    has_chinese = kind_counts["han"] / total >= 0.15
    has_english = kind_counts["latin"] / total >= 0.15
    has_japanese = kind_counts["kana"] / total >= 0.15
    chinese_variant = None
    if has_chinese:
        chinese_variant = "cht" if traditional_hits > simplified_hits * 2 else "chs"
    parts = [part for part, present in ((chinese_variant, has_chinese), ("eng", has_english), ("jpn", has_japanese))
             if present and part]
    suggested_language = "+".join(parts) if parts else "unknown"
    bilingual = len(parts) >= 2
    if not bilingual:
        layout = None
    elif mixed_events / max(len(events), 1) >= 0.3:
        layout = "same-event"
    else:
        layout = "separate-events"

    preview_step = max(len(events) // DIALOGUE_PREVIEW_LINES, 1)
    preview = [" / ".join(event["lines"]) for event in events[::preview_step][:DIALOGUE_PREVIEW_LINES]]
    return {
        "encoding": encoding,
        "format": subtitle_format,
        "events": len(events),
        "dialogue_lines": len(all_lines),
        "line_kinds": kind_counts,
        "simplified_hits": simplified_hits,
        "traditional_hits": traditional_hits,
        "mixed_han_latin_events": mixed_events,
        "style_kinds": {str(style): counts for style, counts in style_kinds.items()} if subtitle_format in {"ass", "ssa"} else None,
        "suggested_language": suggested_language,
        "suggested_bilingual": bilingual,
        "suggested_layout": layout,
        "dialogue_preview": preview,
    }


# ---------------------------------------------------------------- 6. 合成样本（只测工具能力）

SYNTHETIC_SRT_TEMPLATE = "1\r\n00:00:01,000 --> 00:00:02,000\r\n{line}\r\n\r\n2\r\n00:00:03,000 --> 00:00:04,000\r\nsynthetic sample\r\n"


def write_synthetic_sources(source_root: Path, relative_names: list) -> None:
    for relative_name in relative_names:
        target = source_root / relative_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(SYNTHETIC_SRT_TEMPLATE.format(line=Path(relative_name).stem).encode("utf-8-sig"))


class RawNameZipInfo(zipfile.ZipInfo):
    """让标准库按给定的原始字节写成员名、不设 UTF-8 标志（只用于合成测试样本）。

    标准库写入时，非 ASCII 名一律编码成 UTF-8 并置 0x800 标志；这里覆盖私有方法 _encodeFilenameFlags，
    把 cp437 字符串原样编回字节。依赖 CPython 内部实现，只在探针里用。
    """

    def _encodeFilenameFlags(self):
        return self.filename.encode("cp437"), self.flag_bits & ~0x800


def write_raw_name_zip(archive_path: Path, relative_names: list, encoding: str) -> None:
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for relative_name in relative_names:
            info = RawNameZipInfo("placeholder")
            # 构造后再赋值：构造函数会把 '\\'（0x5C）换成 '/'，Big5 的「功」「許」第二字节正是 0x5C
            info.filename = info.orig_filename = relative_name.encode(encoding).decode("cp437")
            info.compress_type = zipfile.ZIP_DEFLATED
            zip_file.writestr(info, SYNTHETIC_SRT_TEMPLATE.format(line=Path(relative_name).stem).encode("utf-8-sig"))


def build_synthetic_samples(tools: dict, synthetic_root: Path) -> list:
    """用 7z.exe 合成样本库缺少的格式；每项返回 {path, expected_files, note}，造不出来的记 error。"""
    if "7z" not in tools:
        return [{"name": "全部合成样本", "error": "没有可用的 7z.exe，跳过合成"}]
    sevenzip = tools["7z"]["path"]
    samples = []

    def make(name: str, relative_names: list, extra_arguments: list, expected_name_encoding: str | None) -> None:
        source_root = synthetic_root / "src" / name
        write_synthetic_sources(source_root, relative_names)
        archive_path = synthetic_root / name
        top_level_dirs = sorted({relative_name.split("/")[0] for relative_name in relative_names})
        result = run_command([sevenzip, "a", "-bd", "-sccUTF-8", *extra_arguments, archive_path, *top_level_dirs],
                             working_dir=source_root)
        sample = {"name": name, "path": archive_path, "expected_files": relative_names}
        if result["returncode"] != 0:
            sample["error"] = short_error(result["stderr"] or result["stdout"])
        elif expected_name_encoding:
            # 确认 7z 真的按指定代码页写了原始字节，而不是写成带 UTF-8 标志的名字
            with zipfile.ZipFile(archive_path) as zip_file:
                infos = [info for info in zip_file.infolist() if not info.is_dir()]
                actual = {info.orig_filename.encode("cp437") if not info.flag_bits & 0x800 else b"utf8-flag"
                          for info in infos}
            wanted = {name.encode(expected_name_encoding) for name in relative_names}
            sample["raw_names_verified"] = actual == wanted
            if not sample["raw_names_verified"]:
                sample["error"] = f"7z 没有按 {expected_name_encoding} 写原始文件名"
        samples.append(sample)

    make("synthetic-lzma2.7z", ["合成样本/简体中文.chs.srt", "合成样本/子目录/英文.eng.srt"], ["-t7z", "-m0=lzma2"], None)
    # 仅存储 + 关闭头压缩：排除「7z 文件头本身用 LZMA 压缩」的因素，单独看 tar 能不能读 7z 容器
    make("synthetic-copy.7z", ["合成样本/简体中文.chs.srt"], ["-t7z", "-mx=0", "-mhc=off"], None)
    gbk_names = ["简体字幕/秋刀鱼之味.简体.srt", "简体字幕/肖申克的救赎.英文.srt"]
    # 「功」「許」的 Big5 第二字节是 0x5C（反斜杠），专门测分隔符被误改的问题
    big5_names = ["繁體字幕/成功的電影.繁體.srt", "繁體字幕/許願.英文.srt"]
    # 7z 写的版本：会附带 0x7075 Unicode 路径字段（读取方可以不靠代码页）
    make("synthetic-gbk-names-7z.zip", gbk_names, ["-tzip", "-mcu=off", "-mcp=936"], "gbk")
    make("synthetic-big5-names-7z.zip", big5_names, ["-tzip", "-mcu=off", "-mcp=950"], "big5")
    # 标准库写的版本：只有原始字节名、没有扩展字段，和真实样本里的 GBK 包一样
    for name, relative_names, encoding in (("synthetic-gbk-names-raw.zip", gbk_names, "gbk"),
                                           ("synthetic-big5-names-raw.zip", big5_names, "big5")):
        archive_path = synthetic_root / name
        write_raw_name_zip(archive_path, relative_names, encoding)
        samples.append({"name": name, "path": archive_path, "expected_files": relative_names})

    # 嵌套：外层 zip（UTF-8 名，标准库写）里放一个内层 zip、一个内层 7z、一个子目录里的字幕
    nested_path = synthetic_root / "synthetic-nested.zip"
    inner_zip = next((s for s in samples if s["name"] == "synthetic-gbk-names-raw.zip"), None)
    inner_7z = next((s for s in samples if s["name"] == "synthetic-lzma2.7z" and "error" not in s), None)
    with zipfile.ZipFile(nested_path, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr("外层目录/中英双语.chs&eng.srt", SYNTHETIC_SRT_TEMPLATE.format(line="外层"))
        if inner_zip:
            zip_file.write(inner_zip["path"], "外层目录/内层/inner.zip")
        if inner_7z:
            zip_file.write(inner_7z["path"], "外层目录/内层/inner.7z")
    expected_nested = ["外层目录/中英双语.chs&eng.srt"]
    if inner_zip:
        expected_nested.append("外层目录/内层/inner.zip")
    if inner_7z:
        expected_nested.append("外层目录/内层/inner.7z")
    samples.append({"name": "synthetic-nested.zip", "path": nested_path, "expected_files": expected_nested})
    return samples


# ---------------------------------------------------------------- 主流程：逐个样本


def expected_member_files(archive: Path, true_format: str, tools: dict) -> tuple:
    """正确名称：zip 用回转结果；RAR / 7z 用 7z -sccUTF-8 的列表（RAR4 带 Unicode 名字段），没有 7z 时用 tar。"""
    if true_format == "zip":
        with zipfile.ZipFile(archive) as zip_file:
            members = [(info, decode_zip_member_name(info)) for info in zip_file.infolist()]
        name_details = [{**detail, "is_dir": info.is_dir(), "size": info.file_size} for info, detail in members]
        return [d["decoded"] for d in name_details if not d["is_dir"]], name_details, "zipfile 回转"
    if "7z" in tools:
        listing = sevenzip_list(tools["7z"]["path"], archive)
        return listing["files"], None, "7z -sccUTF-8 列表"
    if "tar" in tools:
        listing = tar_list(tools["tar"]["path"], archive)
        return listing["files"], None, "tar 列表"
    return [], None, "无工具"


def probe_archive(archive: Path, display_name: str, tools: dict, work_dir: Path, depth: int, origin: str) -> list:
    """探测一个包（及其内层包，深度 ≤ MAX_NESTING_DEPTH），返回报告条目列表（内层包各占一条）。"""
    true_format = detect_archive_format(archive)
    entry = {
        "archive": display_name,
        "origin": origin,
        "depth": depth,
        "size": archive.stat().st_size,
        "sha256": sha256_of_file(archive),
        "extension": archive.suffix.lower(),
        "true_format": true_format,
        "extension_matches": extension_matches_format(archive, true_format),
    }
    if true_format == "loose":
        entry["subtitles"] = [{"member_path": None, **analyze_subtitle_bytes(archive.read_bytes())}]
        return [entry]

    expected_files, name_details, name_reference = expected_member_files(archive, true_format, tools)
    entry["name_reference"] = name_reference
    entry["member_names"] = name_details
    if true_format == "rar4":
        entry["rar4_unicode_name_flags"] = read_rar4_name_flags(archive)
    entry["member_count"] = len(expected_files)
    entry["max_directory_depth"] = max((name.count("/") for name in expected_files), default=0)
    entry["tool_matrix"] = run_tool_matrix(tools, archive, true_format, expected_files, work_dir)

    # 内容来源：zip 用 zipfile 解出的目录，其他用 7z（再不行 tar / py7zr）解出的目录
    content_tool = next((name for name in ("zipfile", "7z", "py7zr", "tar")
                         if entry["tool_matrix"]["by_tool"].get(name, {}).get("extract_ok")), None)
    entry["content_source_tool"] = content_tool
    entry["subtitles"], entry["non_subtitle_members"], entry["inner_archives"] = [], [], []
    nested_entries = []
    if content_tool is None:
        return [entry]
    content_root = work_dir / content_tool
    for relative_name in sorted(list_files_on_disk(content_root)):
        member_path = content_root / relative_name
        member_format = detect_archive_format(member_path)
        if member_format != "loose":
            entry["inner_archives"].append({"member_path": relative_name, "true_format": member_format})
            if depth < MAX_NESTING_DEPTH:
                nested_entries += probe_archive(member_path, f"{display_name}!/{relative_name}", tools,
                                                work_dir / f"inner-{len(entry['inner_archives'])}", depth + 1, origin)
        elif Path(relative_name).suffix.lower() in SUBTITLE_EXTENSIONS:
            entry["subtitles"].append({"member_path": relative_name, **analyze_subtitle_bytes(member_path.read_bytes())})
        else:
            entry["non_subtitle_members"].append(relative_name)
    return [entry] + nested_entries


# ---------------------------------------------------------------- 统计与输出


def summarize_samples(entries: list, manifest: dict | None) -> dict:
    """真实样本统计（按 sha256 去重，只算顶层真实样本）；语言 / 双语优先用 manifest 人工标注。"""
    unique, seen = [], set()
    for entry in entries:
        if entry["origin"] == "real" and entry["depth"] == 0 and entry["sha256"] not in seen:
            seen.add(entry["sha256"])
            unique.append(entry)
    archives = [e for e in unique if e["true_format"] != "loose"]

    def count(values):
        result = {}
        for value in values:
            result[str(value)] = result.get(str(value), 0) + 1
        return dict(sorted(result.items()))

    zip_names = [d for e in archives if e.get("member_names") for d in e["member_names"] if not d["is_dir"]]
    subtitles = [s for e in unique for s in e.get("subtitles", [])]
    summary = {
        "unique_archives_and_loose_files": len(unique),
        "duplicates_removed": sum(1 for e in entries if e["origin"] == "real" and e["depth"] == 0) - len(unique),
        "true_format": count(e["true_format"] for e in unique),
        "extension_mismatch": sum(1 for e in archives if e["extension_matches"] is False),
        "zip_member_name_encoding": count(d["chosen_encoding"] for d in zip_names),
        "rar4_members_with_unicode_name": count(flag for e in archives for flag in e.get("rar4_unicode_name_flags", [])),
        "archives_with_subdirectories": sum(1 for e in archives if e.get("max_directory_depth", 0) > 0),
        "archives_with_inner_archives": sum(1 for e in archives if e.get("inner_archives")),
        "subtitle_files": len(subtitles),
        "subtitle_encoding": count(s["encoding"] for s in subtitles),
        "subtitle_format": count(s["format"] for s in subtitles),
        "max_subtitles_in_one_archive": max((len(e.get("subtitles", [])) for e in archives), default=0),
        "non_subtitle_members": sum(len(e.get("non_subtitle_members", [])) for e in archives),
    }
    if manifest:
        labelled = [(a, s) for a in manifest["archives"] if a.get("duplicate_of") is None for s in a["subtitles"]]
        summary["language_source"] = "manifest.json（人工标注）"
        summary["language"] = count(s["language"] for _, s in labelled)
        summary["bilingual_layout"] = count(s["bilingual_layout"] if s["bilingual"] else "单语" for _, s in labelled)
        summary["content_scope"] = count(s["content_scope"] for _, s in labelled)
        summary["archive_bilingual_form"] = count(a["bilingual_form"] for a in manifest["archives"]
                                                  if a.get("duplicate_of") is None)
    else:
        summary["language_source"] = "脚本建议值（未人工核对）"
        summary["language"] = count(s["suggested_language"] for s in subtitles)
        summary["bilingual_layout"] = count(s["suggested_layout"] or "单语" for s in subtitles)
    return summary


def build_draft_manifest(entries: list) -> dict:
    """标注草稿：结构与最终 manifest.json 相同，语言等字段先填脚本建议值，confidence 留 auto 待人工改。"""
    first_seen, archives = {}, []
    for entry in entries:
        if entry["origin"] != "real" or entry["depth"] != 0:
            continue
        duplicate_of = first_seen.get(entry["sha256"])
        first_seen.setdefault(entry["sha256"], entry["archive"])
        name_encoding_by_path = {d["decoded"]: d["chosen_encoding"] for d in entry.get("member_names") or []}
        archives.append({
            "archive": entry["archive"],
            "sha256": entry["sha256"],
            "true_format": entry["true_format"],
            "extension_matches": entry["extension_matches"],
            "duplicate_of": duplicate_of,
            "non_subtitle_members": entry.get("non_subtitle_members", []),
            "subtitles": [{
                "member_path": subtitle["member_path"],
                "name_encoding": name_encoding_by_path.get(subtitle["member_path"],
                                                          "rar-unicode" if entry["true_format"].startswith("rar") else None),
                "encoding": subtitle["encoding"],
                "format": subtitle["format"],
                "language": subtitle["suggested_language"],
                "bilingual": subtitle["suggested_bilingual"],
                "bilingual_layout": subtitle["suggested_layout"],
                "content_scope": "feature",
                "part": None,
                "confidence": "auto",
                "note": "",
            } for subtitle in entry.get("subtitles", [])],
        })
    return {"schema_version": 1, "generated": now_12h(), "archives": archives}


def print_report(report: dict) -> None:
    print(f"== 合璧字幕 解包工具链探针  {report['generated']}")
    print(f"系统代码页：{report['environment']['code_pages']}  Python {report['environment']['python']}")
    print("\n== 工具探测")
    for candidate in report["tool_discovery"]["candidates"]:
        status = "可用" if candidate.get("usable") else ("存在但不可用" if candidate["exists"] else "不存在")
        print(f"  [{candidate['tool']}] {candidate['source']:<22} {status:<8} {candidate.get('path') or ''}  {candidate.get('version') or ''}")
    tool_names = list(report["tool_discovery"]["tools"])
    print("\n== 能力矩阵（列出/列出名对/解开/落盘名对；- = 不适用）")
    print("  " + " | ".join(f"{name:^12}" for name in tool_names) + " | 内容一致 | 包")
    for entry in report["archives"]:
        if entry["true_format"] == "loose":
            continue
        cells = []
        for name in tool_names:
            result = entry["tool_matrix"]["by_tool"].get(name, {})
            if result.get("status"):
                cells.append(f"{'-' if result['status'] == '不适用' else result['status']:^12}")
            else:
                flags = [result["list_ok"], result["list_names_ok"], result["extract_ok"], result["disk_names_ok"]]
                cells.append(f"{''.join('Y' if flag else 'n' for flag in flags):^12}")
        consistent = "是" if entry["tool_matrix"]["content_consistent"] else "否"
        print("  " + " | ".join(cells) + f" |   {consistent}   | [{entry['true_format']}] {entry['archive']}")
    print("\n== 字幕文件")
    for entry in report["archives"]:
        for subtitle in entry.get("subtitles", []):
            print(f"\n  {entry['archive']} :: {subtitle['member_path']}")
            print(f"    编码 {subtitle['encoding']}  格式 {subtitle['format']}  事件 {subtitle['events']}  "
                  f"行类型 {subtitle['line_kinds']}  简/繁特征字 {subtitle['simplified_hits']}/{subtitle['traditional_hits']}  "
                  f"同事件中英 {subtitle['mixed_han_latin_events']}")
            print(f"    建议：{subtitle['suggested_language']}  双语={subtitle['suggested_bilingual']}  形式={subtitle['suggested_layout']}")
            if subtitle.get("style_kinds"):
                print(f"    按 Style：{subtitle['style_kinds']}")
            for line in subtitle["dialogue_preview"]:
                print(f"      | {line[:100]}")
    print("\n== 样本统计")
    for key, value in report["sample_summary"].items():
        print(f"  {key}: {value}")
    print(f"\n样本完整性：{'未改动' if report['fixtures_unchanged'] else '!! 有变化 !!'}")


def make_json_safe(value):
    """报告里的 Path 转成相对仓库的字符串。"""
    if isinstance(value, Path):
        return relative_to_repository(value)
    if isinstance(value, dict):
        return {key: make_json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [make_json_safe(item) for item in value]
    return value


def main() -> int:
    # 输出被重定向（管道 / 文件）时统一用 UTF-8；交互终端保持默认。-I 模式下 PYTHONIOENCODING 不生效，只能在这里设
    if sys.stdout.isatty():
        sys.stdout.reconfigure(errors="backslashreplace")
    else:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description="字幕包解包工具链探针（P2-C）")
    parser.add_argument("--samples", type=Path, default=DEFAULT_SAMPLES_DIR, help="样本根目录（只读）")
    parser.add_argument("--with-synthetic", action="store_true", help="用 7z.exe 合成 7z / GBK / Big5 / 嵌套样本")
    parser.add_argument("--keep-tmp", action="store_true", help="保留 tests/tmp/archive_probe/")
    arguments = parser.parse_args()

    samples_dir = arguments.samples.resolve()
    hashes_before = snapshot_fixture_hashes(samples_dir)
    if TMP_ROOT.exists():
        shutil.rmtree(TMP_ROOT)
    TMP_ROOT.mkdir(parents=True)

    discovery = discover_archive_tools()
    tools = discovery["tools"]
    entries = []
    sample_files = sorted(path for path in samples_dir.rglob("*")
                          if path.is_file() and path.name not in {"_probe-report.json", "manifest.json"})
    for index, sample in enumerate(sample_files, start=1):
        display_name = sample.relative_to(samples_dir).as_posix()
        entries += probe_archive(sample, display_name, tools, TMP_ROOT / "real" / f"{index:02d}", 0, "real")

    synthetic_build = []
    if arguments.with_synthetic:
        synthetic_root = TMP_ROOT / "synthetic"
        synthetic_root.mkdir()
        synthetic_build = build_synthetic_samples(tools, synthetic_root)
        for index, sample in enumerate(synthetic_build, start=1):
            if "error" in sample:
                continue
            entry_list = probe_archive(sample["path"], sample["name"], tools, TMP_ROOT / "synth-work" / f"{index:02d}", 0, "synthetic")
            # 合成样本的正确名称是已知的：用它复核回转 / 列表结果
            top_entry = entry_list[0]
            if top_entry.get("member_names"):
                reference_names = [d["decoded"] for d in top_entry["member_names"] if not d["is_dir"]]
            else:
                reference_names = sevenzip_list(tools["7z"]["path"], sample["path"])["files"]
            top_entry["synthetic_expected_files"] = sample["expected_files"]
            top_entry["synthetic_reference_matches"] = sorted(sample["expected_files"]) == sorted(reference_names)
            entries += entry_list

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")) if MANIFEST_PATH.exists() else None
    report = {
        "generated": now_12h(),
        "environment": {"python": sys.version.split()[0], "code_pages": windows_code_pages()},
        "tool_discovery": discovery,
        "synthetic_build": [{k: v for k, v in s.items() if k != "path"} for s in synthetic_build],
        "archives": entries,
        "sample_summary": summarize_samples(entries, manifest),
    }
    hashes_after = snapshot_fixture_hashes(samples_dir)
    report["fixtures_unchanged"] = hashes_before == hashes_after

    report = make_json_safe(report)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    DRAFT_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    DRAFT_MANIFEST_PATH.write_text(json.dumps(build_draft_manifest(entries), ensure_ascii=False, indent=2), encoding="utf-8")
    print_report(report)
    print(f"\n报告：{relative_to_repository(REPORT_PATH)}；标注草稿：{relative_to_repository(DRAFT_MANIFEST_PATH)}")

    if not arguments.keep_tmp:
        shutil.rmtree(TMP_ROOT)
    return 0 if report["fixtures_unchanged"] else 1


if __name__ == "__main__":
    sys.exit(main())
