"""Declarative scenario rules over observations ("strategies as data").

A rule describes a COINCIDENCE of observations (for example a sweep of lows together with an
aligned CVD trend). A match is a teaching scenario with context and limitations, never an
instruction. Specs are plain JSON, validated strictly and evaluated without eval/exec.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from fnmatch import fnmatchcase
from typing import Any

from ofx.domain import DataQuality, weakest
from ofx.language import LanguagePolicyError, require_compliant
from ofx.orderflow.observation import Observation, cap_confidence

_RANK = {"bar_approximated": 0, "estimated": 1, "exact": 2}
MAX_CONDITIONS, MAX_WINDOW = 8, 100


class SpecError(ValueError):
    pass


@dataclass(frozen=True)
class Condition:
    kind: str  # exact kind or fnmatch pattern, e.g. "liquidity_sweep_*"
    min_confidence: float = 0.0
    quality_at_least: str = "bar_approximated"

    def matches(self, o: Observation) -> bool:
        return (fnmatchcase(o.kind, self.kind) and o.confidence >= self.min_confidence
                and _RANK[o.data_quality.value] >= _RANK[self.quality_at_least])


@dataclass(frozen=True)
class Rule:
    name: str
    description: str
    window_bars: int
    all_of: tuple[Condition, ...]
    none_of: tuple[Condition, ...]
    teaching_note: str


@dataclass(frozen=True)
class ScenarioMatch:
    rule: str
    ts_start: datetime
    ts_end: datetime
    summary: str
    teaching_note: str
    confidence: float
    data_quality: DataQuality
    evidence: tuple[dict[str, Any], ...]
    limitations: str = "Several observations occurring together describe a context; they do not establish what happens next."

    def to_dict(self) -> dict[str, Any]:
        return {"rule": self.rule, "ts_start": self.ts_start.isoformat(), "ts_end": self.ts_end.isoformat(),
                "summary": self.summary, "teaching_note": self.teaching_note, "confidence": round(self.confidence, 3),
                "data_quality": self.data_quality.value, "evidence": list(self.evidence), "limitations": self.limitations}


def _cond(d: Any) -> Condition:
    if not isinstance(d, dict) or not isinstance(d.get("kind"), str) or not d["kind"]:
        raise SpecError("each condition needs a string 'kind'")
    extra = set(d) - {"kind", "min_confidence", "quality_at_least"}
    if extra:
        raise SpecError(f"unknown condition fields: {sorted(extra)}")
    mc = d.get("min_confidence", 0.0)
    q = d.get("quality_at_least", "bar_approximated")
    if not isinstance(mc, (int, float)) or isinstance(mc, bool) or not 0 <= mc <= 1:
        raise SpecError("min_confidence must be within [0, 1]")
    if q not in _RANK:
        raise SpecError(f"quality_at_least must be one of {sorted(_RANK)}")
    return Condition(d["kind"], float(mc), q)


def parse_rule(spec: Any) -> Rule:
    if not isinstance(spec, dict):
        raise SpecError("spec must be an object")
    extra = set(spec) - {"name", "description", "window_bars", "all_of", "none_of", "teaching_note"}
    if extra:
        raise SpecError(f"unknown fields: {sorted(extra)}")
    name = spec.get("name")
    if not isinstance(name, str) or not 1 <= len(name) <= 80:
        raise SpecError("name must be a string of 1-80 characters")
    w = spec.get("window_bars", 5)
    if not isinstance(w, int) or isinstance(w, bool) or not 1 <= w <= MAX_WINDOW:
        raise SpecError(f"window_bars must be an integer in [1, {MAX_WINDOW}]")
    all_of = spec.get("all_of")
    if not isinstance(all_of, list) or not 1 <= len(all_of) <= MAX_CONDITIONS:
        raise SpecError(f"all_of must list 1-{MAX_CONDITIONS} conditions")
    none_of = spec.get("none_of", [])
    if not isinstance(none_of, list) or len(none_of) > MAX_CONDITIONS:
        raise SpecError("none_of must be a short list")
    desc, note = spec.get("description", ""), spec.get("teaching_note", "")
    for label, text in (("name", name), ("description", desc), ("teaching_note", note)):
        if not isinstance(text, str):
            raise SpecError(f"{label} must be text")
        try:
            require_compliant(text)
        except LanguagePolicyError as e:  # rules may describe context, never instructions
            raise SpecError(f"{label}: {e}") from e
    return Rule(name, desc, w, tuple(_cond(c) for c in all_of), tuple(_cond(c) for c in none_of), note)


def evaluate(rule: Rule, observations: list[Observation], bar: timedelta) -> list[ScenarioMatch]:
    """Anchor on each observation matching the first condition; every other condition needs a matching
    observation within +-window bars of the anchor's end, and no none_of condition may match there."""
    span = bar * rule.window_bars
    matches: list[ScenarioMatch] = []
    last_end: datetime | None = None
    for anchor in sorted(observations, key=lambda o: o.ts_end):
        if not rule.all_of[0].matches(anchor):
            continue
        near = [o for o in observations if abs(o.ts_end - anchor.ts_end) <= span]
        chosen: list[Observation] = [anchor]
        ok = True
        for c in rule.all_of[1:]:
            hit = next((o for o in near if c.matches(o) and o not in chosen), None)
            if hit is None:
                ok = False
                break
            chosen.append(hit)
        if not ok or any(c.matches(o) for c in rule.none_of for o in near):
            continue
        start, end = min(o.ts_start for o in chosen), max(o.ts_end for o in chosen)
        if last_end is not None and start <= last_end:
            continue  # overlapping match: report the first only
        last_end = end
        q = weakest(*(o.data_quality for o in chosen))
        conf = cap_confidence(min(o.confidence for o in chosen), q)
        kinds = ", ".join(sorted({o.kind for o in chosen}))
        matches.append(ScenarioMatch(
            rule.name, start, end, f"{rule.name}: {len(chosen)} observations coincided ({kinds}) within {rule.window_bars} bars.",
            rule.teaching_note, conf, q, tuple({"kind": o.kind, "ts_end": o.ts_end.isoformat(), "confidence": round(o.confidence, 3)} for o in chosen)))
    return matches


EXAMPLE_RULES: list[dict[str, Any]] = [
    {"name": "Sweep of lows with supportive flow", "window_bars": 6,
     "description": "A sweep of prior lows alongside cumulative delta rising while price is flat or falling.",
     "teaching_note": "Study how often price accepted back inside the range versus continued lower after this context.",
     "all_of": [{"kind": "liquidity_sweep_low"}, {"kind": "cvd_trend_diverging"}]},
    {"name": "Heavy flow absorbed near extremes", "window_bars": 4,
     "description": "Absorption together with an exhaustion sign at the same extreme.",
     "teaching_note": "Compare the next sessions' behaviour to see whether the pause resolved either way.",
     "all_of": [{"kind": "absorption_*"}, {"kind": "exhaustion_*"}]},
]
