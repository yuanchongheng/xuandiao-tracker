#!/usr/bin/env python3
"""Normalize legacy date-only registration starts.

A calendar date is sufficient when the announcement gives no opening clock time.
The front-end already understands startDateOnly; this script only migrates legacy
data and deliberately does not rewrite JavaScript source at runtime.
"""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent


def main():
    path = ROOT / "data.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    changed = 0
    for record in data.get("records", []):
        if record.pop("startTimeUnknown", None):
            record["startDateOnly"] = True
            changed += 1
    if changed:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"start-date policy: migrated_records={changed}")


if __name__ == "__main__":
    main()
