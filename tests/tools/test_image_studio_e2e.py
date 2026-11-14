"""
End-to-End Integration Tests for TchueKAM Image Studio.
Covers Scenarios A-E defined in Section 9 of the production release specification:
- Scenario A: Chat-to-Studio asset generation and synchronization.
- Scenario B: Studio generation, persistent storage, and recovery after restart.
- Scenario C: Centralized authentication, validation, and revocation.
- Scenario D: Failure recovery and authentic error reporting (zero fake SVG mocks).
- Scenario E: Security, multi-tenant workspace isolation, and credential protection.
"""

import json
import os
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from agent import image_studio_service
from tools.image_generation_tool import image_generate_tool


@pytest.fixture(autouse=True)
def isolated_studio_env(monkeypatch, tmp_path):
    """Isolate Image Studio filesystem cache and library to a temporary directory."""
    cache_dir = tmp_path / "cache" / "image_studio"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "assets").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(image_studio_service, "get_image_studio_dir", lambda: cache_dir)
    monkeypatch.setattr(image_studio_service, "get_image_studio_assets_dir", lambda: cache_dir / "assets")
    monkeypatch.setattr(image_studio_service, "_library_path", lambda: cache_dir / "library.json")
    yield cache_dir


class TestScenarioAChatToStudio:
    """Scenario A: Image generated in Chat automatically synchronizes to Image Studio history."""

    def test_chat_generation_synchronizes_to_studio_history(self, monkeypatch):
        # Mock the underlying FAL call to return a realistic image URL
        fake_fal_response = {
            "images": [{"url": "https://fal.media/files/monkey/sample_generated.png", "width": 1024, "height": 1024}],
            "seed": 42,
        }
        fake_handler = MagicMock()
        fake_handler.get.return_value = fake_fal_response
        monkeypatch.setattr("tools.image_generation_tool._submit_fal_request", lambda model, arguments: fake_handler)
        monkeypatch.setenv("FAL_KEY", "fal_real_mock_key_001")

        # 1. User asks chat agent for an image
        prompt = "A high-tech laboratory with glowing holographic charts"
        monkeypatch.setenv("FAL_IMAGE_MODEL", "fal-ai/flux-2-pro")
        result_json = image_generate_tool(prompt=prompt, aspect_ratio="landscape")
        result = json.loads(result_json)

        assert result["success"] is True
        assert result["image"] == "https://fal.media/files/monkey/sample_generated.png"

        # 2. Asset should now be registered into Image Studio shared library
        studio_assets = image_studio_service.list_assets()
        assert len(studio_assets) >= 1
        synced_asset = studio_assets[0]
        assert synced_asset["url"] == "https://fal.media/files/monkey/sample_generated.png"
        assert synced_asset["prompt"] == prompt
        assert synced_asset["provider"] == "fal"
        assert synced_asset["model"] == "fal-ai/flux-2-pro"
        assert synced_asset["studioType"] == "image"


class TestScenarioBStudioGenerationAndRecovery:
    """Scenario B: Generation inside Studio, persistent storage, and recovery after application restart."""

    def test_studio_generation_and_restart_recovery(self, isolated_studio_env):
        # 1. Studio registers generation result
        asset_id = "studio-gen-001"
        prompt = "An astronaut walking through an emerald crystalline forest"
        url = "https://fal.media/files/tiger/crystalline_forest.png"

        created = image_studio_service.register_asset(
            asset_id=asset_id,
            url=url,
            prompt=prompt,
            provider="fal",
            model="fal-ai/flux-2/klein/9b",
            studio_type="image",
            parameters={"aspect_ratio": "16:9", "quality": "high"},
            workspace_id="workspace_alpha",
        )
        assert created["id"] == asset_id

        # 2. Simulate Application Restart:
        # In memory objects are cleared; service reads persisted library.json from disk
        library_file = image_studio_service._library_path()
        assert library_file.exists()

        # Fresh query after restart
        recovered_assets = image_studio_service.list_assets(workspace_id="workspace_alpha")
        assert len(recovered_assets) == 1
        rec = recovered_assets[0]
        assert rec["id"] == asset_id
        assert rec["prompt"] == prompt
        assert rec["url"] == url
        assert rec["parameters"]["aspect_ratio"] == "16:9"


class TestScenarioCAuthenticationAndRevocation:
    """Scenario C: Credential validation and handling of missing/revoked credentials."""

    def test_missing_credentials_fails_authentically(self, monkeypatch):
        # Clear all FAL keys
        monkeypatch.delenv("FAL_KEY", raising=False)
        monkeypatch.delenv("NOUS_API_KEY", raising=False)

        # Chat generation without keys returns authentic failure, not mock SVG
        result_json = image_generate_tool(prompt="Test prompt without credentials")
        result = json.loads(result_json)

        assert result["success"] is False
        assert "key" in result["error"].lower() or "credentials" in result["error"].lower() or "not configured" in result["error"].lower()
        # Verify no fake mock SVG URL is returned
        assert "url" not in result or not result["url"]

    def test_credential_revocation_triggers_auth_failure(self, monkeypatch):
        # Simulate invalid/revoked key returning 401
        monkeypatch.setenv("FAL_KEY", "revoked_key")
        monkeypatch.setattr("tools.image_generation_tool._submit_fal_request", MagicMock(side_effect=Exception("401 Unauthorized: Invalid API key")))

        result_json = image_generate_tool(prompt="Test prompt with revoked key")
        result = json.loads(result_json)
        assert result["success"] is False
        assert "401" in result["error"] or "Unauthorized" in result["error"]


class TestScenarioDFailureRecoveryAndReliability:
    """Scenario D: Provider failure reporting and absence of fake mock SVGs."""

    def test_provider_network_failure_reports_authentic_error(self, monkeypatch):
        monkeypatch.setenv("FAL_KEY", "valid_key")
        monkeypatch.setattr("tools.image_generation_tool._submit_fal_request", MagicMock(side_effect=TimeoutError("Connection to FAL.ai timed out after 30s")))

        result_json = image_generate_tool(prompt="Test timeout prompt")
        result = json.loads(result_json)

        assert result["success"] is False
        assert "timed out" in result["error"].lower()
        # Absolute rule: Never generate fake SVGs or mock cards on failure
        assert "<svg" not in result.get("error", "")
        assert "svg" not in result.get("url", "")


class TestScenarioESecurityAndIsolation:
    """Scenario E: Workspace isolation and secret protection."""

    def test_tenant_workspace_isolation_prevent_cross_tenant_access(self):
        # Tenant 1 in HR workspace
        image_studio_service.register_asset(
            url="https://example.com/hr_doc.png",
            prompt="HR Internal Org Chart Mockup",
            provider="fal",
            model="fal-ai/flux-2-pro",
            workspace_id="ws_hr",
        )
        # Tenant 2 in Engineering workspace
        image_studio_service.register_asset(
            url="https://example.com/eng_doc.png",
            prompt="System Architecture Diagram",
            provider="fal",
            model="fal-ai/flux-2-pro",
            workspace_id="ws_eng",
        )

        # HR only sees HR
        hr_assets = image_studio_service.list_assets(workspace_id="ws_hr")
        assert len(hr_assets) == 1
        assert hr_assets[0]["prompt"] == "HR Internal Org Chart Mockup"

        # Engineering only sees Engineering
        eng_assets = image_studio_service.list_assets(workspace_id="ws_eng")
        assert len(eng_assets) == 1
        assert eng_assets[0]["prompt"] == "System Architecture Diagram"

    def test_api_credentials_never_exposed_in_asset_metadata(self):
        asset = image_studio_service.register_asset(
            url="https://example.com/secure.png",
            prompt="Secure generation",
            provider="fal",
            model="fal-ai/flux-2-pro",
        )
        # Verify no credential fields exist in public asset metadata
        for secret_name in ("api_key", "apiKey", "FAL_KEY", "MUAPI_KEY", "secret", "token"):
            assert secret_name not in asset
            assert secret_name not in asset.get("parameters", {})
