import math

from ._core import haversine_km


def spatial_context(portfolio, events, as_of):
    shocks, regions, evidence = {}, {}, []
    active = [e for e in events if e.known_at <= as_of]
    for position in portfolio.positions:
        total = 0.0
        for exposure in position.exposures:
            impact = 0.0
            for event in active:
                if event.sector not in ("all", exposure.sector):
                    continue
                distance = haversine_km(
                    exposure.latitude, exposure.longitude, event.latitude, event.longitude
                )
                age = (as_of - event.occurred_at).total_seconds() / 3600
                contribution = (
                    event.scenario_impact_bps
                    * math.exp(-distance / event.radius_km)
                    * 2 ** (-age / event.half_life_hours)
                )
                impact += contribution
            total += exposure.share * impact / 10000
            region = regions.setdefault(
                exposure.region,
                {
                    "region": exposure.region,
                    "latitude": exposure.latitude,
                    "longitude": exposure.longitude,
                    "sector_impacts_bps": {},
                },
            )
            region["sector_impacts_bps"][exposure.sector] = impact
        shocks[position.symbol] = total
    for event in active:
        evidence.append(event.model_dump(mode="json"))
    # Equal sector average within region is a disclosed modeling assumption.
    for r in regions.values():
        values = list(r["sector_impacts_bps"].values())
        r["scenario_impact_bps"] = sum(values) / len(values)
    index = sum(portfolio.economic_weights.get(k, 0) * r["scenario_impact_bps"] for k, r in regions.items())
    return {
        "asset_shocks": shocks,
        "regions": list(regions.values()),
        "events": evidence,
        "economic_stress_index_bps": index,
        "economic_weight_coverage": sum(portfolio.economic_weights.values()),
        "interpretation": "Assumed spatial stress proxy; not measured GDP or a causal estimate.",
    }
