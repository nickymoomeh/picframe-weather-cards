"""Scheduled snapshots use a current clock without another weather request."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
from PIL import Image, ImageChops

from weather_cards import client, service
from weather_cards.config import Config
from weather_cards.render import render
from weather_cards.sample import sample
from weather_cards.storage import cached, read_json, save_json, store


@pytest.fixture
def cfg(tmp_path):
    return Config(
        output=str(tmp_path / "cards/weather.png"),
        state_dir=str(tmp_path / "state"),
        window_start="00:00",
        window_end="00:00",
    )


@pytest.fixture
def retrieved():
    return datetime(2026, 10, 31, 9, 1, tzinfo=UTC)


def seed(cfg, retrieved):
    obj = store(cfg, sample(retrieved, "sunny"), retrieved)
    save_json(cfg.state / "forecast-status.json", {"offline": False})
    # Use the production atomic publication path for the original card.
    service.render_cached(cfg, retrieved)
    return obj


def scheduled_tick(cfg, now, monkeypatch, *, started=None):
    clock = Mock()
    clock.now.return_value = now
    monkeypatch.setattr(service, "datetime", clock)
    service.tick(cfg, started or now)
    clock.now.assert_called_once_with(UTC)


def no_fetch(monkeypatch):
    fetch = Mock(side_effect=AssertionError("Queue rendering must not fetch weather"))
    post = Mock()
    monkeypatch.setattr(client, "fetch", fetch)
    monkeypatch.setattr(client, "request_json", post)
    return fetch, post


def test_due_queue_renders_clock_and_snapshots_new_image(cfg, retrieved, monkeypatch):
    obj = seed(cfg, retrieved)
    old_image = Path(cfg.output).read_bytes()
    original_cache = (cfg.state / "cache.json").read_bytes()
    queue_time = retrieved + timedelta(minutes=19)
    save_json(cfg.state / "schedule.json", {"refresh": retrieved.timestamp()})
    fetch, post = no_fetch(monkeypatch)
    audited = []
    real_render = service.render

    def inspect(*args, **kwargs):
        return real_render(*args, **kwargs, audit=audited)

    monkeypatch.setattr(service, "render", inspect)
    scheduled_tick(cfg, queue_time, monkeypatch)

    fetch.assert_not_called()
    post.assert_called_once()
    assert post.call_args.args[0] == cfg.api_url
    payload = post.call_args.args[1]
    snapshot = Path(payload["path"])
    assert snapshot != Path(cfg.output)
    assert snapshot.read_bytes() == Path(cfg.output).read_bytes() != old_image
    assert next(a["text"] for a in audited if a["role"] == "clock") == "09:20"
    assert (
        next(a["text"] for a in audited if a["role"] == "status")
        == "Updated 31 Oct 09:01 GMT"
    )
    assert (cfg.state / "cache.json").read_bytes() == original_cache
    assert read_json(cfg.state / "schedule.json")["refresh"] == retrieved.timestamp()
    with Image.open(snapshot) as actual:
        assert (
            ImageChops.difference(actual, render(cfg, obj, queue_time)).getbbox()
            is None
        )


def test_fetch_due_once_and_clock_sampled_after_fetch(cfg, retrieved, monkeypatch):
    started = retrieved + timedelta(minutes=30)
    queued = started + timedelta(minutes=1)
    seed(cfg, retrieved)
    save_json(cfg.state / "schedule.json", {"refresh": retrieved.timestamp()})
    fetch = Mock(return_value=sample(started, "sunny"))
    post = Mock()
    monkeypatch.setattr(client, "fetch", fetch)
    monkeypatch.setattr(client, "request_json", post)
    spy = Mock(wraps=service.render)
    monkeypatch.setattr(service, "render", spy)

    scheduled_tick(cfg, queued, monkeypatch, started=started)

    fetch.assert_called_once_with(cfg, started)
    assert spy.call_count == 2  # scheduled refresh, then cache-only queue render
    assert spy.call_args.args[2] == queued
    assert spy.call_args.args[1]["retrieved"] == started.timestamp()
    assert read_json(cfg.state / "schedule.json")["refresh"] == started.timestamp()
    post.assert_called_once()


@pytest.mark.parametrize(
    "age,expected",
    [(20, "Updated"), (120, "Earlier forecast"), (240, "Stale"), (721, "Stale")],
)
def test_cached_age_and_expiry_at_queue_time(
    cfg, retrieved, monkeypatch, age, expected
):
    seed(cfg, retrieved)
    now = retrieved + timedelta(minutes=age)
    # Forecast work was checked recently; this tick is queue-only.
    save_json(cfg.state / "schedule.json", {"refresh": now.timestamp()})
    fetch, post = no_fetch(monkeypatch)
    audit = []
    real_render = service.render
    monkeypatch.setattr(
        service, "render", lambda *a, **kw: real_render(*a, **kw, audit=audit)
    )
    scheduled_tick(cfg, now, monkeypatch)
    fetch.assert_not_called()
    assert next(a["text"] for a in audit if a["role"] == "status").startswith(expected)
    assert any(a["role"] == "current-temperature" for a in audit) == (
        age <= cfg.expire_minutes
    )
    assert cached(cfg, now)["retrieved"] == retrieved.timestamp()
    if age > cfg.stale_minutes:
        with Image.open(post.call_args.args[1]["path"]) as image:
            assert image.getpixel((1830, 94)) == (255, 82, 95)


def test_offline_failure_survives_queue_rerender_and_recovery(
    cfg, retrieved, monkeypatch
):
    seed(cfg, retrieved)
    failed_at = retrieved + timedelta(minutes=30)
    monkeypatch.setattr(client, "fetch", Mock(side_effect=ValueError("outage")))
    service.generate(cfg, failed_at)
    assert read_json(cfg.state / "forecast-status.json") == {"offline": True}
    queue_time = failed_at + timedelta(minutes=10)
    save_json(cfg.state / "schedule.json", {"refresh": failed_at.timestamp()})
    fetch, post = no_fetch(monkeypatch)
    spy = Mock(wraps=service.render)
    monkeypatch.setattr(service, "render", spy)
    scheduled_tick(cfg, queue_time, monkeypatch)
    fetch.assert_not_called()
    assert spy.call_args.kwargs["offline"] is True
    assert spy.call_args.args[1]["retrieved"] == retrieved.timestamp()
    with Image.open(post.call_args.args[1]["path"]) as image:
        assert image.getpixel((1830, 94)) == (255, 82, 95)

    recovered = queue_time + timedelta(minutes=30)
    monkeypatch.setattr(client, "fetch", Mock(return_value=sample(recovered, "sunny")))
    service.generate(cfg, recovered)
    assert read_json(cfg.state / "forecast-status.json") == {"offline": False}
    spy.reset_mock()
    assert service.queue(cfg, recovered + timedelta(hours=1), refresh_image=True)
    assert spy.call_args.kwargs["offline"] is False


@pytest.mark.parametrize("broken", ["missing", "corrupt"])
def test_missing_cache_queues_unavailable_instead_of_old_weather(
    cfg, retrieved, monkeypatch, broken
):
    seed(cfg, retrieved)
    path = cfg.state / "cache.json"
    if broken == "missing":
        path.unlink()
    else:
        path.write_text("{broken")
    now = retrieved + timedelta(minutes=10)
    save_json(cfg.state / "schedule.json", {"refresh": now.timestamp()})
    fetch, post = no_fetch(monkeypatch)
    spy = Mock(wraps=service.render)
    monkeypatch.setattr(service, "render", spy)
    scheduled_tick(cfg, now, monkeypatch)
    fetch.assert_not_called()
    assert spy.call_args.args[1] is None
    with Image.open(post.call_args.args[1]["path"]) as image:
        assert image.getpixel((1830, 94)) == (255, 82, 95)
        assert ImageChops.difference(image, render(cfg, None, now)).getbbox() is None


@pytest.mark.parametrize("reason", ["interval", "window", "disabled"])
def test_skipped_queue_does_not_render_or_fetch(cfg, retrieved, monkeypatch, reason):
    seed(cfg, retrieved)
    now = retrieved + timedelta(minutes=10)
    save_json(cfg.state / "schedule.json", {"refresh": retrieved.timestamp()})
    if reason == "interval":
        save_json(cfg.state / "queue.json", {"attempt": retrieved.timestamp()})
    elif reason == "window":
        cfg.window_start, cfg.window_end = "12:00", "13:00"
    else:
        cfg.queue_enabled = False
    fetch, post = no_fetch(monkeypatch)
    spy = Mock(wraps=service.render)
    monkeypatch.setattr(service, "render", spy)
    monkeypatch.setattr(service, "datetime", Mock(now=Mock(return_value=now)))
    service.tick(cfg, now)
    spy.assert_not_called()
    fetch.assert_not_called()
    post.assert_not_called()


@pytest.mark.parametrize(
    "utc,local",
    [
        ("2026-03-29T00:30:00+00:00", "00:30"),
        ("2026-03-29T01:30:00+00:00", "02:30"),
        ("2026-10-25T00:30:00+00:00", "01:30"),
        ("2026-10-25T01:30:00+00:00", "01:30"),
    ],
)
def test_queue_clock_uses_london_dst(cfg, monkeypatch, utc, local):
    now = datetime.fromisoformat(utc)
    retrieved = now - timedelta(minutes=10)
    seed(cfg, retrieved)
    save_json(cfg.state / "schedule.json", {"refresh": retrieved.timestamp()})
    fetch, post = no_fetch(monkeypatch)
    audit = []
    real_render = service.render
    monkeypatch.setattr(
        service, "render", lambda *a, **kw: real_render(*a, **kw, audit=audit)
    )
    scheduled_tick(cfg, now, monkeypatch)
    fetch.assert_not_called()
    assert next(a["text"] for a in audit if a["role"] == "clock") == local
    post.assert_called_once()


def test_queue_rerender_failure_never_posts_partial_or_previous_card(
    cfg, retrieved, monkeypatch
):
    seed(cfg, retrieved)
    old = Path(cfg.output).read_bytes()
    no_fetch(monkeypatch)
    post = client.request_json
    image = Mock()

    def fail(f, **kwargs):
        f.write(b"partial PNG")
        raise OSError("disk full")

    image.save.side_effect = fail
    monkeypatch.setattr(service, "render", Mock(return_value=image))
    with pytest.raises(OSError, match="disk full"):
        service.queue(cfg, retrieved + timedelta(minutes=10), refresh_image=True)
    post.assert_not_called()
    assert Path(cfg.output).read_bytes() == old
    assert not list(Path(cfg.output).parent.glob("*.tmp"))


@pytest.mark.parametrize("failed", [False, True])
def test_existing_installation_without_forecast_status(
    cfg, retrieved, monkeypatch, failed
):
    seed(cfg, retrieved)
    (cfg.state / "forecast-status.json").unlink()
    last_attempt = retrieved + timedelta(minutes=5 if failed else 0)
    save_json(cfg.state / "schedule.json", {"refresh": last_attempt.timestamp()})
    fetch, post = no_fetch(monkeypatch)
    spy = Mock(wraps=service.render)
    monkeypatch.setattr(service, "render", spy)
    scheduled_tick(cfg, retrieved + timedelta(minutes=10), monkeypatch)
    fetch.assert_not_called()
    assert spy.call_args.kwargs["offline"] is failed
    post.assert_called_once()


def test_queue_interval_still_sixty_minutes(cfg, retrieved, monkeypatch):
    seed(cfg, retrieved)
    fetch, post = no_fetch(monkeypatch)
    spy = Mock(wraps=service.render)
    monkeypatch.setattr(service, "render", spy)
    assert service.queue(cfg, retrieved, refresh_image=True)
    assert not service.queue(cfg, retrieved + timedelta(minutes=59), refresh_image=True)
    assert service.queue(cfg, retrieved + timedelta(minutes=60), refresh_image=True)
    assert spy.call_count == post.call_count == 2
    fetch.assert_not_called()
