#!/usr/bin/env python3
"""Atomic progress event and five-minute heartbeat command-line tool."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.progress import heartbeat_once, record_event, run_heartbeat  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Maintain AATM status and append progress events safely.")
    parser.add_argument("--root", type=Path, default=ROOT, help="Project root (defaults to this repository).")
    commands = parser.add_subparsers(dest="command", required=True)

    event = commands.add_parser("event", help="Record a significant development event immediately.")
    event.add_argument("--phase", required=True)
    event.add_argument("--task", required=True)
    event.add_argument("--action", required=True)
    event.add_argument("--activity", required=True)
    event.add_argument("--project-status", default="Developing", choices=["Planning", "Developing", "Testing", "Debugging", "Blocked", "Completed"])
    event.add_argument("--files-created", action="append", default=[])
    event.add_argument("--files-modified", action="append", default=[])
    event.add_argument("--tests", default="Not run")
    event.add_argument("--results", default="")
    event.add_argument("--problems", default="None")
    event.add_argument("--solutions", default="None")

    heartbeat = commands.add_parser("heartbeat", help="Update STATUS.txt on a periodic heartbeat.")
    heartbeat.add_argument("--interval", type=int, default=300, help="Seconds between status timestamp updates (default: 300).")
    heartbeat.add_argument("--idle-after", type=int, default=300, help="Seconds without an event before status says idle (default: 300).")
    heartbeat.add_argument("--once", action="store_true", help="Run one heartbeat and exit (useful for checks).")

    args = parser.parse_args()
    if args.command == "event":
        timestamp = record_event(
            args.root,
            phase=args.phase,
            task=args.task,
            action=args.action,
            activity=args.activity,
            files_created=args.files_created,
            files_modified=args.files_modified,
            tests=args.tests,
            results=args.results,
            problems=args.problems,
            solutions=args.solutions,
            project_status=args.project_status,
        )
        print(f"Recorded progress event at {timestamp}.")
        return 0

    if args.once:
        print(heartbeat_once(args.root, idle_after_seconds=args.idle_after))
        return 0
    run_heartbeat(args.root, interval_seconds=args.interval, idle_after_seconds=args.idle_after)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
