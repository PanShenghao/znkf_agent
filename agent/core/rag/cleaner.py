"""
文件职能: 文档清洗 —— 去噪声、归一化，为切块/向量化做准备。
"""
import re


def clean_text(text: str) -> str:
    """统一的清洗管道。"""
    if not text:
        return ""
    # 统一换行
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # 全角空格/特殊空白 → 半角空格
    text = text.replace("　", " ")
    # 去掉连续 3+ 空行 → 2 空行
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 行尾去空格
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    # 连续空格/制表符 → 单个空格
    text = re.sub(r"[ \t]{2,}", " ", text)
    # 注意：保留段落空行（供分块按段落切），只把 3+ 空行压成 2 空行
    return text.strip()
