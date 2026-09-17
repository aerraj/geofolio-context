# Company installation and operations

## Local or small-team pilot

Docker Compose is the recommended first installation: it includes Python and the compiler and persists data in the `workspace` named volume. The default port mapping is `127.0.0.1:8000:8000`, keeping access on the host. Native startup scripts are an alternative for developers with Python/C++ already installed.

Run `geofolio init` in the same directory as `geofolio serve` (or specify identical `--data-dir` paths) to display the generated administrator and viewer access keys. Native credentials are in `.geofolio/access.json` with owner-only permissions on POSIX. SQLite lives in `.geofolio/workspace.sqlite3`; Docker uses `/data`. On Windows, protect this directory with user-specific filesystem ACLs. Never commit a workspace or share the administrator key with read-only users.

## Shared company access

Place the single service behind your company HTTPS reverse proxy or private network gateway. Configure an explicit trusted hostname and forward the original Host and scheme correctly. Run with `--secure-cookie` behind HTTPS. The application rejects cross-origin writes and WebSocket connections and has no permissive CORS policy. Configure Uvicorn's proxy trust only for the actual proxy network; do not trust arbitrary public forwarded headers.

All portfolio/context/schema/API documentation reads require a valid key or cookie. Anonymous `/health` returns process status only. All portfolio, market and scenario writes require the administrator role. Browser cookies expire after eight hours and invalidate when the service restarts. Signing out deletes the current browser cookie; it does not revoke a previously copied cookie. Restart the service to invalidate all sessions. Use organization SSO and individual identities upstream when per-user revocation, MFA or named audit attribution is needed. Shared role keys are for small-team pilots, not an enterprise identity solution.

Environment overrides: `GEOFOLIO_TOKEN` for administrator access and `GEOFOLIO_VIEWER_TOKEN` for read-only access. Set long independent random values using your secret manager. Rotate both keys in the credential file or environment and restart to revoke keys/sessions. Keys are never sent to market-data providers or stored in browser localStorage. Browser login attempts are rate-limited at the service process level; upstream throttling is also appropriate for a shared installation.

## Persistence and backups

SQLite stores one portfolio configuration, at most 2,001 market records, 1,000 event records and 1,000 audit entries. The activity endpoint shows the latest 100. The record buffer supports restart recovery and is not a full immutable regulatory audit log. Annual macro releases are fetched again after restart. A config update clears market/event history and starts new feed subscriptions; prior configuration changes remain in the audit trail. Scenario deletion removes that assumption's saved event and records an audit entry.

Stop the service before copying the entire data directory/volume for a consistent backup. Keep access keys and database backups private. Restore them into an empty workspace and restart. `docker compose down` preserves the volume; do not use `down -v` unless you intentionally want to delete it. Run one process per workspace, not multiple Uvicorn workers sharing in-memory state.

## Feed behavior

Coinbase closed candles bootstrap up to 290 aligned real frames, with incomplete candles excluded. Each close is conservatively timestamped at bucket end. Historical and streaming observations share `kind=live` to denote the real-data workspace, with source fields distinguishing `closed-candle` from `ticker`. This is live-monitoring warmup, **not point-in-time historical backtesting**: candle data are fetched now and may reflect later revisions. Missing intervals reset the estimator. Streaming quote buffers select observations at or before a sampling cutoff, subject to max age.

USGS polls each minute and retains the first observed version of an event ID. Economic shock is zero unless explicitly modeled in a separate simulated assumption. The 1,000-event cap requires periodic curated workspace maintenance for long-running deployments. Event observations and assumptions are individually labeled. Model assumptions can double-count overlapping risks; review active assumptions before adding more.

World Bank data refresh daily; failed calls retry after five minutes. The feed status is independent of cached observations, so a failed refresh is visible even if earlier annual values remain. Annual data retain their release year and latest fetch time and are never called real-time GDP.

Monitor `/v1/workspace` feed status and `/v1/context` freshness/quality; `/health` does not establish healthy providers. Budget network connectivity to Coinbase, USGS and the World Bank. Vendor availability and regional access restrictions can prevent a feed from working. Analytics only resume after sufficient valid samples.

## Scope and limits

This release is a single-workspace internal research application. It does not provide individual accounts, tenant isolation, distributed storage, scheduled reporting, trade execution, licensed equity coverage, full GIS boundary maps, calibrated macro impact coefficients, or validated future returns. Company production rollout should add the operational and identity controls required by that company's own policies.
