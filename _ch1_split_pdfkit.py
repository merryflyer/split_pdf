#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 pdfkit 技能内置的 PyMuPDF 环境, 把第一章按小节(小结)精确拆分。
逻辑: 以全局有序的结构标题(章/节/小节)为切分点, 每小节起点=它前面、
且与上一小节之间出现的第一个结构标题(可跨页), 用 show_pdf_page 按 y 裁切。
"""
import fitz, re, os

SRC = "/Users/seagull/Documents/sk/split_pdf/计算机系统原理 2023年版.pdf"
OUTDIR = "/Users/seagull/Documents/sk/split_pdf/split_output_ch1"
HEADING_MIN_SIZE = 12.0
MIN_TOP_Y = 22
CN_NUM = r'[一二三四五六七八九十百零两]'

def classify(text, size):
    t = text.strip()
    if size < HEADING_MIN_SIZE:
        return 0
    if re.match(r'^第\s*[0-9]+\s*章', t):
        return 1
    if re.match(r'^第\s*' + CN_NUM + r'+\s*章', t):
        return 0
    if re.match(r'^(\d+\s*\.\s*)+(?=\d)', t):
        return 3 if t.count('.') >= 2 else 2
    if re.match(r'^\d+\s*\.\s*\d+\s*$', t):
        return 2
    if t in ('本章小结', '习题', '编者的话'):
        return 3
    return 0

def detect_headings(doc):
    headings = []
    for pno in range(doc.page_count):
        page = doc[pno]
        lines_info = []
        for b in page.get_text("dict")["blocks"]:
            for line in b.get("lines", []):
                spans = line["spans"]
                txt = "".join(s["text"] for s in spans)
                if not txt.strip():
                    continue
                size = max(s["size"] for s in spans)
                y = round(line["bbox"][1])
                lines_info.append({"y": y, "size": size,
                                   "txt": txt, "lv": classify(txt, size)})
        lines_info.sort(key=lambda x: x["y"])
        i = 0
        while i < len(lines_info):
            li = lines_info[i]
            if li["lv"]:
                full = li["txt"]
                j = i + 1
                while j < len(lines_info):
                    lj = lines_info[j]
                    if lj["size"] >= HEADING_MIN_SIZE and not lj["lv"]:
                        full += " " + lj["txt"]
                        j += 1
                    else:
                        break
                headings.append({"p": pno, "y": li["y"], "lv": li["lv"],
                                 "t": re.sub(r'\s+', ' ', full.strip())})
                i = j
            else:
                i += 1
    return headings

def pos(h):
    return (h["p"], h["y"])

def find_textbook_start(headings):
    for h in headings:
        if h["lv"] == 1:
            return h["p"]
    return 0

def chapter_bounds(headings, no):
    ch = [h for h in headings if h["lv"] == 1]
    nums = []
    for h in ch:
        m = re.search(r'第\s*(\d+)\s*章', h["t"])
        nums.append(int(m.group(1)) if m else None)
    if no not in nums:
        return None
    idx = nums.index(no)
    cs = ch[idx]["p"]
    ce = ch[idx + 1]["p"] if idx + 1 < len(ch) else doc_page_count
    return cs, ce

def build_sections(headings, range_start, level):
    struct = [h for h in headings if h["p"] >= range_start and h["lv"] >= 1]
    struct.sort(key=pos)
    bounds = [h for h in headings if h["p"] >= range_start and h["lv"] == level]
    bounds.sort(key=pos)
    if not bounds:
        return []
    starts, prev = [], (range_start, -1)
    for b in bounds:
        cand = [H for H in struct if prev < pos(H) <= pos(b)]
        starts.append(cand[0] if cand else b)
        prev = pos(b)
    sections, n = [], len(bounds)
    for k, b in enumerate(bounds):
        sp, sy = pos(starts[k])
        ep, ey = pos(starts[k + 1]) if k + 1 < n else (doc_page_count - 1, None)
        sections.append({"p_s": sp, "y_s": sy, "p_e": ep, "y_e": ey,
                         "title": b["t"], "lv": b["lv"]})
    return sections

def sanitize(name):
    name = re.sub(r'\s*\.\s*', '.', name)
    return re.sub(r'[/\\:*"<>|?]', '_', name).strip()

def add_section(out_doc, src, sec):
    p_s, y_s, p_e, y_e = sec["p_s"], sec["y_s"], sec["p_e"], sec["y_e"]
    for p in range(p_s, p_e + 1):
        page = src[p]
        w, h = page.rect.width, page.rect.height
        if p == p_s and p == p_e:
            top, bot = y_s, (y_e if y_e is not None else h)
        elif p == p_s:
            top = y_s if y_s > MIN_TOP_Y else 0
            bot = h
        elif p == p_e and y_e is not None:
            top, bot = 0, y_e
        else:
            out_doc.insert_pdf(src, from_page=p, to_page=p)
            continue
        if bot - top < 1:
            continue
        np = out_doc.new_page(width=w, height=bot - top)
        np.show_pdf_page(np.rect, src, p, clip=fitz.Rect(0, top, w, bot))

if __name__ == "__main__":
    global doc_page_count
    doc = fitz.open(SRC)
    doc_page_count = doc.page_count
    headings = detect_headings(doc)
    ts = find_textbook_start(headings)
    cb = chapter_bounds(headings, 1)
    cs, ce = cb
    sections = build_sections(headings, cs, 3)
    sections = [s for s in sections if cs <= s["p_s"] < ce]
    if sections:
        last = dict(sections[-1])
        if last["p_e"] >= ce:
            last["p_e"] = ce - 1
            last["y_e"] = None
        sections[-1] = last
    os.makedirs(OUTDIR, exist_ok=True)
    manifest = []
    for i, s in enumerate(sections):
        out = fitz.open()
        add_section(out, doc, s)
        if out.page_count == 0:
            out.close()
            continue
        fname = f"{i+1:02d}_{sanitize(s['title'])[:40]}.pdf"
        out.save(os.path.join(OUTDIR, fname))
        out.close()
        manifest.append((f"{i+1:02d}", s["title"], s["p_s"] + 1, s["p_e"] + 1, fname))
    with open(os.path.join(OUTDIR, "清单.txt"), "w", encoding="utf-8") as f:
        f.write(f"源文件: {SRC}\n范围: 第1章(p{cs+1}-{ce})\n拆分层级: level=3 (小节/小结)\n")
        f.write(f"共 {len(sections)} 个文件(经 pdfkit PyMuPDF 拆分)\n\n")
        for m in manifest:
            f.write(f"[{m[0]}] {m[1]}  (PDF原页 {m[2]}-{m[3]})  -> {m[4]}\n")
    print(f"完成! 生成 {len(sections)} 个文件, 位于 {OUTDIR}/")
