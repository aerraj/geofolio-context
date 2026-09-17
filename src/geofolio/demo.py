from datetime import UTC, datetime, timedelta

import numpy as np

from .models import MarketFrame, Portfolio, Quote, SpatialEvent


def demo_portfolio():
    return Portfolio.model_validate(
        {
            "name": "Synthetic global exposure lab",
            "hedge_symbol": "HEDGE",
            "interval_seconds": 1,
            "max_quote_age_seconds": 5,
            "horizon_steps": 60,
            "cash_usd": 10000,
            "economic_weights": {"Mumbai": 0.4, "Singapore": 0.35, "New York": 0.25},
            "positions": [
                {
                    "symbol": "INDUSTRY",
                    "units": 400,
                    "exposures": [
                        {
                            "region": "Mumbai",
                            "latitude": 19.076,
                            "longitude": 72.8777,
                            "share": 0.7,
                            "sector": "manufacturing",
                        },
                        {"region": "Singapore", "latitude": 1.3521, "longitude": 103.8198, "share": 0.3},
                    ],
                },
                {
                    "symbol": "LOGISTICS",
                    "units": 500,
                    "exposures": [
                        {"region": "Singapore", "latitude": 1.3521, "longitude": 103.8198, "share": 0.6},
                        {"region": "New York", "latitude": 40.7128, "longitude": -74.006, "share": 0.4},
                    ],
                },
            ],
        }
    )


class Demo:
    def __init__(self, portfolio):
        self.rng = np.random.default_rng(7)
        self.symbols = sorted({p.symbol for p in portfolio.positions} | {portfolio.hedge_symbol})
        self.prices = np.full(len(self.symbols), 100.0)

    def frame(self, when):
        common = self.rng.normal(0, 0.0007)
        self.prices *= np.exp(common + self.rng.normal(0, 0.0003, len(self.symbols)))
        return MarketFrame(
            frame_id="demo:" + when.isoformat(),
            as_of=when,
            kind="simulated",
            quotes={
                s: Quote(price=float(v), observed_at=when, source="seeded-demo/7")
                for s, v in zip(self.symbols, self.prices)
            },
        )


def warm_demo(engine):
    demo = Demo(engine.portfolio)
    end = datetime.now(UTC).replace(microsecond=0)
    exposure = next((e for p in engine.portfolio.positions for e in p.exposures), None)
    if exposure:
        engine.event(
            SpatialEvent(
                event_id="demo:port-disruption",
                occurred_at=end - timedelta(hours=1),
                known_at=end - timedelta(hours=1),
                latitude=exposure.latitude,
                longitude=exposure.longitude,
                radius_km=700,
                half_life_hours=12,
                scenario_impact_bps=-120,
                description="Synthetic logistics disruption; illustrative shock, not observed economic loss.",
                source="synthetic-demo",
                kind="simulated",
            )
        )
    for i in range(engine.portfolio.min_samples + 1):
        engine.ingest(
            demo.frame(
                end
                - timedelta(seconds=(engine.portfolio.min_samples - i) * engine.portfolio.interval_seconds)
            )
        )
    return demo
