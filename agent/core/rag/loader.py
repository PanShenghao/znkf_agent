"""
文件职能: 多格式文档加载 —— 按扩展名路由到对应解析器。
支持 .md/.txt/.pdf/.docx/.xlsx；图片 OCR 与复杂 PDF 版式解析（Unstructured）留作后续。
"""
from pathlib import Path

SUPPORTED_EXTS = {".md", ".txt", ".pdf", ".docx", ".xlsx"}


def list_supported_files(directory: str) -> list[Path]:
    """返回目录下所有受支持文档（按文件名排序，稳定）。"""
    p = Path(directory)
    files = [f for f in p.iterdir() if f.is_file() and f.suffix.lower() in SUPPORTED_EXTS]
    return sorted(files)


def load_document(path: str | Path) -> str:
    """按扩展名路由，把文档解析成纯文本。"""
    path = Path(path)
    ext = path.suffix.lower()
    if ext in (".md", ".txt"):
        return path.read_text(encoding="utf-8")
    if ext == ".pdf":
        return _load_pdf(path)
    if ext == ".docx":
        return _load_docx(path)
    if ext == ".xlsx":
        return _load_xlsx(path)
    raise ValueError(f"不支持的文件类型: {ext}")


def _load_pdf(path: Path) -> str:
    """PDF：抽文本层（扫描件 OCR 需后续接 OCR）。"""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    parts = []
    for i, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        if text.strip():
            parts.append(f"[第{i}页]\n{text}")
    return "\n\n".join(parts)


def _load_docx(path: Path) -> str:
    """DOCX：段落 + 表格（保留结构）。"""
    import docx

    d = docx.Document(str(path))
    parts = [p.text for p in d.paragraphs if p.text.strip()]
    for table in d.tables:
        parts.append("--- 表格 ---")
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            parts.append(" | ".join(cells))
    return "\n".join(parts)


def _load_xlsx(path: Path) -> str:
    """XLSX：按「Sheet + 行列」转结构化文本（当数据不当散文）。"""
    import openpyxl

    wb = openpyxl.load_workbook(str(path), data_only=True)
    parts = []
    for ws in wb.worksheets:
        parts.append(f"# Sheet: {ws.title}")
        for row in ws.iter_rows(values_only=True):
            cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts)
