# Model methodology and research limits

## Portfolio and hedge

Value is `V_t = cash + Σ units_i × price_i,t`. Historical portfolio returns are reconstructed with the same fixed units and constant cash. Returns are simple returns at a fixed configured cadence. This naturally allows weights to change with prices and avoids assuming a continuously rebalanced portfolio.

The C++ kernel uses centered online covariance sums for an OLS slope with intercept. `h = S_xy / S_xx`, where x is hedge return and y portfolio return. This minimizes in-window variance of `r_p - h r_h`. The result reports intercept, R², residual standard deviation with n−2 degrees of freedom and sample count. Hedge variance ≤1e−20 is treated as degenerate. Ratios are not clipped; large ratios are evidence of unstable/unusable estimates, not an authorization to lever a portfolio. No hedge transaction is executed. Spot units-to-short assumes a unit multiplier of one.

Single hedge is the current scope. Multiple instruments require covariance regularization, hedge constraints and realistic financing/turnover costs. C++ work per frame is O(window) for OLS and O(events×exposures) for distances; it is not a constant-time tick engine.

## Geographic/economic transmission

For exposure j and event e:

`impact_j,e_bps = assumed_shock_e_bps × exp(−great_circle_km / radius_e) × 2^(−age_hours / half_life_e)`.

Asset shock is the exposure-share-weighted sum across matching sectors and known events, divided by 10,000. Exposures can cover less than 100%; uncovered shares contribute zero. Negative bps denote adverse shocks. Duplicate economic risks across multiple event reports are not automatically deconflicted.

A region's stress is the unweighted mean of its configured sector stresses. The economic index is the sum of region stress times caller-supplied economic weights; uncovered weight contributes zero, and weights are not renormalized. It is a scenario index, **not percent GDP, measured output loss, or a causally identified effect**. Regional representative points approximate geography; no polygon intersections, input-output network, satellite imagery analysis or supply-chain graph is included.

USGS observed events have zero shock by default. Calibrating a shock requires historical event studies, sector/geography exposure data and leakage-safe validation. Earthquake magnitude alone does not determine economic damage.

## Portfolio scenarios

Convert aligned asset returns to log returns, subtract each asset's window log mean, and sample joint rows in circular five-observation blocks. Blocks retain short within-block temporal patterns and simultaneous cross-asset dependence but not long regime dynamics. A fixed seed stabilizes snapshots and makes model output reproducible conditional on identical inputs.

Simulate fixed current holdings with zero interest on cash. Baseline log drift is zero; this does not imply zero arithmetic expected return because of compounding. The assumed asset shock is clipped to [−95%, +100%], converted to a log shock, and spread once across the horizon. It is not repeated as a full shock at every step. The spatial scenario reuses the baseline draws, isolating the assumed spatial perturbation. The indicative hedge is not applied to these paths.

Quantiles are empirical 5th, 50th and 95th percentiles. Scenario VaR is the 95th percentile of `current_value − terminal_value`; expected shortfall averages losses at or beyond that threshold. A negative VaR represents a gain at the threshold and is not forcibly set to zero. These are model-conditional statistics, not calibrated probabilities of real outcomes. Costs, bid/ask spread, taxes, financing, liquidity, structural breaks and extreme unseen events are excluded.

## Validation performed and required

Automated tests compare C++ slope/intercept with NumPy least squares, check lower in-sample hedged variance, known geographic distances, temporal exclusion and half-life behavior, reproducibility, joint sampling dependence, schema/API behavior, stale data, gap resets and zero-variance guards. These tests validate implementation, **not investment performance**.

Before using any forecasts for decisions:

1. Acquire properly licensed point-in-time prices, asset-level exposures and macro/event data with release and revision timestamps.
2. Replay strictly in information-arrival order, using only past windows. Fit impact coefficients on training data and freeze them for each test interval.
3. Evaluate rolling out-of-sample median errors and 90% band coverage at fixed horizons against no-change, volatility-only and no-spatial baselines.
4. Evaluate hedged realized variance, turnover, borrowing and transaction costs, drawdowns and stability by regime.
5. Report uncertainty across independent periods; use block-aware inference for overlapping horizons and avoid cherry-picked events.

No walk-forward performance results or causal validation are claimed by this repository.
