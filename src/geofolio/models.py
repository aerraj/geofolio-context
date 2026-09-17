from datetime import datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Quote(Model):
    price: float = Field(ge=1e-9, le=1e12)
    observed_at: AwareDatetime
    source: str = Field(min_length=1, max_length=100)


class MarketFrame(Model):
    protocol: Literal["geofolio.market/1.0"] = "geofolio.market/1.0"
    frame_id: str = Field(min_length=1, max_length=128)
    as_of: AwareDatetime
    kind: Literal["simulated", "live", "historical"]
    currency: Literal["USD"] = "USD"
    quotes: dict[str, Quote] = Field(min_length=2, max_length=100)

    @model_validator(mode="after")
    def cutoff(self):
        if any(q.observed_at > self.as_of for q in self.quotes.values()):
            raise ValueError("quote timestamp is after frame cutoff")
        return self


class SpatialEvent(Model):
    protocol: Literal["geofolio.spatial/1.0"] = "geofolio.spatial/1.0"
    event_id: str = Field(min_length=1, max_length=128)
    occurred_at: AwareDatetime
    known_at: AwareDatetime
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_km: float = Field(gt=0, le=20000)
    half_life_hours: float = Field(gt=0, le=8760)
    scenario_impact_bps: float = Field(ge=-1000, le=1000)
    sector: str = Field(default="all", max_length=100)
    source: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=1000)
    kind: Literal["simulated", "observed"]

    @model_validator(mode="after")
    def chronology(self):
        if self.occurred_at > self.known_at:
            raise ValueError("event cannot be known before occurrence")
        return self


class Exposure(Model):
    region: str = Field(min_length=1, max_length=100)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    share: float = Field(gt=0, le=1)
    sector: str = Field(default="all", max_length=100)


class Position(Model):
    symbol: str = Field(min_length=1, max_length=32)
    units: float = Field(gt=0, le=1e12)
    exposures: list[Exposure] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def shares(self):
        if sum(e.share for e in self.exposures) > 1.00000001:
            raise ValueError("geographic exposure shares exceed one")
        return self


class Portfolio(Model):
    name: str = Field(default="Research portfolio", max_length=100)
    positions: list[Position] = Field(min_length=1, max_length=50)
    hedge_symbol: str = Field(min_length=1, max_length=32)
    cash_usd: float = Field(default=0, ge=0, le=1e18)
    interval_seconds: int = Field(default=60, ge=1, le=86400)
    window: int = Field(default=120, ge=20, le=2000)
    min_samples: int = Field(default=20, ge=3, le=2000)
    horizon_steps: int = Field(default=30, ge=1, le=240)
    paths: int = Field(default=1000, ge=100, le=5000)
    max_quote_age_seconds: int = Field(default=120, ge=1)
    # Explicit externally supplied weights, never inferred GDP estimates.
    economic_weights: dict[str, float] = Field(default_factory=dict)
    macro_countries: list[Annotated[str, Field(pattern=r"^[A-Z]{3}$")]] = Field(
        default_factory=lambda: ["USA", "IND", "SGP"], max_length=10
    )

    @model_validator(mode="after")
    def consistency(self):
        if self.paths * self.horizon_steps * len(self.positions) > 2_000_000:
            raise ValueError("scenario workload exceeds 2 million asset-step draws")
        symbols = [p.symbol for p in self.positions]
        if len(set(symbols)) != len(symbols):
            raise ValueError("position symbols must be unique")
        if self.min_samples > self.window:
            raise ValueError("min_samples exceeds window")
        if any(not 0 <= w <= 1 for w in self.economic_weights.values()):
            raise ValueError("economic weights must be finite and in [0,1]")
        if sum(self.economic_weights.values()) > 1.00000001:
            raise ValueError("economic weights exceed one")
        regions = {e.region for p in self.positions for e in p.exposures}
        if set(self.economic_weights) - regions:
            raise ValueError("economic weights reference unknown exposure regions")
        coordinates = {}
        for p in self.positions:
            for e in p.exposures:
                point = (e.latitude, e.longitude)
                if e.region in coordinates and coordinates[e.region] != point:
                    raise ValueError("a region must have a single representative point")
                coordinates[e.region] = point
        return self


def iso(value: datetime) -> str:
    return value.isoformat()
