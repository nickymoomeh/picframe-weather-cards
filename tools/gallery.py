"""Build synthetic previews without HTTP, production state or configuration."""

from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageDraw

from weather_cards.config import Config
from weather_cards.render import PALETTES, render
from weather_cards.sample import sample

root = Path(__file__).resolve().parents[1] / "gallery"
root.mkdir(exist_ok=True)
thumbs = []
for kind in PALETTES:
    for mode in ("minimal", "detailed"):
        now = datetime(2026, 10, 31, 21 if "night" in kind else 12, 30, tzinfo=UTC)
        data = sample(now, kind)
        obj = dict(
            data=data, retrieved=now.timestamp(), valid_until=data["hourly"]["time"][-1]
        )
        image = render(Config(layout=mode), obj, now, forced_theme=kind)
        name = f"{kind}-{mode}.png"
        image.save(root / name)
        thumb = image.resize((480, 300))
        thumbs.append((name, thumb))
sheet = Image.new("RGB", (960, 3300), "#0b1425")
draw = ImageDraw.Draw(sheet)
for i, (name, thumb) in enumerate(thumbs):
    x = (i % 2) * 480
    y = (i // 2) * 330
    sheet.paste(thumb, (x, y))
    draw.text((x + 12, y + 306), name, fill="white")
sheet.save(root / "contact-sheet.jpg", quality=90)
(root / "README.md").write_text(
    "# Synthetic weather card gallery\n\nNo live forecast data. Original icons and backgrounds, MIT licensed.\n\n"
    + "\n".join(f"## {name}\n\n![{name}]({name})\n" for name, _ in thumbs)
)
