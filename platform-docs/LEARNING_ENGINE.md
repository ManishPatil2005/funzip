# Learning Engine

## 1. Purpose
Teach how markets operate by connecting concepts to **live and historical charts**, in language that explains
rather than instructs.

## 2. Content sources and rights
The brief names public teachings by James Dalton, Axia Futures, Jigsaw, Blackroot, SpotGamma, John Keppler,
Auction Market Theory and Market Generated Information as inspiration. Rules:
- All lesson text is **written by us (or licensed)**. We do not copy books, courses or videos.
- Ideas are credited by name where they originate (for example, value area and day-type vocabulary from Market
  Profile literature), with references to the original works for further reading.
- No implied endorsement, partnership or affiliation with any named person or firm; no use of their logos.
- Each lesson has a reviewer and a review date; lessons that depend on contested interpretations say so.

## 3. Concept graph
Concepts have prerequisites, forming a learning path.

Foundation: auction process; participants (initiative vs responsive); time, price, volume; balance vs imbalance.
Market Profile: TPO, value area, POC, initial balance, open types, day types, profile shapes, excess, single
prints, the 80% rule, multi-day value relationships.
Volume and orderflow: volume profile, delta, CVD, imbalance, absorption, exhaustion, trapped traders, with the
data-quality caveats from ORDERFLOW_ENGINE.
Structure and liquidity: swings, break of structure, liquidity pools, sweeps, fair value gaps, order blocks,
breaker and mitigation blocks (ICT/SMC vocabulary defined explicitly, with a note that definitions vary between
practitioners).
Context: market breadth, sector rotation, volatility regimes, events.
Process: hypothesis, testing, costs, out-of-sample, overfitting, risk and position sizing.

## 4. Lesson format
1. Idea in plain words (60 seconds).
2. Definition used by the platform (exact rule and parameters).
3. Annotated live or historical example (frozen with a `data_version` so it never changes).
4. What the concept cannot tell you (limits, failure cases, alternative readings).
5. Try it: open the scanner builder or backtester with a prefilled idea.
6. Check understanding: short quiz with explanations.

## 5. Teaching mode on the chart
Toggle "Explain": overlays value area, POC, IB, single prints, sweeps and so on with short captions such as:
"According to Auction Market Theory, acceptance above the prior value area can indicate higher-auction
participation; rejection back inside suggests the move lacked follow-through. Both readings are possible."
Hover any annotation to see: definition, why it is drawn here, data quality, and a link to the lesson.

## 6. Language policy (enforced by a linter)
Allowed: "could indicate", "is consistent with", "according to X theory", "one reading", "alternative reading",
"risk area", "participation".
Not allowed in generated or authored text: `buy`, `sell`, `hold`, `entry`, `target`, `stop` as instructions,
"will", "guaranteed", "sure". The linter runs in CI on lesson content and at runtime on AI output. Words such as
"buyers" and "sellers" describing participants are allowed.

## 7. Scenario analysis and probability distribution (from the brief)
Presented as **empirical conditional statistics**, never forecasts: "In N historical sessions with similar
structure on this instrument, the next session closed above the prior value area high X% of the time (95%
interval a to b). Small samples and regime changes limit relevance." Always shows N, the matching rule, the
period, and a warning when N is small.

## 8. Progress and community (later)
Learning paths, progress tracking, annotated session journal where users record their own reading of the
auction and later compare with what happened; community sharing of annotated examples with moderation.

## 9. Quality bar
Accuracy review, glossary consistency, accessibility, translation readiness (Hindi and other Indian languages
are a likely growth lever [U]), and measured learning outcomes (quiz gain, journal accuracy over time).
