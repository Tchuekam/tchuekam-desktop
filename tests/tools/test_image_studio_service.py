"""
Unit tests for agent.image_studio_service.
Verifies shared generation history, asset registration, CRUD operations,
multi-tenant workspace isolation, provider discovery, and synchronized model catalog.
"""

import json
import os
import tempfile
import uuid
import pytest
from pathlib import Path

from agent import image_studio_service


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


class TestImageStudioServiceRegistration:
    def test_register_asset_minimal(self):
        asset = image_studio_service.register_asset(
            url="https://example.com/generated_1.png",
            prompt="A futuristic neon cyber city",
            provider="fal",
            model="fal-ai/flux-2/klein/9b",
        )
        assert asset["id"] is not None
        assert asset["url"] == "https://example.com/generated_1.png"
        assert asset["prompt"] == "A futuristic neon cyber city"
        assert asset["provider"] == "fal"
        assert asset["model"] == "fal-ai/flux-2/klein/9b"
        assert asset["studioType"] == "image"
        assert asset["mimeType"] == "image/png"
        assert asset["status"] == "completed"
        assert asset["workspaceId"] == "default"

    def test_register_asset_full_metadata(self, tmp_path):
        dummy_file = tmp_path / "test_cached.png"
        dummy_file.write_bytes(b"\x89PNG\r\n\x1a\n")

        custom_id = "asset-custom-uuid-123"
        asset = image_studio_service.register_asset(
            url="https://example.com/asset123.mp4",
            prompt="A cinematic drone shot over mountains",
            provider="fal",
            model="fal-ai/ltx-2.3-22b/text-to-video",
            studio_type="video",
            parameters={"aspect_ratio": "16:9", "duration": 5, "resolution": "1080p"},
            dimensions={"width": 1920, "height": 1080},
            duration=5.0,
            mime_type="video/mp4",
            local_path=str(dummy_file),
            user_id="user_alice",
            workspace_id="workspace_prod",
            conversation_id="conv_9988",
            job_id="job_fal_001",
            tags=["cinematic", "drone", "4k"],
            favorite=True,
            asset_id=custom_id,
        )
        assert asset["id"] == custom_id
        assert asset["userId"] == "user_alice"
        assert asset["workspaceId"] == "workspace_prod"
        assert asset["conversationId"] == "conv_9988"
        assert asset["jobId"] == "job_fal_001"
        assert asset["studioType"] == "video"
        assert asset["mimeType"] == "video/mp4"
        assert asset["dimensions"] == {"width": 1920, "height": 1080}
        assert asset["duration"] == 5.0
        assert asset["tags"] == ["cinematic", "drone", "4k"]
        assert asset["favorite"] is True
        assert asset["localPath"] == str(dummy_file)


class TestImageStudioServiceQueryAndFilter:
    def test_list_and_get_assets(self):
        # Register two assets
        a1 = image_studio_service.register_asset(
            url="https://example.com/img1.png",
            prompt="A golden retriever in autumn leaves",
            provider="fal",
            model="fal-ai/flux-2-pro",
            studio_type="image",
        )
        a2 = image_studio_service.register_asset(
            url="https://example.com/vid1.mp4",
            prompt="Ocean waves crashing against rocks",
            provider="muapi",
            model="kling-video",
            studio_type="video",
        )

        all_assets = image_studio_service.list_assets()
        assert len(all_assets) == 2
        # Verify chronological order (newest first)
        assert all_assets[0]["id"] == a2["id"]
        assert all_assets[1]["id"] == a1["id"]

        # Get by id
        fetched = image_studio_service.get_asset(a1["id"])
        assert fetched is not None
        assert fetched["prompt"] == "A golden retriever in autumn leaves"

        assert image_studio_service.get_asset("non-existent-id") is None

    def test_filter_by_studio_type(self):
        image_studio_service.register_asset(url="u1", prompt="p1", provider="fal", model="m1", studio_type="image")
        image_studio_service.register_asset(url="u2", prompt="p2", provider="fal", model="m2", studio_type="video")
        image_studio_service.register_asset(url="u3", prompt="p3", provider="muapi", model="m3", studio_type="audio")

        imgs = image_studio_service.list_assets(studio_type="image")
        assert len(imgs) == 1
        assert imgs[0]["prompt"] == "p1"

        vids = image_studio_service.list_assets(studio_type="video")
        assert len(vids) == 1
        assert vids[0]["prompt"] == "p2"

        audios = image_studio_service.list_assets(studio_type="audio")
        assert len(audios) == 1
        assert audios[0]["prompt"] == "p3"

    def test_filter_by_provider_and_search(self):
        image_studio_service.register_asset(
            url="u1",
            prompt="Neon cyberpunk street",
            provider="fal",
            model="fal-ai/flux-2-pro",
            tags=["cyberpunk", "tokyo"],
        )
        image_studio_service.register_asset(
            url="u2",
            prompt="Cozy coffee shop interior",
            provider="muapi",
            model="flux-schnell",
            tags=["interior", "warm"],
        )

        fal_assets = image_studio_service.list_assets(provider="fal")
        assert len(fal_assets) == 1
        assert fal_assets[0]["provider"] == "fal"

        muapi_assets = image_studio_service.list_assets(provider="muapi")
        assert len(muapi_assets) == 1
        assert muapi_assets[0]["provider"] == "muapi"

        # Search by tag
        search_results = image_studio_service.list_assets(search="tokyo")
        assert len(search_results) == 1
        assert search_results[0]["prompt"] == "Neon cyberpunk street"

        # Search by prompt word
        search_coffee = image_studio_service.list_assets(search="coffee")
        assert len(search_coffee) == 1
        assert search_coffee[0]["prompt"] == "Cozy coffee shop interior"


class TestWorkspaceIsolation:
    def test_multi_tenant_workspace_isolation(self):
        # Register assets under separate workspaces
        a_team1 = image_studio_service.register_asset(
            url="u_team1",
            prompt="Confidential product mock",
            provider="fal",
            model="fal-ai/flux-2/klein/9b",
            workspace_id="ws_finance",
        )
        a_team2 = image_studio_service.register_asset(
            url="u_team2",
            prompt="Public marketing banner",
            provider="fal",
            model="fal-ai/flux-2/klein/9b",
            workspace_id="ws_marketing",
        )

        # Query as ws_finance
        finance_items = image_studio_service.list_assets(workspace_id="ws_finance")
        assert len(finance_items) == 1
        assert finance_items[0]["id"] == a_team1["id"]
        assert all(item["workspaceId"] == "ws_finance" for item in finance_items)

        # Query as ws_marketing
        marketing_items = image_studio_service.list_assets(workspace_id="ws_marketing")
        assert len(marketing_items) == 1
        assert marketing_items[0]["id"] == a_team2["id"]
        assert all(item["workspaceId"] == "ws_marketing" for item in marketing_items)

        # Unauthorized delete attempt: ws_marketing tries to delete ws_finance asset
        deleted = image_studio_service.delete_asset(a_team1["id"], workspace_id="ws_marketing")
        assert deleted is False

        # Verify finance asset still exists (scoped lookup) and is invisible elsewhere
        assert image_studio_service.get_asset(a_team1["id"], workspace_id="ws_finance") is not None
        assert image_studio_service.get_asset(a_team1["id"], workspace_id="ws_marketing") is None
        assert image_studio_service.get_asset(a_team1["id"]) is None  # default workspace != all workspaces
        assert image_studio_service.list_assets() == []  # omitted workspace never lists everything

        # Authorized delete
        authorized_delete = image_studio_service.delete_asset(a_team1["id"], workspace_id="ws_finance")
        assert authorized_delete is True
        assert image_studio_service.get_asset(a_team1["id"], workspace_id="ws_finance") is None


class TestSynchronizedCatalogAndProviders:
    def test_get_providers_info(self, monkeypatch):
        monkeypatch.setenv("FAL_KEY", "fal_test_key_12345")
        monkeypatch.delenv("MUAPI_KEY", raising=False)

        providers = image_studio_service.get_providers_info()
        assert len(providers) == 2

        fal_prov = next(p for p in providers if p["id"] == "fal")
        assert fal_prov["isPrimary"] is True
        assert fal_prov["configured"] is True
        assert fal_prov["capabilities"]["textToImage"] is True
        assert fal_prov["capabilities"]["textToVideo"] is True
        assert fal_prov["capabilities"]["clipping"] is False

        muapi_prov = next(p for p in providers if p["id"] == "muapi")
        assert muapi_prov["isPrimary"] is False
        assert muapi_prov["configured"] is False
        assert muapi_prov["capabilities"]["clipping"] is True
        assert muapi_prov["capabilities"]["lipsync"] is True

    def test_get_synchronized_model_catalog(self):
        catalog = image_studio_service.get_synchronized_model_catalog()
        assert "providers" in catalog
        assert "imageModels" in catalog
        assert "videoModels" in catalog

        assert len(catalog["imageModels"]) > 0
        fal_flux = next((m for m in catalog["imageModels"] if "flux" in m["id"].lower()), None)
        assert fal_flux is not None
        assert fal_flux["provider"] == "fal"
        assert "text-to-image" in fal_flux["capabilities"]
        assert len(fal_flux["aspectRatios"]) > 0

        assert len(catalog["videoModels"]) > 0
        ltx_video = next((m for m in catalog["videoModels"] if "ltx" in m["id"].lower()), None)
        assert ltx_video is not None
        assert ltx_video["provider"] == "fal"
        assert "text-to-video" in ltx_video["capabilities"]

