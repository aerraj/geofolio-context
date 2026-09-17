import numpy as np


def project(returns, values, cash, shocks, steps, paths, interval_seconds, seed=42):
    """Joint circular block bootstrap preserves cross-asset dependence.

    Zero drift baseline, current holdings held fixed, one-off spatial price shock
    spread across the horizon. Historical sample means are intentionally removed.
    """
    r = np.asarray(returns, dtype=float)
    if not np.isfinite(r).all() or np.any(r <= -1):
        raise ValueError("invalid return range: inspect prices and corporate actions")
    values = np.asarray(values, dtype=float)
    centered = np.log1p(r) - np.log1p(r).mean(axis=0)
    rng = np.random.default_rng(seed)
    block = min(5, len(r))
    starts = rng.integers(0, len(r), size=(paths, (steps + block - 1) // block))
    indices = ((starts[..., None] + np.arange(block)) % len(r)).reshape(paths, -1)[:, :steps]
    draws = centered[indices]
    stress = np.log1p(np.clip(np.asarray(shocks), -0.95, 1.0)) / steps
    with np.errstate(over="raise", invalid="raise"):
        try:
            return _summarize(draws, stress, values, cash, steps, paths, interval_seconds, seed, block)
        except FloatingPointError as exc:
            raise ValueError("numerical overflow: inspect price units and corporate actions") from exc


def _summarize(draws, stress, values, cash, steps, paths, interval_seconds, seed, block):
    baseline = (np.exp(np.cumsum(draws, axis=1)) * values).sum(axis=2) + cash
    scenario = (np.exp(np.cumsum(draws + stress, axis=1)) * values).sum(axis=2) + cash
    current = float(values.sum() + cash)

    def bands(samples):
        q = np.quantile(samples, [0.05, 0.5, 0.95], axis=0)
        return [{"step": 0, "p05": current, "p50": current, "p95": current}] + [
            {"step": i + 1, "p05": float(q[0, i]), "p50": float(q[1, i]), "p95": float(q[2, i])}
            for i in range(steps)
        ]

    losses = current - scenario[:, -1]
    var = float(np.quantile(losses, 0.95))
    return {
        "method": "joint-circular-block-bootstrap-zero-log-drift",
        "seed": seed,
        "paths": paths,
        "block_length": block,
        "horizon_seconds": steps * interval_seconds,
        "baseline": bands(baseline),
        "spatial_scenario": bands(scenario),
        "scenario_loss_probability": float(np.mean(scenario[:, -1] < current)),
        "scenario_var95_usd": var,
        "scenario_expected_shortfall95_usd": float(losses[losses >= var].mean()),
        "assumptions": [
            "Fixed long-only units; cash earns zero; no fees, taxes, financing or liquidity costs.",
            "Spatial shock is a user assumption applied once over the horizon, clipped to [-95%, +100%].",
            "Empirical 5/50/95 percentiles are scenario bands, not calibrated confidence intervals.",
            "Zero log drift; short-window returns do not establish expected growth.",
            "Hedge is indicative and is not applied to these portfolio paths.",
        ],
    }
