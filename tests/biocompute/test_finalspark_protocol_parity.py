"""Anti-drift guard between the two FinalSpark protocol implementations.

There are deliberately two:

  1. skills/science/finalspark-livemea/scripts/livemea.py
     Standalone agent-facing CLI. Runs in an isolated `uv` env via PEP 723 inline
     dependencies, with NO import dependency on this repository, so it keeps
     working independently of the package.

  2. biocompute/providers/finalspark/client.py
     Importable library form used by the BioCompute provider.

Duplication is intentional; silent divergence is not. This test parses the skill
script WITHOUT importing it (so its uv-managed dependencies are not required) and
asserts the protocol constants agree. If someone updates one and not the other,
this fails.

Also included: the live-service integration test, marked `integration` so it is
excluded by the project default `addopts = -m 'not integration'` and never
hammers shared infrastructure in normal CI runs.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from biocompute.providers.finalspark import client

SKILL_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "skills" / "science" / "finalspark-livemea" / "scripts" / "livemea.py"
)


def _module_constants(path: Path) -> dict[str, object]:
    """Read top-level literal assignments without executing the module."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    try:
                        out[target.id] = ast.literal_eval(node.value)
                    except ValueError:
                        pass
    return out


@pytest.fixture(scope="module")
def skill_constants() -> dict[str, object]:
    assert SKILL_SCRIPT.exists(), f"skill script missing at {SKILL_SCRIPT}"
    return _module_constants(SKILL_SCRIPT)


def test_base_url_matches(skill_constants):
    assert skill_constants["BASE_URL"] == client.BASE_URL


def test_sample_rate_matches(skill_constants):
    assert skill_constants["SAMPLE_RATE_HZ"] == client.SAMPLE_RATE_HZ


def test_attribution_matches(skill_constants):
    assert skill_constants["ATTRIBUTION"] == client.ATTRIBUTION


def test_sample_rate_is_documented_value():
    """3750 Hz = 30 kHz hardware / 8 (wavelet downsampling)."""
    assert client.SAMPLE_RATE_HZ == 3750.0


def test_max_channels_matches_server_payload_ceiling():
    assert client.MAX_CHANNELS == 32


def test_client_never_sends_credentials():
    """Read-only, public scope: no auth headers, no tokens, no cookies."""
    source = Path(client.__file__).read_text(encoding="utf-8").lower()
    for forbidden in ("authorization", "api_key", "apikey", "bearer",
                      "password", "cookie", "x-auth"):
        assert forbidden not in source, f"credential-like token '{forbidden}' in client"


def test_stream_rejects_too_many_channels():
    with pytest.raises(client.FinalSparkError, match="max 32 channels"):
        client.stream_packets("id", 0, list(range(40)), 1600, 1)


# --------------------------------------------------------------- integration


@pytest.fixture(autouse=True)
def _space_out_live_calls(request):
    """Pause between live-service tests.

    These tests hit shared public infrastructure that also serves FinalSpark's own
    live view. Run back-to-back they reliably trigger connection timeouts -- each
    passes alone but the group fails. Spacing them out is both the fix and the
    courteous thing to do. Applies only to `integration`-marked tests.
    """
    import time

    if request.node.get_closest_marker("integration"):
        time.sleep(3.0)
    yield


@pytest.mark.integration
def test_live_service_reachable():
    """Hits the public live service. Excluded from default runs."""
    from biocompute.core.registry import get_provider

    provider = get_provider("finalspark")
    conn = provider.connect()
    assert conn.reachable, conn.detail
    assert conn.metadata["sample_rate_hz"] == 3750.0


@pytest.mark.integration
def test_live_discovery_and_layout():
    from biocompute.core.registry import get_provider

    provider = get_provider("finalspark")
    devices = provider.discover()
    assert devices
    usable = [d for d in devices if d.usable]
    assert usable, "no usable controllers right now"
    layout = provider.get_layout(usable[0].device_id)
    assert layout.electrodes
    assert all(e.x_um is not None for e in layout.electrodes)


@pytest.mark.integration
@pytest.mark.timeout(300)
def test_live_recording_small():
    """Deliberately small: 2 segments, 4 channels. Do not hammer shared hardware."""
    from biocompute.core.registry import get_provider
    from biocompute.core.schema import RecordRequest

    provider = get_provider("finalspark")
    rec = provider.record(
        RecordRequest(channels=[0, 1, 2, 3], n_segments=2, timeout_s=180,
                      experiment_id="ci-smoke")
    )
    assert rec.data.shape == (2, 4, 1600)
    assert rec.contiguous is False  # gappy feed, must never claim otherwise
    assert rec.units == "microvolts"
    assert rec.provider_metadata["biological"] is True
    assert rec.provider_metadata["attribution"] == client.ATTRIBUTION
