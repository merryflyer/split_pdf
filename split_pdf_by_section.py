#!/usr/bin/env python3
"""
pdf-section-splitter — 按标题层级拆分 PDF,支持页面中间的标题矢量裁切。

用法:
  python split_pdf_by_section.py --input book.pdf --output_dir out/ [--level 3] [--chapter N] [--min-size 11.8] [--preview]

依赖: pip install pymupdf
核心逻辑在 pdfsplit/ 包内, 本文件仅作 CLI 入口。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pdfsplit import (HEADING_MIN_SIZE, build_sections, chapter_bounds,
                      clamp_last_section_to_next_chapter, detect_headings,
                      render, sanitize)

import fitz


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output_dir", required=True)
    ap.add_argument("--level", type=int, default=3, choices=[1, 2, 3])
    ap.add_argument("--chapter", type=int, default=None)
    ap.add_argument("--min-size", type=float, default=HEADING_MIN_SIZE,
                    help="标题最小字号阈值(默认 %(default)s, 比正文略高即可)")
    ap.add_argument("--preview", action="store_true")
    args = ap.parse_args()

    doc = fitz.open(args.input)
    headings = detect_headings(doc, args.min_size)
    cb = chapter_bounds(doc, args.min_size)

    # 确定处理的页范围
    if args.chapter is not None:
        p_start = cb.get(args.chapter)
        if p_start is None:
            print(f"未找到第 {args.chapter} 章")
            return
        nxt = args.chapter + 1
        p_end = cb.get(nxt, doc.page_count) - 1
        tag = f"ch{args.chapter}"
    else:
        p_start, p_end = 0, doc.page_count - 1
        tag = "full"

    sections = build_sections(headings, args.level, p_start, p_end)

    # 章模式: 下一章标题不在页首时, 把其上方残留的章末内容并进末节, 避免丢失
    if args.chapter is not None and args.chapter + 1 in cb:
        clamp_last_section_to_next_chapter(doc, headings, sections,
                                           cb[args.chapter + 1])

    os.makedirs(args.output_dir, exist_ok=True)

    # 文件名唯一性: {i:02d} 序号前缀天然去重, 无需额外处理
    fnames = [f"{i:02d}_{sanitize(s['title'])}.pdf"
              for i, s in enumerate(sections, 1)]

    # 清单
    lines = [f"# 拆分清单 (level={args.level}, {tag})  源: {os.path.basename(args.input)}",
             f"# 共 {len(sections)} 个"]
    for i, s in enumerate(sections, 1):
        y_e_s = f"y{s['y_e']}" if s["y_e"] is not None else "文末"
        lines.append(f"{i:02d}\t原书 p{s['p_s']+1}~p{s['p_e']+1} ({y_e_s})\t{s['title']}")

    if args.preview:
        print("\n".join(lines))
        return

    skipped = []
    for i, s in enumerate(sections, 1):
        ok = render(doc, s, os.path.join(args.output_dir, fnames[i - 1]))
        if not ok:
            skipped.append(f"{i:02d} {s['title']}")
    with open(os.path.join(args.output_dir, "清单.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"完成: {len(sections) - len(skipped)}/{len(sections)} 个文件 -> {args.output_dir}")
    if skipped:
        print(f"警告: {len(skipped)} 个小节内容为空被跳过(未生成文件):")
        for item in skipped:
            print(f"  - {item}")


if __name__ == "__main__":
    main()
