from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from geofolio.adapters import history_frames, worldbank_observations
from geofolio.api import create_app
from geofolio.auth import Access
from geofolio.demo import demo_portfolio
from geofolio.workspace import default_portfolio, initialize


def test_credentials_private_and_stable(tmp_path):
    keys, created = initialize(tmp_path)
    assert created and keys["admin"] != keys["viewer"]
    assert initialize(tmp_path) == (keys, False)
    import os

    if os.name != "nt":
        assert (tmp_path / "access.json").stat().st_mode & 0o777 == 0o600


def test_sessions_tampering_and_restart():
    access = Access("admin", "viewer")
    cookie = access.session("viewer")
    assert access.role({}, {"geofolio_session": cookie}) == "viewer"
    assert access.role({}, {"geofolio_session": cookie.replace("viewer", "admin")}) is None
    assert Access("admin", "viewer").role({}, {"geofolio_session": cookie}) is None


def test_roles_csrf_websocket_and_persistence(tmp_path):
    portfolio = demo_portfolio()
    with TestClient(create_app(portfolio, token="admin", viewer_token="viewer", data_dir=tmp_path)) as c:
        assert c.get("/v1/workspace").status_code == 401
        with pytest.raises(WebSocketDisconnect):
            with c.websocket_connect("/v1/stream"):
                pass
        assert (
            c.post(
                "/auth/login", json={"key": "viewer"}, headers={"Origin": "https://evil.example"}
            ).status_code
            == 403
        )
        login = c.post("/auth/login", json={"key": "viewer"})
        assert login.status_code == 200
        assert "HttpOnly" in login.headers["set-cookie"]
        w = c.get("/v1/workspace").json()
        assert w["role"] == "viewer" and w["persistent"]
        payload = {
            "expected_revision": w["configuration_revision"],
            "portfolio": portfolio.model_dump(mode="json"),
        }
        assert c.put("/v1/portfolio", json=payload).status_code == 403
        c.post("/auth/login", json={"key": "admin"})
        payload["portfolio"]["name"] = "Treasury team"
        assert c.put("/v1/portfolio", json=payload).status_code == 200
        assert c.put("/v1/portfolio", json=payload).status_code == 409
        assert c.get("/v1/audit").json()["entries"][0]["action"] == "portfolio.updated"
        assert c.post("/auth/logout").status_code == 200
        assert c.get("/v1/context").status_code == 401
    with TestClient(create_app(portfolio, token="admin", data_dir=tmp_path)) as c:
        c.headers["Authorization"] = "Bearer admin"
        assert c.get("/v1/workspace").json()["portfolio"]["name"] == "Treasury team"


def test_macro_latest_non_null():
    row = {"countryiso3code": "USA", "country": {"value": "United States"}}
    payload = [
        {},
        [
            dict(row, date="2025", value=None),
            dict(row, date="2024", value=10),
            dict(row, date="2023", value=9),
        ],
    ]
    result = worldbank_observations(payload, "NY.GDP.MKTP.CD")
    assert len(result) == 1 and result[0]["year"] == 2024 and result[0]["value"] == 10


def test_closed_candle_alignment():
    import asyncio

    end = int(datetime.now(UTC).timestamp() // 60) * 60

    def handler(request):
        # Reverse-order, one still-open candle, one completed common close.
        return httpx.Response(200, json=[[end, 1, 2, 1, 1.8, 100], [end - 60, 1, 2, 1, 1.5, 100]])

    async def check():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            frames = await history_frames(default_portfolio(), client)
        assert len(frames) == 1
        assert frames[0].as_of.timestamp() == end
        assert all(q.price == 1.5 for q in frames[0].quotes.values())
        assert all("closed-candle" in q.source for q in frames[0].quotes.values())

    asyncio.run(check())


def test_scenario_removal_persists_and_observation_is_protected(tmp_path):
    from geofolio.models import SpatialEvent

    now = datetime.now(UTC)
    event = SpatialEvent(
        event_id="test:scenario",
        occurred_at=now,
        known_at=now,
        latitude=0,
        longitude=0,
        radius_km=100,
        half_life_hours=24,
        scenario_impact_bps=-100,
        source="test",
        kind="simulated",
    )
    with TestClient(create_app(demo_portfolio(), token="admin", data_dir=tmp_path)) as c:
        c.headers["Authorization"] = "Bearer admin"
        assert c.get("/v1/map").json()["type"] == "FeatureCollection"
        assert c.post("/v1/events", json=event.model_dump(mode="json")).status_code == 200
        assert c.delete("/v1/events/test:scenario").status_code == 200
        observed = event.model_copy(update={"event_id": "observed", "kind": "observed"})
        c.post("/v1/events", json=observed.model_dump(mode="json"))
        assert c.delete("/v1/events/observed").status_code == 409
    with TestClient(create_app(demo_portfolio(), token="admin", data_dir=tmp_path)) as c:
        c.headers["Authorization"] = "Bearer admin"
        events = c.get("/v1/workspace").json()["events"]
        assert [e["event_id"] for e in events] == ["observed"]
