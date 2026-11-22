"""Lightweight offline OCR helper for Business Hub desktop app.

Reads a JSON payload on stdin:
  {"data_url": "data:...;base64,...", "file_name": "...", "mime_type": "..."}

Writes a single JSON object to stdout:
  {"ok": true, "text": "...", "engine": "rapidocr|pypdf|fitz|utf8"}
or:
  {"ok": false, "unavailable": false, "error": "..."}

Designed for 2 GB RAM office PCs: caps image dimensions before OCR and runs
as a short-lived one-shot process so all OCR memory is reclaimed immediately.
"""

from __future__ import annotations

import base64
import io
import json
import sys
from typing import Any


MAX_IMAGE_EDGE = 1600
MAX_OCR_PDF_PAGES = 3


def _decode_payload_bytes(data_url: str) -> bytes:
    raw = (data_url or "").strip()
    if "," in raw:
        raw = raw.split(",", 1)[1]
    return base64.b64decode(raw)


def _resize_image_for_low_ram(img: Any) -> Any:
    from PIL import Image, ImageOps

    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    elif img.mode == "L":
        img = img.convert("RGB")

    width, height = img.size
    longest = max(width, height)
    if longest > MAX_IMAGE_EDGE:
        scale = MAX_IMAGE_EDGE / float(longest)
        new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
        img = img.resize(new_size, Image.Resampling.BILINEAR)
    return img


def _run_rapidocr_on_image_bytes(image_bytes: bytes) -> str:
    import numpy as np
    from PIL import Image
    from rapidocr_onnxruntime import RapidOCR

    img = Image.open(io.BytesIO(image_bytes))
    img = _resize_image_for_low_ram(img)
    arr = np.array(img)
    ocr = RapidOCR()
    result, _ = ocr(arr)
    if not result:
        return ""
    lines = [str(item[1]).strip() for item in result if len(item) >= 2 and str(item[1]).strip()]
    return "\n".join(lines).strip()


def _extract_pdf_text(pdf_bytes: bytes) -> tuple[str, str]:
    # 1. Fast embedded text layer via pypdf
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
        text = "\n\n".join(p for p in pages if p).strip()
        if text:
            return text, "pypdf"
    except Exception:
        pass

    # 2. Embedded text layer or raster fallback via PyMuPDF (if installed)
    try:
        import fitz

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages = [page.get_text("text").strip() for page in doc]
        text = "\n\n".join(p for p in pages if p).strip()
        if text:
            return text, "fitz"

        ocr_chunks: list[str] = []
        for idx, page in enumerate(doc):
            if idx >= MAX_OCR_PDF_PAGES:
                break
            pix = page.get_pixmap(dpi=140, alpha=False)
            page_text = _run_rapidocr_on_image_bytes(pix.tobytes("png"))
            if page_text:
                ocr_chunks.append(page_text)
        joined = "\n\n".join(ocr_chunks).strip()
        if joined:
            return joined, "rapidocr-pdf"
    except Exception:
        pass

    return "", "none"


def main() -> int:
    try:
        raw_bytes = sys.stdin.buffer.read()
        raw_input = raw_bytes.decode("utf-8-sig", errors="replace").strip()
        payload = json.loads(raw_input or "{}")
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"Invalid JSON input: {exc}"}))
        return 1

    try:
        file_bytes = _decode_payload_bytes(str(payload.get("data_url") or ""))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"Invalid base64 payload: {exc}"}))
        return 1

    mime = str(payload.get("mime_type") or "").lower()
    fname = str(payload.get("file_name") or "").lower()

    if "pdf" in mime or fname.endswith(".pdf") or file_bytes.startswith(b"%PDF"):
        text, engine = _extract_pdf_text(file_bytes)
        if text:
            print(json.dumps({"ok": True, "text": text, "engine": engine}))
            return 0
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "PDF contains no extractable text layer.",
                }
            )
        )
        return 0

    try:
        import rapidocr_onnxruntime  # noqa: F401
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "unavailable": True,
                    "error": f"rapidocr_onnxruntime unavailable: {exc}",
                }
            )
        )
        return 0

    try:
        text = _run_rapidocr_on_image_bytes(file_bytes)
        if text:
            print(json.dumps({"ok": True, "text": text, "engine": "rapidocr"}))
            return 0
        print(
            json.dumps(
                {
                    "ok": True,
                    "text": f"[{payload.get('file_name') or 'scan'}]\n[illegible — no readable text detected in image. Unclear text is marked [illegible], never guessed.]",
                    "engine": "rapidocr",
                }
            )
        )
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"OCR failed: {exc}"}))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
