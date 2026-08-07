"""标题层级判定: OCR 容错 + 字号/编号双判据。"""
import re

HEADING_MIN_SIZE = 11.8  # 比正文(~11.1)略高, 避免误判正文为标题
CN_NUM = r"[一二三四五六七八九十百零两]"

# OCR 易混淆字符: 数字 '1' 常被识别成 'L'/'l'/'I', '0' 被识别成 'O'。
CONFUSE_MAP = {"L": "1", "l": "1", "I": "1", "O": "0", "o": "0",
               "｜": "1", "丨": "1"}

_PREFIX_CHARS = frozenset("0123456789. \t")  # 编号前缀合法字符
_SEPARATORS = frozenset(" \t.")              # 编号内的组分隔符

# 编号标题: 数字段(非贪婪) + 前瞻标题首字(非数字/点); 或孤立编号(无标题)。
# 非贪婪 + 前瞻是为了容忍同行碎片拼接后编号与标题间无空白的情况
# (如 '2. 7. 5原码除法运算', 编号碎片与标题碎片是两个 line 对象, 拼接无空格)。
_RE_NUMBERED = re.compile(r"^([0-9.\s]+?)(?=[^\d.\s])")
_RE_NUMBER_ONLY = re.compile(r"^([0-9.\s]+)$")
_RE_CHAPTER = re.compile(r"^第\s*\d+\s*章")                    # 正文章标题(阿拉伯数字)
_RE_TOC_CHAPTER = re.compile(r"^第\s*" + CN_NUM + r"+\s*章")   # 目录章条目(中文数字)

# 无编号但属于小结层级的固定标题
SPECIAL_HEADINGS = ("本章小结", "习题", "编者的话", "组编前言", "大纲前言")


def norm_heading(t):
    """仅规范化编号前缀中的易混淆字符, 其余原样返回。

    OCR 常把编号里的 '1' 认成 'L/l/I'、'0' 认成 'O/o'(如 '1.3.2' -> 'L 3 . 2'),
    只还原「孤立」的易混淆字符(前后都是分隔符或位于首尾), 避免误改标题正文里的
    "IO 模型"、"L2 cache" 这类词(字母与数字/字母直接相邻时不映射、并终止规范化)。
    """
    out = []
    norm_active = True
    n = len(t)
    for i, ch in enumerate(t):
        if norm_active:
            if ch in CONFUSE_MAP:
                prev_ok = i == 0 or t[i - 1] in _SEPARATORS
                next_ok = i == n - 1 or t[i + 1] in _SEPARATORS
                if prev_ok and next_ok:
                    out.append(CONFUSE_MAP[ch])
                    continue
                norm_active = False  # 与字母/数字相邻 -> 视为正文起始, 停止规范化
            elif ch in _PREFIX_CHARS:
                out.append(ch)
                continue
            else:
                norm_active = False  # 进入标题正文, 关闭规范化
        out.append(ch)
    return "".join(out)


def classify(text, size, min_size=HEADING_MIN_SIZE):
    """返回层级: 1=章, 2=节, 3=小结, 0=非标题。

    文本层可能含 OCR 残损: 编号里的 '1' 被识别成 'L'/'l'/'I',
    若不匹配数字则小节整段漏检、内容被并入上一节(见经验文件「已知坑」)。
    匹配前用 norm_heading 把编号前缀还原成数字。
    """
    t = text.strip()
    tn = norm_heading(t)
    if size < min_size:
        return 0
    # 章: 阿拉伯数字 "第N章" (正文)
    if _RE_CHAPTER.match(tn):
        return 1
    # 目录里的 "第一章" 中文数字 -> 排除(不是正文标题)
    if _RE_TOC_CHAPTER.match(tn):
        return 0
    # 编号标题: 容忍缺失的点/空格。OCR 常把 '1.3.2' 认成 'L 3 . 2'
    # (章节间的点也一起丢)。做法: 取开头连续 [数字/点/空格] 段,
    # 按分隔符切成数字组, 组数即层级 —— 3 组=小结, 2 组=节。
    # 兼容性: '10.2'(两位章节号) -> 组 ['10','2'] -> 2 组 -> 节, 正确。
    m = _RE_NUMBERED.match(tn) or _RE_NUMBER_ONLY.match(tn)
    if m:
        groups = [g for g in re.split(r"[.\s]+", m.group(1).strip()) if g]
        n = len(groups)
        if n == 3:
            return 3
        if n == 2:
            return 2
    if tn in SPECIAL_HEADINGS:
        return 3
    return 0
