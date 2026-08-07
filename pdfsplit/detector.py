"""标题扫描: 视觉行合并、层级判定、跨行标题合并、章节边界定位。"""
import re

from .classifier import HEADING_MIN_SIZE, classify, norm_heading

ROW_Y_TOL = 4       # pt; 同一视觉行的碎片 y 容差(对比行首 y, 防链式漂移)
CONT_MERGE_GAP = 40  # pt; 跨行标题续行的最大纵距(经验值)


def _iter_page_lines(page):
    """提取页内文本行, 并把同一视觉行的多个 line 对象合并为一个逻辑行。

    教材的文字层常把标题拆成同行多个碎片(如编号 '2. 7. 5' 是小字号、
    标题 '原码除法运算' 是大字号, 两个 line 对象)。按基线(bbox 底边)接近度
    分组 —— 同行碎片的基线几乎相同, 而 bbox 顶边因字号不同会有几 pt 偏差,
    不能用顶边排序(会把大字号碎片排到小字号碎片前面, 拼错顺序)。
    组内按 x 拼接、取最大字号, 逻辑行 y 取各碎片顶边最小值。
    否则整行因编号碎片字号不足而漏检(静默丢小节)。
    """
    frags = []
    for b in page.get_text("dict")["blocks"]:
        for line in b.get("lines", []):
            spans = line["spans"]
            txt = "".join(s["text"] for s in spans)
            if not txt.strip():
                continue
            frags.append({"x": line["bbox"][0], "top": round(line["bbox"][1]),
                          "base": line["bbox"][3], "txt": txt,
                          "size": max(s["size"] for s in spans)})
    frags.sort(key=lambda f: (f["base"], f["x"]))
    rows = []
    for f in frags:
        # 与行首碎片的基线对比(不更新), 防止链式漂移跨行
        if rows and abs(f["base"] - rows[-1]["base"]) <= ROW_Y_TOL:
            rows[-1]["fs"].append(f)
        else:
            rows.append({"base": f["base"], "fs": [f]})
    out = []
    for r in rows:
        fs = sorted(r["fs"], key=lambda f: f["x"])
        out.append({"y": min(f["top"] for f in fs),
                    "size": max(f["size"] for f in fs),
                    "txt": "".join(f["txt"] for f in fs)})
    out.sort(key=lambda r: r["y"])
    return out


def detect_headings(doc, min_size=HEADING_MIN_SIZE):
    """扫描全本, 返回全局按(页,y)排序的标题行列表。

    两级合并:
    1. 视觉行合并(_iter_page_lines): 同行碎片拼接, 修复编号/标题字号不一的漏检。
    2. 跨行标题合并: 标题行之后, 同页、纵距 < CONT_MERGE_GAP 的续行并入标题文本
       (仅用于文件名, 定位 y 仍用首行)。续行条件满足其一:
       - 大字号非标题行(size >= min_size), 如 '位记数制' 这类被拆出的标题后半段;
       - 同层且不以数字开头的标题行(规则 5)。
       合并窗口在遇到第一个不满足条件的行时立即关闭,
       防止隔着正文行把远处的大字号行(如公式)误并进标题。
    """
    merged = []
    open_h = None  # 当前可接收续行的标题
    for pno in range(doc.page_count):
        for row in _iter_page_lines(doc[pno]):
            lv = classify(row["txt"], row["size"], min_size)
            if open_h is not None and row["y"] - open_h["last_y"] < CONT_MERGE_GAP:
                cont_bigtext = lv == 0 and row["size"] >= min_size
                cont_heading = (lv and lv == open_h["lv"]
                                and not re.match(r"^\d", norm_heading(row["txt"]).strip()))
                if cont_bigtext or cont_heading:
                    open_h["t"] += row["txt"].strip()
                    open_h["last_y"] = row["y"]
                    continue
            open_h = None
            if lv:
                entry = {"p": pno, "y": row["y"], "lv": lv,
                         "t": re.sub(r"\s+", " ", norm_heading(row["txt"]).strip()),
                         "last_y": row["y"]}
                merged.append(entry)
                open_h = entry
    return merged


def chapter_bounds(doc, min_size=HEADING_MIN_SIZE):
    """返回各章正文起始页索引: {章号: 页索引}。

    必须用 classify 过滤(只认大字号正文章标题), 否则会误把目录页里的
    '第N章'(小字号)也当成章起点; 取首次出现(正文), 忽略后续重复。
    """
    bounds = {}
    for pno in range(doc.page_count):
        for row in _iter_page_lines(doc[pno]):
            if classify(row["txt"], row["size"], min_size) == 1:  # 仅正文大字号章标题
                m = re.match(r"^第\s*(\d+)\s*章", norm_heading(row["txt"]))
                if m:
                    bounds.setdefault(int(m.group(1)), pno)
    return bounds
