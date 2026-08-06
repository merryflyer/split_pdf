"""标题扫描: 全局检测、按(页,y)排序、跨行合并、章节边界定位。"""
import re

from .classifier import HEADING_MIN_SIZE, classify, norm_heading


def detect_headings(doc, min_size=HEADING_MIN_SIZE):
    """扫描全本, 返回全局按(页,y)排序的标题行列表。"""
    raw = []
    for pno in range(doc.page_count):
        page = doc[pno]
        for b in page.get_text("dict")["blocks"]:
            for line in b.get("lines", []):
                spans = line["spans"]
                txt = "".join(s["text"] for s in spans)
                if not txt.strip():
                    continue
                size = max(s["size"] for s in spans)
                y = round(line["bbox"][1])
                lv = classify(txt, size, min_size)
                if lv:
                    norm = norm_heading(txt)
                    raw.append({"p": pno, "y": y, "lv": lv,
                                "t": re.sub(r"\s+", " ", norm.strip())})
    raw.sort(key=lambda h: (h["p"], h["y"]))
    # 合并跨行标题: 同页、同层、纵向相邻、续行不以数字开头
    merged = []
    for h in raw:
        if (merged and merged[-1]["p"] == h["p"] and merged[-1]["lv"] == h["lv"]
                and h["y"] - merged[-1]["last_y"] < 40
                and not re.match(r"^\d", h["t"])):
            merged[-1]["t"] += h["t"]
            merged[-1]["last_y"] = h["y"]
        else:
            merged.append({**h, "last_y": h["y"]})
    return merged


def chapter_bounds(doc, min_size=HEADING_MIN_SIZE):
    """返回各章正文起始页索引: {章号: 页索引}。

    必须用 classify 过滤(只认大字号正文章标题), 否则会误把目录页里的
    '第N章'(小字号)也当成章起点; 取首次出现(正文), 忽略后续重复。
    """
    bounds = {}
    for pno in range(doc.page_count):
        page = doc[pno]
        for b in page.get_text("dict")["blocks"]:
            for line in b.get("lines", []):
                spans = line["spans"]
                txt = "".join(s["text"] for s in spans)
                size = max(s["size"] for s in spans)
                if classify(txt, size, min_size) == 1:  # 仅正文大字号章标题
                    m = re.match(r"^第\s*(\d+)\s*章", norm_heading(txt))
                    if m:
                        bounds.setdefault(int(m.group(1)), pno)
    return bounds
