"""
ASSRT API 联网探针（P2-B P2-assrt-probe）

用途：
    实测 ASSRT 官方 API（https://api.assrt.net/v1/）：quota / search / detail 各返回哪些字段、
    cnt 上限与 pos 分页语义、配额怎么扣；顺带为 3 部样本影片各下载 2 个字幕包，供 P2-C 解包测试。
    这是探针脚本，不是插件代码；P4 写 ASSRT Provider 时参考这里的结论，不直接复用。

适用情况：
    - 需要联网，并且环境变量 ASSRT_TOKEN 已设置（32 位字母数字，在 ASSRT 用户面板获取）。
    - 影片沿用 docs/api-notes/subhd.md 的 3 部（秋刀鱼之味 / 肖申克的救赎 / 阳光灿烂的日子），方便两个源对比。

如何使用（用仓库 .venv 的解释器，-I 隔离模式）：
    .venv\\Scripts\\python.exe -I scripts\\assrt_probe.py --dry-run     只打印请求清单与预计次数，不联网
    .venv\\Scripts\\python.exe -I scripts\\assrt_probe.py               全量执行（第 1 次运行，run_tag=r1）
    .venv\\Scripts\\python.exe -I scripts\\assrt_probe.py --resume      续跑（run_tag=r2）：已保存的文档页与搜索结果读文件，
                                                                       只请求剩下的部分（加 --dry-run 先看清单）
    输出：
        tests/fixtures/assrt/*.json            每个 API 请求的原始响应体（只把 token 替换成 ***）
        tests/fixtures/assrt/api-doc.html      官方文档原文（出处）
        tests/fixtures/assrt/_run-log-{r1,r2}.json  每次请求的序号、时刻、参数、状态、条数、配额、耗时、保存文件
        tests/fixtures/archives/assrt/*        下载的字幕包（只保存、判魔数，不解压）

安全与限速约束（对应 CLAUDE.md 硬性约束 2、3）：
    - Token 只从环境变量读取，不打印、不写日志；用 Authorization: Bearer 请求头传，不进 URL；
      写任何文件前仍把 token 字符串替换成 ***（兜底）。
    - Authorization 用 add_unredirected_header 添加：urllib 跟随重定向时不会把它带到新地址；
      下载字幕包（文件服务器可能是别的主机）根本不带 Authorization。
    - 所有出站请求（文档页、API、下载）都走同一个限速客户端：两次请求之间至少 16 秒（≤4 次/分钟，
      低于本账号 5 次/分钟的配额；文档写的 20 次/分钟是「初始配额」，实际以用户面板为准），
      每次运行最多 40 次；遇到超额 30900、Token 无效 20001、HTTP 429 / 5xx（ASSRT 超额返回 509）
      或网络错误：先保存响应体，再立即停止整个运行，不重试。

依赖（全部标准库）：
    urllib.request / urllib.parse / urllib.error —— 发 HTTP 请求、拼查询串、处理 HTTP 错误
    json      —— 解析 API 响应、写运行日志
    time      —— time.monotonic 计算请求间隔，time.sleep 补足间隔
    os / re / pathlib / argparse / datetime —— 读环境变量、清理文件名、路径、命令行、日志时刻
"""

import argparse
import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# 仓库根目录与输出目录（脚本在 scripts/ 下，往上一级就是仓库根）
REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
API_FIXTURE_DIR = REPOSITORY_ROOT / "tests" / "fixtures" / "assrt"
ARCHIVE_FIXTURE_DIR = REPOSITORY_ROOT / "tests" / "fixtures" / "archives" / "assrt"

# ASSRT 接口地址（官方文档 https://assrt.net/api/doc：https://api.assrt.net/v1/{endpoint}）
API_BASE_URL = "https://api.assrt.net/v1/"
API_DOC_URL = "https://assrt.net/api/doc"

# 限速与计数：每次运行最多 40 次。
# 间隔：文档写初始配额 20 次/分钟，但本账号用户面板显示 5 次/分钟（2026-10-16 第 1 次运行 4 秒间隔触发 HTTP 509）；
# 改为 16 秒（任意 60 秒内最多 4 次，留 1 次余量）
MIN_SECONDS_BETWEEN_REQUESTS = 16.0
MAX_REQUESTS_PER_RUN = 40
HTTP_TIMEOUT_SECONDS = 30
# 下载走文件服务器（file0 / file1.assrt.net），第 2 次运行 file0 30 秒超时，下载单独放宽到 60 秒
DOWNLOAD_TIMEOUT_SECONDS = 60
# 下载失败不停止整个运行（换下一个候选），但连续这么多次下载网络错误就停止（CLAUDE.md「同一操作连续报错 2 次就停」）
MAX_CONSECUTIVE_DOWNLOAD_NETWORK_ERRORS = 2
# 每部影片本次运行最多尝试几个下载候选 = 还缺的个数 + 这个余量（失败时可换的候选数）
DOWNLOAD_SUBSTITUTE_MAX = 1
MAX_ARCHIVE_BYTES = 20 * 1024 * 1024  # 单个字幕包上限 20 MB，超过就放弃保存

USER_AGENT = "HebiSubs-probe/0.1 (MoviePilot plugin research; low-frequency)"

# 样本影片：沿用 subhd.md 的 3 部。IMDb 号凭记忆填写（不确定），只作为搜索关键词试探，填错也无副作用
SAMPLE_FILMS = [
    {"key": "秋刀鱼之味", "zh": "秋刀鱼之味", "en": "An Autumn Afternoon", "imdb": "tt0056444"},
    {"key": "肖申克的救赎", "zh": "肖申克的救赎", "en": "The Shawshank Redemption", "imdb": "tt0111161"},
    {"key": "阳光灿烂的日子", "zh": "阳光灿烂的日子", "en": "In the Heat of the Sun", "imdb": "tt0111797"},
]
# 用这部影片测 cnt 上限与 pos 分页（结果最多，最可能超过 15 条）
PAGING_TEST_FILM_KEY = "肖申克的救赎"

DETAIL_TOP_N = 3            # 每部影片对中文名搜索结果的前 N 条调 detail
EXTRA_DETAIL_MAX = 2        # 前 N 条里双语不足 2 条时，每部最多再补几条 detail
DOWNLOADS_PER_FILM = 2      # 每部影片下载几个字幕包

# 压缩包格式偏好：rar / 7z 最优先（P2-C 测外部工具要用），其次 zip，裸字幕最后
ARCHIVE_EXTENSION_RANK = {".rar": 0, ".7z": 0, ".zip": 1}

# API 层面需要立即停止整个运行的 status：20001 Token 不存在；30900 超出请求配额
FATAL_API_STATUS_CODES = {20001, 30900}


# ---------------------------------------------------------------------------
# 日志：显示时刻用 12 小时制并标 AM/PM（CLAUDE.md 代码规范）
# ---------------------------------------------------------------------------
def format_time_12h(moment=None):
    moment = moment or datetime.datetime.now()
    return moment.strftime("%I:%M:%S %p")


def log_message(message_text):
    print(f"[{format_time_12h()}] {message_text}", flush=True)


# ---------------------------------------------------------------------------
# Token 脱敏：任何要落盘或输出的文本都先过这里
# ---------------------------------------------------------------------------
class TokenRedactor:
    def __init__(self, secret_token):
        self.secret_token = secret_token

    def redact_text(self, text_value):
        if self.secret_token and isinstance(text_value, str):
            return text_value.replace(self.secret_token, "***")
        return text_value


class StopProbeRun(Exception):
    """遇到超额、Token 无效、429 / 5xx、网络错误时抛出：立即结束整个运行，不重试。"""


# ---------------------------------------------------------------------------
# 限速客户端：所有出站请求的唯一入口，负责间隔、计数、日志记录
# ---------------------------------------------------------------------------
class RateLimitedClient:
    def __init__(self, redactor):
        self.redactor = redactor
        self.request_count = 0
        self.last_request_finished_at = None  # time.monotonic() 值；用「上一次结束」算间隔，比「上一次开始」更保守
        self.request_log_entries = []

    def wait_for_rate_limit(self):
        if self.last_request_finished_at is None:
            return
        elapsed_seconds = time.monotonic() - self.last_request_finished_at
        if elapsed_seconds < MIN_SECONDS_BETWEEN_REQUESTS:
            time.sleep(MIN_SECONDS_BETWEEN_REQUESTS - elapsed_seconds)

    def fetch(self, request_label, url, bearer_token=None, max_body_bytes=None,
              timeout_seconds=HTTP_TIMEOUT_SECONDS, network_error_is_fatal=True):
        """发一个 GET 请求，返回 (http_status, 响应头 dict, 响应体 bytes, 最终 URL)。
        network_error_is_fatal=False（下载用）：网络错误不抛出，返回 (None, {}, b"", None)，由调用方换候选。"""
        if self.request_count >= MAX_REQUESTS_PER_RUN:
            raise StopProbeRun(f"已达每次运行上限 {MAX_REQUESTS_PER_RUN} 次，拒绝再发：{request_label}")
        self.wait_for_rate_limit()
        self.request_count += 1

        http_request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        if bearer_token:
            # unredirected header：urllib 跟随重定向时不会复制它，token 不会被带到其他主机
            http_request.add_unredirected_header("Authorization", f"Bearer {bearer_token}")

        started_at_wall = datetime.datetime.now()
        started_at_monotonic = time.monotonic()
        try:
            with urllib.request.urlopen(http_request, timeout=timeout_seconds) as http_response:
                http_status = http_response.status
                response_headers = dict(http_response.headers.items())
                final_url = http_response.geturl()
                read_limit = (max_body_bytes + 1) if max_body_bytes else -1
                response_body = http_response.read(read_limit)
        except urllib.error.HTTPError as http_error:
            # 4xx / 5xx 也读出响应体返回给调用方：先落盘（ASSRT 的错误 JSON 在这里），再由调用方决定是否停止
            http_status = http_error.code
            response_headers = dict(http_error.headers.items()) if http_error.headers else {}
            final_url = http_error.geturl() or url
            response_body = http_error.read()
        except (urllib.error.URLError, TimeoutError, OSError) as network_error:
            self.last_request_finished_at = time.monotonic()
            error_text = self.redactor.redact_text(str(network_error))
            log_entry = self.record(request_label, url, started_at_wall, started_at_monotonic, None, None, None)
            log_entry["network_error"] = error_text
            if network_error_is_fatal:
                raise StopProbeRun(f"网络错误：{error_text}")
            return None, {}, b"", None
        self.last_request_finished_at = time.monotonic()

        self.record(request_label, url, started_at_wall, started_at_monotonic,
                    http_status, final_url, len(response_body))
        return http_status, response_headers, response_body, final_url

    def record(self, request_label, url, started_at_wall, started_at_monotonic,
               http_status, final_url, body_length):
        log_entry = {
            "seq": self.request_count,
            "time": format_time_12h(started_at_wall),
            "label": request_label,
            "url": self.redactor.redact_text(url),
            "final_url": self.redactor.redact_text(final_url) if final_url and final_url != url else None,
            "http_status": http_status,
            "body_bytes": body_length,
            "elapsed_ms": round((time.monotonic() - started_at_monotonic) * 1000),
        }
        self.request_log_entries.append(log_entry)
        return log_entry


def stop_if_fatal_http_status(http_status):
    """HTTP 429 / 5xx（ASSRT 的 ServerFail 类，含 509 配额超限）：调用方保存响应体之后调用，立即停止运行。"""
    if http_status == 429 or http_status >= 500:
        raise StopProbeRun(f"HTTP {http_status}，停止运行（不重试）")


# ---------------------------------------------------------------------------
# API 调用：拼 URL、解析 JSON、保存原始响应、打印一行摘要
# ---------------------------------------------------------------------------
def count_subs_in_response(response_json):
    """search / detail 返回 {status, sub: {subs: [...]}}；返回条数，结构不符时返回 None。"""
    sub_block = response_json.get("sub") if isinstance(response_json, dict) else None
    if isinstance(sub_block, dict) and isinstance(sub_block.get("subs"), list):
        return len(sub_block["subs"])
    return None


def call_api(client, redactor, secret_token, endpoint, query_params, save_name):
    query_string = urllib.parse.urlencode(query_params)
    request_url = API_BASE_URL + endpoint + (("?" + query_string) if query_string else "")
    request_label = f"GET {endpoint} " + " ".join(f"{k}={v}" for k, v in query_params.items())

    http_status, _, response_body, _ = client.fetch(request_label, request_url, bearer_token=secret_token)

    # 原始响应体按 UTF-8 解码（JSON 规定 UTF-8），只做 token 替换后原样落盘
    response_text = redactor.redact_text(response_body.decode("utf-8", errors="replace"))
    API_FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    (API_FIXTURE_DIR / save_name).write_text(response_text, encoding="utf-8")

    try:
        response_json = json.loads(response_text)
    except json.JSONDecodeError:
        response_json = None
    api_status = response_json.get("status") if isinstance(response_json, dict) else None
    item_count = count_subs_in_response(response_json) if response_json else None

    log_entry = client.request_log_entries[-1]
    log_entry.update({"api_status": api_status, "items": item_count, "saved_as": save_name})
    if endpoint == "user/quota" and isinstance(response_json, dict):
        log_entry["quota"] = (response_json.get("user") or {}).get("quota")
    log_message(f"#{client.request_count:02d}/{MAX_REQUESTS_PER_RUN} {request_label} → HTTP {http_status} "
                f"status={api_status} items={item_count}"
                + (f" quota={log_entry['quota']}" if "quota" in log_entry else "") + f" → {save_name}")

    stop_if_fatal_http_status(http_status)
    if api_status in FATAL_API_STATUS_CODES:
        raise StopProbeRun(f"API status={api_status}（20001 Token 不存在 / 30900 超出配额），停止运行")
    return response_json


def subs_of(response_json):
    if isinstance(response_json, dict) and isinstance(response_json.get("sub"), dict):
        subs_list = response_json["sub"].get("subs")
        if isinstance(subs_list, list):
            return subs_list
    return []


# ---------------------------------------------------------------------------
# 挑选：哪些条目调 detail、哪些下载（启发式，只为取样，不代表插件的打分规则）
# ---------------------------------------------------------------------------
def looks_bilingual(subtitle_item):
    """按 lang.desc 含「双语」、或 langlist 同时有中文类和英文类标志来判断（键名以实测为准，这里宽松匹配）。"""
    language_info = subtitle_item.get("lang") or {}
    if not isinstance(language_info, dict):
        return "双语" in str(language_info)
    description_text = str(language_info.get("desc") or "")
    if "双语" in description_text:
        return True
    language_flags = language_info.get("langlist") or {}
    if isinstance(language_flags, dict):
        enabled_keys = {key for key, value in language_flags.items() if value}
        if "langdou" in enabled_keys:
            return True
        has_chinese = any(key.startswith(("langchs", "langcht")) for key in enabled_keys)
        has_english = any(key.startswith("langeng") for key in enabled_keys)
        return has_chinese and has_english
    return False


def archive_extension_rank(file_name):
    return ARCHIVE_EXTENSION_RANK.get(Path(str(file_name or "")).suffix.lower(), 2)


def merge_search_results(*result_lists):
    """按 id 去重合并多次搜索结果，保留第一次出现的顺序（中文名搜索在前，作为 source_rank）。"""
    seen_ids, merged_items = set(), []
    for result_list in result_lists:
        for subtitle_item in result_list:
            subtitle_id = subtitle_item.get("id")
            if subtitle_id is not None and subtitle_id not in seen_ids:
                seen_ids.add(subtitle_id)
                merged_items.append(subtitle_item)
    return merged_items


def detail_item_of(detail_json):
    detail_subs = subs_of(detail_json)
    return detail_subs[0] if detail_subs else None


def detail_file_name(detail_item):
    """压缩包文件名：优先 filename，其次下载 URL 路径的最后一段。"""
    file_name = detail_item.get("filename")
    if not file_name and detail_item.get("url"):
        file_name = urllib.parse.unquote(urllib.parse.urlparse(detail_item["url"]).path.rsplit("/", 1)[-1])
    return file_name or ""


# ---------------------------------------------------------------------------
# 下载：文件名清理、魔数判断、落盘
# ---------------------------------------------------------------------------
def sanitize_file_name(raw_file_name, fallback_name):
    """只取 basename，去掉 Windows 非法字符与首尾空格 / 点；为空时用 fallback。"""
    base_name = re.split(r"[\\/]", raw_file_name or "")[-1]
    base_name = re.sub(r'[<>:"|?*\x00-\x1f]', "_", base_name).strip(" .")
    return base_name or fallback_name


def detect_magic_format(head_bytes):
    if head_bytes.startswith(b"PK\x03\x04"):
        return "zip"
    if head_bytes.startswith(b"Rar!\x1a\x07\x01\x00"):
        return "rar5"
    if head_bytes.startswith(b"Rar!\x1a\x07\x00"):
        return "rar4"
    if head_bytes.startswith(b"7z\xbc\xaf\x27\x1c"):
        return "7z"
    if head_bytes.lstrip(b"\xef\xbb\xbf").lstrip()[:1] in (b"<",):
        return "html?"  # 可能是拦截页 / 错误页
    return "other"


def archive_target_candidates(detail_item, subtitle_id):
    """这条字幕下载后可能的落盘路径（同名冲突时会加 -id 后缀），用来判断续跑时是否已经下载过。"""
    file_name = sanitize_file_name(detail_file_name(detail_item), f"assrt-{subtitle_id}.bin")
    plain_path = ARCHIVE_FIXTURE_DIR / file_name
    return [plain_path, ARCHIVE_FIXTURE_DIR / f"{plain_path.stem}-{subtitle_id}{plain_path.suffix}"]


def already_downloaded_archive(detail_item, subtitle_id):
    for candidate_path in archive_target_candidates(detail_item, subtitle_id):
        if candidate_path.is_file():
            return candidate_path
    return None


def download_archive(client, detail_item, subtitle_id, url_note=""):
    """返回 (结果 dict 或 None, 失败类型 None / "network" / "http" / "no_url")。下载失败不停止运行，由调用方换候选。"""
    download_url = detail_item.get("url")
    if not download_url:
        log_message(f"  id={subtitle_id} detail 里没有 url，跳过下载")
        return None, "no_url"
    request_label = f"GET download id={subtitle_id}{url_note}"
    # 下载不带 Authorization（文件服务器可能是其他主机）；网络错误不致命，超时单独放宽
    http_status, response_headers, response_body, final_url = client.fetch(
        request_label, download_url, bearer_token=None, max_body_bytes=MAX_ARCHIVE_BYTES,
        timeout_seconds=DOWNLOAD_TIMEOUT_SECONDS, network_error_is_fatal=False)
    log_entry = client.request_log_entries[-1]

    if http_status is None:
        log_message(f"#{client.request_count:02d}/{MAX_REQUESTS_PER_RUN} {request_label} → 网络错误："
                    f"{log_entry.get('network_error')}（耗时 {log_entry['elapsed_ms']} ms）")
        return None, "network"
    if http_status != 200 or len(response_body) > MAX_ARCHIVE_BYTES:
        # 非 200 的响应体也保存下来（可能是过期提示页），便于分析；文件服务器响应里不含 token
        error_save_name = f"download-error-{subtitle_id}-http{http_status}.bin"
        API_FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        (API_FIXTURE_DIR / error_save_name).write_bytes(response_body[:65536])
        log_entry.update({"saved_as": error_save_name, "note": "非 200 或超过大小上限，未当作字幕包保存",
                          "content_type": response_headers.get("Content-Type")})
        log_message(f"#{client.request_count:02d}/{MAX_REQUESTS_PER_RUN} {request_label} → HTTP {http_status} "
                    f"{len(response_body)} 字节，未当作字幕包保存 → {error_save_name}")
        return None, "http"

    magic_format = detect_magic_format(response_body[:16])
    file_name = sanitize_file_name(detail_file_name(detail_item), f"assrt-{subtitle_id}.bin")
    ARCHIVE_FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    target_path = ARCHIVE_FIXTURE_DIR / file_name
    if target_path.exists():
        target_path = ARCHIVE_FIXTURE_DIR / f"{target_path.stem}-{subtitle_id}{target_path.suffix}"
    target_path.write_bytes(response_body)

    log_entry.update({"saved_as": target_path.name, "magic_format": magic_format,
                      "content_type": response_headers.get("Content-Type")})
    log_message(f"#{client.request_count:02d}/{MAX_REQUESTS_PER_RUN} {request_label} → HTTP {http_status} "
                f"{len(response_body)} 字节 魔数={magic_format} → archives/assrt/{target_path.name}")
    return {"id": subtitle_id, "file": target_path.name, "bytes": len(response_body), "magic": magic_format}, None


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
# 续跑（--resume）：之前运行已成功保存的响应直接读文件，不再请求
#   - 文档页、搜索（中文名 / 英文名 / 分页测试）：文件存在就复用
#   - IMDb 搜索：已保存的复用；PAGING_TEST_FILM_KEY 那部重测 1 次（第 1 次运行的空结果紧挨着 509，
#     不能排除是被限流），另存为 -search-imdb-retest.json；其余没保存的不再请求（省配额）
#   - detail：已保存的复用（其中的下载链接是旧的）；已经下载过的字幕包不再下载
#   - 旧链接下载失败 → 重新请求 detail 拿新链接再试 1 次 → 仍失败就换下一个候选
# ---------------------------------------------------------------------------
def saved_fixture_exists(save_name):
    return (API_FIXTURE_DIR / save_name).is_file()


def load_saved_fixture(save_name):
    return json.loads((API_FIXTURE_DIR / save_name).read_text(encoding="utf-8"))


def imdb_search_plan(film_key, resume):
    """返回 IMDb 搜索在本次运行中的 (动作, 保存文件后缀)：动作为 request / reuse / skip。"""
    if not resume:
        return "request", "imdb"
    if film_key == PAGING_TEST_FILM_KEY:
        return ("reuse" if saved_fixture_exists(f"{film_key}-search-imdb-retest.json") else "request"), "imdb-retest"
    return ("reuse" if saved_fixture_exists(f"{film_key}-search-imdb.json") else "skip"), "imdb"


def paging_search_plans():
    """cnt 上限与 pos 分页测试：(保存后缀, 额外参数)。同一部影片、同一关键词。"""
    return [("zh-cnt50", {"cnt": 50}), ("zh-pos15-cnt15", {"pos": 15, "cnt": 15}),
            ("zh-pos10-cnt10", {"pos": 10, "cnt": 10})]


def choose_detail_targets(candidate_items):
    """每部前 N 条（中文名结果在前）；其中双语不足 DOWNLOADS_PER_FILM 条时，从后面按双语补最多 EXTRA_DETAIL_MAX 条。"""
    detail_targets = candidate_items[:DETAIL_TOP_N]
    if sum(looks_bilingual(item) for item in detail_targets) < DOWNLOADS_PER_FILM:
        extra_bilingual = [item for item in candidate_items[DETAIL_TOP_N:] if looks_bilingual(item)]
        detail_targets = detail_targets + extra_bilingual[:EXTRA_DETAIL_MAX]
    return detail_targets


def detail_save_name(film_key, subtitle_id, run_tag=None):
    return f"{film_key}-detail-{subtitle_id}" + (f"-{run_tag}" if run_tag else "") + ".json"


def plan_resume_film_work(film_key):
    """续跑 dry-run 用：从已保存的搜索结果推算这部影片要请求几次 detail、还缺几个下载、有几个旧链接。"""
    def saved_items(save_suffix):
        save_name = f"{film_key}-search-{save_suffix}.json"
        return subs_of(load_saved_fixture(save_name)) if saved_fixture_exists(save_name) else []

    candidate_items = merge_search_results(saved_items("zh"), saved_items("en"),
                                           saved_items(imdb_search_plan(film_key, True)[1]))
    detail_targets = choose_detail_targets(candidate_items)
    details_to_request, downloaded_count, has_reused_detail = 0, 0, False
    for subtitle_item in detail_targets:
        subtitle_id = subtitle_item.get("id")
        if saved_fixture_exists(detail_save_name(film_key, subtitle_id)):
            has_reused_detail = True
            detail_item = detail_item_of(load_saved_fixture(detail_save_name(film_key, subtitle_id)))
            if detail_item and already_downloaded_archive(detail_item, subtitle_id):
                downloaded_count += 1
        else:
            details_to_request += 1
    downloads_missing = max(DOWNLOADS_PER_FILM - downloaded_count, 0)
    return {"details": details_to_request, "downloads_missing": downloads_missing,
            "has_reused_detail": has_reused_detail, "targets": len(detail_targets)}


def print_request_plan(resume):
    film_count = len(SAMPLE_FILMS)

    def count_unless_saved(save_names):
        return sum(0 if (resume and saved_fixture_exists(name)) else 1 for name in save_names)

    imdb_request_count = sum(imdb_search_plan(film["key"], resume)[0] == "request" for film in SAMPLE_FILMS)
    paging_request_count = count_unless_saved(f"{PAGING_TEST_FILM_KEY}-search-{suffix}.json"
                                              for suffix, _ in paging_search_plans())
    plan_rows = [
        ("GET 官方文档页 api/doc（不带 token）", count_unless_saved(["api-doc.html"]), 0),
        ("user/quota（起始）", 1, 0),
        ("sub/search 中文名 cnt=15 × 每部影片", count_unless_saved(f"{f['key']}-search-zh.json" for f in SAMPLE_FILMS), 0),
        ("user/quota（3 次搜索后，看扣减方式；续跑时省略）", 0 if resume else 1, 0),
        ("sub/search 英文名 cnt=15 × 每部影片", count_unless_saved(f"{f['key']}-search-en.json" for f in SAMPLE_FILMS), 0),
        ("sub/search IMDb 号", imdb_request_count, 0),
        (f"sub/search {PAGING_TEST_FILM_KEY} cnt=50 / pos=15 / pos=10（cnt 上限与 pos 语义）", paging_request_count, 0),
        ("user/quota（分页测试后，只在本次做了分页测试时）", 1 if paging_request_count else 0, 0),
    ]
    if resume:
        for film in SAMPLE_FILMS:
            film_plan = plan_resume_film_work(film["key"])
            # 最坏：缺的下载 + 换候选余量，每次下载如果用的是旧链接还要多 1 次 detail 刷新
            download_attempts_worst = min(film_plan["downloads_missing"] + DOWNLOAD_SUBSTITUTE_MAX, film_plan["targets"])
            refresh_worst = download_attempts_worst if film_plan["has_reused_detail"] else 0
            plan_rows.append((f"{film['key']}：sub/detail（新请求；已保存的复用）", film_plan["details"], 0))
            plan_rows.append((f"{film['key']}：下载还缺 {film_plan['downloads_missing']} 个（失败可换 1 个候选）",
                              film_plan["downloads_missing"] if film_plan["downloads_missing"] else 0,
                              download_attempts_worst - film_plan["downloads_missing"] + refresh_worst))
    else:
        plan_rows += [
            (f"sub/detail 每部前 {DETAIL_TOP_N} 条（双语不足时每部再补 ≤{EXTRA_DETAIL_MAX} 条）",
             film_count * DETAIL_TOP_N, film_count * EXTRA_DETAIL_MAX),
            (f"下载字幕包 每部 {DOWNLOADS_PER_FILM} 个（不带 token；失败每部可换 {DOWNLOAD_SUBSTITUTE_MAX} 个）",
             film_count * DOWNLOADS_PER_FILM, film_count * DOWNLOAD_SUBSTITUTE_MAX),
        ]
    plan_rows.append(("user/quota（结束）", 1, 0))

    planned_total = sum(planned for _, planned, _ in plan_rows)
    worst_total = planned_total + sum(extra for _, _, extra in plan_rows)
    log_message(f"请求清单（{'续跑' if resume else '全量'}；0 = 复用已保存文件或跳过；+N = 最坏情况追加）：")
    for row_index, (row_description, planned, extra) in enumerate(plan_rows):
        print(f"    {row_index:>2}. {row_description:<56} {planned}" + (f" (+{extra})" if extra else ""))
    print(f"    计划 {planned_total} 次，最坏 {worst_total} 次；上限 {MAX_REQUESTS_PER_RUN} 次；"
          f"间隔 ≥{MIN_SECONDS_BETWEEN_REQUESTS:.0f} 秒，预计最长约 "
          f"{(worst_total * MIN_SECONDS_BETWEEN_REQUESTS + DOWNLOAD_TIMEOUT_SECONDS * MAX_CONSECUTIVE_DOWNLOAD_NETWORK_ERRORS) / 60:.1f} 分钟")
    print("    影片：" + "；".join(f"{f['zh']} / {f['en']} / {f['imdb']}" for f in SAMPLE_FILMS))
    return worst_total


class DownloadFailureTracker:
    """统计连续的下载网络错误：达到上限就停止整个运行；任何一次下载成功（或非网络类失败）都清零。"""

    def __init__(self):
        self.consecutive_network_errors = 0

    def record(self, failure_kind):
        if failure_kind == "network":
            self.consecutive_network_errors += 1
            if self.consecutive_network_errors >= MAX_CONSECUTIVE_DOWNLOAD_NETWORK_ERRORS:
                raise StopProbeRun(f"连续 {self.consecutive_network_errors} 次下载网络错误，停止运行")
        else:
            self.consecutive_network_errors = 0


def run_probe(client, redactor, secret_token, film_reports, resume, run_tag):
    """film_reports 由调用方传入并就地填写：中途停止时，已拿到的部分仍能写进运行日志。"""
    film_reports.update({film["key"]: {"queries": {}} for film in SAMPLE_FILMS})
    films_by_key = {film["key"]: film for film in SAMPLE_FILMS}
    download_failure_tracker = DownloadFailureTracker()

    def search(film_key, query_text, save_suffix, extra_params=None, action="request"):
        query_params = {"q": query_text, "cnt": 15}
        query_params.update(extra_params or {})
        save_name = f"{film_key}-search-{save_suffix}.json"
        if action == "skip":
            log_message(f"跳过 {save_name}（续跑不补请求）")
            return []
        if action == "reuse" or (resume and saved_fixture_exists(save_name)):
            response_json = load_saved_fixture(save_name)
            log_message(f"复用已保存 {save_name}（不请求）")
        else:
            response_json = call_api(client, redactor, secret_token, "sub/search", query_params, save_name)
        result_items = subs_of(response_json)
        film_reports[film_key]["queries"][save_suffix] = {
            "params": query_params, "status": (response_json or {}).get("status"),
            "count": len(result_items), "ids": [item.get("id") for item in result_items],
        }
        return result_items

    # 0. 官方文档原文（出处）
    if resume and saved_fixture_exists("api-doc.html"):
        log_message("复用已保存 api-doc.html（不请求）")
    else:
        doc_status, _, doc_body, _ = client.fetch("GET api/doc", API_DOC_URL)
        API_FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        (API_FIXTURE_DIR / "api-doc.html").write_bytes(doc_body)
        client.request_log_entries[-1]["saved_as"] = "api-doc.html"
        log_message(f"#{client.request_count:02d}/{MAX_REQUESTS_PER_RUN} GET api/doc → HTTP {doc_status} "
                    f"{len(doc_body)} 字节 → api-doc.html")
        stop_if_fatal_http_status(doc_status)

    # 1. 起始配额
    call_api(client, redactor, secret_token, "user/quota", {}, f"quota-{run_tag}-1-start.json")

    # 2. 中文名搜索
    zh_results = {key: search(key, films_by_key[key]["zh"], "zh") for key in films_by_key}

    # 3. 3 次搜索后的配额（续跑时搜索是复用的，没有意义，省略）
    if not resume:
        call_api(client, redactor, secret_token, "user/quota", {}, f"quota-{run_tag}-2-after-3-searches.json")

    # 4–5. 英文名、IMDb 号搜索
    en_results = {key: search(key, films_by_key[key]["en"], "en") for key in films_by_key}
    imdb_results = {}
    for film_key in films_by_key:
        imdb_action, imdb_suffix = imdb_search_plan(film_key, resume)
        imdb_results[film_key] = search(film_key, films_by_key[film_key]["imdb"], imdb_suffix, action=imdb_action)

    # 6–8. cnt 上限与 pos 分页
    paging_requests_before = client.request_count
    for paging_suffix, paging_params in paging_search_plans():
        search(PAGING_TEST_FILM_KEY, films_by_key[PAGING_TEST_FILM_KEY]["zh"], paging_suffix, paging_params)
    if client.request_count > paging_requests_before:
        call_api(client, redactor, secret_token, "user/quota", {}, f"quota-{run_tag}-3-after-paging.json")

    def fetch_fresh_detail(film_key, subtitle_id):
        save_name = detail_save_name(film_key, subtitle_id, run_tag if saved_fixture_exists(
            detail_save_name(film_key, subtitle_id)) else None)
        return detail_item_of(call_api(client, redactor, secret_token, "sub/detail", {"id": subtitle_id}, save_name))

    def try_download(film_key, entry):
        """下载一个候选：旧链接失败就刷新 detail 再试 1 次。返回结果 dict 或 None。"""
        download_result, failure_kind = download_archive(
            client, entry["detail"], entry["id"], url_note="" if entry["fresh"] else "（旧链接）")
        download_failure_tracker.record(failure_kind)
        if download_result is None and not entry["fresh"]:
            refreshed_detail = fetch_fresh_detail(film_key, entry["id"])
            if refreshed_detail:
                entry.update({"detail": refreshed_detail, "fresh": True})
                download_result, failure_kind = download_archive(client, refreshed_detail, entry["id"],
                                                                 url_note="（刷新后）")
                download_failure_tracker.record(failure_kind)
        return download_result

    # 9–10. 每部影片：detail（已保存的复用）→ 挑选 → 下载。复用了旧 detail 的影片放最后（旧链接最可能失败）
    def film_uses_saved_detail(film_key):
        candidate_items = merge_search_results(zh_results[film_key], en_results[film_key], imdb_results[film_key])
        return resume and any(saved_fixture_exists(detail_save_name(film_key, item.get("id")))
                              for item in choose_detail_targets(candidate_items))

    for film_key in sorted(films_by_key, key=film_uses_saved_detail):
        candidate_items = merge_search_results(zh_results[film_key], en_results[film_key], imdb_results[film_key])
        detail_targets = choose_detail_targets(candidate_items)

        detailed_entries = []
        for source_rank, subtitle_item in enumerate(candidate_items):
            if subtitle_item not in detail_targets:
                continue
            subtitle_id = subtitle_item.get("id")
            if resume and saved_fixture_exists(detail_save_name(film_key, subtitle_id)):
                detail_item, is_fresh = detail_item_of(load_saved_fixture(detail_save_name(film_key, subtitle_id))), False
                log_message(f"复用已保存 {detail_save_name(film_key, subtitle_id)}（不请求；下载链接是旧的）")
            else:
                detail_item, is_fresh = fetch_fresh_detail(film_key, subtitle_id), True
            if detail_item:
                detailed_entries.append({
                    "id": subtitle_id, "source_rank": source_rank + 1, "detail": detail_item, "fresh": is_fresh,
                    "bilingual": looks_bilingual(subtitle_item) or looks_bilingual(detail_item),
                    "file_name": detail_file_name(detail_item),
                })

        # 下载挑选：双语优先 → rar/7z > zip > 其他 → 原始顺序；已下载过的直接算数
        detailed_entries.sort(key=lambda entry: (not entry["bilingual"],
                                                 archive_extension_rank(entry["file_name"]),
                                                 entry["source_rank"]))
        download_results, attempted_ids = [], []
        for entry in detailed_entries:
            existing_path = already_downloaded_archive(entry["detail"], entry["id"])
            if existing_path and len(download_results) < DOWNLOADS_PER_FILM:
                log_message(f"已下载过 id={entry['id']} → archives/assrt/{existing_path.name}（不请求）")
                download_results.append({"id": entry["id"], "file": existing_path.name,
                                         "bytes": existing_path.stat().st_size,
                                         "magic": detect_magic_format(existing_path.read_bytes()[:16]),
                                         "from_previous_run": True})
        downloads_missing = DOWNLOADS_PER_FILM - len(download_results)
        attempt_budget = downloads_missing + DOWNLOAD_SUBSTITUTE_MAX if downloads_missing else 0
        for entry in detailed_entries:
            if len(download_results) >= DOWNLOADS_PER_FILM or len(attempted_ids) >= attempt_budget:
                break
            if any(result["id"] == entry["id"] for result in download_results):
                continue
            attempted_ids.append(entry["id"])
            download_result = try_download(film_key, entry)
            if download_result:
                download_results.append(download_result)
        for download_result in download_results:
            matching_entry = next(e for e in detailed_entries if e["id"] == download_result["id"])
            download_result.update({"bilingual_guess": matching_entry["bilingual"],
                                    "source_rank": matching_entry["source_rank"]})

        film_reports[film_key].update({
            "merged_candidates": len(candidate_items),
            "detail_ids": [entry["id"] for entry in sorted(detailed_entries, key=lambda e: e["source_rank"])],
            "download_selection_order": [
                {"id": e["id"], "bilingual_guess": e["bilingual"], "file_name": e["file_name"],
                 "source_rank": e["source_rank"], "detail_fresh": e["fresh"]} for e in detailed_entries],
            "download_attempted_ids": attempted_ids,
            "downloads": download_results,
        })

    # 11. 结束配额
    call_api(client, redactor, secret_token, "user/quota", {}, f"quota-{run_tag}-4-end.json")


def write_run_log(client, redactor, film_reports, stop_reason, run_tag):
    run_log = {
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d ") + format_time_12h(),
        "run_tag": run_tag,
        "request_count": client.request_count,
        "max_requests_per_run": MAX_REQUESTS_PER_RUN,
        "min_seconds_between_requests": MIN_SECONDS_BETWEEN_REQUESTS,
        "stop_reason": stop_reason,
        "requests": client.request_log_entries,
        "films": film_reports,
    }
    log_text = redactor.redact_text(json.dumps(run_log, ensure_ascii=False, indent=2))
    API_FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    (API_FIXTURE_DIR / f"_run-log-{run_tag}.json").write_text(log_text, encoding="utf-8")


def main():
    # Windows 控制台默认编码可能不是 UTF-8，中文日志改用 UTF-8 输出
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    argument_parser = argparse.ArgumentParser(description="ASSRT API 联网探针（P2-B）")
    argument_parser.add_argument("--dry-run", action="store_true", help="只打印请求清单与预计次数，不联网")
    argument_parser.add_argument("--resume", action="store_true",
                                 help="续跑：已保存的文档页、搜索、detail 直接读文件，已下载的包不再下载")
    argument_parser.add_argument("--run-tag", default=None,
                                 help="本次运行的标签（写进配额文件名与运行日志名），默认全量 r1、续跑 r2")
    arguments = argument_parser.parse_args()
    run_tag = arguments.run_tag or ("r2" if arguments.resume else "r1")
    if not re.fullmatch(r"r\d+", run_tag):
        log_message("--run-tag 只能是 r 加数字（如 r3）")
        return 2
    if not arguments.dry_run and saved_fixture_exists(f"_run-log-{run_tag}.json"):
        log_message(f"_run-log-{run_tag}.json 已存在，换一个 --run-tag，避免覆盖之前的运行记录；请求 0 次")
        return 2

    worst_total = print_request_plan(arguments.resume)
    if worst_total > MAX_REQUESTS_PER_RUN:
        log_message(f"最坏情况 {worst_total} 次超过上限 {MAX_REQUESTS_PER_RUN}，请先调整清单")
        return 2
    if arguments.dry_run:
        log_message("dry-run 结束，请求 0 次")
        return 0

    secret_token = os.environ.get("ASSRT_TOKEN", "")
    if not re.fullmatch(r"[A-Za-z0-9]{32}", secret_token):
        log_message("环境变量 ASSRT_TOKEN 未设置或格式不对（应为 32 位字母数字），请求 0 次，退出")
        return 2

    redactor = TokenRedactor(secret_token)
    client = RateLimitedClient(redactor)
    film_reports, stop_reason = {}, None
    try:
        run_probe(client, redactor, secret_token, film_reports, arguments.resume, run_tag)
    except StopProbeRun as stop_error:
        stop_reason = str(stop_error)
        log_message(f"提前停止：{stop_reason}")
    finally:
        write_run_log(client, redactor, film_reports, stop_reason, run_tag)
        log_message(f"结束：共发出 {client.request_count}/{MAX_REQUESTS_PER_RUN} 次请求；"
                    f"运行日志 → tests/fixtures/assrt/_run-log-{run_tag}.json")
    return 1 if stop_reason else 0


if __name__ == "__main__":
    sys.exit(main())
