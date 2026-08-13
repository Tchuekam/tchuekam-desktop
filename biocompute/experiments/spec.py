"""Experiment specification and result types.

An experiment is DECLARED before it is run. The hypothesis, the controls, and --
critically -- the falsification criterion are written down first, so a result
cannot be reinterpreted after the fact to mean whatever it happened to show.

`EvidenceLevel` is applied to every statement a report makes. Nothing is allowed
to move up a level without the evidence that level requires.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class EvidenceLevel(str, Enum):
    """How strongly a statement is supported. Never upgrade without evidence."""

    FACT = "FACT"
    """Directly stated in source code, documentation, or a published paper."""

    MEASUREMENT = "MEASUREMENT"
    """We ran it and recorded the number, with parameters and provenance."""

    INFERENCE = "INFERENCE"
    """Follows logically from FACTs/MEASUREMENTs, but was not itself observed."""

    HYPOTHESIS = "HYPOTHESIS"
    """A testable proposition we have not yet tested."""

    SPECULATION = "SPECULATION"
    """Plausible, no supporting evidence. Never appears in a conclusion."""


@dataclass
class Statement:
    """One claim, with its evidence level and support."""

    text: str
    level: EvidenceLevel
    support: str = ""

    def render(self) -> str:
        s = f"[{self.level.value}] {self.text}"
        return f"{s}\n    support: {self.support}" if self.support else s


@dataclass
class LabelSource:
    """Where classification labels come from. Guards against manufactured labels."""

    description: str
    is_ground_truth: bool
    #: True only when the experimental setup genuinely applied/knew the condition.
    valid_for_supervised_learning: bool
    caveats: list[str] = field(default_factory=list)

    def validate(self) -> None:
        if not self.valid_for_supervised_learning:
            raise ValueError(
                f"label source '{self.description}' is not valid for supervised "
                f"learning. Do not manufacture labels from assumptions. Caveats: "
                f"{self.caveats}"
            )


@dataclass
class ExperimentSpec:
    """A pre-registered experiment."""

    name: str
    research_question: str
    hypothesis: str
    null_hypothesis: str
    task: str
    independent_variables: list[str]
    dependent_variables: list[str]
    controls: list[str]
    protocol: list[str]
    label_source: LabelSource
    provider: str
    #: What outcome would count as evidence FOR the hypothesis.
    evidence_for: str
    #: What outcome would count as evidence AGAINST it.
    evidence_against: str
    known_confounds: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    alpha: float = 0.05
    seeds: dict[str, int] = field(default_factory=lambda: {"global": 0})
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["label_source"] = asdict(self.label_source)
        return d


@dataclass
class ExperimentResult:
    """What actually happened. Conclusions are Statements, never bare prose."""

    spec: ExperimentSpec
    manifest_path: str | None
    recording_summary: dict[str, Any] = field(default_factory=dict)
    model_results: dict[str, Any] = field(default_factory=dict)
    primary_metric: float | None = None
    primary_metric_name: str = "accuracy_mean"
    chance_level: float | None = None
    p_value: float | None = None
    conclusion: list[Statement] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    next_experiment: str | None = None

    @property
    def hypothesis_supported(self) -> bool | None:
        """None means undetermined -- which is a legitimate outcome, not a failure."""
        if self.p_value is None or self.primary_metric is None or self.chance_level is None:
            return None
        return self.p_value < self.spec.alpha and self.primary_metric > self.chance_level

    def to_dict(self) -> dict:
        return {
            "spec": self.spec.to_dict(),
            "manifest_path": self.manifest_path,
            "recording_summary": self.recording_summary,
            "model_results": self.model_results,
            "primary_metric": self.primary_metric,
            "primary_metric_name": self.primary_metric_name,
            "chance_level": self.chance_level,
            "p_value": self.p_value,
            "hypothesis_supported": self.hypothesis_supported,
            "conclusion": [asdict(s) for s in self.conclusion],
            "limitations": self.limitations,
            "next_experiment": self.next_experiment,
        }
