import numpy as np
import pytest
from geofolio._core import haversine_km, hedge


def test_known_beta_and_numpy_reference():
    rng = np.random.default_rng(18)
    x = rng.normal(0, 0.01, 250)
    y = 1.7 * x + 0.0002 + rng.normal(0, 0.001, 250)
    result = hedge(y.tolist(), x.tolist())
    expected = np.linalg.lstsq(np.column_stack([np.ones(len(x)), x]), y, rcond=None)[0]
    assert result["ratio"] == pytest.approx(expected[1], rel=1e-12)
    assert result["intercept"] == pytest.approx(expected[0], abs=1e-14)
    assert np.var(y - result["ratio"] * x) < np.var(y)


@pytest.mark.parametrize(
    "y,x", [([1, 2], [1, 2]), ([1, 2, 3], [1, 1, 1]), ([1, 2, 3], [1, 2]), ([1, 2, float("nan")], [1, 2, 3])]
)
def test_invalid_returns(y, x):
    with pytest.raises(ValueError):
        hedge(y, x)


def test_distance():
    assert haversine_km(0, 0, 0, 0) == 0
    assert haversine_km(0, 0, 0, 180) == pytest.approx(20015.1144, rel=1e-7)
    assert haversine_km(40.7128, -74.006, 51.5074, -0.1278) == pytest.approx(5570.23, rel=1e-4)
    with pytest.raises(ValueError):
        haversine_km(100, 0, 0, 0)
