from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .archive import initialize_archive, load_archive, merge_records, save_archive, write_archive_manifest
from .collector import collect_all
from .exporter import export_site
from .feasibility import assess
from .utils import PROJECT_ROOT, read_csv, read_json, write_json
from .validator import validate_site
from .web import serve


def _root(value: str | None) -> Path:
    return Path(value).resolve() if value else PROJECT_ROOT


def cmd_init(args: argparse.Namespace) -> int:
    root = _root(args.root)
    rows = initialize_archive(root / "data/archive.jsonl", root / "data/seed_updates.json")
    write_archive_manifest(root / "data/archive_manifest.json", rows)
    print(json.dumps({"status": "initialized", "archive_records": len(rows), "root": str(root)}, ensure_ascii=False, indent=2))
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    root = _root(args.root)
    existing = initialize_archive(root / "data/archive.jsonl", root / "data/seed_updates.json")
    records, logs, health = collect_all(
        root / "config/sources.json",
        root / "data/source_health.json",
        source_id=args.source,
        sleep_seconds=args.sleep,
    )
    config = read_json(root / "config/sources.json", {})
    merged, stats = merge_records(existing, records, max_records=int(config.get("archive_limit", 100000)), minimum_relevance_score=int(config.get("minimum_relevance_score", 4)), near_duplicate_threshold=float(config.get("near_duplicate_threshold", 0.90)))
    save_archive(root / "data/archive.jsonl", merged)
    write_archive_manifest(root / "data/archive_manifest.json", merged)
    payload = {"merge": stats, "source_logs": logs, "source_health": health}
    write_json(root / "outputs/source_sync_log.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    # Source failures are recorded, not treated as a whole-run failure.
    return 0


def load_assessment(root: Path, path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    payload = read_json(Path(path), None)
    if not isinstance(payload, dict):
        raise ValueError("assessment input must be a JSON object")
    measures = read_csv(root / "data/technology_guidance.csv")
    return assess(payload, measures)


def cmd_build(args: argparse.Namespace) -> int:
    root = _root(args.root)
    initialize_archive(root / "data/archive.jsonl", root / "data/seed_updates.json")
    feasibility_result = load_assessment(root, args.feasibility_input)
    manifest = export_site(root, Path(args.output).resolve() if args.output else root / "site", feasibility_result=feasibility_result)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    site = Path(args.site).resolve() if args.site else _root(args.root) / "site"
    result = validate_site(site)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


def cmd_serve(args: argparse.Namespace) -> int:
    root = _root(args.root)
    site = Path(args.site).resolve() if args.site else root / "site"
    if not (site / "index.html").exists():
        export_site(root, site)
    serve(site, args.host, args.port)
    return 0


def cmd_feasibility(args: argparse.Namespace) -> int:
    root = _root(args.root)
    payload = read_json(Path(args.input), None)
    if not isinstance(payload, dict):
        raise ValueError("assessment input must be a JSON object")
    result = assess(payload, read_csv(root / "data/technology_guidance.csv"))
    output = Path(args.output).resolve() if args.output else root / "outputs/feasibility_result.json"
    write_json(output, result)
    print(json.dumps({"output": str(output), "conclusion": result["feasibility"]["conclusion"], "mode": result["mode"]}, ensure_ascii=False, indent=2))
    return 0


def cmd_all(args: argparse.Namespace) -> int:
    root = _root(args.root)
    cmd_init(argparse.Namespace(root=str(root)))
    if not args.skip_sync:
        cmd_sync(argparse.Namespace(root=str(root), source=args.source, sleep=args.sleep))
    result = load_assessment(root, args.feasibility_input)
    site = Path(args.output).resolve() if args.output else root / "site"
    manifest = export_site(root, site, feasibility_result=result)
    validation = validate_site(site)
    print(json.dumps({"build": manifest, "validation": validation}, ensure_ascii=False, indent=2))
    return 0 if validation["ok"] else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="zcpark", description="园区碳观察：公开数据同步、自动报告与可行性分析")
    parser.add_argument("--root", help="repository root; defaults to the installed project root")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="initialize the rolling archive from reviewed seeds")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("sync", help="collect public sources and merge the rolling archive")
    p.add_argument("--source", help="only retry one source id")
    p.add_argument("--sleep", type=float, default=0.5, help="sleep between sources")
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("build", help="build the deployable static website and reports")
    p.add_argument("--output", help="output directory; defaults to site/")
    p.add_argument("--feasibility-input", help="optional JSON scenario for a generated feasibility report")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("validate", help="validate site files, local links and interaction hooks")
    p.add_argument("--site", help="site directory; defaults to site/")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("serve", help="serve the built site locally")
    p.add_argument("--site", help="site directory; defaults to site/")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("feasibility", help="run a feasibility screening from JSON")
    p.add_argument("--input", required=True)
    p.add_argument("--output")
    p.set_defaults(func=cmd_feasibility)

    p = sub.add_parser("all", help="initialize, optionally sync, build and validate")
    p.add_argument("--skip-sync", action="store_true", help="build from the current archive without network collection")
    p.add_argument("--source")
    p.add_argument("--sleep", type=float, default=0.5)
    p.add_argument("--output")
    p.add_argument("--feasibility-input")
    p.set_defaults(func=cmd_all)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
