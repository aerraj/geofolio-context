"""Public feeds. No orders or credentials; caller owns sampling cadence."""

import asyncio
import json
import logging
from collections import deque
from datetime import UTC, datetime

import httpx
import websockets

from .models import Quote, SpatialEvent

log = logging.getLogger(__name__)


def coinbase_quote(message):
    if message.get("type") != "ticker":
        return None
    return message["product_id"], Quote(
        price=float(message["price"]),
        observed_at=datetime.fromisoformat(message["time"]),
        source="coinbase-exchange/ticker",
    )


async def coinbase(symbols, latest, status):
    delay = 1
    while True:
        try:
            async with websockets.connect(
                "wss://ws-feed.exchange.coinbase.com", ping_interval=20, ping_timeout=20, max_size=1_000_000
            ) as ws:
                await ws.send(
                    json.dumps(
                        {"type": "subscribe", "product_ids": symbols, "channels": ["ticker", "heartbeat"]}
                    )
                )
                status["market"] = "connected"
                delay = 1
                async for raw in ws:
                    message = json.loads(raw)
                    if message.get("type") == "error":
                        raise ValueError(message.get("message", "feed subscription failed"))
                    parsed = coinbase_quote(message)
                    if parsed:
                        symbol, quote = parsed
                        if symbol in symbols and (
                            symbol not in latest or quote.observed_at > latest[symbol][-1].observed_at
                        ):
                            latest.setdefault(symbol, deque(maxlen=2048)).append(quote)
        except (OSError, ValueError, KeyError, websockets.exceptions.WebSocketException) as exc:
            status["market"] = "reconnecting: " + type(exc).__name__
            log.warning("Coinbase disconnected: %s", exc)
            await asyncio.sleep(delay)
            delay = min(60, delay * 2)


def usgs_events(payload, known_at):
    result = []
    for feature in payload.get("features", []):
        props, coords = feature["properties"], feature["geometry"]["coordinates"]
        magnitude = props.get("mag")
        if magnitude is None or magnitude < 4.5:
            continue
        occurred = datetime.fromtimestamp(props["time"] / 1000, UTC)
        if occurred > known_at:
            continue
        # Preserve observation but require explicit economic calibration: default shock is ZERO.
        result.append(
            SpatialEvent(
                event_id="usgs:" + feature["id"],
                occurred_at=occurred,
                known_at=known_at,
                latitude=coords[1],
                longitude=coords[0],
                radius_km=300,
                half_life_hours=24,
                scenario_impact_bps=0,
                kind="observed",
                source=props["url"],
                description=f"M{magnitude}: {props.get('place', 'unknown location')}. Uncalibrated: zero impact.",
            )
        )
    return result


async def usgs(engine, status, lock, store=None):
    url = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson"
    async with httpx.AsyncClient(timeout=15) as client:
        while True:
            try:
                response = await client.get(url)
                response.raise_for_status()
                events = usgs_events(response.json(), datetime.now(UTC))
                async with lock:
                    for event in events:
                        if event.event_id not in engine.events:
                            engine.event(event)
                            if store:
                                store.record("spatial", event)
                status["spatial"] = "connected; observed events have zero impact until calibrated"
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                status["spatial"] = "feed error: " + type(exc).__name__
                log.warning("USGS feed: %s", exc)
            await asyncio.sleep(60)


async def history_frames(portfolio, client):
    """Fetch only closed candles, align symbols, retain real-data provenance."""
    from .models import MarketFrame

    interval = portfolio.interval_seconds
    if interval not in {60, 300, 900, 3600, 21600, 86400}:
        return []
    end = int(datetime.now(UTC).timestamp() // interval) * interval
    count = min(portfolio.window + 1, 290)
    symbols = sorted({p.symbol for p in portfolio.positions} | {portfolio.hedge_symbol})
    series = {}
    for symbol in symbols:
        # Symbols are allowlisted by live-mode validation before URL construction.
        response = await client.get(
            f"https://api.exchange.coinbase.com/products/{symbol}/candles",
            params={
                "granularity": interval,
                "start": datetime.fromtimestamp(end - count * interval, UTC).isoformat(),
                "end": datetime.fromtimestamp(end, UTC).isoformat(),
            },
        )
        response.raise_for_status()
        series[symbol] = {
            int(row[0]) + interval: float(row[4])
            for row in response.json()
            if end - count * interval < int(row[0]) + interval <= end
        }
        await asyncio.sleep(0.2)
    common = sorted(set.intersection(*(set(s) for s in series.values())))
    return [
        MarketFrame(
            frame_id=f"coinbase-candle:{t}",
            as_of=datetime.fromtimestamp(t, UTC),
            kind="live",
            quotes={
                s: Quote(
                    price=series[s][t],
                    observed_at=datetime.fromtimestamp(t, UTC),
                    source="coinbase-exchange/closed-candle",
                )
                for s in symbols
            },
        )
        for t in common
    ]


def worldbank_observations(payload, indicator):
    if not isinstance(payload, list) or len(payload) != 2 or not isinstance(payload[1], list):
        raise ValueError("unexpected World Bank response")
    latest = {}
    for row in payload[1]:
        if row.get("value") is None:
            continue
        code = row["countryiso3code"]
        if code not in latest or int(row["date"]) > latest[code]["year"]:
            latest[code] = {
                "country_code": code,
                "country": row["country"]["value"],
                "indicator": indicator,
                "year": int(row["date"]),
                "value": float(row["value"]),
                "unit": "current USD" if indicator == "NY.GDP.MKTP.CD" else "annual percent",
                "source": "The World Bank: World Development Indicators",
                "url": f"https://data.worldbank.org/indicator/{indicator}",
            }
    return list(latest.values())


async def fetch_macro(countries, client):
    observations = []
    if not countries:
        return {"status": "no_countries_configured", "observations": []}
    for indicator in ["NY.GDP.MKTP.CD", "NY.GDP.MKTP.KD.ZG"]:
        response = await client.get(
            f"https://api.worldbank.org/v2/country/{';'.join(countries)}/indicator/{indicator}",
            params={"format": "json", "per_page": 200, "mrv": 5},
        )
        response.raise_for_status()
        observations.extend(worldbank_observations(response.json(), indicator))
    return {
        "status": "available",
        "fetched_at": datetime.now(UTC).isoformat(),
        "observations": observations,
        "frequency": "annual",
        "interpretation": "Latest available annual releases; not real-time GDP. Not used as a return signal.",
    }


async def worldbank(engine, status, lock):
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        while True:
            try:
                macro = await fetch_macro(engine.portfolio.macro_countries, client)
                async with lock:
                    engine.macro = macro
                status["macro"] = "available; annual release data"
                delay = 86400
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                status["macro"] = "unavailable: " + type(exc).__name__
                delay = 300
            await asyncio.sleep(delay)
