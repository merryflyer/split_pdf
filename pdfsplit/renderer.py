"""按 y 坐标矢量裁切, 渲染单节 PDF。"""
import fitz

MIN_CLIP_HEIGHT = 10  # pt; 小于此高度的裁切片视为页眉/空白残渣, 跳过


def render(doc, section, out_path):
    """渲染单个 section 为独立 PDF 文件。

    返回 True=已写出, False=内容为空(所有裁切片均不足 MIN_CLIP_HEIGHT)已跳过,
    调用方应据此告警, 避免静默产出 0 页空文件。
    """
    new = fitz.open()
    p_s, y_s = section["p_s"], section["y_s"]
    p_e, y_e = section["p_e"], section["y_e"]
    for pn in range(p_s, p_e + 1):
        src = doc[pn]
        rect = src.rect
        top = y_s if pn == p_s else 0
        bottom = y_e if (pn == p_e and y_e is not None) else rect.height
        if bottom - top < MIN_CLIP_HEIGHT:
            continue
        clip = fitz.Rect(0, top, rect.width, bottom)
        np = new.new_page(width=rect.width, height=clip.height)
        np.show_pdf_page(np.rect, doc, pn, clip=clip)
    if new.page_count == 0:
        new.close()
        return False
    new.save(out_path)
    new.close()
    return True
