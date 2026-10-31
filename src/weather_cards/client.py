import json
import logging
import os
import time
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .weather import CURRENT, DAILY, HOURLY, validate

LOG = logging.getLogger(__name__)


def request_json(url, payload=None):
    body = None if payload is None else json.dumps(payload).encode()
    req = Request(
        url,
        data=body,
        headers={
            "User-Agent": "picframe-weather-cards/0.1",
            "Content-Type": "application/json",
        },
    )
    if payload is not None and os.environ.get("WEATHER_CARD_AUTHORIZATION"):
        req.add_header("Authorization", os.environ["WEATHER_CARD_AUTHORIZATION"])
    with urlopen(req, timeout=10) as response:
        raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("Response too large")
        if payload is not None:
            return None
        return json.loads(raw)


def fetch(cfg, now):
    params = dict(
        latitude=cfg.latitude,
        longitude=cfg.longitude,
        timezone=cfg.timezone,
        timeformat="unixtime",
        temperature_unit="celsius",
        wind_speed_unit="mph",
        precipitation_unit="mm",
        forecast_days=3,
        current=",".join(CURRENT),
        hourly=",".join(HOURLY),
        daily=",".join([*DAILY, "sunrise", "sunset"]),
    )
    for attempt, model in enumerate((cfg.model, "best_match")):
        try:
            data = validate(
                request_json(
                    "https://api.open-meteo.com/v1/forecast?"
                    + urlencode(params | {"models": model})
                )
            )
            if (
                abs(data["current"]["time"] - now.timestamp()) > 5400
                or data["hourly"]["time"][-1] < now.timestamp() + 12 * 3600
            ):
                raise ValueError("Response not current")
            return data
        except (URLError, OSError, ValueError) as exc:
            LOG.warning("Forecast attempt %s (%s) failed: %s", attempt + 1, model, exc)
            if attempt == 0:
                time.sleep(1)
    raise ValueError("Both forecast attempts failed")
