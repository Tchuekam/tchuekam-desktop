"""Reservoir computing: digital baseline, with a slot a biological reservoir can fill.

    input encoder -> reservoir -> readout -> prediction

This is THE architecture that matters for biological compute, because in reservoir
computing the reservoir is never trained. Only the linear readout is. That sidesteps
the credit-assignment problem which makes gradient-based training of biological
tissue impossible: you cannot address individual synapses, so you cannot backprop.

`ReservoirBackend` is the substitution point. `DigitalReservoir` (an echo-state
network, pure numpy) is the baseline. A `BiologicalReservoir` would implement the
same three methods by stimulating tissue and reading the response.

NO BIOLOGICAL RESERVOIR IS IMPLEMENTED HERE. It requires stimulation, which this
subsystem does not do. `BiologicalReservoirStub` documents the contract and raises
on use, so the interface is designed but the capability stays closed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from biocompute.models.base import Model


class InputEncoder:
    """Maps a feature vector to reservoir input.

    For a digital reservoir this is a random projection. For a biological reservoir
    the same interface would map features to stimulation parameters -- which is
    exactly where the platform's 16-trigger / ~10 s reconfiguration cost would bite.
    """

    def __init__(self, n_inputs: int, n_reservoir: int, scale: float = 1.0, seed: int = 0):
        rng = np.random.default_rng(seed)
        self.W_in = rng.uniform(-scale, scale, size=(n_reservoir, n_inputs + 1))
        self.scale = scale
        self.seed = seed

    def encode(self, x: np.ndarray) -> np.ndarray:
        return self.W_in @ np.concatenate([[1.0], x])

    def describe(self) -> dict:
        return {"type": "random_projection", "scale": self.scale, "seed": self.seed,
                "shape": list(self.W_in.shape)}


class ReservoirBackend(ABC):
    """The substitutable component. Digital today; biological is the research target."""

    name: str = "reservoir"
    biological: bool = False

    @abstractmethod
    def reset(self) -> None:
        """Return to a known initial state."""

    @abstractmethod
    def step(self, encoded_input: np.ndarray) -> np.ndarray:
        """Advance one step, return the observable state vector."""

    @property
    @abstractmethod
    def state_dim(self) -> int: ...

    def describe(self) -> dict:
        return {"name": self.name, "biological": self.biological,
                "state_dim": self.state_dim}


class DigitalReservoir(ReservoirBackend):
    """Echo-state network. Leaky-integrator tanh units, fixed random recurrent weights."""

    name = "digital_esn"
    biological = False

    def __init__(self, n_units: int = 200, spectral_radius: float = 0.9,
                 leak_rate: float = 0.3, sparsity: float = 0.1, seed: int = 0):
        self.n_units = n_units
        self.spectral_radius = spectral_radius
        self.leak_rate = leak_rate
        self.sparsity = sparsity
        self.seed = seed

        rng = np.random.default_rng(seed)
        W = rng.uniform(-1, 1, size=(n_units, n_units))
        W[rng.random((n_units, n_units)) > sparsity] = 0.0
        eigs = np.linalg.eigvals(W)
        radius = np.max(np.abs(eigs))
        if radius > 0:
            W *= spectral_radius / radius
        self.W = W
        self._state = np.zeros(n_units)

    @property
    def state_dim(self) -> int:
        return self.n_units

    def reset(self) -> None:
        self._state = np.zeros(self.n_units)

    def step(self, encoded_input: np.ndarray) -> np.ndarray:
        pre = self.W @ self._state + encoded_input
        self._state = (1 - self.leak_rate) * self._state + self.leak_rate * np.tanh(pre)
        return self._state.copy()

    def describe(self) -> dict:
        return {**super().describe(), "n_units": self.n_units,
                "spectral_radius": self.spectral_radius, "leak_rate": self.leak_rate,
                "sparsity": self.sparsity, "seed": self.seed}


class BiologicalReservoirStub(ReservoirBackend):
    """Contract for a future biological reservoir. Intentionally not implemented.

    A real implementation would, per step:
      1. map `encoded_input` to validated stimulation parameters
      2. obtain human approval for the protocol (not per step -- per protocol)
      3. upload parameters (~10 s on FinalSpark, with a recording blackout)
      4. fire a trigger
      5. wait out the artifact window (~10 ms) and the network floor (>=200 ms)
      6. read the per-channel response as the state vector

    Steps 2-3 make per-step reconfiguration impractical, so a realistic biological
    reservoir must hold its stimulation mapping FIXED across a whole run and vary
    only which trigger fires. That constraint should shape the encoder design.
    """

    name = "biological_stub"
    biological = True

    def __init__(self, n_channels: int = 32):
        self.n_channels = n_channels

    @property
    def state_dim(self) -> int:
        return self.n_channels

    def reset(self) -> None:
        raise NotImplementedError(self._msg())

    def step(self, encoded_input):
        raise NotImplementedError(self._msg())

    @staticmethod
    def _msg() -> str:
        return (
            "BiologicalReservoir requires stimulation, which BioCompute does not "
            "implement. See docs/biocompute/SAFETY.md for the approval architecture "
            "any implementation must satisfy."
        )


class ReservoirModel(Model):
    """Reservoir + ridge readout, behind the standard Model interface.

    Swap `backend` to compare digital against biological on an identical task with
    identical evaluation. That comparison is the point of this module.
    """

    name = "reservoir"
    temporal = True

    def __init__(self, backend: ReservoirBackend | None = None, n_units: int = 200,
                 spectral_radius: float = 0.9, leak_rate: float = 0.3,
                 washout: int = 5, ridge_alpha: float = 1.0, input_scale: float = 0.5,
                 seed: int = 0):
        super().__init__(n_units=n_units, spectral_radius=spectral_radius,
                         leak_rate=leak_rate, washout=washout,
                         ridge_alpha=ridge_alpha, input_scale=input_scale, seed=seed)
        self.backend = backend or DigitalReservoir(
            n_units=n_units, spectral_radius=spectral_radius,
            leak_rate=leak_rate, seed=seed
        )
        self.name = f"reservoir_{self.backend.name}"
        self.washout = washout
        self.ridge_alpha = ridge_alpha
        self.input_scale = input_scale
        self.seed = seed
        self._encoder: InputEncoder | None = None
        self._readout = None
        self._n_train = 0

    def _states(self, X: np.ndarray) -> np.ndarray:
        """Run each sample through the reservoir; return its final state.

        Each row is treated as an independent trial: reset, drive the reservoir for
        `washout` steps to let transients settle, then read the state.
        """
        assert self._encoder is not None
        out = np.empty((len(X), self.backend.state_dim))
        for i, x in enumerate(X):
            self.backend.reset()
            enc = self._encoder.encode(x) * self.input_scale
            state = None
            for _ in range(max(1, self.washout)):
                state = self.backend.step(enc)
            out[i] = state
        return out

    def fit(self, X, y):
        from sklearn.linear_model import RidgeClassifier

        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y)
        self._n_train = len(y)
        self._encoder = InputEncoder(
            n_inputs=X.shape[1], n_reservoir=self.backend.state_dim,
            scale=1.0, seed=self.seed
        )

        def _f():
            states = self._states(X)
            self._readout = RidgeClassifier(alpha=self.ridge_alpha)
            self._readout.fit(states, y)

        return self._timed_fit(_f)

    def predict(self, X):
        if self._readout is None:
            raise RuntimeError(f"{self.name}: not fitted")
        return self._readout.predict(self._states(np.asarray(X, dtype=np.float64)))

    def describe(self) -> dict:
        return {**super().describe(), "backend": self.backend.describe(),
                "encoder": self._encoder.describe() if self._encoder else None,
                "readout": "ridge_classifier",
                "trained_components": ["readout only -- reservoir weights are fixed"]}
