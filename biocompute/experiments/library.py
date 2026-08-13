"""Pre-registered experiments.

Two experiments are defined, and the distinction between them is the whole point.

E1 runs on the SIMULATOR, where labels are ground truth by construction. It
validates that the pipeline can recover a signal it is known to contain. A failure
here means the machinery is broken. A success says nothing about biology.

E2 runs on REAL organoid data. Because the provider is read-only, we never applied
a stimulus, so there is NO stimulus label available. Inventing one would be
fabrication. The only labels the setup genuinely knows are which electrode each
segment came from -- so E2 asks the narrow, answerable question of whether channel
identity is decodable, and names the amplitude confound up front along with the
control that addresses it.
"""

from __future__ import annotations

import numpy as np

from biocompute.core.schema import Recording
from biocompute.experiments.spec import ExperimentSpec, LabelSource

# --------------------------------------------------------------------- E1


def e1_simulator_stimulus_decoding(seed: int = 0) -> ExperimentSpec:
    """Positive control for the pipeline itself."""
    return ExperimentSpec(
        name="E1-simulator-stimulus-decoding",
        research_question=(
            "Can the BioCompute pipeline recover a known stimulus class from "
            "synthetic neural activity?"
        ),
        hypothesis=(
            "With ground-truth stimulus-conditioned responses present, a linear "
            "decoder on interpretable features classifies the stimulus class above "
            "chance."
        ),
        null_hypothesis=(
            "Decoder accuracy is indistinguishable from the shuffled-label null."
        ),
        task="binary/multiclass classification of stimulus class from one trial",
        independent_variables=["stimulus_class", "response_gain"],
        dependent_variables=["cross-validated accuracy", "permutation p-value"],
        controls=[
            "null dataset: identical generator with response_gain=0.0, where classes "
            "are statistically identical and accuracy MUST fall to chance",
            "permutation test on the real dataset",
            "majority-class model as an accuracy floor",
        ],
        protocol=[
            "generate labelled trials with the seeded simulator",
            "run the default pipeline (validate -> bandpass -> MAD noise -> artifact "
            "-> 6-sigma events -> features)",
            "5-fold stratified CV across all baseline models",
            "permutation test (200 shuffles) on the best model",
            "repeat the whole procedure on the null dataset",
        ],
        label_source=LabelSource(
            description="synthetic stimulus class assigned by the generator",
            is_ground_truth=True,
            valid_for_supervised_learning=True,
        ),
        provider="simulator",
        evidence_for=(
            "accuracy significantly above chance on the real dataset AND at chance on "
            "the null dataset -- together showing the pipeline detects signal that is "
            "present and does not invent signal that is absent"
        ),
        evidence_against=(
            "chance accuracy on the real dataset (pipeline cannot detect known signal), "
            "or above-chance accuracy on the null dataset (pipeline fabricates signal)"
        ),
        known_confounds=[
            "none by construction -- this is synthetic data with a known generator"
        ],
        limitations=[
            "The simulator is a test instrument, not a biophysical model. Success here "
            "validates the software only, and transfers no conclusion to biology.",
        ],
        seeds={"global": seed, "simulator": seed},
    )


# --------------------------------------------------------------------- E2


def e2_channel_identity_decoding(seed: int = 0) -> ExperimentSpec:
    """The first experiment we can legitimately run on real organoid data today."""
    return ExperimentSpec(
        name="E2-finalspark-channel-identity",
        research_question=(
            "Do individual electrodes on a live organoid MEA carry statistically "
            "distinguishable signal, such that a decoder can identify which electrode "
            "a recording segment came from?"
        ),
        hypothesis=(
            "Segments from different electrodes are distinguishable above chance, "
            "because electrodes differ in tissue contact and local activity."
        ),
        null_hypothesis=(
            "Segments are not distinguishable by electrode; accuracy matches the "
            "shuffled-label null."
        ),
        task="multiclass classification of source electrode from a single segment",
        independent_variables=["source electrode"],
        dependent_variables=["cross-validated accuracy", "permutation p-value"],
        controls=[
            "PRIMARY CONTROL: amplitude normalisation. Every (segment, channel) trace "
            "is divided by its own robust sigma, so all traces have unit noise and no "
            "per-channel gain information survives. If accuracy stays above chance "
            "under this control, the discrimination uses signal STRUCTURE, not gain.",
            "permutation test on shuffled electrode labels, with selection correction "
            "across the model set (best-of-K null)",
            "majority-class model as an accuracy floor",
        ],
        protocol=[
            "record N segments from K electrodes of one online, non-maintenance "
            "controller (read-only; no stimulation)",
            "treat each (segment, electrode) pair as one labelled sample",
            "run the default pipeline",
            "5-fold stratified CV across baselines, twice: uncontrolled (raw "
            "amplitude) and controlled (unit-sigma normalised)",
            "selection-corrected permutation test in each condition",
        ],
        label_source=LabelSource(
            description=(
                "electrode index, known from the acquisition request itself -- not "
                "inferred, not assumed"
            ),
            is_ground_truth=True,
            valid_for_supervised_learning=True,
            caveats=[
                "This is NOT a stimulus label. No stimulus was applied. The experiment "
                "cannot speak to stimulus encoding or to learning.",
            ],
        ),
        provider="finalspark",
        evidence_for=(
            "accuracy significantly above chance WITH amplitude normalisation applied "
            "-- showing electrodes differ in signal structure, not merely in gain"
        ),
        evidence_against=(
            "accuracy at chance once amplitude is normalised, which would show that any "
            "uncontrolled discrimination was explained entirely by per-channel gain"
        ),
        known_confounds=[
            "per-channel noise amplitude differences (addressed by the z-score control)",
            "per-channel electrode impedance differences, which we cannot measure "
            "without platform access",
            "temporal drift: segments from one electrode are not independent in time, "
            "so a decoder may key on slow drift rather than electrode identity",
            "organoid coverage: an electrode with no tissue on it is trivially "
            "distinguishable, which is a real but uninteresting effect",
        ],
        limitations=[
            "Read-only public feed. No stimulation, therefore no stimulus-response "
            "and no learning experiment is possible.",
            "Segments are non-contiguous with variable gaps, so no cross-segment "
            "temporal structure can be used.",
            "Signal is wavelet-downsampled to 3750 Hz from a 250-5000 Hz band, so "
            "content above 1875 Hz is aliased and spike shapes are degraded.",
            "A positive result establishes electrode distinguishability ONLY. It is "
            "not evidence of computation, learning, or biological information processing.",
        ],
        seeds={"global": seed},
    )


def channel_identity_dataset(recording: Recording) -> tuple[Recording, np.ndarray]:
    """Reshape a multi-channel recording into per-(segment, channel) samples.

    Each (segment, channel) becomes one single-channel sample labelled by its
    electrode. Returns a new Recording plus the label array.
    """
    n_seg, n_ch, n_samp = recording.data.shape
    flat = recording.data.reshape(n_seg * n_ch, 1, n_samp)
    labels = np.tile(np.array(recording.channels), n_seg)

    stamps = []
    for s in range(n_seg):
        stamp = (
            recording.segment_timestamps[s]
            if s < len(recording.segment_timestamps)
            else recording.timestamp
        )
        stamps.extend([stamp] * n_ch)

    out = Recording(
        experiment_id=recording.experiment_id + "-chanid",
        provider=recording.provider,
        session_id=recording.session_id,
        timestamp=recording.timestamp,
        sample_rate_hz=recording.sample_rate_hz,
        channels=[0],  # each sample is single-channel; identity lives in the label
        units=recording.units,
        data=flat,
        segment_timestamps=stamps,
        contiguous=False,
        channel_layout=recording.channel_layout,
        stimulus_metadata={
            "labels": labels.tolist(),
            "label_source": "source_electrode_index",
            "note": "NOT a stimulus label. No stimulus was applied.",
        },
        provider_metadata=dict(recording.provider_metadata),
    )
    out.add_processing_step(
        "reshape.channel_identity",
        original_shape=list(recording.data.shape),
        new_shape=list(flat.shape),
        original_channels=list(recording.channels),
    )
    return out, labels
