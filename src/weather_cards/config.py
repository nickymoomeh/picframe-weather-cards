import math
import tomllib
from dataclasses import asdict, dataclass
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo


@dataclass
class Config:
    location: str = "Saltwood, Kent"
    latitude: float = 51.080
    longitude: float = 1.085
    timezone: str = "Europe/London"
    layout: str = "automatic"
    output: str = "/home/pi4/FrameCards/weather.png"
    state_dir: str = "~/.local/state/weather-card"
    api_url: str = "http://localhost:9000/api/command"
    queue_enabled: bool = True
    duration: int = 30
    refresh_minutes: int = 30
    queue_minutes: int = 60
    fresh_minutes: int = 60
    stale_minutes: int = 180
    expire_minutes: int = 720
    window_start: str = "07:00"
    window_end: str = "20:30"
    model: str = "ukmo_seamless"
    font: str = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

    def validate(self):
        defaults = asdict(Config())
        for k, v in asdict(self).items():
            expected = type(defaults[k])
            if expected is float:
                if (
                    isinstance(v, bool)
                    or not isinstance(v, (int, float))
                    or not math.isfinite(v)
                ):
                    raise ValueError(k)
            elif type(v) is not expected:
                raise ValueError(f"Invalid type: {k}")
        if not -90 <= self.latitude <= 90 or not -180 <= self.longitude <= 180:
            raise ValueError("Coordinates")
        ZoneInfo(self.timezone)
        if self.layout not in ("minimal", "detailed", "automatic"):
            raise ValueError("layout")
        if not 1 <= self.duration <= 3600:
            raise ValueError("duration")
        if min(self.refresh_minutes, self.queue_minutes, self.fresh_minutes) <= 0:
            raise ValueError("Intervals")
        if not self.fresh_minutes < self.stale_minutes < self.expire_minutes:
            raise ValueError("Freshness thresholds")
        for v in (self.window_start, self.window_end):
            time.fromisoformat(v)
        if not Path(self.output).is_absolute():
            raise ValueError("output must be absolute")
        if len(self.location) > 40 or not self.location.strip():
            raise ValueError("location: 1–40 characters")
        if not self.api_url.startswith(("http://", "https://")):
            raise ValueError("api_url")
        return self

    @property
    def state(self):
        return Path(self.state_dir).expanduser()


def load(path):
    with open(path, "rb") as f:
        return Config(**tomllib.load(f)).validate()


def in_window(cfg, now):
    t = now.astimezone(ZoneInfo(cfg.timezone)).time().replace(tzinfo=None)
    start, end = map(time.fromisoformat, (cfg.window_start, cfg.window_end))
    return (
        start <= t < end
        if start < end
        else (t >= start or t < end)
        if start > end
        else True
    )
