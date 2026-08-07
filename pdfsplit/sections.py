"""拆分区间构造、文件名净化、章末边界钳制。"""
import re

# 章末延伸判定: 下一章标题上方存在正文的最小区域上沿(页眉/页码区以下)
_CONTENT_TOP_MARGIN = 50


def build_sections(headings, level, p_start, p_end):
    """构造拆分区间。标题全局已按(页,y)排序。

    关键: 先为每一节算 raised 起点 —— 从本小节向前回溯, 经过的所有
    lv<level 结构标题(节/章)取最早的一个; 遇到上一个同层标题则停,
    起点取自身。再令『本节终点 = 下一节的 raised 起点』,
    保证严格相邻、不重叠、不漏字。

    注意回溯必须【持续越过】多级父标题直到同层为止, 不能只停在第一个父级:
    结构为 第1章 -> 1.1 -> 1.1.1 时, 若只回溯到 1.1, 章标题和章引言会
    掉出所有小节文件之外(静默丢内容)。持续回溯到 第1章 才能把引言找回来。
    """
    bounds = [h for h in headings if h["lv"] == level and p_start <= h["p"] <= p_end]
    if not bounds:
        return []
    # 1) 计算每节的 raised 起点 (p, y)
    starts = []
    for s in bounds:
        idx = headings.index(s)
        si = idx
        for j in range(idx - 1, -1, -1):
            h = headings[j]
            if h["lv"] == level:
                break  # 遇到上一个同层小节 -> 起点取已记录的最早父标题
            if h["lv"] < level:
                si = j  # 记录父标题并继续向前, 取最早的一个(覆盖多级父标题)
        starts.append((headings[si]["p"], headings[si]["y"]))
    # 2) 构造区间: 终点 = 下一节的 raised 起点
    sections = []
    for k, s in enumerate(bounds):
        p_s, y_s = starts[k]
        if k + 1 < len(bounds):
            p_e, y_e = starts[k + 1]
        else:
            p_e, y_e = p_end, None
        sections.append({"p_s": p_s, "y_s": y_s, "p_e": p_e, "y_e": y_e,
                         "title": s["t"], "lv": s["lv"]})
    return sections


def clamp_last_section_to_next_chapter(doc, headings, sections, next_chapter_page):
    """--chapter 模式下, 若下一章标题不在页首且其上方仍有正文/图片,
    把末节终点延伸到该标题前, 避免章末内容(标题上方的半页)丢失。

    下一章起新页(标题上方只有页眉/页码)时不延伸, 防止把页眉残渣带进末节。
    """
    if not sections:
        return
    y_next = min((h["y"] for h in headings
                  if h["lv"] == 1 and h["p"] == next_chapter_page), default=None)
    if y_next is None:
        return
    if _has_content_above(doc, next_chapter_page, y_next):
        sections[-1]["p_e"] = next_chapter_page
        sections[-1]["y_e"] = y_next


def _has_content_above(doc, pno, y_limit):
    """页面 pno 在 (页眉区, y_limit) 之间是否存在正文文本或图片。"""
    page = doc[pno]
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") == 1:  # 图片块
            if _CONTENT_TOP_MARGIN < b["bbox"][1] < y_limit - 5:
                return True
            continue
        for line in b.get("lines", []):
            txt = "".join(s["text"] for s in line["spans"]).strip()
            y = line["bbox"][1]
            if not txt or y <= _CONTENT_TOP_MARGIN or y >= y_limit - 5:
                continue
            if re.fullmatch(r"\d+", txt):  # 页码
                continue
            return True
    return False


def sanitize(name):
    """文件名净化: 非法字符替换为下划线, 点号两侧空白折叠('2 . 1 . 1'->'2.1.1'),
    折叠连续空白, 截断 80 字符。"""
    for ch in '\\/:*?"<>|':
        name = name.replace(ch, "_")
    name = re.sub(r"\s*\.\s*", ".", name)
    name = re.sub(r"\s+", " ", name)
    return name.strip()[:80]
