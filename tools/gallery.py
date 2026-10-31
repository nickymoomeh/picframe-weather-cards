"""Reproduce previews/comparisons; no HTTP, production state or config writes."""

import argparse
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

from baseline_render import render as baseline
from PIL import Image, ImageDraw, ImageFont

from weather_cards.config import Config
from weather_cards.render import PALETTES, render
from weather_cards.sample import sample

ROOT = Path(__file__).resolve().parents[1] / "gallery"


def fixture(kind):
    now = datetime(2026, 10, 31, 21 if "night" in kind else 9, 1, tzinfo=UTC)
    data = sample(now, kind)
    data["current"].update(
        temperature_2m=1 if kind == "snow" else 10,
        apparent_temperature=-2 if kind == "snow" else 8,
    )
    data["daily"]["temperature_2m_max"] = [3 if kind == "snow" else 13] * 3
    data["daily"]["temperature_2m_min"] = [-2 if kind == "snow" else 7] * 3
    temperatures = [1, 2, 1, 0] if kind == "snow" else [10, 12, 13, 10]
    for i in range(len(data["hourly"]["time"])):
        data["hourly"]["temperature_2m"][i] = temperatures[min(i // 3, 3)]
    if kind == "thunderstorm":
        data["current"].update(precipitation=4, wind_speed_10m=26, wind_gusts_10m=40)
        data["hourly"]["precipitation_probability"] = [85] * 72
    return now, dict(
        data=data, retrieved=now.timestamp(), valid_until=data["hourly"]["time"][-1]
    )


def contact(items, path, columns=2, width=480):
    height = width * 1200 // 1920
    rows = math.ceil(len(items) / columns)
    sheet = Image.new("RGB", (width * columns, (height + 40) * rows), "#0b1425")
    draw = ImageDraw.Draw(sheet)
    for i, (label, image) in enumerate(items):
        x = i % columns * width
        y = i // columns * (height + 40)
        sheet.paste(
            image.resize((width, height), Image.Resampling.LANCZOS), (x, y + 40)
        )
        draw.text(
            (x + 16, y + 10), label, fill="white", font=ImageFont.load_default(size=18)
        )
    sheet.save(path, quality=94)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", default=Config().font)
    args = parser.parse_args()
    ROOT.mkdir(exist_ok=True)
    thumbs = []
    for kind in PALETTES:
        for mode in ("minimal", "detailed"):
            now, obj = fixture(kind)
            cfg = Config(layout=mode, font=args.font)
            image = render(cfg, obj, now, forced_theme=kind)
            name = f"{kind}-{mode}.png"
            image.save(ROOT / name)
            thumbs.append((name, image))
    contact(thumbs, ROOT / "contact-sheet.jpg")
    for mode, kind in (("minimal", "sunny"), ("detailed", "rain")):
        now, obj = fixture(kind)
        cfg = Config(layout=mode, font=args.font)
        before = baseline(cfg, obj, now, forced_theme=kind)
        after = render(cfg, obj, now, forced_theme=kind)
        before.save(ROOT / f"comparison-{mode}-before.png")
        after.save(ROOT / f"comparison-{mode}-after.png")
        contact(
            [("Before · " + mode, before), ("After · " + mode, after)],
            ROOT / f"comparison-{mode}.jpg",
            width=960,
        )
    for label, age, offline in (
        ("offline", 0, True),
        ("stale", 4, False),
        ("unavailable", 13, False),
    ):
        now, obj = fixture("rain")
        render(
            Config(font=args.font), obj, now + timedelta(hours=age), offline=offline
        ).save(ROOT / f"{label}.png")
    write_assessment(args.font)
    (ROOT / "README.md").write_text(
        "# Distance-readable weather cards\n\n"
        "Synthetic illustrations, not the user's captured forecast. The minimal comparison recreates "
        "Saltwood at 09:01 on Saturday 31 October, 10°C and clear sky; other values are simulated. "
        "Both sides use identical data, time and font. Before is the renderer from `18b3de0`. "
        "Original icons/backgrounds are MIT licensed.\n\n"
        "[14-inch / 10-foot assessment](viewing-distance.md) · [All-theme contact sheet](contact-sheet.jpg)\n\n"
        "## Minimal: before / after\n\n![Minimal comparison](comparison-minimal.jpg)\n\n"
        "[Before at full resolution](comparison-minimal-before.png) · [After at full resolution](comparison-minimal-after.png)\n\n"
        "## Detailed: before / after\n\n![Detailed comparison](comparison-detailed.jpg)\n\n"
        "[Before at full resolution](comparison-detailed-before.png) · [After at full resolution](comparison-detailed-after.png)\n\n"
        "## Offline, stale and unavailable\n\n"
        "[Offline](offline.png) · [Stale](stale.png) · [Expired / unavailable](unavailable.png)\n\n"
        "## All ten themes, both layouts\n\n"
        + "\n".join(f"### {name}\n\n![{name}]({name})\n" for name, _ in thumbs)
    )


def write_assessment(font):
    try:
        ImageFont.truetype(font, 30)

        def face(size):
            return ImageFont.truetype(font, size)

        face_name = Path(font).name
    except OSError:

        def face(size):
            return ImageFont.load_default(size=size)

        face_name = "Pillow default fallback"
    mm_per_pixel = 14 * 25.4 / math.hypot(1920, 1200)
    rows = []
    for label, value, old, new in [
        ("Forecast time", "10:00", 30, 72),
        ("Forecast temperature", "14°", 60, 112),
        ("Rain probability", "Rain 65%", 27, 48),
        ("Detailed metric value", "12 mph", 34, 48),
        ("Update / warning text", "Offline", 23, 44),
    ]:
        heights = [
            face(n).getbbox(value)[3] - face(n).getbbox(value)[1] for n in (old, new)
        ]
        mm = [h * mm_per_pixel for h in heights]
        angles = [math.degrees(2 * math.atan(h / (2 * 3048))) * 60 for h in mm]
        rows.append(
            f"| {label} | {old} → {new} | {heights[0]} → {heights[1]} | {mm[0]:.1f} → {mm[1]:.1f} | {angles[0]:.1f} → {angles[1]:.1f} |"
        )
    (ROOT / "viewing-distance.md").write_text(
        "# 14-inch / 10-foot viewing assessment\n\n"
        "Assumptions: full-screen 1920 × 1200, 16:10 active panel, 14-inch diagonal, "
        "no overscan, viewing distance 10 feet (3,048 mm). The active area is approximately "
        "301.6 × 188.5 mm: each pixel is 0.1571 mm. These are calculated dimensions, "
        "not a physical viewing test. Measurements below use actual rendered glyph ink in `"
        + face_name
        + "`, "
        "rather than treating font em size as letter height.\n\n"
        "| Element | Font px before → after | Ink height px | Physical height mm | Angular height arcminutes |\n"
        "| --- | --- | --- | --- | --- |\n" + "\n".join(rows) + "\n\n"
        "Forecast icon boxes grow from 95 px (14.9 mm) to 180 px (28.3 mm) in minimal "
        "and 160 px (25.1 mm) in detailed. The drawing occupies part of each box. Main "
        "temperature stays at 235 px; it remains the dominant element. Forecast times grow "
        "2.4× in nominal type size and temperatures 1.87×. Four columns are retained.\n\n"
        "## What this means from the sofa\n\n"
        "The main temperature, four future temperatures, times and icons are the primary "
        "two-to-three-second reading target. Their physical size is substantially larger "
        "in both layouts. Repeated condition sentences and low-risk precipitation labels "
        "are removed. Precipitation probability appears at 20% or above, or for a wet/snow/storm "
        "weather code even below 20%. Detailed pressure is omitted so four useful metrics "
        "can have larger values. Wind/gust/rain/humidity labels and values remain secondary; "
        "they are smaller than the forecast and may still require more attention or a "
        "closer view. Source attribution intentionally remains close-reading text. The "
        "offline/stale message is larger, with a 36 px red dot instead of 24 px.\n\n"
        "This assessment does not guarantee comfortable reading for every viewer: eyesight, "
        "panel contrast, glare and room lighting matter. A large PNG or contact sheet on a "
        "computer monitor cannot establish ten-foot readability. The numeric comparison "
        "supports a material improvement; confirm it on the actual 14-inch frame before "
        "treating sofa-distance readability as verified.\n\n"
        "## Equivalent-angle review before updating the Pi\n\n"
        "At 60 cm viewing distance, display a complete card at **59.4 mm wide** (measure "
        "the image with a ruler; browser zoom and CSS millimetres are not reliable physical "
        "calibration). This approximates the angular size of a 301.6 mm-wide frame at ten "
        "feet. Compare full-resolution before/after files at exactly the same measured "
        "width. This is an angular-size check, not a substitute for the Pi's panel and "
        "lighting. For the final manual test, stand ten feet away and try to read the four "
        "times and temperatures in two or three seconds, then check the warning and wet-hour "
        "probabilities. No deployment is performed by this generator.\n\n"
        "## Geometry verification\n\n"
        "Tests record measured text-ink rectangles and conservative icon boxes. They check "
        "canvas boundaries, four-column boundaries and pairwise overlap across all ten "
        "themes, both layouts, supported extremes, long locations, clock-change labels, "
        "offline/stale/expired cards and shortened/exhausted forecasts. DejaVu Sans and "
        "the Pillow fallback are checked when the configured test font is available. "
        "Custom fonts can have different metrics; unusually wide strings are fitted to "
        "their region. Geometry checks do not assess eyesight or aesthetic quality.\n"
    )


if __name__ == "__main__":
    main()
