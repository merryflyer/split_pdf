# split_pdf

按标题层级（章 / 节 / 小结）拆分带文字层的教材 PDF。标题出现在**页面中间**时按 y 坐标**矢量裁切**，不丢字、不串内容、文字不模糊。

> 方法论与已知坑见 [经验_PDF按小结拆分.md](经验_PDF按小结拆分.md)。
> 同名用户级 Skill：`~/.workbuddy/skills/pdf-section-splitter`。

## 安装

```bash
pip install pymupdf
```

## 用法

```bash
# 全本按小结(默认 level=3)拆分
python split_pdf_by_section.py --input book.pdf --output_dir out/

# 只拆第一章
python split_pdf_by_section.py --input book.pdf --output_dir out/ --chapter 1

# 换粒度: 按节(level=2) / 按章(level=1)
python split_pdf_by_section.py --input book.pdf --output_dir out/ --level 2

# 只看方案不生成
python split_pdf_by_section.py --input book.pdf --output_dir out/ --preview

# 换书时调整标题字号阈值(默认 11.8, 比正文略高即可)
python split_pdf_by_section.py --input book.pdf --output_dir out/ --min-size 12.5
```

| 参数 | 说明 |
|------|------|
| `--input` | 源 PDF 路径（必填） |
| `--output_dir` | 输出目录（必填） |
| `--level` | 拆分粒度：1=章，2=节，3=小结（默认 3） |
| `--chapter` | 只拆第 N 章 |
| `--min-size` | 标题最小字号阈值（默认 11.8） |
| `--preview` | 只打印拆分清单，不生成文件 |

输出：`NN_标题.pdf` 序列 + `清单.txt`（区间清单）。内容为空的小节会跳过并打印警告，不会产出 0 页空文件。

## 项目结构

```
split_pdf_by_section.py   # CLI 入口(薄包装)
pdfsplit/                 # 核心库
  classifier.py           # 标题层级判定(OCR 容错 + 字号/编号双判据)
  detector.py             # 全文标题扫描、跨行合并、章节边界
  sections.py             # 区间构造、章末钳制、文件名净化
  renderer.py             # 按 y 坐标矢量裁切渲染
tests/test_split_pdf.py   # 单元测试 + 合成 PDF 端到端测试
```

## 测试

```bash
python -m pytest tests/ -q
```

## 验收清单

每次拆分后必查（详见经验文档）：

- 编号连续的小节各自独立成文件，无被上一节吞并（重点排查 OCR 损坏编号 `1↔L`）
- 0 个空文件；章引言已进首个小节；末节不含下一章内容
