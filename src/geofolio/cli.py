import argparse
import json
import os
from pathlib import Path

import uvicorn

from .api import create_app
from .demo import demo_portfolio, warm_demo
from .engine import Engine
from .models import Portfolio
from .workspace import default_portfolio, initialize


def main():
    parser = argparse.ArgumentParser(description="Spatial market context and portfolio scenario research")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--mode", choices=["demo", "manual", "live"], default="live")
    serve.add_argument("--portfolio", type=Path)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--data-dir", type=Path, default=Path(".geofolio"))
    serve.add_argument("--secure-cookie", action="store_true", help="Require HTTPS for session cookies")
    init = sub.add_parser("init", help="Initialize a private company workspace and access keys")
    init.add_argument("--data-dir", type=Path, default=Path(".geofolio"))
    demo = sub.add_parser("demo", help="Emit one deterministic-seed synthetic context")
    demo.add_argument("--output", type=Path)
    replay = sub.add_parser("replay", help="Replay market/spatial JSONL in arrival order")
    replay.add_argument("--portfolio", type=Path, required=True)
    replay.add_argument("input", type=Path)
    args = parser.parse_args()
    if args.command == "init":
        keys, created = initialize(args.data_dir)
        print(f"Workspace: {args.data_dir.resolve()}")
        print("Administrator access key: " + keys["admin"])
        print("Viewer access key: " + keys["viewer"])
        print("Keep these private. Share viewer access with read-only teammates.")
    elif args.command == "demo":
        engine = Engine(demo_portfolio())
        warm_demo(engine)
        result = json.dumps(engine.snapshot(), indent=2, allow_nan=False)
        if args.output:
            args.output.write_text(result + "\n")
        else:
            print(result)
    elif args.command == "replay":
        from .models import MarketFrame, SpatialEvent

        engine = Engine(Portfolio.model_validate_json(args.portfolio.read_text()))
        with args.input.open() as stream:
            for number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                    if row.get("protocol") == "geofolio.spatial/1.0":
                        engine.event(SpatialEvent.model_validate(row))
                    else:
                        engine.ingest(MarketFrame.model_validate(row))
                except ValueError as exc:
                    raise SystemExit(f"Invalid record at line {number}: {exc}") from exc
        print(json.dumps(engine.snapshot(), indent=2, allow_nan=False))
    else:
        if (
            args.mode == "manual"
            and not args.portfolio
            and not (args.data_dir / "workspace.sqlite3").exists()
        ):
            parser.error("manual mode requires --portfolio on first setup")
        portfolio = (
            Portfolio.model_validate_json(args.portfolio.read_text())
            if args.portfolio
            else (demo_portfolio() if args.mode == "demo" else default_portfolio())
        )
        keys, created = initialize(args.data_dir)
        if created:
            print(
                "Workspace created. Run geofolio init --data-dir "
                + str(args.data_dir)
                + " to view access keys."
            )
        print(f"Open http://{'127.0.0.1' if args.host == '0.0.0.0' else args.host}:{args.port}")
        uvicorn.run(
            create_app(
                portfolio,
                args.mode,
                os.getenv("GEOFOLIO_TOKEN", keys["admin"]),
                os.getenv("GEOFOLIO_VIEWER_TOKEN", keys["viewer"]),
                args.data_dir,
                secure_cookie=args.secure_cookie,
            ),
            host=args.host,
            port=args.port,
        )


if __name__ == "__main__":
    main()
