import json
import math
import os
import tempfile
from pathlib import Path

from .weather import validate


def atomic(path, writer):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".weather-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            writer(f)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def save_json(path, data):
    atomic(path, lambda f: f.write(json.dumps(data, allow_nan=False).encode()))


def read_json(path):
    try:
        if Path(path).stat().st_size > 2_000_000:
            return None
        value = json.loads(Path(path).read_text())
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def cached(cfg, now):
    obj = read_json(cfg.state / "cache.json")
    try:
        if obj["schema"] != 1 or obj["coordinates"] != [cfg.latitude, cfg.longitude]:
            return None
        if (
            isinstance(obj["retrieved"], bool)
            or not isinstance(obj["retrieved"], (int, float))
            or not math.isfinite(obj["retrieved"])
        ):
            return None
        if abs(obj["retrieved"] - obj["data"]["current"]["time"]) > 5400:
            return None
        age = now.timestamp() - obj["retrieved"]
        if not 0 <= age <= 30 * 86400:
            return None
        validate(obj["data"])
        if obj["valid_until"] != obj["data"]["hourly"]["time"][-1]:
            return None
        return obj
    except (KeyError, TypeError, ValueError):
        return None


def store(cfg, data, now):
    obj = dict(
        schema=1,
        coordinates=[cfg.latitude, cfg.longitude],
        retrieved=now.timestamp(),
        valid_until=data["hourly"]["time"][-1],
        data=data,
    )
    save_json(cfg.state / "cache.json", obj)
    return obj
