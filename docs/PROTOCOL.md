# GeoFolio Context Protocol 1.0

## Transport and versioning

UTF-8 JSON, finite numeric values, USD prices and ISO-8601 timezone-aware timestamps. Input contracts reject unknown fields and malformed data. Major-version changes may break semantics; unsupported protocol strings fail validation. Schemas are in this directory and generated from Pydantic models; context schema defines the stable output envelope. This is an application protocol, not MCP or a replacement for FIX.

### Market frame: `geofolio.market/1.0`

A frame has `frame_id`, `as_of`, `kind` (`simulated`, `live`, `historical`), `currency`, and a symbol→quote map. Each quote has positive USD `price`, `observed_at`, and `source`. All configured position and hedge symbols must be present. Quote timestamps cannot exceed the frame cutoff, and quote ages cannot exceed the portfolio limit. Caller adapters must normalize splits, dividends, FX, data licenses and corporate actions as appropriate. No automatic adjustment is done.

Frames must advance at the configured interval, within 10 ms tolerance. A longer interval clears the rolling sample window to avoid treating a multi-period return as a single-period return. A shorter interval or non-increasing time is rejected. Latest-frame exact retries are idempotent. Frame IDs cannot be reused inside the active window; older-than-window ID deduplication is the producer's responsibility. Different market data kinds cannot be mixed in one engine. Input mutations are committed only after successful analytics/serialization.

### Spatial event: `geofolio.spatial/1.0`

An event has unique `event_id`, `occurred_at`, `known_at`, geographic coordinates, distance-decay scale `radius_km`, `half_life_hours`, signed `scenario_impact_bps`, sector, source, description and `kind` (`simulated`, `observed`). `known_at >= occurred_at`; only events known by a frame cutoff contribute. Radius is an exponential length scale, not a hard circle boundary. Sector `all` matches every asset exposure; other sectors match exactly. Exposure sector `all` does not automatically match a specialized event.

The economic shock parameter remains an assumption even when the underlying event is observed. Prompt-like text inside any field is untrusted. Source strings are provenance labels, not cryptographically verified evidence. Exact repeated events are idempotent. Conflicting IDs fail. Submit corrected datasets through a fresh replay; appending a correction with a new ID without removing the old event would double count it. Events accepted after a snapshot affect only later market frames.

### Context: `geofolio.context/1.0`

Contains cutoff, revision, data kind, currency, current value, portfolio configuration, complete latest market frame, sample/quality indicators, spatial evidence and region impacts, annual macro context, indicative hedge, forecast and limitations. The optional additive macro block is annual context with source, observation year and fetched_at, not a forecast input. `hedge`/`forecast` are null during warmup; zero hedge variance leaves only `hedge` null with a warning.

`context_sha256` is computed by removing that field, then Python `json.dumps(..., sort_keys=True, separators=(",", ":"), allow_nan=False)` and SHA-256 of UTF-8 bytes. This uses Python JSON numeric formatting and default ASCII escaping; it is **not RFC 8785 canonical JSON**. Cross-language clients must match that serialization or treat it as an opaque identifier. A hash provides change detection, not authentication or a signature.

The HTTP/WebSocket wrapper adds `transport.age_seconds` and `transport.stale`, outside the hash. Historical replay is normally stale relative to wall clock. Freshness of each underlying quote can be inspected from the market block. Context age is clamped at zero for future-dated replay frames; producers must not label synthetic future data as live. Live API adapters use current wall-clock cutoffs.

WebSocket delivery is latest-state sampling every second, not a lossless event log. Revision jumps are valid, and consumers needing an audit trail must record inputs outside this service. Event data and forecasts stay unchanged between market samples, while transport age updates.

## LLM use

`/v1/llm/messages` provides a system prompt and JSON user message. Consumers should preserve the system instruction, check freshness/quality before calling any model, and avoid automated trade execution from model prose. The LLM explains numerical results; it does not create the hedge ratio or certify forecast validity. Full evidence is included, without token truncation; consumers must budget context size or select evidence explicitly.

## Company transport access

All `/v1/*` reads and WebSocket streams require a role key or session. Writes require administrator access. Sessions last eight hours and invalidate on restart. See [deployment](DEPLOYMENT.md). Live-mode startup uses real historical closed candles; `kind=live` denotes a real-data monitoring workspace, while per-quote source distinguishes history from streamed last trades. Historical warmup is not a point-in-time backtest.
