from datetime import UTC, datetime

from fastapi.testclient import TestClient

from geofolio.adapters import coinbase_quote, usgs_events
from geofolio.api import create_app
from geofolio.demo import Demo, demo_portfolio


def test_manual_api_auth_validation_schema_and_websocket():
    p = demo_portfolio()
    with TestClient(create_app(p, token="test-token")) as client:
        assert client.get("/health").json()["status"] == "ok"
        assert client.get("/").status_code == 200
        assert client.get("/v1/context").status_code == 401
        client.headers["Authorization"] = "Bearer test-token"
        assert client.get("/v1/schema/market").json()["properties"]["protocol"]
        assert client.get("/v1/schema/unknown").status_code == 404
        frame = Demo(p).frame(datetime.now(UTC)).model_dump(mode="json")
        assert (
            client.post("/v1/market", json=frame, headers={"Authorization": "Bearer wrong"}).status_code
            == 401
        )
        headers = {"Authorization": "Bearer test-token"}
        assert client.post("/v1/market", json=frame, headers=headers).status_code == 200
        assert client.post("/v1/market", json={"wrong": 1}, headers=headers).status_code == 422
        with client.websocket_connect("/v1/stream") as ws:
            assert ws.receive_json()["context"]["data_kind"] == "simulated"
        assert client.get("/v1/llm/messages").json()["messages"][0]["role"] == "system"


def test_demo_lifecycle_and_disabled_ingest():
    with TestClient(create_app(demo_portfolio(), mode="demo", token="test-token")) as client:
        client.headers["Authorization"] = "Bearer test-token"
        assert client.get("/v1/context").json()["context"]["quality"]["status"] == "ready"
        f = client.get("/v1/context").json()["context"]["market"]
        assert client.post("/v1/market", json=f).status_code == 409


def test_adapter_payloads():
    assert coinbase_quote({"type": "heartbeat"}) is None
    symbol, quote = coinbase_quote(
        {"type": "ticker", "product_id": "BTC-USD", "price": "60000", "time": "2026-01-01T00:00:00Z"}
    )
    assert symbol == "BTC-USD" and quote.price == 60000
    now = datetime.now(UTC)
    payload = {
        "features": [
            {
                "id": "abc",
                "geometry": {"coordinates": [70, 20, 10]},
                "properties": {
                    "time": now.timestamp() * 1000 - 1000,
                    "mag": 5,
                    "url": "https://earthquake.usgs.gov/test",
                    "place": "test",
                },
            }
        ]
    }
    events = usgs_events(payload, now)
    assert events[0].scenario_impact_bps == 0
    assert events[0].latitude == 20
    assert events[0].kind == "observed"
