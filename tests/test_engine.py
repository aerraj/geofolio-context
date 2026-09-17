import hashlib
import json
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from geofolio.demo import Demo, demo_portfolio, warm_demo
from geofolio.engine import Engine
from geofolio.forecast import project
from geofolio.models import MarketFrame, Portfolio, SpatialEvent
from geofolio.spatial import spatial_context


def test_full_context_and_hash():
    engine = Engine(demo_portfolio())
    warm_demo(engine)
    c = dict(engine.last)
    digest = c.pop("context_sha256")
    assert (
        hashlib.sha256(
            json.dumps(c, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
        == digest
    )
    assert c["quality"]["status"] == "ready"
    assert c["hedge"]["samples"] == 20
    assert c["hedge"]["units_to_short"] == pytest.approx(
        c["hedge"]["ratio"] * c["portfolio_value"] / c["market"]["quotes"]["HEDGE"]["price"]
    )
    assert c["forecast"]["spatial_scenario"][-1]["p50"] < c["forecast"]["baseline"][-1]["p50"]
    for row in c["forecast"]["spatial_scenario"]:
        assert row["p05"] <= row["p50"] <= row["p95"]
    assert len(engine.llm_messages()) == 2


def test_duplicate_out_of_order_gap_and_kind():
    engine = Engine(demo_portfolio())
    demo = warm_demo(engine)
    last = engine.frames[-1]
    assert engine.ingest(last) == engine.last
    assert engine.revision == 21
    with pytest.raises(ValueError, match="increasing"):
        engine.ingest(last.model_copy(update={"frame_id": "new"}))
    later = demo.frame(last.as_of + timedelta(seconds=3))
    with pytest.raises(ValueError, match="mix"):
        engine.ingest(later.model_copy(update={"kind": "live"}))
    result = engine.ingest(later)
    assert result["quality"]["gap_resets"] == 1
    assert result["quality"]["status"] == "warming_up"
    assert result["forecast"] is None


def test_stale_missing_future_and_nonfinite():
    engine = Engine(demo_portfolio())
    demo = Demo(engine.portfolio)
    now = datetime.now(UTC)
    frame = demo.frame(now)
    payload = frame.model_dump(mode="json")
    payload["quotes"]["HEDGE"]["price"] = float("nan")
    with pytest.raises(ValueError):
        MarketFrame.model_validate(payload)
    payload = frame.model_dump()
    payload["quotes"]["HEDGE"]["observed_at"] = now + timedelta(seconds=1)
    with pytest.raises(ValueError, match="cutoff"):
        MarketFrame.model_validate(payload)
    with pytest.raises(ValueError, match="stale"):
        engine.ingest(frame.model_copy(update={"as_of": now + timedelta(seconds=100)}))
    with pytest.raises(ValueError, match="missing"):
        engine.ingest(frame.model_copy(update={"quotes": {}}))
    assert engine.revision == 0


def test_spatial_known_time_distance_and_decay():
    p = demo_portfolio()
    now = datetime.now(UTC)
    event = SpatialEvent(
        event_id="e",
        occurred_at=now,
        known_at=now,
        latitude=19.076,
        longitude=72.8777,
        radius_km=100,
        half_life_hours=1,
        scenario_impact_bps=-100,
        source="test",
        kind="simulated",
    )
    before = spatial_context(p, [event], now - timedelta(seconds=1))
    after = spatial_context(p, [event], now)
    later = spatial_context(p, [event], now + timedelta(hours=1))
    assert before["events"] == []
    assert abs(after["asset_shocks"]["INDUSTRY"]) > abs(after["asset_shocks"]["LOGISTICS"])
    assert later["asset_shocks"]["INDUSTRY"] == pytest.approx(after["asset_shocks"]["INDUSTRY"] / 2)
    engine = Engine(p)
    assert engine.event(event)
    assert not engine.event(event)
    with pytest.raises(ValueError, match="ID"):
        engine.event(event.model_copy(update={"scenario_impact_bps": -50}))


def test_zero_variance_hedge_is_unavailable():
    engine = Engine(demo_portfolio())
    demo = Demo(engine.portfolio)
    now = datetime.now(UTC)
    for i in range(21):
        frame = demo.frame(now + timedelta(seconds=i))
        frame.quotes["HEDGE"].price = 100
        engine.ingest(frame)
    assert engine.last["hedge"] is None
    assert "zero" in engine.last["quality"]["hedge_warning"]
    assert engine.last["forecast"] is not None


def test_forecast_reproducible_and_perfect_dependence():
    r = np.array([[0.01, 0.01], [-0.01, -0.01], [0.005, 0.005], [-0.005, -0.005]])
    a = project(r, [50, 50], 10, [0, 0], 10, 200, 60)
    b = project(r[:, :1], [100], 10, [0], 10, 200, 60)
    assert a == project(r, [50, 50], 10, [0, 0], 10, 200, 60)
    assert a["spatial_scenario"] == b["spatial_scenario"]
    assert a["baseline"] == a["spatial_scenario"]
    assert a["scenario_expected_shortfall95_usd"] >= a["scenario_var95_usd"]


def test_bad_exposure_and_weights():
    data = demo_portfolio().model_dump()
    data["positions"][0]["exposures"][0]["share"] = 1
    with pytest.raises(ValueError, match="exposure"):
        Portfolio.model_validate(data)
    data = demo_portfolio().model_dump()
    data["economic_weights"] = {"Atlantis": 0.5}
    with pytest.raises(ValueError, match="unknown"):
        Portfolio.model_validate(data)


def test_failed_forecast_does_not_mutate_state(monkeypatch):
    engine = Engine(demo_portfolio())
    demo = warm_demo(engine)
    before = engine.snapshot()["context"]
    when = engine.frames[-1].as_of + timedelta(seconds=1)

    def fail(*args, **kwargs):
        raise ValueError("numerical failure")

    monkeypatch.setattr("geofolio.engine.project", fail)
    with pytest.raises(ValueError, match="numerical"):
        engine.ingest(demo.frame(when))
    assert engine.last is before
    assert engine.revision == before["revision"]
    assert engine.frames[-1].as_of < when


def test_event_after_cutoff_not_in_context():
    engine = Engine(demo_portfolio())
    demo = warm_demo(engine)
    event = next(iter(engine.events.values())).model_copy(
        update={"event_id": "future", "known_at": engine.frames[-1].as_of + timedelta(hours=1)}
    )
    engine.event(event)
    engine.ingest(demo.frame(engine.frames[-1].as_of + timedelta(seconds=1)))
    assert "future" not in [e["event_id"] for e in engine.last["spatial"]["events"]]


def test_oversized_workload_rejected():
    data = demo_portfolio().model_dump()
    data.update(paths=5000, horizon_steps=240)
    with pytest.raises(ValueError, match="workload"):
        Portfolio.model_validate(data)
