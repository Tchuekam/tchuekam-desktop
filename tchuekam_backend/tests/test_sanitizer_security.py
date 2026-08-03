"""
Tests unitaires et d'intégration pour l'assainissement XSS, l'en-tête de sécurité HTTP et la mise en cache.
"""

from fastapi.testclient import TestClient
from tchuekam_backend.core.cache import cache_service
from tchuekam_backend.core.sanitizer import XSSSanitizer
from tchuekam_backend.main import app

client = TestClient(app)


def test_xss_sanitizer_strips_dangerous_scripts():
    payload = "<script>alert('xss')</script>Hello <b>World</b>"
    cleaned = XSSSanitizer.sanitize_string(payload, allow_html=False)
    assert "<script>" not in cleaned
    assert "alert" not in cleaned
    assert "Hello World" in cleaned or "Hello &lt;b&gt;World&lt;/b&gt;" in cleaned or "Hello World" in cleaned


def test_security_headers_in_response():
    response = client.get("/health")
    assert response.status_code == 200
    headers = response.headers
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("X-XSS-Protection") == "1; mode=block"
    assert "default-src 'self'" in headers.get("Content-Security-Policy", "")


def test_cache_service_operations():
    cache_service.clear()
    assert cache_service.get("key1") is None
    cache_service.set("key1", {"data": "test_val"}, ttl_seconds=10)
    assert cache_service.get("key1") == {"data": "test_val"}
    cache_service.delete("key1")
    assert cache_service.get("key1") is None
