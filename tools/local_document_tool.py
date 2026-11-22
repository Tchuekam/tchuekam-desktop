"""Offline-capable local document reader tool for PDF, DOCX, XLSX, CSV, RTF, PPTX, and OCR images."""

from __future__ import annotations

import csv
import html
import io
import json
import logging
import os
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

from tools.registry import registry

logger = logging.getLogger(__name__)

_OCR_ENGINE: Any = None

IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff", ".tif"})
TEXT_EXTENSIONS = frozenset({
    ".txt", ".md", ".markdown", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".log", ".py", ".js", ".ts", ".tsx", ".jsx", ".css", ".html", ".xml", ".sql",
    ".sh", ".ps1", ".bat", ".c", ".cpp", ".h", ".rs", ".go", ".java", ".env",
})


def _resolve_readable_path(file_path: str) -> Path:
    raw = (file_path or "").strip()
    if not raw:
        raise ValueError("path is required")
    p = Path(raw).expanduser()
    if not p.is_absolute():
        cwd = os.getenv("TERMINAL_CWD") or os.getcwd()
        p = Path(cwd) / p
    return p.resolve()


def _parse_page_range(page_range: Optional[str], total_pages: int) -> List[int]:
    if not page_range or not page_range.strip():
        return list(range(total_pages))
    indices: List[int] = []
    for part in page_range.split(","):
        chunk = part.strip()
        if not chunk:
            continue
        if "-" in chunk:
            a_str, b_str = chunk.split("-", 1)
            start = max(1, int(a_str.strip()))
            end = min(total_pages, int(b_str.strip()))
            for i in range(start, end + 1):
                if (i - 1) not in indices:
                    indices.append(i - 1)
        else:
            idx = int(chunk) - 1
            if 0 <= idx < total_pages and idx not in indices:
                indices.append(idx)
    return indices or list(range(total_pages))


def _read_pdf(path: Path, page_range: Optional[str]) -> tuple[str, int]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    total = len(reader.pages)
    chosen = _parse_page_range(page_range, total)
    chunks: List[str] = []
    for idx in chosen:
        text = reader.pages[idx].extract_text() or ""
        if text.strip():
            chunks.append(f"[Page {idx + 1}]\n{text.strip()}")
    return ("\n\n".join(chunks), total)


def _read_docx(path: Path) -> tuple[str, int]:
    try:
        from docx import Document

        doc = Document(str(path))
        parts: List[str] = []
        for para in doc.paragraphs:
            if para.text and para.text.strip():
                parts.append(para.text.strip())
        for table in doc.tables:
            for row in table.rows:
                cells = [c.text.strip().replace("\n", " ") for c in row.cells]
                if any(cells):
                    parts.append(" | ".join(cells))
        if parts:
            return ("\n".join(parts), len(parts))
    except Exception:
        pass

    # Pure-stdlib Office Open XML (.docx) fallback (zero external dependencies)
    with zipfile.ZipFile(path, "r") as zf:
        if "word/document.xml" not in zf.namelist():
            return ("", 0)
        root = ET.fromstring(zf.read("word/document.xml"))
        paragraphs: List[str] = []
        for p_el in root.iter():
            if p_el.tag.endswith("}p") or p_el.tag == "p":
                texts = [
                    t_el.text
                    for t_el in p_el.iter()
                    if (t_el.tag.endswith("}t") or t_el.tag == "t") and t_el.text
                ]
                line = "".join(texts).strip()
                if line:
                    paragraphs.append(line)
        return ("\n".join(paragraphs), len(paragraphs))


def _xlsx_col_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha()).upper()
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return max(0, idx - 1)


def _read_xlsx(path: Path, max_rows_per_sheet: int = 250) -> tuple[str, int]:
    try:
        import openpyxl  # type: ignore

        wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
        sheets_out: List[str] = []
        for name in wb.sheetnames:
            ws = wb[name]
            rows_txt: List[str] = []
            for r_idx, row in enumerate(ws.iter_rows(values_only=True)):
                if r_idx >= max_rows_per_sheet:
                    rows_txt.append("... [rows truncated]")
                    break
                vals = ["" if v is None else str(v).strip() for v in row]
                if any(vals):
                    rows_txt.append(" | ".join(vals))
            if rows_txt:
                sheets_out.append(f"[Sheet: {name}]\n" + "\n".join(rows_txt))
        count = len(wb.sheetnames)
        wb.close()
        return ("\n\n".join(sheets_out), count)
    except Exception:
        pass

    # Pure-stdlib XML fallback (always works offline with zero extra packages)
    with zipfile.ZipFile(path, "r") as zf:
        shared_strings: List[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            ss_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in ss_root.iter():
                if si.tag.endswith("}si") or si.tag == "si":
                    texts = [t.text or "" for t in si.iter() if t.tag.endswith("}t") or t.tag == "t"]
                    shared_strings.append("".join(texts))

        sheet_names: List[tuple[str, str]] = []
        if "xl/workbook.xml" in zf.namelist() and "xl/_rels/workbook.xml.rels" in zf.namelist():
            rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
            rid_to_target: Dict[str, str] = {}
            for rel in rels_root:
                rid = rel.attrib.get("Id")
                target = rel.attrib.get("Target")
                if rid and target:
                    target_norm = target.lstrip("/")
                    if not target_norm.startswith("xl/"):
                        target_norm = "xl/" + target_norm
                    rid_to_target[rid] = target_norm
            wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
            for elem in wb_root.iter():
                if elem.tag.endswith("}sheet") or elem.tag == "sheet":
                    sname = elem.attrib.get("name", "Sheet")
                    rid = next((v for k, v in elem.attrib.items() if k.endswith("}id") or k == "id"), "")
                    target = rid_to_target.get(rid)
                    if target and target in zf.namelist():
                        sheet_names.append((sname, target))

        if not sheet_names:
            for name in sorted(zf.namelist()):
                if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"):
                    sheet_names.append((Path(name).stem, name))

        sheets_out: List[str] = []
        for sname, sfile in sheet_names:
            root = ET.fromstring(zf.read(sfile))
            rows_txt: List[str] = []
            for r_idx, row_el in enumerate(root.iter()):
                if not (row_el.tag.endswith("}row") or row_el.tag == "row"):
                    continue
                if len(rows_txt) >= max_rows_per_sheet:
                    rows_txt.append("... [rows truncated]")
                    break
                row_cells: Dict[int, str] = {}
                for c_el in row_el:
                    if not (c_el.tag.endswith("}c") or c_el.tag == "c"):
                        continue
                    ref = c_el.attrib.get("r", "")
                    col_idx = _xlsx_col_index(ref) if ref else len(row_cells)
                    ctype = c_el.attrib.get("t", "")
                    val_str = ""
                    if ctype == "inlineStr":
                        val_str = "".join(t.text or "" for t in c_el.iter() if t.tag.endswith("}t") or t.tag == "t")
                    else:
                        v_el = next((ch for ch in c_el if ch.tag.endswith("}v") or ch.tag == "v"), None)
                        raw_val = v_el.text if (v_el is not None and v_el.text is not None) else ""
                        if ctype == "s" and raw_val.isdigit():
                            sidx = int(raw_val)
                            val_str = shared_strings[sidx] if 0 <= sidx < len(shared_strings) else raw_val
                        else:
                            val_str = raw_val
                    row_cells[col_idx] = val_str.strip()
                if row_cells and any(row_cells.values()):
                    max_col = max(row_cells.keys())
                    ordered = [row_cells.get(i, "") for i in range(max_col + 1)]
                    rows_txt.append(" | ".join(ordered))
            if rows_txt:
                sheets_out.append(f"[Sheet: {sname}]\n" + "\n".join(rows_txt))
        return ("\n\n".join(sheets_out), len(sheet_names))


def _read_pptx(path: Path) -> tuple[str, int]:
    with zipfile.ZipFile(path, "r") as zf:
        slides = sorted(
            n for n in zf.namelist()
            if re.match(r"ppt/slides/slide\d+\.xml$", n)
        )
        out: List[str] = []
        for idx, sfile in enumerate(slides, 1):
            root = ET.fromstring(zf.read(sfile))
            texts = [el.text.strip() for el in root.iter() if (el.tag.endswith("}t") or el.tag == "t") and el.text and el.text.strip()]
            if texts:
                out.append(f"[Slide {idx}]\n" + "\n".join(texts))
        return ("\n\n".join(out), len(slides))


def _read_rtf(path: Path) -> tuple[str, int]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    # Strip RTF control groups like {\fonttbl ...} cleanly while keeping readable prose
    text = re.sub(r"\{\\(?:fonttbl|colortbl|stylesheet|info|pict|object)[^{}]*\}", "", raw, flags=re.I | re.S)
    text = re.sub(r"\\par[d]?\b", "\n", text)
    text = re.sub(r"\\tab\b", "\t", text)
    text = re.sub(r"\\'([0-9a-fA-F]{2})", lambda m: bytes.fromhex(m.group(1)).decode("cp1252", errors="replace"), text)
    text = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", text)
    text = text.replace("{", "").replace("}", "")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return (text, 1)


def _read_csv(path: Path, delimiter: Optional[str] = None, max_rows: int = 300) -> tuple[str, int]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    sep = delimiter or ("\t" if path.suffix.lower() == ".tsv" else ",")
    reader = csv.reader(io.StringIO(raw), delimiter=sep)
    lines: List[str] = []
    for idx, row in enumerate(reader):
        if idx >= max_rows:
            lines.append("... [rows truncated]")
            break
        lines.append(" | ".join(cell.strip() for cell in row))
    return ("\n".join(lines), len(lines))


def _ocr_image(path: Path) -> tuple[str, int]:
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        from rapidocr_onnxruntime import RapidOCR

        _OCR_ENGINE = RapidOCR()
    result, _ = _OCR_ENGINE(str(path))
    if not result:
        return ("", 0)
    lines = [str(item[1]).strip() for item in result if len(item) >= 2 and str(item[1]).strip()]
    return ("\n".join(lines), len(lines))


def read_document(
    path: str,
    max_chars: int = 24000,
    page_range: Optional[str] = None,
    ocr: bool = True,
) -> str:
    """Read local documents (PDF, DOCX, XLSX, CSV, RTF, PPTX, images via OCR, text) offline."""
    try:
        resolved = _resolve_readable_path(path)
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)

    if not resolved.exists() or not resolved.is_file():
        return json.dumps({
            "success": False,
            "path": str(resolved),
            "error": f"Document not found: {resolved}",
        }, ensure_ascii=False)

    ext = resolved.suffix.lower()
    max_chars = max(500, min(int(max_chars or 24000), 200000))
    fmt = ext.lstrip(".") or "txt"
    units = 1

    try:
        if ext == ".pdf":
            content, units = _read_pdf(resolved, page_range)
        elif ext in {".docx", ".docm"}:
            content, units = _read_docx(resolved)
        elif ext in {".xlsx", ".xlsm"}:
            content, units = _read_xlsx(resolved)
        elif ext == ".pptx":
            content, units = _read_pptx(resolved)
        elif ext == ".rtf":
            content, units = _read_rtf(resolved)
        elif ext in {".csv", ".tsv"}:
            content, units = _read_csv(resolved)
        elif ext in IMAGE_EXTENSIONS:
            if not ocr:
                return json.dumps({
                    "success": False,
                    "path": str(resolved),
                    "error": "OCR disabled for image document",
                }, ensure_ascii=False)
            content, units = _ocr_image(resolved)
            fmt = "image-ocr"
        elif ext in {".html", ".htm"}:
            raw_html = resolved.read_text(encoding="utf-8", errors="replace")
            content = html.unescape(re.sub(r"<[^>]+>", " ", raw_html))
            content = re.sub(r"[ \t]+", " ", content).strip()
        else:
            raw_bytes = resolved.read_bytes()
            if b"\x00" in raw_bytes[:4096] and ext not in TEXT_EXTENSIONS:
                return json.dumps({
                    "success": False,
                    "path": str(resolved),
                    "error": f"Unsupported binary document format '{ext}'",
                }, ensure_ascii=False)
            content = raw_bytes.decode("utf-8", errors="replace")
    except Exception as exc:
        logger.warning("read_document failed on %s: %s", resolved, exc)
        return json.dumps({
            "success": False,
            "path": str(resolved),
            "format": fmt,
            "error": f"Failed to read document ({fmt}): {exc}",
        }, ensure_ascii=False)

    truncated = len(content) > max_chars
    if truncated:
        content = content[:max_chars].rstrip() + "\n... [content truncated]"

    return json.dumps({
        "success": True,
        "path": str(resolved),
        "format": fmt,
        "units": units,
        "truncated": truncated,
        "content": content,
    }, ensure_ascii=False)


def check_local_document_requirements() -> bool:
    return True


registry.register(
    name="read_document",
    toolset="file",
    schema={
        "name": "read_document",
        "description": (
            "Read and extract text offline from local documents including PDF (.pdf), Word (.docx), "
            "Excel spreadsheets (.xlsx), PowerPoint (.pptx), RTF (.rtf), CSV/TSV, HTML, plain text/code, "
            "and images via offline OCR (.png, .jpg, .webp)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the local document or image file.",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters to return (default 24000).",
                },
                "page_range": {
                    "type": "string",
                    "description": "Optional 1-indexed PDF page range such as '1-3' or '1,4'.",
                },
                "ocr": {
                    "type": "boolean",
                    "description": "Enable local offline OCR for image files (default true).",
                },
            },
            "required": ["path"],
        },
    },
    handler=lambda args, **kw: read_document(
        path=str(args.get("path") or ""),
        max_chars=int(args.get("max_chars") or 24000),
        page_range=args.get("page_range"),
        ocr=bool(args.get("ocr", True)),
    ),
    check_fn=check_local_document_requirements,
    emoji="📄",
)
