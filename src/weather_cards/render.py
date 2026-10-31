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


def forecast_time_label(timestamp, timezone):
    """Only suffix an ambiguous autumn wall-clock hour; selection stays unchanged."""
    local = datetime.fromtimestamp(timestamp, timezone)
    wall = local.replace(tzinfo=None)
    first, second = (
        wall.replace(tzinfo=timezone, fold=0),
        wall.replace(tzinfo=timezone, fold=1),
    )
    ambiguous = first.utcoffset() != second.utcoffset()
    return local.strftime("%H:%M %Z" if ambiguous else "%H:%M")


def render(cfg, obj, now, offline=False, forced_theme=None, *, audit=None):
    """Render one complete card. Optional audit records actual ink/layout bounds.

    The audit is used by visual geometry tests; it does not change saved images.
    """
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

    def text(
        x, y, value, size=44, fill="white", *, width=1720, center=False, role="text"
    ):
        # Fit only exceptional long strings/custom fonts; core forecast sizes are
        # fixed for normal supported values. Measure real ink, not nominal ems.
        chosen = font(size)
        while chosen.getbbox(value, anchor="lt")[2] > width and size > 20:
            size -= 1
            chosen = font(size)
        box = chosen.getbbox(value, anchor="lt")
        if center:
            x -= (box[2] - box[0]) / 2
        d.text((x, y), value, font=chosen, fill=fill, anchor="lt")
        if audit is not None:
            audit.append(
                dict(
                    role=role,
                    text=value,
                    size=size,
                    box=(x + box[0], y + box[1], x + box[2], y + box[3]),
                )
            )

    def symbol(x, y, size, weather, role):
        icon(d, x, y, size, weather, accent)
        if audit is not None:
            audit.append(dict(role=role, box=(x, y, x + size, y + size)))

    text(100, 70, cfg.location, 48, width=1360, role="location")
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
        137,
        f"{weekdays[local.weekday()]} {local.day} {months[local.month - 1]}",
        38,
        "#d9e4ed",
        width=1360,
        role="date",
    )
    text(1540, 70, f"{local:%H:%M}", 66, width=250, role="clock")
    warn = offline or age > cfg.stale_minutes or not usable
    if warn:
        d.ellipse((1812, 76, 1848, 112), fill="#ff525f")
        if audit is not None:
            audit.append(dict(role="offline-dot", box=(1812, 76, 1848, 112)))
    if not data:
        symbol(1360, 280, 360, "overcast", "unavailable-icon")
        text(100, 350, "Weather temporarily", 80, width=1180)
        text(100, 460, "unavailable", 96, width=1180)
        text(105, 640, "We’ll try again automatically.", 48, width=1180)
        text(105, 720, "No recent forecast available.", 44, "#d9e4ed", width=1180)
    else:
        mode = layout(cfg, data)
        text(
            94,
            225,
            f"{c['temperature_2m']:.0f}°",
            235,
            width=1100,
            role="current-temperature",
        )
        text(108, 435, CODES[c["weather_code"]], 58, width=1110, role="condition")
        text(
            108,
            515,
            f"Feels like {c['apparent_temperature']:.0f}°",
            44,
            "#d9e4ed",
            width=1110,
            role="feels-like",
        )
        symbol(1300, 210, 350, kind, "current-icon")
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
                580,
                f"High {daily['temperature_2m_max'][idx]:.0f}°    Low {daily['temperature_2m_min'][idx]:.0f}°",
                44,
                width=1110,
                role="high-low",
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
                    1280,
                    580,
                    f"{label.title()}  {datetime.fromtimestamp(t, tz):%H:%M}",
                    44,
                    width=540,
                    role="solar",
                )
        if mode == "detailed":
            # Four useful metrics with room-sized values. Pressure remains in
            # validated/cache data; omit it from the card to avoid a fifth column.
            items = [
                ("WIND", f"{c['wind_speed_10m']:.0f} mph"),
                ("GUSTS", f"{c['wind_gusts_10m']:.0f} mph"),
                ("RAIN", f"{c['precipitation']:.1f} mm"),
                ("HUMIDITY", f"{c['relative_humidity_2m']:.0f}%"),
            ]
            for i, (label, value) in enumerate(items):
                x = 110 + i * 435
                text(x, 635, label, 36, "#d9e4ed", width=400, role="metric-label")
                text(x, 682, value, 48, width=400, role="metric-value")
        ps = periods(data, now)
        divider = 735 if mode == "detailed" else 665
        d.line((100, divider, 1820, divider), fill="#6e879c", width=1)
        if not ps:
            text(
                108,
                850,
                "Future forecast not available in saved data",
                48,
                role="forecast-unavailable",
            )
        for i, period in enumerate(ps):
            center = 310 + i * 435
            text(
                center,
                755 if mode == "detailed" else 700,
                forecast_time_label(period["time"], tz),
                72,
                width=410,
                center=True,
                role=f"forecast-{i}-time",
            )
            icon_size = 160 if mode == "detailed" else 180
            symbol(
                center - icon_size / 2,
                825 if mode == "detailed" else 800,
                icon_size,
                theme(period["weather_code"], period["is_day"]),
                f"forecast-{i}-icon",
            )
            text(
                center,
                990,
                f"{period['temperature_2m']:.0f}°",
                112,
                width=410,
                center=True,
                role=f"forecast-{i}-temperature",
            )
            # Wet hours warrant a large probability. Dry, low-risk hours need no
            # repeated description/probability beneath an already clear icon.
            if period["precipitation_probability"] >= 20 or period["weather_code"] in (
                51,
                53,
                55,
                56,
                57,
                61,
                63,
                65,
                66,
                67,
                71,
                73,
                75,
                77,
                80,
                81,
                82,
                85,
                86,
                95,
                96,
                99,
            ):
                probability_label = (
                    "Precip"
                    if period["weather_code"]
                    in (56, 57, 66, 67, 71, 73, 75, 77, 85, 86)
                    else "Rain"
                )
                text(
                    center,
                    1080,
                    f"{probability_label} {period['precipitation_probability']:.0f}%",
                    48,
                    "#d9e4ed",
                    width=410,
                    center=True,
                    role=f"forecast-{i}-precipitation",
                )
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
    text(100, 1146, status, 44, "#e6edf3", width=1250, role="status")
    text(
        1420,
        1142,
        "Open-Meteo / Met Office",
        22,
        "#c0d3e0",
        width=400,
        role="attribution",
    )
    text(1420, 1172, "CC BY-SA", 20, "#c0d3e0", width=400, role="licence")
    return im
