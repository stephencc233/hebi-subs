"""
SubHD 页面离线解析探针（P2-A P2-subhd-probe）

用途：
    解析手动保存的 SubHD 网页（搜索页 /search/、影片页 /d/、字幕详情页 /a/），
    输出对齐 D014 候选模型的 JSON，用来验证「列表页能拿到哪些字段、是不是服务器直接给出」。
    这是探针脚本，不是插件代码；P4 写 SubHD Provider 时参考这里的选择器，不直接复用。

适用情况：
    - 输入是浏览器「另存为」的网页：
        * xxx.raw.html：Chrome 打开 view-source: 后另存，源码被包在 <td class="line-content"> 里并做了转义，
          脚本会先「解包」还原成服务器原始 HTML（= 服务器直接给出的内容）；
        * xxx.rendered.html：浏览器保存的完整网页（= JS 执行后的 DOM）。
    - 不联网、不发任何请求；下载按钮只记录结构，不触发。

如何使用（用仓库 .venv 的解释器，-I 隔离模式）：
    .venv\\Scripts\\python.exe -I scripts\\subhd_parse_probe.py tests\\fixtures\\subhd --out-dir tests\\fixtures\\subhd\\parsed
    .venv\\Scripts\\python.exe -I scripts\\subhd_parse_probe.py tests\\fixtures\\subhd --compare-raw-rendered --out-dir tests\\fixtures\\subhd\\parsed
    输入可以是文件或目录（目录下的 *.html 全部解析）。

输出字段（D014）：
    title, sid, detail_url, download_count, release_group, uploader, upload_time, rating,
    source_type, language_tags, format, source_rank
    拿不到的字段一律输出 null（不输出 0）；源站特有信息放 raw_extra。

依赖（全部标准库）：
    html.parser.HTMLParser —— 把 HTML 建成一棵最小 DOM 树，便于按 class / href 查找
    （HTMLParser 的 convert_charrefs 同时负责还原 view-source 页面里被转义的源码）
    re                    —— 匹配 URL 路径、数字、"共 N 条" 等文本
    json / argparse / pathlib / datetime —— 输出、命令行、路径、日志时刻
"""

import argparse
import datetime
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

# 站点根地址：保存页面的 saved-from 是 subhd.tv，canonical 是 subhd.me（两个域名并存），
# detail_url 统一按页面自己的来源域名拼接，拿不到时退回这个默认值
DEFAULT_SITE_ROOT = "https://subhd.tv"

# HTML 中没有结束标签的空元素：建树时遇到它们不入栈
VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "source", "track", "wbr",
}


# ---------------------------------------------------------------------------
# 日志：显示时刻用 12 小时制并标 AM/PM（CLAUDE.md 代码规范）
# ---------------------------------------------------------------------------
def log_message(message_text):
    timestamp_12h = datetime.datetime.now().strftime("%I:%M:%S %p")
    print(f"[{timestamp_12h}] {message_text}")


# ---------------------------------------------------------------------------
# 第 1 层：最小 DOM 树（HTMLParser 只给事件流，这里把事件流组装成树）
# ---------------------------------------------------------------------------
class HtmlNode:
    """一个元素节点：标签名、属性字典、子节点列表（子节点是 HtmlNode 或 str 文本）。"""

    def __init__(self, tag_name, attribute_dict, parent_node):
        self.tag_name = tag_name
        self.attribute_dict = attribute_dict
        self.parent_node = parent_node
        self.child_list = []

    # 取属性（不存在返回空串，方便直接做字符串判断）
    def attr(self, attribute_name):
        return self.attribute_dict.get(attribute_name) or ""

    def class_set(self):
        return set(self.attr("class").split())

    def has_classes(self, *required_class_names):
        return set(required_class_names) <= self.class_set()

    # 节点下全部文本，空白折叠成一个空格
    def text_content(self):
        text_piece_list = []

        def collect_text(node):
            for child in node.child_list:
                if isinstance(child, str):
                    text_piece_list.append(child)
                else:
                    collect_text(child)

        collect_text(self)
        return re.sub(r"\s+", " ", "".join(text_piece_list)).strip()

    # 深度优先遍历所有后代元素（文档顺序）
    def iter_descendants(self):
        for child in self.child_list:
            if isinstance(child, HtmlNode):
                yield child
                yield from child.iter_descendants()

    def find_all(self, predicate):
        return [node for node in self.iter_descendants() if predicate(node)]

    def find_first(self, predicate):
        for node in self.iter_descendants():
            if predicate(node):
                return node
        return None


class MinimalDomBuilder(HTMLParser):
    """把 HTML 解析成 HtmlNode 树；对未闭合标签做宽容处理（结束标签向上找最近的同名节点）。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root_node = HtmlNode("#document", {}, None)
        self.current_node = self.root_node
        self.comment_list = []

    def handle_starttag(self, tag, attrs):
        new_node = HtmlNode(tag, dict(attrs), self.current_node)
        self.current_node.child_list.append(new_node)
        if tag not in VOID_ELEMENTS:
            self.current_node = new_node

    def handle_startendtag(self, tag, attrs):
        # <path ... /> 这类自闭合标签：挂到当前节点下，不入栈
        self.current_node.child_list.append(HtmlNode(tag, dict(attrs), self.current_node))

    def handle_endtag(self, tag):
        probe_node = self.current_node
        while probe_node is not None and probe_node.tag_name != tag:
            probe_node = probe_node.parent_node
        if probe_node is not None and probe_node.parent_node is not None:
            self.current_node = probe_node.parent_node

    def handle_data(self, data):
        self.current_node.child_list.append(data)

    def handle_comment(self, data):
        self.comment_list.append(data)


def build_dom_tree(html_text):
    dom_builder = MinimalDomBuilder()
    dom_builder.feed(html_text)
    dom_builder.close()
    return dom_builder.root_node


# ---------------------------------------------------------------------------
# 第 2 层：输入预处理（view-source 解包、来源 URL、页面类型）
# ---------------------------------------------------------------------------
def extract_saved_from_url(saved_html_text):
    """浏览器另存网页时在文件头写的 <!-- saved from url=(N)URL -->。"""
    match = re.search(r"<!-- saved from url=\(\d+\)(\S+?) -->", saved_html_text[:500])
    return match.group(1) if match else None


def is_view_source_wrapper(saved_html_text):
    return 'class="line-content"' in saved_html_text and 'class="line-number"' in saved_html_text


def unwrap_view_source_html(saved_html_text):
    """
    view-source 另存页 → 服务器原始 HTML。
    原理：Chrome 把源码每一行放进 <td class="line-content">，标签被拆成带高亮 class 的 <span>，
    源码字符被转义成文本；所以「取每个 line-content 单元格的纯文本、按行拼接」即可还原源码。
    非包装格式（rendered 页）原样返回。
    """
    if not is_view_source_wrapper(saved_html_text):
        return saved_html_text
    wrapper_tree = build_dom_tree(saved_html_text)
    source_line_list = []
    for cell_node in wrapper_tree.find_all(lambda node: node.tag_name == "td" and node.has_classes("line-content")):
        line_piece_list = []

        def collect_raw_text(node):
            for child in node.child_list:
                if isinstance(child, str):
                    line_piece_list.append(child)
                else:
                    collect_raw_text(child)

        collect_raw_text(cell_node)
        source_line_list.append("".join(line_piece_list))
    # convert_charrefs=True 时 HTMLParser 已把 &lt; &amp; 等实体还原成字符，拼接后就是原始源码
    return "\n".join(source_line_list)


def find_canonical_url(dom_root):
    link_node = dom_root.find_first(lambda node: node.tag_name == "link" and node.attr("rel") == "canonical")
    if link_node:
        return link_node.attr("href")
    meta_node = dom_root.find_first(lambda node: node.tag_name == "meta" and node.attr("property") == "og:url")
    return meta_node.attr("content") if meta_node else None


def detect_page_type(page_url):
    """按 URL 路径判断页面类型：search / movie（/d/豆瓣ID）/ subtitle_detail（/a/sid）。"""
    if not page_url:
        return "unknown"
    if re.search(r"/search/", page_url):
        return "search"
    if re.search(r"/d/\d+", page_url):
        return "movie"
    if re.search(r"/a/[A-Za-z0-9_-]+", page_url):
        return "subtitle_detail"
    return "unknown"


def site_root_of(page_url):
    match = re.match(r"(https?://[^/]+)", page_url or "")
    return match.group(1) if match else DEFAULT_SITE_ROOT


# ---------------------------------------------------------------------------
# 第 3 层：字段提取小工具
# ---------------------------------------------------------------------------
def href_matches(node, path_pattern):
    """按 href 的路径部分匹配：raw 里是相对路径 /a/xxx，浏览器另存的 rendered 页会被改写成绝对地址。"""
    return node.tag_name == "a" and re.match(path_pattern, urlparse(node.attr("href")).path) is not None


def parse_int_or_none(text_value):
    """'3978' → 3978；空串或非纯数字 → None（拿不到就是 None，不是 0）。"""
    cleaned_text = (text_value or "").replace(",", "").strip()
    return int(cleaned_text) if cleaned_text.isdigit() else None


def extract_tag_badges(container_node):
    """
    卡片 / 行 / 详情页共用的标签区：
        来源徽章 span.rounded.text-white（背景色区分：官方字幕 / 原创翻译 / 其他来源…）
        语言 span.p-1.fw-bold（含「双语」）
        格式 span.p-1.text-secondary（SRT / ASS …）
    """
    badge_node = container_node.find_first(
        lambda node: node.tag_name == "span" and node.has_classes("rounded", "text-white"))
    language_tag_list = [node.text_content() for node in container_node.find_all(
        lambda node: node.tag_name == "span" and node.has_classes("p-1", "fw-bold"))]
    format_list = [node.text_content() for node in container_node.find_all(
        lambda node: node.tag_name == "span" and node.has_classes("p-1", "text-secondary"))]
    badge_color_match = re.search(r"background-color:\s*(#[0-9a-fA-F]+)", badge_node.attr("style")) if badge_node else None
    return {
        "source_type": badge_node.text_content() if badge_node else None,
        "source_type_color": badge_color_match.group(1) if badge_color_match else None,
        "language_tags": language_tag_list or None,
        "format": format_list or None,
    }


def extract_release_group(container_node):
    """字幕组（制作组）：可选的 a[href^="/zu/"]；没有就是 None。"""
    group_link_node = container_node.find_first(lambda node: href_matches(node, r"/zu/\d+"))
    if not group_link_node:
        return None, None
    return group_link_node.text_content(), group_link_node.attr("href").split("/")[-1]


def extract_uploader(container_node):
    """
    发布人 / 上传人：a[href^="/u/"]。详情页还有一个头像链接，没有头像图时里面是用户名首字母（如「S」），
    所以优先取带 fw-bold 的用户名链接，退回时用 href 路径里的用户名，不用头像链接的文字。
    """
    user_link_list = container_node.find_all(lambda node: href_matches(node, r"/u/[^/]+"))
    for user_link_node in user_link_list:
        if user_link_node.has_classes("fw-bold") and user_link_node.text_content():
            return user_link_node.text_content()
    for user_link_node in user_link_list:
        if user_link_node.text_content():
            return unquote(urlparse(user_link_node.attr("href")).path.split("/u/")[-1])
    return None


def extract_upload_time(container_node):
    """上传时间取 <time datetime="ISO">：显示文字会被页面 JS 改成访问者本地时区，属性值才可靠。"""
    time_node = container_node.find_first(lambda node: node.tag_name == "time")
    if not time_node:
        return None, None
    return time_node.attr("datetime") or None, time_node.text_content() or None


def extract_icon_labeled_stats(stats_container_node):
    """
    搜索页卡片的统计行：每个数值 <span> 前面有一个 Bootstrap 图标 <svg class="bi bi-xxx">，
    按「最近一个图标」给后面的 span 定性：bi-file-earmark-fill=大小，bi-download=下载数，bi-clock-fill=时间。
    """
    labeled_stat_dict = {}
    last_icon_name = None
    for child in stats_container_node.child_list:
        if not isinstance(child, HtmlNode):
            continue
        if child.tag_name == "svg":
            icon_class_list = [name for name in child.class_set() if name.startswith("bi-")]
            last_icon_name = icon_class_list[0] if icon_class_list else None
        elif child.tag_name == "span" and last_icon_name:
            labeled_stat_dict[last_icon_name] = child.text_content()
            last_icon_name = None
    return labeled_stat_dict


def extract_list_engagement_counts(container_node):
    """
    列表页（搜索卡片 / 影片页行）标签区后面的两个小计数，**只在大于 0 时才出现**：
        评论数 span.p-1.text-primary（内含 svg.bi-chat）
        「支持」点赞数 span.p-1.text-danger > span.align-baseline（红色大拇指）
    元素不存在时返回 None（实际多半是 0，但按 D014「拿不到记为无」处理，由核心层决定怎么解释）。
    """
    comment_span_node = container_node.find_first(
        lambda node: node.tag_name == "span" and node.has_classes("p-1", "text-primary")
        and node.find_first(lambda inner: inner.tag_name == "svg" and inner.has_classes("bi-chat")))
    like_span_node = container_node.find_first(
        lambda node: node.tag_name == "span" and node.has_classes("p-1", "text-danger"))
    like_value_node = like_span_node.find_first(
        lambda node: node.tag_name == "span" and node.has_classes("align-baseline")) if like_span_node else None
    return {
        "comment_count": parse_int_or_none(comment_span_node.text_content()) if comment_span_node else None,
        "like_count": parse_int_or_none(like_value_node.text_content()) if like_value_node else None,
    }


def guess_video_release_group(release_name):
    """
    从片源版本名末尾的「-XXX」推断视频压制组（如 -CMCT、-usury）。
    注意：这是视频的压制组，不是字幕制作组；两者分开存，标注为推断值。
    """
    match = re.search(r"-([A-Za-z0-9]+)$", (release_name or "").strip())
    return match.group(1) if match else None


def empty_candidate():
    """D014 字段骨架：全部 None，拿到才填。"""
    return {
        "title": None, "sid": None, "detail_url": None, "download_count": None,
        "release_group": None, "uploader": None, "upload_time": None, "rating": None,
        "source_type": None, "language_tags": None, "format": None, "source_rank": None,
        "raw_extra": {},
    }


# ---------------------------------------------------------------------------
# 第 4 层：三种页面的解析器
# ---------------------------------------------------------------------------
def parse_search_page(dom_root, site_root):
    """
    搜索页 /search/{关键词}[/{页码}]：每条字幕是一张卡片 div.bg-white.shadow-sm.rounded-3.mb-4。
    关键词是模糊匹配，可能混入别的影片（卡片里的 /d/{豆瓣ID} 用来做身份过滤）。
    """
    card_node_list = [node for node in dom_root.find_all(
        lambda node: node.tag_name == "div" and node.has_classes("bg-white", "shadow-sm", "rounded-3", "mb-4"))
        if node.find_first(lambda inner: href_matches(inner, r"/a/"))]
    candidate_list = []
    for card_index, card_node in enumerate(card_node_list, start=1):
        candidate = empty_candidate()
        release_link_node = card_node.find_first(
            lambda node: node.tag_name == "div" and node.has_classes("view-text"))
        detail_link_node = card_node.find_first(lambda node: href_matches(node, r"/a/[A-Za-z0-9_-]+"))
        movie_title_node = card_node.find_first(
            lambda node: href_matches(node, r"/a/") and node.has_classes("align-middle"))
        movie_link_node = card_node.find_first(lambda node: href_matches(node, r"/d/\d+"))
        stats_row_node = card_node.find_first(
            lambda node: node.tag_name == "div" and node.has_classes("pt-2", "text-secondary", "f12"))
        engagement_count_dict = extract_list_engagement_counts(card_node)

        sid_value = detail_link_node.attr("href").split("/a/")[-1]
        labeled_stat_dict = extract_icon_labeled_stats(stats_row_node) if stats_row_node else {}
        upload_time_iso, upload_time_display = extract_upload_time(card_node)
        release_group_name, release_group_id = extract_release_group(card_node)
        tag_badge_dict = extract_tag_badges(card_node)

        candidate.update({
            "title": release_link_node.text_content() if release_link_node else None,
            "sid": sid_value,
            "detail_url": urljoin(site_root, f"/a/{sid_value}"),
            "download_count": parse_int_or_none(labeled_stat_dict.get("bi-download")),
            "release_group": release_group_name,
            "uploader": extract_uploader(card_node),
            "upload_time": upload_time_iso,
            "rating": None,  # SubHD 列表页没有评分
            "source_type": tag_badge_dict["source_type"],
            "language_tags": tag_badge_dict["language_tags"],
            "format": tag_badge_dict["format"],
            "source_rank": card_index,
        })
        candidate["raw_extra"] = {
            "movie_title": movie_title_node.text_content() if movie_title_node else None,
            "douban_id": movie_link_node.attr("href").split("/d/")[-1] if movie_link_node else None,
            "release_group_id": release_group_id,
            "source_type_color": tag_badge_dict["source_type_color"],
            "size_text": labeled_stat_dict.get("bi-file-earmark-fill"),
            "comment_count": engagement_count_dict["comment_count"],
            "like_count": engagement_count_dict["like_count"],
            "upload_time_display": upload_time_display,
            "video_release_group_guess": guess_video_release_group(
                release_link_node.text_content() if release_link_node else None),
        }
        candidate_list.append(candidate)
    return candidate_list


def parse_movie_page(dom_root, site_root, page_url):
    """
    影片页 /d/{豆瓣ID}：表头「字幕信息 / 下载次数 / 上传人」，每条字幕一行 div.row.pt-2.mb-2；
    没有大小；全部字幕一页列出（样本最多 36 条，未见分页）。
    """
    douban_id_match = re.search(r"/d/(\d+)", page_url or "")
    row_node_list = [node for node in dom_root.find_all(
        lambda node: node.tag_name == "div" and node.has_classes("row", "pt-2", "mb-2"))
        if node.find_first(lambda inner: href_matches(inner, r"/a/"))]
    candidate_list = []
    for row_index, row_node in enumerate(row_node_list, start=1):
        candidate = empty_candidate()
        detail_link_node = row_node.find_first(lambda node: href_matches(node, r"/a/[A-Za-z0-9_-]+"))
        download_cell_node = row_node.find_first(
            lambda node: node.tag_name == "div" and node.has_classes("text-end", "text-secondary"))
        sid_value = detail_link_node.attr("href").split("/a/")[-1]
        upload_time_iso, upload_time_display = extract_upload_time(row_node)
        release_group_name, release_group_id = extract_release_group(row_node)
        tag_badge_dict = extract_tag_badges(row_node)
        engagement_count_dict = extract_list_engagement_counts(row_node)

        candidate.update({
            "title": detail_link_node.text_content(),
            "sid": sid_value,
            "detail_url": urljoin(site_root, f"/a/{sid_value}"),
            "download_count": parse_int_or_none(download_cell_node.text_content()) if download_cell_node else None,
            "release_group": release_group_name,
            "uploader": extract_uploader(row_node),
            "upload_time": upload_time_iso,
            "rating": None,
            "source_type": tag_badge_dict["source_type"],
            "language_tags": tag_badge_dict["language_tags"],
            "format": tag_badge_dict["format"],
            "source_rank": row_index,
        })
        candidate["raw_extra"] = {
            "douban_id": douban_id_match.group(1) if douban_id_match else None,
            "release_group_id": release_group_id,
            "source_type_color": tag_badge_dict["source_type_color"],
            "comment_count": engagement_count_dict["comment_count"],
            "like_count": engagement_count_dict["like_count"],
            "upload_time_display": upload_time_display,
            "video_release_group_guess": guess_video_release_group(detail_link_node.text_content()),
        }
        candidate_list.append(candidate)
    return candidate_list


def parse_subtitle_detail_page(dom_root, site_root):
    """
    字幕详情页 /a/{sid}：片源版本、字幕组、标签、统计（大小 / 下载数 / 时间）、发布人、
    「支持」点赞数、包内文件清单，以及下载按钮结构（只描述，不触发）。
    """
    candidate = empty_candidate()
    download_button_node = dom_root.find_first(
        lambda node: node.tag_name == "button" and node.has_classes("subtitle-prepare-download"))
    edition_node = dom_root.find_first(lambda node: node.has_classes("subtitle-edition"))
    metadata_tags_node = dom_root.find_first(lambda node: node.has_classes("subtitle-metadata-tags"))
    metadata_stats_node = dom_root.find_first(lambda node: node.has_classes("subtitle-metadata-stats"))
    publisher_row_node = dom_root.find_first(lambda node: node.has_classes("subtitle-publisher-row"))
    edition_block_node = edition_node.parent_node if edition_node else None
    like_count_node = dom_root.find_first(lambda node: node.tag_name == "span" and node.has_classes("upv"))
    breadcrumb_movie_node = dom_root.find_first(lambda node: href_matches(node, r"/d/\d+"))
    preview_container_node = dom_root.find_first(lambda node: node.attr("id") == "subtitleFilePreview")

    # 统计区没有图标，按顺序是 [大小, 下载数, 时间]（3 个样本页一致）
    stat_span_list = [child for child in (metadata_stats_node.child_list if metadata_stats_node else [])
                      if isinstance(child, HtmlNode) and child.tag_name == "span"]
    size_text = stat_span_list[0].text_content() if len(stat_span_list) >= 1 else None
    download_text = stat_span_list[1].text_content() if len(stat_span_list) >= 2 else None
    upload_time_iso, upload_time_display = extract_upload_time(metadata_stats_node) if metadata_stats_node else (None, None)
    release_group_name, release_group_id = extract_release_group(edition_block_node) if edition_block_node else (None, None)
    tag_badge_dict = extract_tag_badges(metadata_tags_node) if metadata_tags_node else {
        "source_type": None, "source_type_color": None, "language_tags": None, "format": None}
    total_uploads_match = re.search(r"总共发布过字幕\s*(\d+)\s*条",
                                    publisher_row_node.text_content() if publisher_row_node else "")

    # 包内文件清单：a.subtitle-file-name 的 data-filename 是完整包内路径，后面的 span 是大小
    archive_member_list = []
    for file_row_node in dom_root.find_all(lambda node: node.has_classes("subtitle-file-row")):
        file_link_node = file_row_node.find_first(lambda node: node.has_classes("subtitle-file-name"))
        file_size_node = file_row_node.find_first(lambda node: node.has_classes("subtitle-file-size"))
        archive_member_list.append({
            "path_in_archive": file_link_node.attr("data-filename") if file_link_node else None,
            "size_text": file_size_node.text_content() if file_size_node else None,
        })

    sid_value = download_button_node.attr("data-sid") if download_button_node else None
    candidate.update({
        "title": edition_node.text_content() if edition_node else None,
        "sid": sid_value,
        "detail_url": urljoin(site_root, f"/a/{sid_value}") if sid_value else None,
        "download_count": parse_int_or_none(download_text),
        "release_group": release_group_name,
        "uploader": extract_uploader(publisher_row_node) if publisher_row_node else None,
        "upload_time": upload_time_iso,
        "rating": None,  # 没有评分，只有「支持」点赞数（见 raw_extra.like_count）
        "source_type": tag_badge_dict["source_type"],
        "language_tags": tag_badge_dict["language_tags"],
        "format": tag_badge_dict["format"],
        "source_rank": None,  # 详情页没有列表位置
    })
    candidate["raw_extra"] = {
        "douban_id": breadcrumb_movie_node.attr("href").split("/d/")[-1] if breadcrumb_movie_node else None,
        "release_group_id": release_group_id,
        "source_type_color": tag_badge_dict["source_type_color"],
        "size_text": size_text,
        "upload_time_display": upload_time_display,
        "like_count": parse_int_or_none(like_count_node.text_content()) if like_count_node else None,
        "uploader_total_uploads": int(total_uploads_match.group(1)) if total_uploads_match else None,
        "archive_members": archive_member_list or None,
        "preview_api_path": preview_container_node.attr("data-preview-url") if preview_container_node else None,
        "download_button": {
            "tag": download_button_node.tag_name,
            "class": download_button_node.attr("class"),
            "data_sid": sid_value,
            "data_loading_text": download_button_node.attr("data-loading-text") or None,
            "data_error_text": download_button_node.attr("data-error-text") or None,
            "note": "点击由 subhd.js 处理：POST /api/sub/prepare-download {sid} → JSON {success,url:'/down/…'} → 浏览器跳转（本脚本不触发）",
        } if download_button_node else None,
        "video_release_group_guess": guess_video_release_group(edition_node.text_content() if edition_node else None),
    }
    return candidate


def extract_list_page_navigation(dom_root):
    """列表页的结果总数、当前页、分页链接、排序选项（影片页有「默认排序 / 按时间」下拉）。"""
    heading_text = " ".join(node.text_content() for node in dom_root.find_all(lambda node: node.tag_name == "h4"))
    total_match = re.search(r"共\s*(\d+)\s*条\s*当前第\s*(\d+)\s*页", heading_text)
    pagination_link_list = sorted({unquote(node.attr("href")) for node in dom_root.find_all(
        lambda node: node.tag_name == "a" and node.has_classes("page-link"))})
    sort_option_list = [{"label": node.text_content(), "href": node.attr("href"), "active": node.has_classes("active")}
                        for node in dom_root.find_all(
                            lambda node: node.tag_name == "a" and node.has_classes("dropdown-item")
                            and "/d/" in node.attr("href"))]
    return {
        "total_results": int(total_match.group(1)) if total_match else None,
        "current_page": int(total_match.group(2)) if total_match else None,
        "pagination_links": pagination_link_list or None,
        "sort_options": sort_option_list or None,
    }


# ---------------------------------------------------------------------------
# 第 5 层：单文件解析入口 + raw / rendered 对比
# ---------------------------------------------------------------------------
def parse_saved_page(input_file_path):
    saved_html_text = input_file_path.read_text(encoding="utf-8")
    input_kind = "raw(view-source)" if is_view_source_wrapper(saved_html_text) else "rendered(dom)"
    saved_from_url = extract_saved_from_url(saved_html_text)
    page_source_text = unwrap_view_source_html(saved_html_text)
    dom_root = build_dom_tree(page_source_text)
    canonical_url = find_canonical_url(dom_root)
    page_url = saved_from_url or canonical_url
    page_type = detect_page_type(page_url)
    site_root = site_root_of(page_url)

    result = {
        "input_file": input_file_path.name,
        "input_kind": input_kind,
        "saved_from_url": unquote(saved_from_url) if saved_from_url else None,
        "canonical_url": canonical_url,
        "page_type": page_type,
        "parsed_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    if page_type == "search":
        result["navigation"] = extract_list_page_navigation(dom_root)
        result["candidates"] = parse_search_page(dom_root, site_root)
    elif page_type == "movie":
        result["navigation"] = extract_list_page_navigation(dom_root)
        result["candidates"] = parse_movie_page(dom_root, site_root, page_url)
    elif page_type == "subtitle_detail":
        result["detail"] = parse_subtitle_detail_page(dom_root, site_root)
    return result


def compare_raw_and_rendered(raw_result, rendered_result):
    """
    同一页面 raw（服务器原始 HTML）vs rendered（JS 执行后 DOM）：
    逐条按 sid 比较 D014 字段。raw 里有值 = 服务器直接给出；只有 rendered 有 = JS 渲染。
    """
    compared_field_list = ["title", "download_count", "release_group", "uploader", "upload_time",
                           "source_type", "language_tags", "format", "source_rank"]
    raw_by_sid = {item["sid"]: item for item in raw_result.get("candidates", [])}
    rendered_by_sid = {item["sid"]: item for item in rendered_result.get("candidates", [])}
    field_report_dict = {}
    for field_name in compared_field_list:
        field_report_dict[field_name] = {
            "non_null_in_raw": sum(1 for item in raw_by_sid.values() if item[field_name] is not None),
            "non_null_in_rendered": sum(1 for item in rendered_by_sid.values() if item[field_name] is not None),
            "value_mismatch_sids": [sid for sid in raw_by_sid if sid in rendered_by_sid
                                    and raw_by_sid[sid][field_name] != rendered_by_sid[sid][field_name]],
        }
    # raw_extra 里的列表页附加字段也一起比（大小、评论数、点赞数、字幕组 ID）
    for extra_field_name in ["size_text", "comment_count", "like_count", "release_group_id"]:
        field_report_dict["raw_extra." + extra_field_name] = {
            "non_null_in_raw": sum(1 for item in raw_by_sid.values()
                                   if item["raw_extra"].get(extra_field_name) is not None),
            "non_null_in_rendered": sum(1 for item in rendered_by_sid.values()
                                        if item["raw_extra"].get(extra_field_name) is not None),
            "value_mismatch_sids": [sid for sid in raw_by_sid if sid in rendered_by_sid
                                    and raw_by_sid[sid]["raw_extra"].get(extra_field_name)
                                    != rendered_by_sid[sid]["raw_extra"].get(extra_field_name)],
        }
    display_time_diff_count = sum(
        1 for sid in raw_by_sid if sid in rendered_by_sid
        and raw_by_sid[sid]["raw_extra"].get("upload_time_display")
        != rendered_by_sid[sid]["raw_extra"].get("upload_time_display"))
    return {
        "raw_file": raw_result["input_file"],
        "rendered_file": rendered_result["input_file"],
        "candidate_count_raw": len(raw_by_sid),
        "candidate_count_rendered": len(rendered_by_sid),
        "sids_only_in_raw": sorted(set(raw_by_sid) - set(rendered_by_sid)),
        "sids_only_in_rendered": sorted(set(rendered_by_sid) - set(raw_by_sid)),
        "fields": field_report_dict,
        "time_display_text_changed_by_js": display_time_diff_count,
    }


def collect_input_files(input_path_list):
    html_file_list = []
    for input_path in input_path_list:
        if input_path.is_dir():
            html_file_list.extend(sorted(input_path.glob("*.html")))
        elif input_path.suffix.lower() == ".html":
            html_file_list.append(input_path)
    return html_file_list


def write_json_file(output_file_path, data_object):
    output_file_path.write_text(json.dumps(data_object, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8", newline="\n")


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # Windows 控制台默认 GBK，中文日志改 UTF-8 输出
    argument_parser = argparse.ArgumentParser(description="SubHD 保存网页离线解析探针")
    argument_parser.add_argument("inputs", nargs="+", type=Path, help="保存的 .html 文件或所在目录")
    argument_parser.add_argument("--out-dir", type=Path, default=None, help="JSON 输出目录（不填则只打印摘要）")
    argument_parser.add_argument("--compare-raw-rendered", action="store_true",
                                 help="对同名 raw / rendered 页面做字段对比，输出 _compare_raw_vs_rendered.json")
    parsed_arguments = argument_parser.parse_args()

    html_file_list = collect_input_files(parsed_arguments.inputs)
    if parsed_arguments.out_dir:
        parsed_arguments.out_dir.mkdir(parents=True, exist_ok=True)

    result_by_file_name = {}
    for html_file_path in html_file_list:
        page_result = parse_saved_page(html_file_path)
        result_by_file_name[html_file_path.name] = page_result
        item_count = len(page_result.get("candidates", [])) if "candidates" in page_result else (
            1 if page_result.get("detail") else 0)
        log_message(f"{html_file_path.name}: {page_result['page_type']} / {page_result['input_kind']} / 条目 {item_count}")
        if parsed_arguments.out_dir:
            write_json_file(parsed_arguments.out_dir / (html_file_path.stem + ".json"), page_result)

    if parsed_arguments.compare_raw_rendered:
        comparison_list = []
        for file_name, raw_result in result_by_file_name.items():
            if not file_name.endswith(".raw.html") or "candidates" not in raw_result:
                continue
            rendered_result = result_by_file_name.get(file_name.replace(".raw.html", ".rendered.html"))
            if rendered_result:
                comparison = compare_raw_and_rendered(raw_result, rendered_result)
                comparison_list.append(comparison)
                log_message(f"对比 {file_name}: raw {comparison['candidate_count_raw']} 条 / "
                            f"rendered {comparison['candidate_count_rendered']} 条 / "
                            f"JS 改写时间显示 {comparison['time_display_text_changed_by_js']} 处")
        if parsed_arguments.out_dir:
            write_json_file(parsed_arguments.out_dir / "_compare_raw_vs_rendered.json", comparison_list)


if __name__ == "__main__":
    main()
