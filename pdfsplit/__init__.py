"""pdfsplit — 按标题层级拆分 PDF 的核心库。

模块划分:
  classifier  标题层级判定(OCR 容错 + 字号/编号双判据)
  detector    全文标题扫描、排序、跨行合并、章节边界
  sections    拆分区间构造、文件名净化、章末边界钳制
  renderer    按 y 坐标矢量裁切渲染单节 PDF
"""
from .classifier import HEADING_MIN_SIZE, classify, norm_heading
from .detector import chapter_bounds, detect_headings
from .renderer import MIN_CLIP_HEIGHT, render
from .sections import (build_sections, clamp_last_section_to_next_chapter,
                       sanitize)

__version__ = "2.0.0"

__all__ = [
    "HEADING_MIN_SIZE",
    "MIN_CLIP_HEIGHT",
    "build_sections",
    "chapter_bounds",
    "clamp_last_section_to_next_chapter",
    "classify",
    "detect_headings",
    "norm_heading",
    "render",
    "sanitize",
]
