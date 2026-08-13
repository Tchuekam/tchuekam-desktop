"""Recording schema: shape validation, segment safety, provenance, round-trip."""

from __future__ import annotations

import numpy as np
import pytest

from biocompute.core.schema import ChannelLayout, ElectrodePosition, Recording


def _rec(**kw) -> Recording:
    base = dict(
        experiment_id="t", provider="simulator", session_id="s",
        timestamp="2026-01-01T00:00:00+00:00", sample_rate_hz=3750.0,
        channels=[0, 1], units="microvolts",
        data=np.zeros((2, 2, 100), dtype=np.float32),
    )
    base.update(kw)
    return Recording(**base)


def test_rejects_non_3d_data():
    with pytest.raises(ValueError, match="n_segments, n_channels, n_samples"):
        _rec(data=np.zeros((2, 100)))


def test_rejects_channel_count_mismatch():
    with pytest.raises(ValueError, match="channels"):
        _rec(data=np.zeros((2, 3, 100)), channels=[0, 1])


def test_rejects_timestamp_count_mismatch():
    with pytest.raises(ValueError, match="segment_timestamps"):
        _rec(segment_timestamps=["2026-01-01T00:00:00+00:00"])


def test_duration_excludes_gaps():
    rec = _rec()
    assert rec.duration_s == pytest.approx(2 * 100 / 3750.0)


def test_duty_cycle_reflects_gaps():
    rec = _rec(
        segment_timestamps=["2026-01-01T00:00:00+00:00", "2026-01-01T00:00:10+00:00"]
    )
    # 2 segments of 100/3750 s spread over ~10 s of wall clock.
    assert rec.duty_cycle < 0.01


def test_assert_contiguous_blocks_gappy_analysis():
    rec = _rec(contiguous=False)
    with pytest.raises(ValueError, match="requires a contiguous recording"):
        rec.assert_contiguous("cross_segment_isi")


def test_assert_contiguous_allows_contiguous():
    _rec(contiguous=True).assert_contiguous("ok")


def test_channel_data_lookup_and_error():
    rec = _rec()
    assert rec.channel_data(1).shape == (2, 100)
    with pytest.raises(KeyError):
        rec.channel_data(99)


def test_data_hash_is_content_sensitive():
    a, b = _rec(), _rec()
    assert a.data_hash() == b.data_hash()
    d = np.zeros((2, 2, 100), dtype=np.float32)
    d[0, 0, 0] = 1.0
    assert _rec(data=d).data_hash() != a.data_hash()


def test_processing_steps_record_params():
    rec = _rec()
    rec.add_processing_step("filter", low_hz=300, order=4)
    assert rec.processing_parameters[0].name == "filter"
    assert rec.processing_parameters[0].params["low_hz"] == 300
    assert rec.processing_parameters[0].applied_at


def test_hdf5_roundtrip_preserves_everything(tmp_path):
    layout = ChannelLayout(
        provider="simulator", device_id="d", mea_index=0, geometry="test",
        electrodes=[ElectrodePosition(0, 0.0, 0.0, label="00"),
                    ElectrodePosition(1, 200.0, 0.0, label="01")],
    )
    rec = _rec(channel_layout=layout, provider_metadata={"biological": False},
               contiguous=True)
    rec.add_processing_step("acquire", seed=1)
    path = tmp_path / "r.h5"
    rec.to_hdf5(str(path))

    back = Recording.from_hdf5(str(path))
    assert back.data_hash() == rec.data_hash()
    assert back.channels == rec.channels
    assert back.contiguous is True
    assert back.channel_layout.geometry == "test"
    assert len(back.channel_layout.electrodes) == 2
    assert back.provider_metadata["biological"] is False
    assert back.processing_parameters[0].params["seed"] == 1


def test_layout_distance():
    layout = ChannelLayout(
        provider="p", device_id="d", mea_index=0, geometry="g",
        electrodes=[ElectrodePosition(0, 0.0, 0.0), ElectrodePosition(1, 300.0, 400.0)],
    )
    assert layout.distance_um(0, 1) == pytest.approx(500.0)
    assert layout.distance_um(0, 99) is None
