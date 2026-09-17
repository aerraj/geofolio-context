import json
import os
import secrets
from pathlib import Path

from .models import Portfolio


def default_portfolio():
    return Portfolio.model_validate(
        {
            "name": "Treasury research workspace",
            "hedge_symbol": "BTC-USD",
            "interval_seconds": 60,
            "window": 120,
            "min_samples": 20,
            "horizon_steps": 30,
            "paths": 1000,
            "cash_usd": 10000,
            "max_quote_age_seconds": 120,
            "positions": [{"symbol": "ETH-USD", "units": 2, "exposures": []}],
            "macro_countries": ["USA", "IND", "SGP"],
        }
    )


def initialize(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    credentials = path / "access.json"
    created = not credentials.exists()
    if created:
        fd = os.open(credentials, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as out:
            json.dump(
                {"admin": secrets.token_urlsafe(32), "viewer": secrets.token_urlsafe(32)}, out, indent=2
            )
    return json.loads(credentials.read_text()), created
