import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from .config import Config, load
from .render import PALETTES, render
from .sample import sample
from .service import generate, lock, queue, tick
from .storage import atomic, cached, read_json


def main(argv=None):
    p = argparse.ArgumentParser(description="Headless weather cards")
    p.add_argument(
        "--config", default=str(Path("~/.config/weather-card/config.toml").expanduser())
    )
    sub = p.add_subparsers(dest="command", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--offline", action="store_true")
    v = sub.add_parser("preview")
    v.add_argument("--theme", choices=PALETTES, default="rain")
    v.add_argument("--layout", choices=("minimal", "detailed"), default="minimal")
    v.add_argument("--output", default="preview.png")
    for cmd in ("queue", "status", "validate-config", "tick"):
        sub.add_parser(cmd)
    args = p.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    now = datetime.now(UTC)
    try:
        if args.command == "preview":
            cfg = Config(layout=args.layout)
            data = sample(now, args.theme)
            obj = dict(
                data=data,
                retrieved=now.timestamp(),
                valid_until=data["hourly"]["time"][-1],
            )
            image = render(cfg, obj, now, forced_theme=args.theme)
            atomic(args.output, lambda f: image.save(f, format="PNG"))
            return 0
        cfg = load(args.config)
        if args.command == "validate-config":
            print("Configuration valid")
            return 0
        if args.command == "status":
            obj = cached(cfg, now)
            print(
                json.dumps(
                    dict(
                        cache_valid=obj is not None,
                        retrieved=obj["retrieved"] if obj else None,
                        age_minutes=(now.timestamp() - obj["retrieved"]) / 60
                        if obj
                        else None,
                        queue=read_json(cfg.state / "queue.json"),
                        output_exists=Path(cfg.output).is_file(),
                    ),
                    indent=2,
                )
            )
            return 0
        with lock(cfg) as acquired:
            if acquired:
                if args.command == "generate":
                    generate(cfg, now, args.offline)
                elif args.command == "queue":
                    return 0 if queue(cfg, now) else 1
                else:
                    tick(cfg, now)
        return 0
    except (OSError, ValueError, TypeError) as exc:
        logging.error("%s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
