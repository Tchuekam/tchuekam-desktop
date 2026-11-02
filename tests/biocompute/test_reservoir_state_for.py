"""`ReservoirModel.state_for`: inspect the reservoir's response to one input
without training a readout (used by the playground endpoint)."""

import numpy as np

from biocompute.models.reservoir import DigitalReservoir, ReservoirModel


def _model():
    return ReservoirModel(backend=DigitalReservoir(n_units=50, seed=42))


def test_state_for_works_on_an_unfitted_model():
    state = _model().state_for(np.linspace(0, 1, 32))
    assert state.shape == (50,)
    assert np.all(np.isfinite(state))


def test_state_for_is_deterministic():
    x = np.linspace(0, 1, 32)
    assert np.array_equal(_model().state_for(x), _model().state_for(x))


def test_state_for_depends_on_the_input():
    m = _model()
    assert not np.allclose(m.state_for(np.zeros(32)), m.state_for(np.ones(32)))


def test_calling_state_for_does_not_change_a_later_fit():
    """fit replaces the encoder, so inspecting first must not leak into training."""
    rng = np.random.default_rng(0)
    X = rng.normal(size=(40, 8))
    y = np.array([0, 1] * 20)

    fresh, inspected = _model(), _model()
    inspected.state_for(np.ones(32))  # different width than the training data
    fresh.fit(X, y)
    inspected.fit(X, y)
    assert np.array_equal(fresh.predict(X), inspected.predict(X))
