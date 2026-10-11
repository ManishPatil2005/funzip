"""The only output type of the analytics layer: an observation, never a call to act."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ofx.domain import DataQuality
from ofx.language import require_compliant

QUALITY_CONFIDENCE_CAP = {
    DataQuality.EXACT: 1.0,
    DataQuality.ESTIMATED: 0.6,
    DataQuality.BAR_APPROXIMATED: 0.35,
}


@dataclass(frozen=True)
class Observation:
    kind: str
    ts_start: datetime
    ts_end: datetime
    summary: str
    data_quality: DataQuality
    method: str
    confidence: float
    price_low: float | None = None
    price_high: float | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    alternatives: tuple[str, ...] = ()
    limitations: str = ""
    teaching_ref: str = ""

    def __post_init__(self) -> None:
        require_compliant(self.summary)
        for alt in self.alternatives:
            require_compliant(alt)
        require_compliant(self.limitations)
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be within [0, 1]")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "ts_start": self.ts_start.isoformat(),
            "ts_end": self.ts_end.isoformat(),
            "price_low": self.price_low,
            "price_high": self.price_high,
            "summary": self.summary,
            "evidence": self.evidence,
            "data_quality": self.data_quality.value,
            "method": self.method,
            "confidence": round(self.confidence, 3),
            "alternative_readings": list(self.alternatives),
            "limitations": self.limitations,
            "teaching_ref": self.teaching_ref,
        }


def cap_confidence(raw: float, quality: DataQuality) -> float:
    """Confidence can never exceed what the data quality allows."""
    return max(0.0, min(raw, QUALITY_CONFIDENCE_CAP[quality]))
