# AI Architecture

The AI is a **translator and explainer**, not an oracle. It never predicts prices and never issues buy or sell
calls.

## 1. Natural language to validated strategy

Example input: "I want stocks breaking a 20 day consolidation with volume expansion and strong sector breadth."

```
text
 -> 1. intent + entity extraction (universe, timeframe, concepts, thresholds)
 -> 2. ambiguity check: if a term is underspecified ("strong breadth"), ask or propose explicit defaults
 -> 3. concept resolution against the platform's registry (consolidation, breakout, volume expansion, breadth)
 -> 4. logic graph (JSON AST) generated under a JSON schema (constrained decoding / schema validation)
 -> 5. static validation: types, units, lookback sufficiency, no lookahead, node limits, allowed indicators only
 -> 6. explain-back: plain-language restatement + the exact definitions used, shown to the user
 -> 7. user confirms or edits in the visual builder (the AST is the same object)
 -> 8. scan on a point-in-time universe -> backtest job with default costs -> report
```

Step 2 and step 6 matter most: "consolidation" and "strong breadth" have many valid definitions. The system
shows the definition it chose (for example "range of the last 20 bars below 1.2 x ATR(20)"; "more than 60% of
sector members above their 50-day average") and lets the user change it. This is how the output stays honest.

## 2. Components
- **Concept registry:** each concept has a machine definition (AST fragment), parameters with defaults and
  ranges, a teaching note, and known failure modes.
- **Planner/translator:** LLM call with the registry summary, the AST JSON schema and few-shot examples.
- **Validator:** deterministic, no LLM. Rejects anything outside the schema or the allowed node set.
- **Orchestrator:** runs scan, backtest and report generation as ordinary jobs with quotas.
- **Report writer:** LLM drafts the narrative from computed numbers only; numbers are inserted by code, not by
  the model, to prevent invented statistics.
- **Tutor (education mode):** retrieval over a curated, **self-authored** lesson corpus plus the user's current
  chart context; explains concepts in conditional language.

## 3. Guardrails
- Output schema allows no trade-instruction fields. A language linter blocks `buy`, `sell`, `hold`, `target`,
  `entry`, `guaranteed`, `will rise/fall` in generated prose; violations are regenerated or replaced with a
  neutral template.
- All claims must trace to a computed metric or a lesson citation; otherwise the report omits them.
- Backtest reports always include trial count, out-of-sample result, cost assumptions, and a "what this does not
  show" section.
- The model has **no tools that touch secrets, orders, or the file system**. Prompt injection cannot reach
  anything dangerous because the only output is a validated AST.
- Cost controls: per-user monthly budget, response caching by normalised prompt, smaller model for
  extraction, larger model only for ambiguity resolution.

## 4. Evaluation
- Golden set of 200+ prompts with expected ASTs (exact and semantic match).
- Adversarial set: injection attempts, requests for advice, nonsense, extreme parameters.
- Metrics: valid-AST rate, correct-intent rate, clarification rate, refusal correctness, latency, cost per
  query. Regression-gated in CI whenever prompts, schema or models change.
- Human review of a sample of explanations by a domain reviewer before launch of each lesson set.

## 5. Beyond translation (later, gated by evidence)
- **Pattern similarity search:** find historical sessions with similar profile structure; presented as "past
  sessions with similar structure and what followed", with sample sizes and dispersion, never a forecast.
- **Regime labelling:** unsupervised or rule-based regimes (trend, balance, volatility state) used as backtest
  filters; validated out of sample.
- **Research assistant for institutions:** batch hypothesis testing with multiple-testing correction.

Model-agnostic by design: a thin interface so models can be swapped or self-hosted for institutional customers.
