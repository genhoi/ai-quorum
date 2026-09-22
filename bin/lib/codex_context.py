#!/usr/bin/env python3
"""Resolve missing Codex settings from the current parent's persisted turn only."""

import json
import os
from pathlib import Path
import sys
from uuid import UUID


def parent_settings(env):
    thread_id = str(UUID(env["CODEX_THREAD_ID"]))
    codex_home = Path(env.get("CODEX_HOME") or Path.home() / ".codex")
    paths = list((codex_home / "sessions").glob(f"**/rollout-*-{thread_id}.jsonl"))
    if len(paths) != 1:
        raise ValueError("current parent rollout is missing or ambiguous")
    context = {}
    with paths[0].open(encoding="utf-8") as stream:
        for line in stream:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue  # The active rollout may end with a partially written line.
            if record.get("type") == "turn_context":
                context = record.get("payload") or {}
    settings = (env.get("CODEX_MODEL") or context.get("model"),
                env.get("CODEX_EFFORT") or context.get("effort"))
    if not all(isinstance(value, str) and value.strip() and "\n" not in value
               and "\r" not in value for value in settings):
        raise ValueError("current parent turn lacks a required model or effort")
    return settings


if __name__ == "__main__":
    try:
        print(*parent_settings(os.environ), sep="\n")
    except (KeyError, ValueError, OSError) as exc:
        print(f"cannot inherit Codex settings: {exc}; set CODEX_MODEL and CODEX_EFFORT explicitly",
              file=sys.stderr)
        sys.exit(1)
