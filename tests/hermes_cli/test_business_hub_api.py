import base64
import pytest

from hermes_cli.web_server import (
    BusinessAiRequest,
    BusinessOcrRequest,
    _extract_pdf_bytes_text,
    api_business_ai,
    api_business_ocr,
)


def _sample_minimal_pdf_bytes(text: str = "Facture Commerciale TchueKAM 250000 FCFA") -> bytes:
    stream = f"BT /F1 12 Tf 50 750 Td ({text}) Tj ET".encode("latin1")
    pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /Contents 4 0 R >>\nendobj\n"
        + f"4 0 obj\n<< /Length {len(stream)} >>\nstream\n".encode("latin1")
        + stream
        + b"\nendstream\nendobj\n%%EOF\n"
    )
    return pdf


def test_extract_pdf_bytes_text_extracts_literal_streams():
    pdf_bytes = _sample_minimal_pdf_bytes("Contrat de Prestation OHADA 2026")
    extracted = _extract_pdf_bytes_text(pdf_bytes)
    assert "Contrat de Prestation OHADA 2026" in extracted


@pytest.mark.asyncio
async def test_api_business_ocr_extracts_pdf_and_marks_empty_as_illegible():
    pdf_bytes = _sample_minimal_pdf_bytes("Attestation de Travail - Douala")
    data_url = "data:application/pdf;base64," + base64.b64encode(pdf_bytes).decode("ascii")

    res = await api_business_ocr(
        BusinessOcrRequest(
            data_url=data_url,
            file_name="attestation.pdf",
            mime_type="application/pdf",
        )
    )
    assert res["ok"] is True
    assert "Attestation de Travail - Douala" in res["text"]

    # Raster image without vision provider falls back to grounded [illegible] marker
    empty_png = base64.b64encode(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR").decode("ascii")
    res_img = await api_business_ocr(
        BusinessOcrRequest(
            data_url=f"data:image/png;base64,{empty_png}",
            file_name="scan.png",
            mime_type="image/png",
        )
    )
    assert res_img["ok"] is True
    assert "[illegible" in res_img["text"]


@pytest.mark.asyncio
async def test_api_business_ai_handles_offline_gracefully():
    res = await api_business_ai(
        BusinessAiRequest(
            operation="improve_summary",
            input="Ingénieur logiciel senior",
            language="fr",
            context="Architecte Cloud",
        )
    )
    assert isinstance(res, dict)
    assert "ok" in res

