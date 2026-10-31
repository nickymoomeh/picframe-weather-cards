"""Geometry is checked against real font ink and conservative icon bounds."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from weather_cards.config import Config
from weather_cards.render import PALETTES, forecast_time_label, render
from weather_cards.sample import sample
from weather_cards.weather import CODES


def fonts():
    candidates = [
        os.environ.get("WEATHER_CARD_TEST_FONT", ""),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    available = [path for path in candidates if path and Path(path).is_file()]
    return list(dict.fromkeys(available)) + ["/missing-font-fallback.ttf"]


def overlaps(a, b):
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def assert_geometry(audit):
    for item in audit:
        left, top, right, bottom = item["box"]
        assert 0 <= left < right <= 1920, item
        assert 0 <= top < bottom <= 1200, item
        if (
            item["role"].startswith("forecast-")
            and item["role"] != "forecast-unavailable"
        ):
            column = int(item["role"].split("-")[1])
            assert 100 + 435 * column <= left and right <= 520 + 435 * column, item
    for i, a in enumerate(audit):
        for b in audit[i + 1 :]:
            assert not overlaps(a["box"], b["box"]), (a, b)


def fixture(kind="sunny"):
    now = datetime(2026, 10, 31, 9, 1, tzinfo=UTC)
    data = sample(now, kind)
    return now, dict(
        data=data, retrieved=now.timestamp(), valid_until=data["hourly"]["time"][-1]
    )


@pytest.mark.parametrize("font", fonts())
@pytest.mark.parametrize("mode", ["minimal", "detailed"])
@pytest.mark.parametrize("kind", PALETTES)
def test_all_themes_boundaries_and_overlap(font, mode, kind):
    now, obj = fixture(kind)
    audit = []
    render(Config(font=font, layout=mode), obj, now, forced_theme=kind, audit=audit)
    assert_geometry(audit)
    times = [a for a in audit if a["role"].endswith("-time")]
    temperatures = [
        a
        for a in audit
        if a["role"].startswith("forecast-") and a["role"].endswith("-temperature")
    ]
    assert len(times) == len(temperatures) == 4
    assert all(a["size"] == 72 for a in times)
    assert all(a["size"] == 112 for a in temperatures)
    assert all("GMT" not in a["text"] for a in times)


@pytest.mark.parametrize("font", fonts())
@pytest.mark.parametrize("mode", ["minimal", "detailed"])
def test_extreme_values_and_long_location(font, mode):
    now, obj = fixture("thunderstorm")
    audit = []
    data = obj["data"]
    data["current"].update(
        temperature_2m=-100,
        apparent_temperature=-120,
        wind_speed_10m=300,
        wind_gusts_10m=400,
        precipitation=500,
        relative_humidity_2m=100,
    )
    data["hourly"]["temperature_2m"] = [-100] * 72
    data["hourly"]["precipitation_probability"] = [100] * 72
    render(
        Config(font=font, layout=mode, location="W" * 40),
        obj,
        now,
        offline=True,
        audit=audit,
    )
    assert_geometry(audit)
    assert all(
        a["size"] == 112
        for a in audit
        if a["role"].startswith("forecast-") and a["role"].endswith("-temperature")
    )


@pytest.mark.parametrize("code", CODES)
def test_every_condition_description_fits(code):
    now, obj = fixture()
    audit = []
    obj["data"]["current"]["weather_code"] = code
    render(Config(), obj, now, audit=audit)
    assert_geometry(audit)


@pytest.mark.parametrize("font", fonts())
@pytest.mark.parametrize(
    "state", ["offline", "stale", "earlier", "expired", "none", "short", "exhausted"]
)
def test_warning_and_missing_forecasts(font, state):
    now, obj = fixture("rain")
    audit = []
    offline = False
    if state == "offline":
        offline = True
    if state == "stale":
        now += timedelta(hours=4)
    if state == "earlier":
        now += timedelta(hours=2)
    if state == "expired":
        now += timedelta(hours=13)
    if state == "none":
        obj = None
    if state == "short":
        h = obj["data"]["hourly"]
        for key in h:
            h[key] = h[key][:2]
    if state == "exhausted":
        h = obj["data"]["hourly"]
        for key in h:
            h[key] = h[key][:1]
    image = render(Config(font=font), obj, now, offline, audit=audit)
    assert_geometry(audit)
    status = next(a for a in audit if a["role"] == "status")
    assert status["size"] >= 38
    if state in ("offline", "stale", "expired", "none"):
        assert image.getpixel((1830, 94)) == (255, 82, 95)
    if state == "offline":
        assert "Offline — last updated 31 Oct 09:01 GMT" == status["text"]
    if state == "expired":
        assert not any(a["role"] == "current-temperature" for a in audit)
    if state == "short":
        assert sum(a["role"].endswith("-time") for a in audit) == 1
    if state == "exhausted":
        assert any(a["role"] == "forecast-unavailable" for a in audit)


def test_probability_only_when_useful():
    now, obj = fixture()
    audit = []
    h = obj["data"]["hourly"]
    h["precipitation_probability"][1] = 20
    render(Config(), obj, now, audit=audit)
    precip = [a for a in audit if a["role"].endswith("-precipitation")]
    assert (
        len(precip) == 1 and precip[0]["text"] == "Rain 20%" and precip[0]["size"] == 48
    )


def test_clock_change_labels_and_geometry():
    tz = ZoneInfo("Europe/London")
    first = datetime(2026, 10, 25, 0, tzinfo=UTC)
    second = datetime(2026, 10, 25, 1, tzinfo=UTC)
    assert forecast_time_label(first.timestamp(), tz) == "01:00 BST"
    assert forecast_time_label(second.timestamp(), tz) == "01:00 GMT"
    assert (
        forecast_time_label(datetime(2026, 7, 1, 12, tzinfo=UTC).timestamp(), tz)
        == "13:00"
    )
    assert (
        forecast_time_label(datetime(2026, 3, 29, 1, tzinfo=UTC).timestamp(), tz)
        == "02:00"
    )
    for font in fonts():
        now, obj = fixture()
        audit = []
        now = first - timedelta(minutes=1)
        obj["retrieved"] = now.timestamp()
        for i in range(72):
            obj["data"]["hourly"]["time"][i] = int(first.timestamp()) + i * 3600
        render(Config(font=font), obj, now, audit=audit)
        assert_geometry(audit)
        assert (
            next(a for a in audit if a["role"] == "forecast-0-time")["text"]
            == "01:00 BST"
        )


def test_snow_uses_precipitation_label():
    now, obj = fixture("snow")
    audit = []
    render(Config(), obj, now, audit=audit)
    labels = [a["text"] for a in audit if a["role"].endswith("-precipitation")]
    assert labels and all(value.startswith("Precip ") for value in labels)
