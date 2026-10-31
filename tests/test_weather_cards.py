import json
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

import pytest
from PIL import Image

from weather_cards import client, service
from weather_cards.cli import main
from weather_cards.config import Config, in_window
from weather_cards.render import PALETTES, render
from weather_cards.sample import sample
from weather_cards.storage import atomic, cached, store
from weather_cards.weather import CODES, layout, periods, theme, validate


@pytest.fixture
def now():
    return datetime(2026, 10, 31, 12, 30, tzinfo=UTC)


@pytest.fixture
def cfg(tmp_path):
    return Config(
        output=str(tmp_path / "cards/weather.png"), state_dir=str(tmp_path / "state")
    )


@pytest.fixture
def data(now):
    return sample(now, "rain")


def test_parse(data):
    assert validate(data) is data


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.pop("current"),
        lambda d: d["current"].update(temperature_2m=None),
        lambda d: d["current"].update(temperature_2m=float("nan")),
        lambda d: d["current"].update(is_day=0.5),
        lambda d: d["hourly"]["time"].reverse(),
        lambda d: d["hourly"]["temperature_2m"].pop(),
        lambda d: d["daily"]["sunset"].clear(),
        lambda d: d["daily"]["temperature_2m_min"].__setitem__(0, 60),
        lambda d: d["current"].update(weather_code=4),
        lambda d: d["current"].update(time=True),
    ],
)
def test_invalid(data, change):
    change(data)
    with pytest.raises(ValueError):
        validate(data)


@pytest.mark.parametrize("code", CODES)
def test_all_codes(code):
    assert theme(code, 1) in PALETTES and theme(code, 0) in (
        "clear-night",
        "cloudy-night",
    )


@pytest.mark.parametrize(
    "code,expected",
    [
        (0, "sunny"),
        (2, "partly-cloudy"),
        (3, "overcast"),
        (61, "rain"),
        (65, "heavy-rain"),
        (95, "thunderstorm"),
        (73, "snow"),
        (45, "fog"),
    ],
)
def test_mapping(code, expected):
    assert theme(code, 1) == expected


def test_periods(data, now):
    ps = periods(data, now)
    assert len(ps) == 4
    assert all(p["time"] > now.timestamp() for p in ps)
    assert all(b["time"] - a["time"] >= 10800 for a, b in zip(ps, ps[1:]))
    assert periods(data, now + timedelta(days=4)) == []


@pytest.mark.parametrize(
    "date,hour,zone",
    [
        ("2026-03-29T00:30:00+00:00", 0, "GMT"),
        ("2026-03-29T01:30:00+00:00", 2, "BST"),
        ("2026-10-25T00:30:00+00:00", 1, "BST"),
        ("2026-10-25T01:30:00+00:00", 1, "GMT"),
    ],
)
def test_dst(date, hour, zone):
    t = datetime.fromisoformat(date).astimezone(ZoneInfo("Europe/London"))
    assert (t.hour, t.tzname()) == (hour, zone)


def test_midnight_window(cfg, now):
    cfg.window_start = "20:30"
    cfg.window_end = "07:00"
    assert in_window(cfg, now.replace(hour=23))
    assert in_window(cfg, now.replace(hour=0))
    assert not in_window(cfg, now)


def test_cache(cfg, data, now):
    obj = store(cfg, data, now)
    assert cached(cfg, now) == obj
    cfg.latitude = 0
    assert cached(cfg, now) is None


def test_corrupt_cache(cfg, now):
    cfg.state.mkdir()
    (cfg.state / "cache.json").write_text("{")
    assert cached(cfg, now) is None


def test_bad_cache_timestamp(cfg, data, now):
    obj = store(cfg, data, now)
    obj["retrieved"] = float("nan")
    (cfg.state / "cache.json").write_text(json.dumps(obj))
    assert cached(cfg, now) is None


@pytest.mark.parametrize(
    "failure",
    [
        TimeoutError("timeout"),
        URLError("offline"),
        HTTPError("url", 503, "down", {}, None),
        ValueError("malformed"),
    ],
)
def test_fetch_failures(cfg, now, monkeypatch, failure):
    req = Mock(side_effect=failure)
    monkeypatch.setattr(client, "request_json", req)
    monkeypatch.setattr(client.time, "sleep", lambda _: None)
    with pytest.raises(ValueError):
        client.fetch(cfg, now)
    assert req.call_count == 2


def test_model_fallback(cfg, data, now, monkeypatch):
    req = Mock(side_effect=[ValueError("unsupported"), data])
    monkeypatch.setattr(client, "request_json", req)
    monkeypatch.setattr(client.time, "sleep", lambda _: None)
    assert client.fetch(cfg, now) == data
    assert "models=best_match" in req.call_args.args[0]
    assert "timezone=Europe%2FLondon" in req.call_args.args[0]


def test_outage_recovery(cfg, data, now, monkeypatch):
    monkeypatch.setattr(client, "fetch", Mock(return_value=data))
    service.generate(cfg, now)
    first = cached(cfg, now)["retrieved"]
    monkeypatch.setattr(client, "fetch", Mock(side_effect=ValueError("offline")))
    service.generate(cfg, now + timedelta(hours=1))
    assert cached(cfg, now + timedelta(hours=1))["retrieved"] == first
    im = Image.open(cfg.output)
    assert im.getpixel((1830, 94)) == (255, 82, 95)
    newer = now + timedelta(hours=2)
    monkeypatch.setattr(client, "fetch", Mock(return_value=sample(newer, "sunny")))
    service.generate(cfg, newer)
    assert cached(cfg, newer)["retrieved"] == newer.timestamp()
    assert Image.open(cfg.output).getpixel((1830, 94)) != (255, 82, 95)


@pytest.mark.parametrize(
    "minutes,red", [(0, False), (61, False), (181, True), (721, True)]
)
def test_freshness(cfg, data, now, minutes, red):
    obj = store(cfg, data, now)
    im = render(cfg, obj, now + timedelta(minutes=minutes))
    assert (im.getpixel((1830, 94)) == (255, 82, 95)) == red


def test_no_cache_offline(cfg, now, monkeypatch):
    monkeypatch.setattr(client, "fetch", Mock(side_effect=AssertionError("network")))
    assert service.generate(cfg, now, True) is None
    assert Image.open(cfg.output).size == (1920, 1200)


def test_atomic_failure(tmp_path):
    p = tmp_path / "image"
    p.write_bytes(b"old")

    def fail(f):
        f.write(b"partial")
        raise ValueError("failed")

    with pytest.raises(ValueError):
        atomic(p, fail)
    assert p.read_bytes() == b"old"
    assert list(tmp_path.iterdir()) == [p]


def test_atomic_publication(cfg, now):
    service.generate(cfg, now, True)
    with Image.open(cfg.output) as im:
        im.verify()
    assert not list(__import__("pathlib").Path(cfg.output).parent.glob("*.tmp"))


def test_queue_dedup_failure_and_snapshot(cfg, now, monkeypatch):
    service.generate(cfg, now, True)
    req = Mock(side_effect=URLError("offline"))
    monkeypatch.setattr(client, "request_json", req)
    assert not service.queue(cfg, now)
    assert not service.queue(cfg, now + timedelta(minutes=1))
    assert req.call_count == 1
    req.side_effect = None
    assert service.queue(cfg, now + timedelta(hours=1))
    payload = req.call_args.args[1]
    assert payload["type"] == "weather"
    assert payload["path"] != cfg.output
    original = __import__("pathlib").Path(payload["path"]).read_bytes()
    atomic(cfg.output, lambda f: f.write(b"changed"))
    assert __import__("pathlib").Path(payload["path"]).read_bytes() == original


def test_independent_schedules(cfg, now, monkeypatch):
    gen = Mock()
    q = Mock()
    monkeypatch.setattr(service, "generate", gen)
    monkeypatch.setattr(service, "queue", q)
    __import__("pathlib").Path(cfg.output).parent.mkdir()
    __import__("pathlib").Path(cfg.output).touch()
    service.tick(cfg, now)
    service.tick(cfg, now + timedelta(minutes=1))
    assert gen.call_count == 1 and q.call_count == 2


@pytest.mark.parametrize("kind", PALETTES)
@pytest.mark.parametrize("mode", ["minimal", "detailed"])
def test_render_all(cfg, now, kind, mode):
    cfg.layout = mode
    data = sample(now, kind)
    validate(data)
    im = render(
        cfg,
        dict(
            data=data, retrieved=now.timestamp(), valid_until=data["hourly"]["time"][-1]
        ),
        now,
        forced_theme=kind,
    )
    assert im.size == (1920, 1200) and im.mode == "RGB"


def test_layout(cfg, data):
    assert layout(cfg, data) == "detailed"
    data["current"]["precipitation"] = 0
    data["current"]["weather_code"] = 0
    assert layout(cfg, data) == "minimal"
    cfg.layout = "detailed"
    assert layout(cfg, data) == "detailed"


def test_preview_no_network(tmp_path, monkeypatch):
    monkeypatch.setattr(
        client, "request_json", Mock(side_effect=AssertionError("network"))
    )
    assert (
        main(["preview", "--theme", "rain", "--output", str(tmp_path / "p.png")]) == 0
    )


def test_config(cfg):
    cfg.validate()
    cfg.queue_minutes = 0
    with pytest.raises(ValueError):
        cfg.validate()


def test_http_transport_timeout_and_error(monkeypatch):
    monkeypatch.setattr(
        client, "urlopen", Mock(side_effect=TimeoutError("read timeout"))
    )
    with pytest.raises(TimeoutError):
        client.request_json("http://localhost/")
    monkeypatch.setattr(
        client, "urlopen", Mock(side_effect=HTTPError("u", 500, "failed", {}, None))
    )
    with pytest.raises(HTTPError):
        client.request_json("http://localhost/", {"action": "queue_card"})


def test_expired_hides_weather(cfg, data, now, monkeypatch):
    obj = store(cfg, data, now)
    # Capture text drawn, verifying unavailable rather than current values.
    import weather_cards.render as renderer

    original = renderer.ImageDraw.Draw
    labels = []

    def draw(*args, **kwargs):
        d = original(*args, **kwargs)
        text = d.text

        def spy(position, value, *a, **kw):
            labels.append(value)
            return text(position, value, *a, **kw)

        d.text = spy
        return d

    monkeypatch.setattr(renderer.ImageDraw, "Draw", draw)
    renderer.render(cfg, obj, now + timedelta(hours=13))
    assert "unavailable" in labels
    assert not any("Feels like" in value for value in labels)


def test_exclusion_lock(cfg):
    with service.lock(cfg) as first:
        assert first
        with service.lock(cfg) as second:
            assert not second


def test_snapshot_cleanup_retains_recent(cfg, now, monkeypatch):
    service.generate(cfg, now, True)
    monkeypatch.setattr(client, "request_json", Mock())
    folder = __import__("pathlib").Path(cfg.output).parent
    recent = folder / "weather-queued-recent.png"
    recent.write_bytes(b"keep")
    assert service.queue(cfg, now)
    assert recent.exists()
