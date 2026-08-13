"""Unit tests for BioCompute pipeline, analysis, Brian2 spiking engine, and models."""

import pytest
import numpy as np
from biocompute.providers.simulator.adapter import SimulatorProvider
from biocompute.providers.simulator.brian2_engine import Brian2SpikingEngine
from biocompute.neural.pipeline import default_pipeline
from biocompute.neural.analysis import summarize, channel_statistics
from biocompute.models.reservoir import DigitalReservoir, ReservoirModel
from biocompute.models.snn_models import SpikingNeuralNetworkModel
from biocompute.models.baselines import TinyCNNModel, SVMModel


def test_signal_pipeline_and_analysis():
    sim = SimulatorProvider(n_channels=4, seed=42)
    rec = sim.record_labeled(n_classes=2, trials_per_class=5)

    pipe = default_pipeline()
    ctx = pipe.run(rec)
    assert ctx.signal.shape == rec.data.shape
    assert ctx.spikes is not None

    stats = summarize(ctx, rec)
    assert "population" in stats
    assert "channels" in stats


def test_brian2_spiking_engine():
    engine = Brian2SpikingEngine(n_neurons=8, seed=42)
    v_uV, spikes = engine.run_simulation(duration_s=0.1)
    assert v_uV.shape[0] == 8
    assert isinstance(spikes, dict)


def test_models_fit_predict():
    X_train = np.random.normal(0, 1, size=(20, 16)).astype(np.float32)
    y_train = np.random.randint(0, 2, size=20)
    X_test = np.random.normal(0, 1, size=(5, 16)).astype(np.float32)


    res = ReservoirModel(backend=DigitalReservoir(n_units=30, seed=42), seed=42)
    res.fit(X_train, y_train)
    preds = res.predict(X_test)
    assert len(preds) == 5

    snn = SpikingNeuralNetworkModel(n_steps=5, epochs=2, seed=42)
    snn.fit(X_train, y_train)
    snn_preds = snn.predict(X_test)
    assert len(snn_preds) == 5

    cnn = TinyCNNModel(epochs=2, random_state=42)
    cnn.fit(X_train, y_train)
    cnn_preds = cnn.predict(X_test)
    assert len(cnn_preds) == 5
