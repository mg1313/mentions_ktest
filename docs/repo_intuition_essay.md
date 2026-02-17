# Intuition Essay: What This Repository Is Actually Doing

This repository is building a bridge between what people say during sports broadcasts and what markets are pricing.

One side of the bridge is market microstructure. The Mentions poller continuously pulls orderbook depth for in-scope Kalshi markets and computes execution-realistic metrics (budget VWAP from actual depth, not midpoint shortcuts). That gives you a time-indexed view of what was tradable and at what effective cost.

The other side of the bridge is broadcast language. The NBA pipeline starts from game schedules, finds replay/video sources, pulls audio, transcribes with game context, and converts text into structured, feed-specific mention counts.

The key idea is that this is not just scraping or just analytics. It is measurement infrastructure:

- Discovery and extraction make sure the right media is found.
- Manifest IDs and append-only outputs make data traceable.
- Prompt context and deterministic corrections reduce transcription noise.
- Feed-level rows keep home/away commentary differences visible.
- Term tables turn raw text into model-friendly features.

So the system is set up to answer questions like:

- Do certain terms spike under specific commentators?
- Do local versus national feeds differ in language usage?
- Does player presence shift mention frequency?
- Do those shifts line up with market behavior?

The technical choices in the code reflect this intent:

- Idempotent persistence and explicit metadata are used so results can be audited.
- Fail-open behavior keeps long-running pipelines from collapsing on single failures.
- Config-driven rules reduce brittle hardcoding.
- Incremental datasets preserve history and avoid destructive rebuild assumptions.

If deciding what to do next, the most leverage usually comes from:

1. Improving data quality confidence (spot-checks, confidence metrics, correction audit summaries).
2. Tightening modeling readiness (time-split evaluation, leakage checks, feed-aware controls).
3. Increasing throughput reliability (batch orchestration, retry queues, cost/latency monitoring).

In short: the repo is becoming an end-to-end observational system linking market state and broadcast language, with enough structure to support rigorous downstream modeling instead of one-off analysis.
