import asyncio
import re
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from pydantic import Field

from .adapters import coinbase, history_frames, usgs, worldbank
from .auth import Access
from .demo import warm_demo
from .engine import Engine
from .models import MarketFrame, Model, Portfolio, Quote, SpatialEvent
from .store import Store


class Login(Model):
    key: str = Field(min_length=1, max_length=256)


class Configuration(Model):
    expected_revision: int = Field(ge=0)
    portfolio: Portfolio


def validate_live(portfolio):
    symbols = {p.symbol for p in portfolio.positions} | {portfolio.hedge_symbol}
    if len(symbols) > 10 or any(not re.fullmatch(r"[A-Z0-9]{2,12}-USD", s) for s in symbols):
        raise ValueError("Live mode supports up to 10 Coinbase USD pairs such as ETH-USD and BTC-USD")
    if portfolio.interval_seconds not in {60, 300, 900, 3600, 21600, 86400}:
        raise ValueError("Live interval must be 60, 300, 900, 3600, 21600 or 86400 seconds")


def create_app(portfolio, mode="manual", token=None, viewer_token=None, data_dir=None, secure_cookie=False):
    if mode not in {"manual", "demo", "live"}:
        raise ValueError("unknown mode")
    store = Store(Path(data_dir) / "workspace.sqlite3") if data_dir else None
    revision, saved = store.config() if store else (0, None)
    if saved:
        portfolio = Portfolio.model_validate(saved)
    if mode == "live":
        validate_live(portfolio)
    if store and not saved:
        revision = store.configure(portfolio, 0, "setup")
    engine = Engine(portfolio)
    access = Access(token, viewer_token)
    lock = asyncio.Lock()
    status = {"mode": mode, "market": "waiting", "spatial": "waiting", "macro": "waiting"}
    latest, tasks = {}, []
    login_attempts = defaultdict(deque)

    def ingest(frame):
        result = engine.ingest(frame)
        if store:
            store.record("market", frame)
        return result

    async def ticker(demo=None):
        while True:
            interval = engine.portfolio.interval_seconds
            await asyncio.sleep(interval - datetime.now(UTC).timestamp() % interval)
            now = datetime.now(UTC)
            cutoff = datetime.fromtimestamp(int(now.timestamp() // interval) * interval, UTC)
            try:
                async with lock:
                    if demo:
                        frame = demo.frame(cutoff)
                    else:
                        symbols = {p.symbol for p in engine.portfolio.positions} | {
                            engine.portfolio.hedge_symbol
                        }
                        if not symbols <= latest.keys():
                            continue
                        # Newer-than-cutoff ticks must wait for the next frame, never backdate them.
                        quotes = {}
                        for s in symbols:
                            candidate = next(
                                (q for q in reversed(latest[s]) if q.observed_at <= cutoff), None
                            )
                            if candidate is None:
                                raise ValueError("waiting for a quote at or before the sample cutoff")
                            quotes[s] = Quote.model_validate(candidate.model_dump())
                        frame = MarketFrame(
                            frame_id="coinbase:" + cutoff.isoformat(),
                            as_of=cutoff,
                            kind="live",
                            quotes=quotes,
                        )
                    ingest(frame)
                    status["sampling"] = "ok"
            except ValueError as exc:
                status["sampling"] = str(exc)

    async def bootstrap():
        status["history"] = "loading real closed candles"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                frames = await history_frames(engine.portfolio, client)
            async with lock:
                for frame in frames:
                    if not engine.frames or frame.as_of > engine.frames[-1].as_of:
                        ingest(frame)
                status["history"] = f"{len(engine.frames)} real frames available"
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            status["history"] = "unavailable; warming from live ticks: " + type(exc).__name__
        # Streaming continues even if historical REST data is temporarily unavailable.
        await ticker()

    def start():
        latest.clear()
        if mode == "demo":
            demo = warm_demo(engine)
            status.update(market="synthetic", spatial="synthetic", macro="disabled in demo")
            tasks.append(asyncio.create_task(ticker(demo)))
        elif mode == "live":
            symbols = sorted({p.symbol for p in engine.portfolio.positions} | {engine.portfolio.hedge_symbol})
            tasks.extend(
                [
                    asyncio.create_task(coinbase(symbols, latest, status)),
                    asyncio.create_task(bootstrap()),
                    asyncio.create_task(usgs(engine, status, lock, store)),
                    asyncio.create_task(worldbank(engine, status, lock)),
                ]
            )

    async def stop():
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        tasks.clear()

    @asynccontextmanager
    async def lifespan(app):
        if store and mode != "demo":
            for kind, body in store.records():
                try:
                    if kind == "spatial":
                        engine.event(SpatialEvent.model_validate_json(body))
                    else:
                        frame = MarketFrame.model_validate_json(body)
                        if mode != "live" or frame.kind == "live":
                            engine.ingest(frame)
                except ValueError:
                    # Old mode or malformed records are never silently used for analytics.
                    status["restore"] = "some incompatible records skipped"
        start()
        yield
        await stop()
        if store:
            store.close()

    app = FastAPI(title="GeoFolio · Company Workspace", version="0.2.0", lifespan=lifespan)
    app.state.engine = engine

    @app.middleware("http")
    async def authentication(request: Request, call_next):
        public = request.url.path in {"/", "/auth/login", "/health", "/favicon.ico"}
        role = access.role(request.headers, request.cookies)
        request.state.role = role
        if not public and not role:
            return JSONResponse({"detail": "Sign in to your company workspace"}, status_code=401)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            if origin and origin != str(request.base_url).rstrip("/"):
                return JSONResponse({"detail": "Cross-origin writes are blocked"}, status_code=403)
            if request.url.path not in {"/auth/login", "/auth/logout"} and role != "admin":
                return JSONResponse({"detail": "Administrator access required"}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        return Path(__file__).with_name("static").joinpath("index.html").read_text()

    @app.get("/favicon.ico")
    async def favicon():
        return Response(status_code=204)

    @app.post("/auth/login")
    async def login(body: Login, request: Request):
        # Bounded process-wide limiter; no client-controlled IP map or unlimited allocation.
        attempts = login_attempts["global"]
        now = time.monotonic()
        while attempts and attempts[0] < now - 60:
            attempts.popleft()
        if len(attempts) >= 30:
            raise HTTPException(429, "Too many sign-in attempts; try again in a minute")
        attempts.append(now)
        role = access.key_role(body.key)
        if not role:
            raise HTTPException(401, "Invalid workspace access key")
        if store:
            store.audit(role, "session.login")
        response = JSONResponse({"role": role})
        response.set_cookie(
            "geofolio_session",
            access.session(role),
            httponly=True,
            samesite="strict",
            secure=secure_cookie,
            max_age=28800,
        )
        return response

    @app.post("/auth/logout")
    async def logout():
        response = JSONResponse({"ok": True})
        response.delete_cookie("geofolio_session")
        return response

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/v1/map")
    async def land_map():
        return FileResponse(
            Path(__file__).with_name("static") / "land.geojson", media_type="application/geo+json"
        )

    @app.get("/v1/workspace")
    async def workspace(request: Request):
        return {
            "role": request.state.role,
            "mode": mode,
            "configuration_revision": revision,
            "portfolio": engine.portfolio.model_dump(mode="json"),
            "feeds": status,
            "persistent": store is not None,
            "macro": engine.macro,
            "events": [e.model_dump(mode="json") for e in engine.events.values()],
        }

    @app.put("/v1/portfolio")
    async def configure(body: Configuration):
        nonlocal engine, revision
        if body.expected_revision != revision:
            raise HTTPException(409, "Workspace changed; reload before saving")
        if mode == "live":
            try:
                validate_live(body.portfolio)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
        async with lock:
            if body.expected_revision != revision:
                raise HTTPException(409, "Workspace changed; reload before saving")
            await stop()
            revision = store.configure(body.portfolio, revision) if store else revision + 1
            engine = Engine(body.portfolio)
            app.state.engine = engine
            status.clear()
            status.update(mode=mode, market="restarting", spatial="restarting", macro="restarting")
            start()
        return {"configuration_revision": revision, "status": "saved; analytics history reset"}

    @app.get("/v1/audit")
    async def audit():
        return {"entries": store.audits() if store else []}

    @app.get("/v1/context")
    async def context():
        return engine.snapshot()

    @app.get("/v1/llm/messages")
    async def messages():
        return {"messages": engine.llm_messages()}

    @app.get("/v1/schema/{kind}")
    async def schema(kind: str):
        model = {"market": MarketFrame, "spatial": SpatialEvent, "portfolio": Portfolio}.get(kind)
        if model is None:
            raise HTTPException(404, "Unknown schema")
        return model.model_json_schema()

    @app.post("/v1/market")
    async def market(frame: MarketFrame):
        if mode != "manual":
            raise HTTPException(409, "Market ingestion requires manual mode")
        async with lock:
            try:
                return ingest(frame)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc

    @app.post("/v1/events")
    async def event(event: SpatialEvent):
        async with lock:
            try:
                accepted = engine.event(event)
                if store and accepted:
                    store.record("spatial", event)
                    store.audit("admin", "event.added", event.event_id)
                return {"accepted": accepted, "effective": "next market frame"}
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc

    @app.delete("/v1/events/{event_id:path}")
    async def remove_scenario(event_id: str):
        async with lock:
            event = engine.events.get(event_id)
            if event is None:
                raise HTTPException(404, "Event not found")
            if event.kind != "simulated":
                raise HTTPException(409, "Only scenario assumptions can be removed")
            if store:
                store.remove_event(event_id)
            del engine.events[event_id]
        return {"removed": event_id, "effective": "next market frame"}

    @app.websocket("/v1/stream")
    async def stream(ws: WebSocket):
        origin = ws.headers.get("origin")
        allowed = {"http://" + ws.headers.get("host", ""), "https://" + ws.headers.get("host", "")}
        if not access.role(ws.headers, ws.cookies) or (origin and origin not in allowed):
            await ws.close(code=1008)
            return
        await ws.accept()
        try:
            while access.role(ws.headers, ws.cookies):
                await asyncio.wait_for(ws.send_json(engine.snapshot()), timeout=10)
                await asyncio.sleep(1)
            await ws.close(code=1008)
        except (TimeoutError, WebSocketDisconnect, RuntimeError):
            pass

    return app
