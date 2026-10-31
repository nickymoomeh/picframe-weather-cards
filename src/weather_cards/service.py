import fcntl
import hashlib
import logging
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from . import client
from .config import in_window
from .render import render
from .storage import atomic, cached, read_json, save_json, store

LOG = logging.getLogger(__name__)


@contextmanager
def lock(cfg):
    cfg.state.mkdir(parents=True, exist_ok=True)
    with (cfg.state / "lock").open("a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            LOG.info("Another execution is active")
            yield False
            return
        yield True


def generate(cfg, now, offline=False):
    obj = cached(cfg, now)
    failed = offline
    if not offline:
        try:
            obj = store(cfg, client.fetch(cfg, now), now)
        except (ValueError, OSError) as exc:
            failed = True
            LOG.warning("Using offline fallback: %s", exc)
    image = render(cfg, obj, now, failed)
    atomic(cfg.output, lambda f: image.save(f, format="PNG"))
    # Keep failure state separate from the last validated forecast. Re-rendering
    # cached data must neither erase an offline warning nor imply a new fetch.
    save_json(cfg.state / "forecast-status.json", dict(offline=failed))
    return obj


def render_cached(cfg, now):
    """Publish with the queue-time clock and original forecast/failure state."""
    obj = cached(cfg, now)
    status = read_json(cfg.state / "forecast-status.json") or {}
    offline = status.get("offline") is True
    if "offline" not in status and obj is not None:
        # Older installations only recorded scheduled attempts. An attempt newer
        # than the validated cache indicates the last scheduled fetch failed.
        last_attempt = (read_json(cfg.state / "schedule.json") or {}).get("refresh", 0)
        offline = (
            isinstance(last_attempt, (int, float)) and last_attempt > obj["retrieved"]
        )
    image = render(cfg, obj, now, offline=offline)
    atomic(cfg.output, lambda f: image.save(f, format="PNG"))


def queue(cfg, now, *, refresh_image=False):
    if not in_window(cfg, now):
        return False
    state = read_json(cfg.state / "queue.json") or {}
    # Persist before sending: ambiguous timeouts cannot cause repeated submissions.
    if 0 <= now.timestamp() - state.get("attempt", 0) < cfg.queue_minutes * 60:
        return False
    if refresh_image:
        render_cached(cfg, now)
    path = Path(cfg.output)
    if not path.is_file():
        LOG.warning("Generate an image before queueing")
        return False
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:20]
    snapshot = path.with_name(f"{path.stem}-queued-{digest}.png")
    if not snapshot.exists():
        atomic(snapshot, lambda f: f.write(path.read_bytes()))
    save_json(
        cfg.state / "queue.json",
        dict(attempt=now.timestamp(), path=str(snapshot), accepted=False),
    )
    try:
        client.request_json(
            cfg.api_url,
            dict(
                action="queue_card",
                path=str(snapshot),
                duration=cfg.duration,
                type="weather",
            ),
        )
    except (OSError, ValueError) as exc:
        LOG.warning("Queue failed; next attempt at next interval: %s", exc)
        return False
    save_json(
        cfg.state / "queue.json",
        dict(attempt=now.timestamp(), path=str(snapshot), accepted=True),
    )
    # Never remove the newest accepted snapshot. Older queued weather requests
    # have been replaced; a displayed card is already decoded by the frame.
    for old in path.parent.glob(f"{path.stem}-queued-*.png"):
        if old != snapshot and now.timestamp() - old.stat().st_mtime > 7 * 86400:
            old.unlink(missing_ok=True)
    return True


def tick(cfg, now):
    schedule = read_json(cfg.state / "schedule.json") or {}
    elapsed = now.timestamp() - schedule.get("refresh", 0)
    if (
        elapsed < 0
        or elapsed >= cfg.refresh_minutes * 60
        or not Path(cfg.output).exists()
    ):
        generate(cfg, now)
        save_json(cfg.state / "schedule.json", dict(refresh=now.timestamp()))
    if cfg.queue_enabled:
        # Read the clock after a potentially slow forecast request. Eligibility
        # and the cached render use this same instant, including local DST rules.
        queue(cfg, datetime.now(UTC), refresh_image=True)
