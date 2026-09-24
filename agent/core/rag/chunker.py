"""
文件职能: 父子分块（Parent-Child Chunking）。
- 大 parent（~600 字符，按段落边界）用于生成上下文；
- 小 child（~200 字符，带 overlap）用于检索；
- 检索命中 child 后，返回其 parent 全文，兼顾「检索精度」与「生成上下文」。
"""
import re
from .schema import PARENT_SIZE, CHILD_SIZE, CHILD_OVERLAP


def _split_parents(text: str, size: int = PARENT_SIZE) -> list[str]:
    """按段落边界切 parent（尽量不超过 size；超长段落再按句切；超长句硬切兜底）。"""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    parents = []
    current = ""
    for p in paragraphs:
        if len(p) > size:
            # 超长段落：先按句号切
            for piece in re.split(r"(?<=[。！？!?])", p):
                piece = piece.strip()
                if not piece:
                    continue
                if len(piece) > size:
                    # 超长句（无标点，如长表格行）：硬切兜底
                    if current:
                        parents.append(current)
                        current = ""
                    for j in range(0, len(piece), size):
                        chunk = piece[j:j + size].strip()
                        if chunk:
                            parents.append(chunk)
                elif len(current) + len(piece) + 1 <= size:
                    current = (current + " " + piece).strip()
                else:
                    if current:
                        parents.append(current)
                    current = piece
        else:
            if len(current) + len(p) + 1 <= size:
                current = (current + "\n" + p).strip() if current else p
            else:
                if current:
                    parents.append(current)
                current = p
    if current:
        parents.append(current)
    return parents


def _split_children(parent: str, size: int = CHILD_SIZE, overlap: int = CHILD_OVERLAP) -> list[str]:
    """把 parent 切成带 overlap 的 child。"""
    children = []
    start = 0
    while start < len(parent):
        piece = parent[start:start + size].strip()
        if piece:
            children.append(piece)
        start += size - overlap
    return children


def chunk_document(text: str, parent_size: int = PARENT_SIZE, child_size: int = CHILD_SIZE,
                   overlap: int = CHILD_OVERLAP) -> list[dict]:
    """返回 child 块列表，每块含 parent 上下文。
    结构: [{"parent_id", "parent_text", "content"}]"""
    parents = _split_parents(text, parent_size)
    chunks = []
    for pi, parent in enumerate(parents):
        for child in _split_children(parent, child_size, overlap):
            chunks.append({
                "parent_id": f"p{pi}",
                "parent_text": parent,
                "content": child,
            })
    return chunks
