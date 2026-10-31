import math
import random
from datetime import datetime
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

from .weather import CODES, layout, periods, theme

PALETTES = {
    "sunny": ("#176f9a", "#082b51", "#ffd985"),
    "partly-cloudy": ("#397d9e", "#183752", "#ffe0a0"),
    "overcast": ("#536e82", "#24364a", "#d0dce5"),
    "rain": ("#355d76", "#132b42", "#a8d7eb"),
    "heavy-rain": ("#284c66", "#101e35", "#9ccbe7"),
    "thunderstorm": ("#414365", "#161b31", "#f4d99c"),
    "snow": ("#557e98", "#233e5a", "#e5f5ff"),
    "fog": ("#687f8b", "#354958", "#e1e8e7"),
    "clear-night": ("#142b52", "#080f25", "#e8dcae"),
    "cloudy-night": ("#293c57", "#0b1429", "#b5cce0"),
}


def icon(draw, x, y, s, kind, accent):
    def ellipse(box, fill):
        draw.ellipse(tuple(int(v) for v in box), fill=fill)

    if kind in ("sunny", "partly-cloudy"):
        cx, cy = x + s * 0.46, y + s * 0.40
        r = s * 0.24
        for i in range(12):
            a = i * math.pi / 6
            draw.line(
                (
                    cx + math.cos(a) * r * 1.25,
                    cy + math.sin(a) * r * 1.25,
                    cx + math.cos(a) * r * 1.55,
                    cy + math.sin(a) * r * 1.55,
                ),
                fill=accent,
                width=max(2, int(s * 0.025)),
            )
        ellipse((cx - r, cy - r, cx + r, cy + r), accent)
    if kind == "clear-night":
        ellipse((x + s * 0.2, y + s * 0.1, x + s * 0.85, y + s * 0.75), accent)
        ellipse((x + s * 0.4, y, x + s * 0.95, y + s * 0.55), "#142b52")
    if kind not in ("sunny", "clear-night"):
        col = "#d7e5ec" if kind not in ("thunderstorm", "heavy-rain") else "#879eaf"
        for a, b, r in ((0.3, 0.48, 0.18), (0.48, 0.35, 0.23), (0.68, 0.47, 0.19)):
            ellipse(
                (x + s * (a - r), y + s * (b - r), x + s * (a + r), y + s * (b + r)),
                col,
            )
        draw.rounded_rectangle(
            (x + s * 0.17, y + s * 0.44, x + s * 0.82, y + s * 0.66),
            radius=int(s * 0.10),
            fill=col,
        )
        if kind in ("rain", "heavy-rain", "cloudy-night"):
            for i in range(3 if kind != "heavy-rain" else 5):
                a = x + s * (0.25 + i * 0.12)
                draw.line(
                    (a, y + s * 0.76, a - s * 0.04, y + s * 0.88),
                    fill=accent,
                    width=max(2, int(s * 0.025)),
                )
        if kind == "thunderstorm":
            draw.polygon(
                [
                    (x + s * 0.52, y + s * 0.65),
                    (x + s * 0.36, y + s * 0.86),
                    (x + s * 0.51, y + s * 0.83),
                    (x + s * 0.45, y + s),
                    (x + s * 0.68, y + s * 0.73),
                    (x + s * 0.53, y + s * 0.76),
                ],
                fill=accent,
            )
        if kind == "snow":
            for i in range(3):
                a = x + s * (0.3 + i * 0.2)
                b = y + s * 0.83
                for ang in (0, math.pi / 3, 2 * math.pi / 3):
                    draw.line(
                        (
                            a - math.cos(ang) * s * 0.055,
                            b - math.sin(ang) * s * 0.055,
                            a + math.cos(ang) * s * 0.055,
                            b + math.sin(ang) * s * 0.055,
                        ),
                        fill=accent,
                        width=3,
                    )
        if kind == "fog":
            for i in range(3):
                draw.line(
                    (
                        x + s * 0.1,
                        y + s * (0.74 + i * 0.08),
                        x + s * 0.9,
                        y + s * (0.74 + i * 0.08),
                    ),
                    fill=accent,
                    width=max(2, int(s * 0.025)),
                )


def render(cfg, obj, now, offline=False, forced_theme=None):
    tz = ZoneInfo(cfg.timezone)
    local = now.astimezone(tz)
    age = (now.timestamp() - obj["retrieved"]) / 60 if obj else float("inf")
    usable = (
        obj is not None
        and age <= cfg.expire_minutes
        and obj["valid_until"] > now.timestamp()
    )
    data = obj["data"] if usable else None
    c = data["current"] if data else None
    day = c["is_day"] if c else 1
    if data:
        for rise, setting in zip(data["daily"]["sunrise"], data["daily"]["sunset"]):
            if datetime.fromtimestamp(rise, tz).date() == local.date():
                day = int(rise <= now.timestamp() < setting)
    kind = forced_theme or (theme(c["weather_code"], day) if c else "overcast")
    top, bottom, accent = PALETTES[kind]
    im = Image.new("RGB", (1920, 1200))
    d = ImageDraw.Draw(im)
    from PIL import ImageColor

    a, b = map(ImageColor.getrgb, (top, bottom))
    for y in range(1200):
        d.line(
            (0, y, 1920, y),
            fill=tuple(int(a[i] + (b[i] - a[i]) * y / 1199) for i in range(3)),
        )
    rng = random.Random(42)
    if kind == "clear-night":
        for _ in range(80):
            x, y = rng.randrange(900, 1880), rng.randrange(50, 720)
            r = rng.choice((1, 1, 2))
            d.ellipse((x, y, x + r, y + r), fill="#9caecb")
    if kind in ("rain", "heavy-rain", "cloudy-night"):
        for _ in range(50):
            x, y = rng.randrange(1100, 1900), rng.randrange(170, 720)
            d.line((x, y, x - 8, y + 32), fill="#49677d", width=2)

    def font(size):
        try:
            return ImageFont.truetype(cfg.font, size)
        except OSError:
            return ImageFont.load_default(size=size)

    def text(x, y, s, size=38, fill="white"):
        d.text((x, y), s, font=font(size), fill=fill)

    text(100, 66, cfg.location, 46)
    weekdays = (
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    )
    months = (
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    )
    text(
        100,
        132,
        f"{weekdays[local.weekday()]} {local.day} {months[local.month - 1]}",
        30,
        "#d9e4ed",
    )
    text(1560, 70, f"{local:%H:%M}", 54)
    warn = offline or age > cfg.stale_minutes or not usable
    if warn:
        d.ellipse((1818, 82, 1842, 106), fill="#ff525f")
    if not data:
        icon(d, 1320, 270, 360, "overcast", accent)
        text(100, 350, "Weather temporarily", 76)
        text(100, 450, "unavailable", 92)
        text(105, 620, "We’ll try again automatically.", 40, "#d9e4ed")
        text(105, 700, "No recent forecast available.", 34, "#d9e4ed")
    else:
        mode = layout(cfg, data)
        text(94, 218, f"{c['temperature_2m']:.0f}°", 235)
        text(108, 495, CODES[c["weather_code"]], 56)
        text(108, 575, f"Feels like {c['apparent_temperature']:.0f}°", 36, "#d9e4ed")
        icon(d, 1270, 230, 390, kind, accent)
        daily = data["daily"]
        idx = next(
            (
                i
                for i, t in enumerate(daily["time"])
                if datetime.fromtimestamp(t, tz).date() == local.date()
            ),
            None,
        )
        if idx is not None:
            text(
                108,
                640,
                f"High {daily['temperature_2m_max'][idx]:.0f}°    Low {daily['temperature_2m_min'][idx]:.0f}°",
                34,
            )
            events = sorted(
                (t, k)
                for k in ("sunrise", "sunset")
                for t in daily[k]
                if t > now.timestamp()
            )
            if events:
                t, label = events[0]
                text(
                    1270,
                    655,
                    f"{label.title()}  {datetime.fromtimestamp(t, tz):%H:%M}",
                    34,
                )
        if mode == "detailed":
            items = [
                ("WIND", f"{c['wind_speed_10m']:.0f} mph"),
                ("GUSTS", f"{c['wind_gusts_10m']:.0f} mph"),
                ("HUMIDITY", f"{c['relative_humidity_2m']:.0f}%"),
                ("RAIN", f"{c['precipitation']:.1f} mm"),
                ("PRESSURE", f"{c['pressure_msl']:.0f} hPa"),
            ]
            for i, (label, value) in enumerate(items):
                text(110 + i * 350, 730, label, 22, "#c0d3e0")
                text(110 + i * 350, 766, value, 34)
        ps = periods(data, now)
        d.line((100, 850, 1820, 850), fill="#6e879c", width=1)
        if not ps:
            text(108, 925, "Future forecast not available in saved data", 38)
        for i, p in enumerate(ps):
            x = 110 + i * 435
            t = datetime.fromtimestamp(p["time"], tz)
            text(x, 880, f"{t:%H:%M %Z}", 30, "#c0d3e0")
            icon(d, x, 940, 95, theme(p["weather_code"], p["is_day"]), accent)
            text(x + 125, 930, f"{p['temperature_2m']:.0f}°", 60)
            text(x, 1040, CODES[p["weather_code"]], 27)
            text(x, 1082, f"Rain {p['precipitation_probability']:.0f}%", 27, "#c0d3e0")
    if obj:
        updated = datetime.fromtimestamp(obj["retrieved"], tz)
        prefix = (
            "Offline — last updated"
            if offline
            else "Stale — last updated"
            if age > cfg.stale_minutes
            else "Earlier forecast — updated"
            if age > cfg.fresh_minutes
            else "Updated"
        )
        status = f"{prefix} {updated:%d %b %H:%M %Z}"
    else:
        status = "Offline — awaiting first forecast"
    text(100, 1150, status, 23, "#d1dce6")
    text(1270, 1150, "Open-Meteo / Met Office · CC BY-SA", 21, "#c0d3e0")
    return im
