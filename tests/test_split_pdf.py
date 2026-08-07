# -*- coding: utf-8 -*-
"""pdfsplit 单元测试 + 基于 fitz 合成 PDF 的端到端测试。"""
import os
import sys

import fitz
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdfsplit import (build_sections, clamp_last_section_to_next_chapter,
                      classify, detect_headings, norm_heading, render,
                      sanitize)


# ---------------- norm_heading: OCR 编号前缀还原 ----------------

class TestNormHeading:
    def test_isolated_L_restored(self):
        assert norm_heading("L 3 . 2 存储器系统") == "1 3 . 2 存储器系统"

    def test_L_before_dot_restored(self):
        assert norm_heading("L.3 概述") == "1.3 概述"

    def test_trailing_L_restored(self):
        assert norm_heading("1.3.L 概述") == "1.3.1 概述"

    def test_io_body_untouched(self):
        # 'I'/'O' 与字母相邻 -> 不映射, 且终止前缀规范化
        assert norm_heading("1.4 IO 模型") == "1.4 IO 模型"

    def test_l2_cache_untouched(self):
        # 'L' 与数字 '2' 直接相邻 -> 不映射
        assert norm_heading("1.3 L2 cache") == "1.3 L2 cache"

    def test_normal_numbering_unchanged(self):
        assert norm_heading("10.2 节标题") == "10.2 节标题"

    def test_body_after_chinese_untouched(self):
        assert norm_heading("1.1 缓存 L1 介绍") == "1.1 缓存 L1 介绍"


# ---------------- classify: 层级判定 ----------------

class TestClassify:
    def test_chapter(self):
        assert classify("第1章 计算机系统概述", 16) == 1

    def test_toc_chapter_excluded(self):
        assert classify("第一章 计算机系统概述", 16) == 0

    def test_small_size_excluded(self):
        assert classify("第1章 计算机系统概述", 9) == 0

    def test_section(self):
        assert classify("1.1 引言", 14) == 2

    def test_subsection(self):
        assert classify("1.1.1 二进制", 13) == 3

    def test_ocr_damaged_subsection(self):
        assert classify("L 3 . 2 存储器", 13) == 3

    def test_ocr_L_dot_section(self):
        assert classify("L.1 引言", 14) == 2

    def test_io_title_stays_section(self):
        # 修复前: I/O 被改成 1/0, "1.4 1" 被误判为 3 组 -> 小结
        assert classify("1.4 IO 模型", 14) == 2

    def test_l2_title_stays_section(self):
        assert classify("1.3 L2 cache", 14) == 2

    def test_two_digit_chapter_number(self):
        assert classify("10.2 标题", 14) == 2

    def test_bare_numbering(self):
        assert classify("1.2", 14) == 2

    def test_special_headings(self):
        assert classify("本章小结", 13) == 3
        assert classify("习题", 13) == 3

    def test_body_text(self):
        assert classify("这是一段正文内容。", 11.1) == 0

    def test_min_size_param(self):
        assert classify("1.1 引言", 11.5) == 0
        assert classify("1.1 引言", 11.5, min_size=11.0) == 2

    def test_no_space_between_numbering_and_title(self):
        # 同行碎片拼接后编号与标题间无空白: '2. 7. 5原码除法运算'
        assert classify("2. 7. 5原码除法运算", 12.9) == 3
        assert classify("2.7.5原码除法运算", 12.9) == 3


# ---------------- sanitize: 文件名净化 ----------------

class TestSanitize:
    def test_illegal_chars(self):
        assert sanitize('a/b\\c:d*e?f"g<h>i|j') == "a_b_c_d_e_f_g_h_i_j"

    def test_length_cap(self):
        assert len(sanitize("长" * 200)) == 80

    def test_whitespace_folded(self):
        assert sanitize("1.1   引言") == "1.1 引言"

    def test_dot_spacing_collapsed(self):
        assert sanitize("2 . 1 . 1 信") == "2.1.1 信"
        assert sanitize("2 .1 . 2 进位记数制") == "2.1.2 进位记数制"


# ---------------- build_sections: 区间构造 ----------------

def _h(p, y, lv, t):
    return {"p": p, "y": y, "lv": lv, "t": t}


class TestBuildSections:
    HEADINGS = [
        _h(0, 100, 1, "第1章"),
        _h(0, 200, 2, "1.1 A"),
        _h(0, 300, 3, "1.1.1 a"),
        _h(1, 100, 3, "1.1.2 b"),
        _h(2, 100, 2, "1.2 B"),      # 跨页父标题
        _h(2, 300, 3, "1.2.1 c"),
    ]

    def test_three_sections(self):
        secs = build_sections(self.HEADINGS, 3, 0, 5)
        assert len(secs) == 3

    def test_first_section_raises_to_chapter(self):
        # 章标题 + 引言必须进首个小节(不能只回溯到 1.1)
        secs = build_sections(self.HEADINGS, 3, 0, 5)
        assert (secs[0]["p_s"], secs[0]["y_s"]) == (0, 100)

    def test_adjacency(self):
        # 终点 == 下一节 raised 起点, 不重叠不漏字
        secs = build_sections(self.HEADINGS, 3, 0, 5)
        for a, b in zip(secs, secs[1:]):
            assert (a["p_e"], a["y_e"]) == (b["p_s"], b["y_s"])

    def test_cross_page_parent(self):
        # 1.2 在 p2, 其子节 1.2.1 的 raised 起点必须上抬到 p2 的 1.2
        secs = build_sections(self.HEADINGS, 3, 0, 5)
        assert (secs[2]["p_s"], secs[2]["y_s"]) == (2, 100)
        assert (secs[1]["p_e"], secs[1]["y_e"]) == (2, 100)

    def test_last_section_to_range_end(self):
        secs = build_sections(self.HEADINGS, 3, 0, 5)
        assert (secs[2]["p_e"], secs[2]["y_e"]) == (5, None)

    def test_same_level_break(self):
        # 同层相邻: 起点取自身, 不回吞上一节
        secs = build_sections(self.HEADINGS, 3, 0, 5)
        assert (secs[1]["p_s"], secs[1]["y_s"]) == (1, 100)

    def test_empty_bounds(self):
        assert build_sections(self.HEADINGS, 3, 10, 20) == []

    def test_level2_split(self):
        secs = build_sections(self.HEADINGS, 2, 0, 5)
        assert len(secs) == 2
        assert (secs[0]["p_s"], secs[0]["y_s"]) == (0, 100)  # 1.1 上抬到第1章
        assert (secs[1]["p_s"], secs[1]["y_s"]) == (2, 100)  # 1.2 自身


# ---------------- detect_headings: 视觉行合并 + 跨行标题合并 ----------------

class TestDetectHeadingsMerging:
    def _doc(self):
        return fitz.open()

    def test_row_fragments_merged(self, tmp_path):
        # 编号碎片(小字号) + 标题碎片(大字号)同一视觉行 -> 合并检出
        # 真实案例: 原书 p83 '2. 7. 5'(11.1) + '原码除法运算'(12.9)
        doc = fitz.open()
        p = doc.new_page(width=595, height=842)
        p.insert_text((92, 566), "2. 7. 5", fontsize=11.1, fontname="helv")
        p.insert_text((140, 566), "Division Title", fontsize=12.9, fontname="helv")
        headings = detect_headings(doc)
        doc.close()
        assert len(headings) == 1
        assert headings[0]["lv"] == 3
        assert "Division Title" in headings[0]["t"]

    def test_continuation_bigtext_merged(self, tmp_path):
        # 标题后半段被拆到下一行(大字号无编号, 纵距<40) -> 并入标题
        doc = fitz.open()
        p = doc.new_page(width=595, height=842)
        p.insert_text((72, 200), "1.2.3 Split", fontsize=16, fontname="helv")
        p.insert_text((72, 224), "Title Tail", fontsize=16, fontname="helv")
        p.insert_text((72, 260), "body text starts here", fontsize=11, fontname="helv")
        headings = detect_headings(doc)
        doc.close()
        assert len(headings) == 1
        assert "Title Tail" in headings[0]["t"]

    def test_continuation_window_closes_on_body(self, tmp_path):
        # 标题与远处大字号行之间隔着正文行 -> 不合并(防止公式误并)
        doc = fitz.open()
        p = doc.new_page(width=595, height=842)
        p.insert_text((72, 200), "1.2.4 Real Title", fontsize=16, fontname="helv")
        p.insert_text((72, 224), "body line in between", fontsize=11, fontname="helv")
        p.insert_text((72, 238), "2Ri+Yo formula", fontsize=15, fontname="helv")
        headings = detect_headings(doc)
        doc.close()
        assert len(headings) == 1
        assert "formula" not in headings[0]["t"]

    def test_distinct_rows_not_merged(self, tmp_path):
        # 相邻正文行(17pt 行距)不能被视觉行合并吞掉
        doc = fitz.open()
        p = doc.new_page(width=595, height=842)
        p.insert_text((72, 100), "1.2.5 Title", fontsize=16, fontname="helv")
        p.insert_text((72, 130), "body row one", fontsize=11, fontname="helv")
        p.insert_text((72, 147), "body row two", fontsize=11, fontname="helv")
        headings = detect_headings(doc)
        text = "\n".join(pg.get_text() for pg in doc)
        doc.close()
        assert len(headings) == 1
        assert "body row one" in text and "body row two" in text

    def test_stray_large_fragment_no_size_boost(self, tmp_path):
        # 真实案例(原书 p56): 公式行 '0. 375x2...' (11.1) 同行混入 1 字符
        # 大号乱码碎片 'i' (12.9) -> 整行字号被顶过阈值, '0. 375' 被误判为
        # 2 组编号节标题(lv2), 进而污染 2.1.3 的 raised 起点。
        doc = fitz.open()
        p = doc.new_page(width=595, height=842)
        p.insert_text((107, 643), "0. 375x2 = 0. 75", fontsize=11.1, fontname="helv")
        p.insert_text((217, 643), "integer part = 0", fontsize=11.1, fontname="helv")
        p.insert_text((317, 646), "i", fontsize=12.9, fontname="helv")
        headings = detect_headings(doc)
        doc.close()
        assert headings == []


# ---------------- 端到端: 合成 PDF 拆分 ----------------

def _line(page, y, text, size):
    page.insert_text((72, y), text, fontsize=size, fontname="helv")


def _make_book(path):
    """3 页小书: 节标题 + 中页小节标题。"""
    doc = fitz.open()
    p0 = doc.new_page(width=595, height=842)
    _line(p0, 100, "1.1 Section One", 16)
    _line(p0, 140, "body of section one intro", 11)
    _line(p0, 300, "1.1.1 First Sub", 16)
    _line(p0, 340, "body of first sub page zero", 11)

    p1 = doc.new_page(width=595, height=842)
    _line(p1, 80, "body continuing first sub", 11)
    _line(p1, 400, "1.1.2 Second Sub", 16)   # 页面中间的标题
    _line(p1, 440, "body of second sub", 11)

    p2 = doc.new_page(width=595, height=842)
    _line(p2, 150, "1.2 Section Two", 16)
    _line(p2, 190, "body of section two", 11)
    _line(p2, 500, "1.2.1 Third Sub", 16)
    _line(p2, 540, "body of third sub", 11)
    doc.save(path)
    doc.close()


def _text(pdf_path):
    doc = fitz.open(pdf_path)
    t = "\n".join(p.get_text() for p in doc)
    np = doc.page_count
    doc.close()
    return t, np


class TestEndToEnd:
    def test_split_level3(self, tmp_path):
        src = tmp_path / "book.pdf"
        out = tmp_path / "out"
        _make_book(str(src))

        doc = fitz.open(str(src))
        headings = detect_headings(doc)
        sections = build_sections(headings, 3, 0, doc.page_count - 1)
        assert [s["title"] for s in sections] == [
            "1.1.1 First Sub", "1.1.2 Second Sub", "1.2.1 Third Sub"]

        out.mkdir()
        files = []
        for i, s in enumerate(sections, 1):
            fname = f"{i:02d}_{sanitize(s['title'])}.pdf"
            assert render(doc, s, str(out / fname)) is True
            files.append(fname)
        doc.close()

        assert len(files) == 3
        # 0 空文件
        for f in files:
            t, np = _text(str(out / f))
            assert np > 0 and t.strip()

        t1, _ = _text(str(out / files[0]))
        # 首个小节 raised 到节标题, 含 1.1 与引言
        assert "1.1 Section One" in t1 and "body of section one intro" in t1
        # 中页切分: 不含下一小节标题
        assert "1.1.2 Second Sub" not in t1

        t2, _ = _text(str(out / files[1]))
        # 中页小节首页确实以本小节标题开头
        assert t2.strip().startswith("1.1.2 Second Sub")
        # 跨页父标题归下一个小节: 1.2 不出现在 1.1.2 里
        assert "1.2 Section Two" not in t2

        t3, _ = _text(str(out / files[2]))
        assert "1.2 Section Two" in t3 and "1.2.1 Third Sub" in t3

    def test_empty_section_skipped(self, tmp_path):
        # 起点 y 超过页面高度 -> 所有裁切片为空 -> render 返回 False, 不落盘
        src = tmp_path / "book.pdf"
        _make_book(str(src))
        doc = fitz.open(str(src))
        out = tmp_path / "empty.pdf"
        ok = render(doc, {"p_s": 0, "y_s": 900, "p_e": 0, "y_e": None}, str(out))
        doc.close()
        assert ok is False
        assert not out.exists()


# ---------------- clamp: 章末边界钳制 ----------------

class TestClampChapterEnd:
    def _doc_with_next_chapter(self, path, body_above):
        doc = fitz.open()
        p = doc.new_page(width=595, height=842)
        if body_above:
            _line(p, 200, "tail content of chapter one", 11)
        _line(p, 400, "2.1 Next Chapter Section", 16)  # 模拟下一章页内标题
        doc.save(path)
        doc.close()

    def test_extends_when_content_above(self, tmp_path):
        src = tmp_path / "b.pdf"
        self._doc_with_next_chapter(str(src), body_above=True)
        doc = fitz.open(str(src))
        headings = [{"p": 0, "y": 386, "lv": 1, "t": "第2章"}]
        sections = [{"p_s": 0, "y_s": 0, "p_e": 0, "y_e": None, "title": "x", "lv": 3}]
        clamp_last_section_to_next_chapter(doc, headings, sections, 0)
        doc.close()
        assert (sections[0]["p_e"], sections[0]["y_e"]) == (0, 386)

    def test_no_extend_when_fresh_page(self, tmp_path):
        src = tmp_path / "b.pdf"
        self._doc_with_next_chapter(str(src), body_above=False)
        doc = fitz.open(str(src))
        headings = [{"p": 0, "y": 386, "lv": 1, "t": "第2章"}]
        sections = [{"p_s": 0, "y_s": 0, "p_e": 0, "y_e": None, "title": "x", "lv": 3}]
        clamp_last_section_to_next_chapter(doc, headings, sections, 0)
        doc.close()
        assert sections[0]["y_e"] is None  # 不延伸

    def test_no_sections_noop(self, tmp_path):
        src = tmp_path / "b.pdf"
        self._doc_with_next_chapter(str(src), body_above=True)
        doc = fitz.open(str(src))
        clamp_last_section_to_next_chapter(doc, [], [], 0)
        doc.close()
