#!/usr/bin/env python3
"""
pdf-section-splitter — 按标题层级拆分 PDF,支持页面中间的标题矢量裁切。

用法:
  python split_by_section.py --input book.pdf --output_dir out/ [--level 3] [--chapter N] [--preview]

依赖: pip install pymupdf
也可用 pdfkit 的 venv: ~/.workbuddy/skills/pdfkit-py/scripts/venv/bin/python3
"""
import argparse
import fitz
import os
import re

HEADING_MIN_SIZE = 11.8  # 比正文(~11.1)略高,避免误判正文为标题
CN_NUM = r"[一二三四五六七八九十百零两]"

# OCR 易混淆字符: 数字 '1' 常被识别成 'L'/'l'/'I', '0' 被识别成 'O'。
# 只在「编号前缀」(开头连续的 数字/点/空格/易混淆字母) 内做还原,
# 标题正文部分保持原样, 避免误改 "L1 cache" 之类的正文。
CONFUSE_MAP = {"L": "1", "l": "1", "I": "1", "O": "0", "o": "0",
               "｜": "1", "丨": "1"}


def _norm_heading(t):
    """仅规范化编号前缀中的易混淆字符, 其余原样返回。"""
    out = []
    norm_active = True
    for ch in t:
        if norm_active:
            if ch in CONFUSE_MAP:
                out.append(CONFUSE_MAP[ch])
                continue
            if re.match(r"[\d\.\s]", ch):
                out.append(ch)
                continue
            norm_active = False  # 进入标题正文, 关闭规范化
        out.append(ch)
    return "".join(out)


def classify(text, size):
    """返回层级: 1=章, 2=节, 3=小结, 0=非标题。

    文本层可能含 OCR 残损: 编号里的 '1' 被识别成 'L'/'l'/'I',
    若不匹配数字则小节整段漏检、内容被并入上一节(见经验文件「已知坑」)。
    匹配前用 _norm_heading 把编号前缀还原成数字。
    """
    t = text.strip()
    tn = _norm_heading(t)
    if size < HEADING_MIN_SIZE:
        return 0
    # 章: 阿拉伯数字 "第N章" (正文)
    if re.match(r"^第\s*\d+\s*章", tn):
        return 1
    # 目录里的 "第一章" 中文数字 -> 排除(不是正文标题)
    if re.match(r"^第\s*" + CN_NUM + r"+\s*章", tn):
        return 0
    # 编号标题: 容忍缺失的点/空格。OCR 常把 '1.3.2' 认成 'L 3 . 2'
    # (章节间的点也一起丢)。做法: 取开头连续 [数字/点/空格] 段,
    # 按分隔符切成数字组, 组数即层级 —— 3 组=小结, 2 组=节。
    # 兼容性: '10.2'(两位章节号) -> 组 ['10','2'] -> 2 组 -> 节, 正确。
    m = re.match(r"^([0-9\.\s]+)\s+([^\d.\s])", tn)   # 数字段 + 空白 + 标题首字(非数字/点)
    if not m:
        m = re.match(r"^([0-9\.\s]+)$", tn)       # 孤立编号(无标题), 如 "1.2"
    if m:
        groups = [g for g in re.split(r"[.\s]+", m.group(1).strip()) if g]
        n = len(groups)
        if n == 3:
            return 3
        if n == 2:
            return 2
    if tn in ("本章小结", "习题", "编者的话", "组编前言", "大纲前言"):
        return 3
    return 0


def detect_headings(doc):
    """扫描全本,返回全局按(页,y)排序的标题行列表。"""
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
                lv = classify(txt, size)
                if lv:
                    norm = _norm_heading(txt)
                    raw.append({"p": pno, "y": y, "lv": lv, "t": re.sub(r"\s+", " ", norm.strip())})
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


def chapter_bounds(doc):
    """返回各章正文起始页索引: {章号: 页索引}。

    必须用 classify 过滤(只认大字号正文章标题),否则会误把目录页里的
    '第N章'(小字号)也当成章起点;取首次出现(正文),忽略后续重复。
    """
    bounds = {}
    for pno in range(doc.page_count):
        page = doc[pno]
        for b in page.get_text("dict")["blocks"]:
            for line in b.get("lines", []):
                spans = line["spans"]
                txt = "".join(s["text"] for s in spans)
                size = max(s["size"] for s in spans)
                if classify(txt, size) == 1:  # 仅正文大字号章标题
                    m = re.match(r"^第\s*(\d+)\s*章", _norm_heading(txt))
                    if m:
                        bounds.setdefault(int(m.group(1)), pno)
    return bounds


def build_sections(headings, level, p_start, p_end):
    """构造拆分区间。标题全局已按(页,y)排序。

    关键: 先为每一节算 raised 起点(向前回溯第一个 lv<level 的结构标题),
    再令『本节终点 = 下一节的 raised 起点』,保证严格相邻、不重叠、不漏字。
    否则会把整页父标题(如 p36 的 1.2 节)错归上一节。
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
                break  # 遇到上一个同层小节 -> 起点取自身
            if h["lv"] < level:
                si = j
                break
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


def sanitize(name):
    for ch in '\\/:*?"<>|':
        name = name.replace(ch, "_")
    return name.strip()[:80]


def render(doc, section, out_path):
    new = fitz.open()
    p_s, y_s = section["p_s"], section["y_s"]
    p_e, y_e = section["p_e"], section["y_e"]
    for pn in range(p_s, p_e + 1):
        src = doc[pn]
        rect = src.rect
        top = y_s if pn == p_s else 0
        bottom = y_e if (pn == p_e and y_e is not None) else rect.height
        clip = fitz.Rect(0, top, rect.width, bottom)
        np = new.new_page(width=rect.width, height=clip.height)
        np.show_pdf_page(np.rect, doc, pn, clip=clip)
    new.save(out_path)
    new.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output_dir", required=True)
    ap.add_argument("--level", type=int, default=3, choices=[1, 2, 3])
    ap.add_argument("--chapter", type=int, default=None)
    ap.add_argument("--preview", action="store_true")
    args = ap.parse_args()

    doc = fitz.open(args.input)
    headings = detect_headings(doc)
    cb = chapter_bounds(doc)

    # 确定处理的页范围
    if args.chapter is not None:
        p_start = cb.get(args.chapter)
        if p_start is None:
            print(f"未找到第 {args.chapter} 章"); return
        nxt = args.chapter + 1
        p_end = cb.get(nxt, doc.page_count - 1)
        if nxt in cb:
            p_end = cb[nxt] - 1
        tag = f"ch{args.chapter}"
    else:
        p_start, p_end = 0, doc.page_count - 1
        tag = "full"

    sections = build_sections(headings, args.level, p_start, p_end)
    os.makedirs(args.output_dir, exist_ok=True)

    # 清单
    lines = [f"# 拆分清单 (level={args.level}, {tag})  源: {os.path.basename(args.input)}",
             f"# 共 {len(sections)} 个"]
    for i, s in enumerate(sections, 1):
        y_e_s = f"y{s['y_e']}" if s["y_e"] is not None else "文末"
        lines.append(f"{i:02d}\t原书 p{s['p_s']+1}~p{s['p_e']+1} ({y_e_s})\t{s['title']}")

    if args.preview:
        print("\n".join(lines))
        return

    for i, s in enumerate(sections, 1):
        fname = f"{i:02d}_{sanitize(s['title'])}.pdf"
        render(doc, s, os.path.join(args.output_dir, fname))
    with open(os.path.join(args.output_dir, "清单.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"完成: {len(sections)} 个文件 -> {args.output_dir}")


if __name__ == "__main__":
    main()
