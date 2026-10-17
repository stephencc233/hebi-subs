"""
ASSRT 补测探针：filelist 与配额计数（P3-A P3-prechecks ①）

用途：
    补测 P2-B 留下的两个问题（docs/api-notes/assrt.md §8「遗留」）：
    ① sub/search 加 filelist=1 时，结果里会不会带包内文件清单（文件名、有没有下载链接）；
    ② 下载请求（文件服务器）和 user/quota 本身算不算配额。
    结论写进 docs/api-notes/assrt.md §9。这是探针脚本，不是插件代码。

适用情况：
    - 需要联网，环境变量 ASSRT_TOKEN 已设置（进程或当前用户级环境变量均可）。
    - 测试期间不要有别的程序用同一个 token / IP 访问 ASSRT（配额按 token 与 IP 共享，会干扰读数）。

如何使用（用仓库 .venv 的解释器，-I 隔离模式）：
    .venv\\Scripts\\python.exe -I scripts\\assrt_quota_probe.py --dry-run    只打印请求清单，请求 0 次
    .venv\\Scripts\\python.exe -I scripts\\assrt_quota_probe.py              执行（固定 run_tag=r4，总共 10 次请求）
    .venv\\Scripts\\python.exe -I scripts\\assrt_quota_probe.py --analyze    只根据已保存的文件重新分析，请求 0 次
    输出（都在 tests/fixtures/assrt/，文件名带 r4）：
        quota-r4-{A1,A2,A3,B1,B2}.json、*-search-zh-filelist-r4.json、秋刀鱼之味-detail-604957-r4.json、
        秋刀鱼之味-onthefly-604957-r4.ass（单文件下载）、_run-log-r4.json（每次请求的时刻、偏移秒数、状态、分析结果）

测量设计（为什么有 2 秒间隔）：
    P2-B 的 r2 / r3 按 16 秒间隔请求，配额读数一直停在 4–5：配额回补（约 12 秒 1 次）把每次扣减都补回来了，
    测不出谁计数。所以两段测量改用 2 秒间隔、每段 ≤4 次（在容量 5 以内），每段开始前空闲 90 秒等配额回满；
    其余请求仍按 16 秒。段首配额读数 <4 说明有别的程序在消耗配额，立即停止整次运行。
    A 段：quota ×3                       → 看 quota 本身是否计数、读数是扣减前还是扣减后
    B 段：quota → 单文件下载 → 整包下载 → quota → 看下载是否计数

安全与限速（CLAUDE.md 硬性约束 2、3）：
    复用 assrt_probe.py 的限速客户端与 token 脱敏：token 只在内存里，用 Authorization: Bearer 请求头传
    （add_unredirected_header，重定向不带走），不打印、不写日志，落盘前仍替换成 ***；下载请求不带 token。
    每次运行上限 10 次；HTTP 429 / 5xx（ASSRT 超额是 509）、API status 30900 / 20001、网络错误：
    先保存响应体，再立即停止，不重试。

依赖（全部标准库）：
    assrt_probe（同目录）—— 限速客户端、token 脱敏、call_api（先落盘再判断是否停止）、魔数判断等
    hashlib / zipfile —— 计算 sha256，只读已有字幕包里各成员的字节做比对（不解压到磁盘）
    winreg —— 读当前用户级环境变量（进程环境变量里没有 token 时）
    json / time / argparse / pathlib / sys / os / re —— 解析、计时、命令行、路径
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import zipfile
from pathlib import Path

# -I 隔离模式不会把脚本目录放进 sys.path，显式加入后才能导入同目录的 assrt_probe
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
import assrt_probe as base  # noqa: E402

RUN_TAG = "r4"
MAX_REQUESTS_THIS_RUN = 10
NORMAL_INTERVAL_SECONDS = 16.0     # 平时间隔，与 P2-B 相同
BURST_INTERVAL_SECONDS = 2.0       # 测量段间隔（用户 2026-10-16 同意）
IDLE_BEFORE_BURST_SECONDS = 90     # 测量段前空闲多久，等配额回满
MIN_QUOTA_AT_BURST_START = 4       # 段首配额读数低于它就停止（有别的消耗者，读数没法解释）

# 覆盖 assrt_probe 的每次运行上限：RateLimitedClient.fetch 与 call_api 的日志在调用时读这个模块常量
base.MAX_REQUESTS_PER_RUN = MAX_REQUESTS_THIS_RUN

# filelist 测试用的两部影片：已有 detail 的条目可以逐条对照（秋刀鱼 3 条、肖申克 5 条）
FILELIST_SEARCHES = [("秋刀鱼之味", "秋刀鱼之味"), ("肖申克的救赎", "肖申克的救赎")]
DOWNLOAD_FILM_KEY = "秋刀鱼之味"
DOWNLOAD_SUBTITLE_ID = 604957                  # 9 个文件的 zip，已有 fixture（archives/assrt/）
SINGLE_FILE_NAME = "03预告chs.ass"             # filelist 里约 4KB 的一个文件
SINGLE_FILE_SAVE_NAME = f"{DOWNLOAD_FILM_KEY}-onthefly-{DOWNLOAD_SUBTITLE_ID}-{RUN_TAG}.ass"


def quota_save_name(step_name):
    return f"quota-{RUN_TAG}-{step_name}.json"


def search_save_name(film_key):
    return f"{film_key}-search-zh-filelist-{RUN_TAG}.json"


def detail_save_name():
    return f"{DOWNLOAD_FILM_KEY}-detail-{DOWNLOAD_SUBTITLE_ID}-{RUN_TAG}.json"


# ---------------------------------------------------------------------------
# 限速客户端：在 assrt_probe.RateLimitedClient 上加「可切换间隔」和「相对起点的秒数」
# ---------------------------------------------------------------------------
class SwitchableIntervalClient(base.RateLimitedClient):
    def __init__(self, redactor):
        super().__init__(redactor)
        self.min_interval_seconds = NORMAL_INTERVAL_SECONDS
        self.run_started_monotonic = time.monotonic()

    def wait_for_rate_limit(self):
        # 用「上一次结束」到「这一次开始」计算间隔（与父类相同），只是间隔值可切换
        if self.last_request_finished_at is None:
            return
        elapsed_seconds = time.monotonic() - self.last_request_finished_at
        if elapsed_seconds < self.min_interval_seconds:
            time.sleep(self.min_interval_seconds - elapsed_seconds)

    def fetch(self, *args, **kwargs):
        # 父类 fetch 先调 wait_for_rate_limit 再发请求：这里包一层，在等待结束、真正发出前记下偏移秒数
        original_wait = self.wait_for_rate_limit
        start_offset_holder = {}

        def wait_then_mark_start():
            original_wait()
            start_offset_holder["t"] = time.monotonic() - self.run_started_monotonic

        self.wait_for_rate_limit = wait_then_mark_start
        try:
            return super().fetch(*args, **kwargs)
        finally:
            del self.wait_for_rate_limit  # 去掉实例属性，恢复类方法
            # 记录请求发出时距运行开始的秒数（判读配额回补要用）；父类在 fetch 里追加日志条目
            if "t" in start_offset_holder and self.request_log_entries \
                    and "t_offset_s" not in self.request_log_entries[-1]:
                self.request_log_entries[-1]["t_offset_s"] = round(start_offset_holder["t"], 1)
                self.request_log_entries[-1]["interval_setting_s"] = self.min_interval_seconds

    def idle(self, seconds, reason_text):
        base.log_message(f"空闲 {seconds} 秒：{reason_text}")
        time.sleep(seconds)


# ---------------------------------------------------------------------------
# 请求清单（dry-run 与执行共用同一份描述）
# ---------------------------------------------------------------------------
REQUEST_PLAN = [
    ("A", BURST_INTERVAL_SECONDS, "user/quota（段首；<4 即停止）", quota_save_name("A1")),
    ("A", BURST_INTERVAL_SECONDS, "user/quota", quota_save_name("A2")),
    ("A", BURST_INTERVAL_SECONDS, "user/quota", quota_save_name("A3")),
    ("idle", IDLE_BEFORE_BURST_SECONDS, "空闲，等配额回满", None),
    ("filelist", NORMAL_INTERVAL_SECONDS, "sub/search q=秋刀鱼之味 cnt=15 filelist=1", search_save_name("秋刀鱼之味")),
    ("filelist", NORMAL_INTERVAL_SECONDS, "sub/search q=肖申克的救赎 cnt=15 filelist=1", search_save_name("肖申克的救赎")),
    ("detail", NORMAL_INTERVAL_SECONDS, f"sub/detail id={DOWNLOAD_SUBTITLE_ID}（拿新下载链接）", detail_save_name()),
    ("idle", IDLE_BEFORE_BURST_SECONDS, "空闲，等配额回满", None),
    ("B", BURST_INTERVAL_SECONDS, "user/quota（段首；<4 即停止）", quota_save_name("B1")),
    ("B", BURST_INTERVAL_SECONDS, f"下载单文件 {SINGLE_FILE_NAME}（filelist 链接，不带 token）", SINGLE_FILE_SAVE_NAME),
    ("B", BURST_INTERVAL_SECONDS, f"下载整包 {DOWNLOAD_SUBTITLE_ID}（不带 token；与已有包相同则不另存）", "（比对 sha256）"),
    ("B", BURST_INTERVAL_SECONDS, "user/quota（段尾）", quota_save_name("B2")),
]


def print_request_plan():
    base.log_message(f"请求清单（run_tag={RUN_TAG}；上限 {MAX_REQUESTS_THIS_RUN} 次）：")
    request_number, total_seconds = 0, 0.0
    for segment, interval_seconds, description, save_name in REQUEST_PLAN:
        if segment == "idle":
            print(f"        —— {description} {interval_seconds} 秒")
            total_seconds += interval_seconds
            continue
        request_number += 1
        total_seconds += interval_seconds + 1.5  # 间隔 + 大约 1 秒响应时间
        print(f"    {request_number:>2}. [{segment:<8}] 间隔 {interval_seconds:>4.0f} 秒  {description:<52} → {save_name}")
    print(f"    合计 {request_number} 次请求（API {request_number - 2} 次 + 下载 2 次），预计约 {total_seconds / 60:.1f} 分钟")
    return request_number


# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------
def read_secret_token():
    """先读进程环境变量，读不到再读当前用户的环境变量（HKCU\\Environment）。值只在内存里用，不打印。"""
    token_value = os.environ.get("ASSRT_TOKEN", "")
    if not token_value and sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as registry_key:
                token_value, _ = winreg.QueryValueEx(registry_key, "ASSRT_TOKEN")
        except OSError:
            token_value = ""
    return token_value


def read_quota(client, redactor, secret_token, step_name, is_segment_start=False):
    response_json = base.call_api(client, redactor, secret_token, "user/quota", {}, quota_save_name(step_name))
    quota_value = ((response_json or {}).get("user") or {}).get("quota")
    if is_segment_start and (not isinstance(quota_value, int) or quota_value < MIN_QUOTA_AT_BURST_START):
        raise base.StopProbeRun(f"段首配额读数 {quota_value} < {MIN_QUOTA_AT_BURST_START}：可能有别的程序在用这个 token / IP，"
                                f"读数没法解释，停止")
    return quota_value


def download_once(client, request_label, download_url, save_name=None):
    """下载一次（不带 token）。返回响应体；非 200 时保存响应体，429 / 5xx 保存后停止运行。"""
    http_status, response_headers, response_body, final_url = client.fetch(
        request_label, download_url, bearer_token=None, max_body_bytes=base.MAX_ARCHIVE_BYTES,
        timeout_seconds=base.DOWNLOAD_TIMEOUT_SECONDS, network_error_is_fatal=True)
    log_entry = client.request_log_entries[-1]
    log_entry.update({"content_type": response_headers.get("Content-Type"),
                      "magic_format": base.detect_magic_format(response_body[:16]),
                      "sha256": hashlib.sha256(response_body).hexdigest()})
    if http_status != 200:
        error_save_name = f"download-error-{DOWNLOAD_SUBTITLE_ID}-{RUN_TAG}-http{http_status}.bin"
        (base.API_FIXTURE_DIR / error_save_name).write_bytes(response_body[:65536])
        log_entry["saved_as"] = error_save_name
        base.log_message(f"#{client.request_count:02d}/{MAX_REQUESTS_THIS_RUN} {request_label} → HTTP {http_status} "
                         f"{len(response_body)} 字节 → {error_save_name}")
        base.stop_if_fatal_http_status(http_status)
        return None
    if save_name:
        (base.API_FIXTURE_DIR / save_name).write_bytes(response_body)
        log_entry["saved_as"] = save_name
    base.log_message(f"#{client.request_count:02d}/{MAX_REQUESTS_THIS_RUN} {request_label} → HTTP {http_status} "
                     f"{len(response_body)} 字节 魔数={log_entry['magic_format']}"
                     + (f" → {save_name}" if save_name else "（只算 sha256，不另存）"))
    return response_body


def run_probe(client, redactor, secret_token):
    # A 段：quota ×3，2 秒间隔（第 1 次请求前没有间隔）
    client.min_interval_seconds = BURST_INTERVAL_SECONDS
    read_quota(client, redactor, secret_token, "A1", is_segment_start=True)
    read_quota(client, redactor, secret_token, "A2")
    read_quota(client, redactor, secret_token, "A3")

    # filelist 搜索 + 拿新下载链接，16 秒间隔
    client.idle(IDLE_BEFORE_BURST_SECONDS, "等配额回满，再做 filelist 搜索")
    client.min_interval_seconds = NORMAL_INTERVAL_SECONDS
    for film_key, query_text in FILELIST_SEARCHES:
        base.call_api(client, redactor, secret_token, "sub/search",
                      {"q": query_text, "cnt": 15, "filelist": 1}, search_save_name(film_key))
    detail_item = base.detail_item_of(base.call_api(client, redactor, secret_token, "sub/detail",
                                                    {"id": DOWNLOAD_SUBTITLE_ID}, detail_save_name()))
    if not detail_item or not detail_item.get("url"):
        raise base.StopProbeRun(f"detail {DOWNLOAD_SUBTITLE_ID} 没有下载链接，B 段无法进行")
    single_file_entry = next((entry for entry in detail_item.get("filelist") or []
                              if entry.get("f") == SINGLE_FILE_NAME and entry.get("url")), None)
    if not single_file_entry:
        raise base.StopProbeRun(f"detail {DOWNLOAD_SUBTITLE_ID} 的 filelist 里没有 {SINGLE_FILE_NAME} 的链接，B 段无法进行")

    # B 段：quota → 单文件 → 整包 → quota，2 秒间隔
    client.idle(IDLE_BEFORE_BURST_SECONDS, "等配额回满，再测下载是否计数")
    client.min_interval_seconds = BURST_INTERVAL_SECONDS
    read_quota(client, redactor, secret_token, "B1", is_segment_start=True)
    download_once(client, f"GET onthefly id={DOWNLOAD_SUBTITLE_ID} {SINGLE_FILE_NAME}",
                  single_file_entry["url"], save_name=SINGLE_FILE_SAVE_NAME)
    package_body = download_once(client, f"GET download id={DOWNLOAD_SUBTITLE_ID}（整包）", detail_item["url"])
    read_quota(client, redactor, secret_token, "B2")

    # 整包与已有 fixture 不同才另存
    existing_package_path = existing_package_fixture(detail_item)
    if package_body and (not existing_package_path or
                         hashlib.sha256(package_body).hexdigest() != sha256_of_file(existing_package_path)):
        changed_save_name = f"{DOWNLOAD_FILM_KEY}-package-{DOWNLOAD_SUBTITLE_ID}-{RUN_TAG}.zip"
        (base.API_FIXTURE_DIR / changed_save_name).write_bytes(package_body)
        client.request_log_entries[-2]["saved_as"] = changed_save_name
        base.log_message(f"整包与已有 fixture 不同，另存 → {changed_save_name}")


# ---------------------------------------------------------------------------
# 分析：只读已保存的文件，可以用 --analyze 离线重跑
# ---------------------------------------------------------------------------
def sha256_of_file(file_path):
    return hashlib.sha256(Path(file_path).read_bytes()).hexdigest()


def existing_package_fixture(detail_item):
    """archives/assrt/ 里 P2-B 下载的同一个包（按 detail 的文件名定位）。"""
    file_name = base.sanitize_file_name(base.detail_file_name(detail_item), "")
    candidate_path = base.ARCHIVE_FIXTURE_DIR / file_name
    return candidate_path if file_name and candidate_path.is_file() else None


def load_fixture_if_exists(save_name):
    fixture_path = base.API_FIXTURE_DIR / save_name
    return json.loads(fixture_path.read_text(encoding="utf-8")) if fixture_path.is_file() else None


def earlier_detail_filelist(subtitle_id):
    """P2-B 保存的 detail（不带 run_tag 的那份）里的文件名清单；没有就返回 None。"""
    for detail_path in sorted(base.API_FIXTURE_DIR.glob(f"*-detail-{subtitle_id}.json")):
        detail_item = base.detail_item_of(json.loads(detail_path.read_text(encoding="utf-8")))
        if detail_item is not None:
            return [entry.get("f") for entry in detail_item.get("filelist") or []]
    return None


def analyze_filelist_search(film_key):
    search_json = load_fixture_if_exists(search_save_name(film_key))
    if search_json is None:
        return None
    item_reports = []
    for subtitle_item in base.subs_of(search_json):
        filelist_value = subtitle_item.get("filelist", "<缺失>")
        filelist_names = ([entry.get("f") for entry in filelist_value if isinstance(entry, dict)]
                          if isinstance(filelist_value, list) else None)
        entry_keys = sorted({key for entry in filelist_value if isinstance(entry, dict) for key in entry}) \
            if isinstance(filelist_value, list) else None
        detail_names = earlier_detail_filelist(subtitle_item.get("id"))
        item_reports.append({
            "id": subtitle_item.get("id"),
            "filelist_type": type(filelist_value).__name__ if filelist_value != "<缺失>" else "missing",
            "file_count": len(filelist_names) if filelist_names is not None else None,
            "entry_keys": entry_keys,
            "has_url": any(isinstance(entry, dict) and entry.get("url") for entry in filelist_value)
            if isinstance(filelist_value, list) else None,
            "names": filelist_names,
            "matches_earlier_detail": (filelist_names == detail_names) if detail_names is not None else None,
            "item_keys": sorted(subtitle_item.keys()),
        })
    return {"status": search_json.get("status"), "count": len(item_reports), "items": item_reports}


def analyze_downloads(run_log_requests):
    report = {}
    single_file_path = base.API_FIXTURE_DIR / SINGLE_FILE_SAVE_NAME
    detail_item = base.detail_item_of(load_fixture_if_exists(detail_save_name()) or {})
    package_path = existing_package_fixture(detail_item) if detail_item else None
    if single_file_path.is_file():
        single_sha256 = sha256_of_file(single_file_path)
        report["single_file"] = {"bytes": single_file_path.stat().st_size, "sha256": single_sha256}
        if package_path:
            # 只读 zip 里各成员的字节算 sha256，不解压；成员名用原始字节，不做编码回转（只比内容）
            with zipfile.ZipFile(package_path) as package_zip:
                matching_members = [member.orig_filename for member in package_zip.infolist()
                                    if hashlib.sha256(package_zip.read(member)).hexdigest() == single_sha256]
            report["single_file"]["matches_member_of_existing_package"] = bool(matching_members)
            report["single_file"]["matching_member_raw_names"] = matching_members
    package_entries = [entry for entry in run_log_requests if "（整包）" in entry.get("label", "")]
    if package_entries and package_path:
        report["package"] = {"downloaded_sha256": package_entries[-1].get("sha256"),
                             "existing_fixture": package_path.name,
                             "existing_sha256": sha256_of_file(package_path)}
        report["package"]["identical"] = report["package"]["downloaded_sha256"] == report["package"]["existing_sha256"]
    return report


def analyze_quota(run_log_requests):
    readings = {}
    for entry in run_log_requests:
        match = re.search(r"quota-r\d+-(\w+)\.json", entry.get("saved_as") or "")
        if match and "quota" in entry:
            readings[match.group(1)] = {"quota": entry["quota"], "t_offset_s": entry.get("t_offset_s"),
                                        "time": entry.get("time")}
    return readings


def analyze(run_log_requests):
    return {
        "quota_readings": analyze_quota(run_log_requests),
        "filelist_search": {film_key: analyze_filelist_search(film_key) for film_key, _ in FILELIST_SEARCHES},
        "downloads": analyze_downloads(run_log_requests),
    }


def print_analysis(findings):
    base.log_message("分析：")
    print("  配额读数：" + "，".join(f"{step}={value['quota']}（+{value['t_offset_s']}s）"
                                   for step, value in findings["quota_readings"].items()))
    for film_key, film_report in findings["filelist_search"].items():
        if not film_report:
            print(f"  {film_key}：没有 filelist 搜索结果文件")
            continue
        print(f"  {film_key}：status={film_report['status']}，{film_report['count']} 条")
        for item in film_report["items"]:
            print(f"    id={item['id']} filelist={item['filelist_type']} 文件数={item['file_count']} "
                  f"键={item['entry_keys']} 有url={item['has_url']} 与旧detail一致={item['matches_earlier_detail']}")
    print("  下载：" + json.dumps(findings["downloads"], ensure_ascii=False))


def write_run_log(client, redactor, stop_reason, findings):
    run_log = {
        "generated_at": time.strftime("%Y-%m-%d ") + base.format_time_12h(),
        "run_tag": RUN_TAG,
        "request_count": client.request_count,
        "max_requests_per_run": MAX_REQUESTS_THIS_RUN,
        "intervals": {"normal_s": NORMAL_INTERVAL_SECONDS, "burst_s": BURST_INTERVAL_SECONDS,
                      "idle_before_burst_s": IDLE_BEFORE_BURST_SECONDS},
        "stop_reason": stop_reason,
        "requests": client.request_log_entries,
        "findings": findings,
    }
    log_text = redactor.redact_text(json.dumps(run_log, ensure_ascii=False, indent=2))
    (base.API_FIXTURE_DIR / f"_run-log-{RUN_TAG}.json").write_text(log_text, encoding="utf-8")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    argument_parser = argparse.ArgumentParser(description="ASSRT 补测：filelist 与配额计数（P3-A）")
    argument_parser.add_argument("--dry-run", action="store_true", help="只打印请求清单，不联网")
    argument_parser.add_argument("--analyze", action="store_true", help="只根据已保存的文件重新分析，不联网")
    arguments = argument_parser.parse_args()
    run_log_path = base.API_FIXTURE_DIR / f"_run-log-{RUN_TAG}.json"

    if arguments.analyze:
        if not run_log_path.is_file():
            base.log_message(f"{run_log_path.name} 不存在，先执行一次")
            return 2
        run_log = json.loads(run_log_path.read_text(encoding="utf-8"))
        run_log["findings"] = analyze(run_log["requests"])
        run_log_path.write_text(json.dumps(run_log, ensure_ascii=False, indent=2), encoding="utf-8")
        print_analysis(run_log["findings"])
        return 0

    planned_request_count = print_request_plan()
    if planned_request_count > MAX_REQUESTS_THIS_RUN:
        base.log_message(f"清单 {planned_request_count} 次超过上限 {MAX_REQUESTS_THIS_RUN}，请先调整")
        return 2
    if arguments.dry_run:
        base.log_message("dry-run 结束，请求 0 次")
        return 0
    if run_log_path.is_file():
        base.log_message(f"{run_log_path.name} 已存在，拒绝覆盖之前的运行记录；请求 0 次")
        return 2

    secret_token = read_secret_token()
    if not re.fullmatch(r"[A-Za-z0-9]{32}", secret_token or ""):
        base.log_message("ASSRT_TOKEN 未设置或格式不对（应为 32 位字母数字），请求 0 次，退出")
        return 2

    redactor = base.TokenRedactor(secret_token)
    client = SwitchableIntervalClient(redactor)
    base.API_FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    stop_reason, findings = None, None
    try:
        run_probe(client, redactor, secret_token)
    except base.StopProbeRun as stop_error:
        stop_reason = str(stop_error)
        base.log_message(f"提前停止：{stop_reason}")
    finally:
        findings = analyze(client.request_log_entries)
        write_run_log(client, redactor, stop_reason, findings)
        base.log_message(f"结束：共发出 {client.request_count}/{MAX_REQUESTS_THIS_RUN} 次请求；"
                         f"运行日志 → tests/fixtures/assrt/{run_log_path.name}")
    print_analysis(findings)
    return 1 if stop_reason else 0


if __name__ == "__main__":
    sys.exit(main())
