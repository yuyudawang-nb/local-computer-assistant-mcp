#!/usr/bin/env python3
"""Local fallback for inspecting/stopping persistent jobs when ChatGPT is offline."""

import argparse
import json
import os
from pathlib import Path

from managed_processes import ManagedProcessManager
from project_state import ProjectState


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("list", "status", "log", "stop"))
    parser.add_argument("job_id", nargs="?")
    parser.add_argument("--root", default=os.getenv("LOCAL_RESEARCH_ROOT", str(Path.home())))
    args = parser.parse_args()
    manager = ManagedProcessManager(ProjectState(Path(args.root).expanduser()).directory)
    if args.action == "list":
        result = manager.list()
    else:
        if not args.job_id:
            parser.error("job_id is required for status, log and stop")
        if args.action == "status":
            result = manager.status(args.job_id)
        elif args.action == "log":
            result = manager.read_log(args.job_id)
        else:
            result = manager.stop(args.job_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
