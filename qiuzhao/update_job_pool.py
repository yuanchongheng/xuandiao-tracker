#!/usr/bin/env python3
"""Free job-pool monitor for the static qiuzhao tracker.

It never auto-promotes unverified jobs into data.js. Instead it:
1) checks every official URL already in the job pool;
2) checks a registry of official recruitment portals;
3) records portal health in job_status.json;
4) records changed official sources in job_candidates.json for manual verification.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import re
import ssl
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
RESTRICTED_CODES = {401, 403, 405, 418, 429, 451}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36 qiuzhao-tracker/1.0"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def parse_js_objects(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        obj = {}
        for key, dq, sq, boolean in re.findall(
            r"([A-Za-z_][A-Za-z0-9_]*):(?:\"((?:\\.|[^\"])*)\"|'((?:\\.|[^'])*)'|(true|false))",
            line,
        ):
            if boolean:
                obj[key] = boolean == "true"
            else:
                raw = dq if dq != "" else sq
                obj[key] = bytes(raw, "utf-8").decode("unicode_escape") if "\\" in raw else raw
        if obj.get("id"):
            out.append(obj)
    return out


def load_jobs() -> list[dict]:
    merged: dict[str, dict] = {}
    for job in parse_js_objects(ROOT / "data.js"):
        merged[job["id"]] = job
    for patch in parse_js_objects(ROOT / "data_additions_20261006.js"):
        jid = patch["id"]
        if patch.get("hidden"):
            merged.pop(jid, None)
        else:
            merged[jid] = {**merged.get(jid, {}), **patch}
    return list(merged.values())


def normalize_body(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="ignore")
    text = re.sub(r"\s+", " ", text)
    return text[:500_000]


def probe(url: str) -> dict:
    req = Request(url, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6"})
    try:
        ctx = ssl.create_default_context()
        with urlopen(req, timeout=12, context=ctx) as resp:
            code = int(getattr(resp, "status", 200) or 200)
            final_url = resp.geturl()
            body = normalize_body(resp.read(500_000))
            state = "ok" if 200 <= code < 400 else "error"
    except HTTPError as e:
        code = int(e.code)
        final_url = getattr(e, "url", url) or url
        try:
            body = normalize_body(e.read(120_000))
        except Exception:
            body = ""
        state = "restricted" if code in RESTRICTED_CODES else "error"
    except (URLError, TimeoutError, ssl.SSLError, OSError) as e:
        return {"url": url, "finalUrl": url, "httpStatus": None, "state": "error", "error": str(e)[:180], "title": "", "hash": "", "body": ""}

    title_match = re.search(r"<title[^>]*>(.*?)</title>", body, flags=re.I | re.S)
    title = re.sub(r"\s+", " ", title_match.group(1)).strip()[:160] if title_match else ""
    digest = hashlib.sha256(body.encode("utf-8", errors="ignore")).hexdigest()[:16] if body else ""
    return {"url": url, "finalUrl": final_url, "httpStatus": code, "state": state, "error": "", "title": title, "hash": digest, "body": body}


def public_probe(result: dict) -> dict:
    return {k: v for k, v in result.items() if k != "body"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    jobs = load_jobs()
    registry = json.loads((ROOT / "source_registry.json").read_text(encoding="utf-8"))
    sources = registry.get("sources", [])
    urls = sorted({j.get("url", "") for j in jobs if j.get("url")} | {s.get("url", "") for s in sources if s.get("url")})

    results: dict[str, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(args.workers, 12))) as pool:
        future_map = {pool.submit(probe, url): url for url in urls}
        for fut in concurrent.futures.as_completed(future_map):
            url = future_map[fut]
            try:
                results[url] = fut.result()
            except Exception as e:
                results[url] = {"url": url, "finalUrl": url, "httpStatus": None, "state": "error", "error": str(e)[:180], "title": "", "hash": "", "body": ""}

    previous_status_path = ROOT / "job_status.json"
    try:
        previous = json.loads(previous_status_path.read_text(encoding="utf-8"))
    except Exception:
        previous = {}
    prev_sources = {x.get("id"): x for x in previous.get("sources", [])}

    checked_at = now_iso()
    source_rows = []
    changed_sources = []
    for source in sources:
        r = results.get(source.get("url", ""), {})
        body_lower = r.get("body", "").lower()
        hits = [kw for kw in source.get("keywords", []) if kw.lower() in body_lower]
        row = {
            "id": source.get("id"), "name": source.get("name"), "kind": source.get("kind"),
            "url": source.get("url"), "state": r.get("state", "error"), "httpStatus": r.get("httpStatus"),
            "title": r.get("title", ""), "contentHash": r.get("hash", ""), "keywordHits": hits[:8]
        }
        source_rows.append(row)
        old = prev_sources.get(source.get("id"))
        if old and row["contentHash"] and old.get("contentHash") and row["contentHash"] != old.get("contentHash"):
            changed_sources.append(row)

    job_rows = {}
    for job in jobs:
        r = results.get(job.get("url", ""), {})
        job_rows[job["id"]] = {
            "state": r.get("state", "error"), "httpStatus": r.get("httpStatus"),
            "finalUrl": r.get("finalUrl", job.get("url", "")), "title": r.get("title", "")
        }

    counts = {"ok": 0, "restricted": 0, "error": 0}
    for r in job_rows.values():
        counts[r.get("state", "error")] = counts.get(r.get("state", "error"), 0) + 1

    status = {
        "generatedAt": checked_at,
        "jobCount": len(jobs),
        "counts": counts,
        "jobs": job_rows,
        "sources": source_rows,
        "note": "restricted 通常表示官网阻止机器人访问，不等于招聘入口失效；error 才需要人工复核。"
    }
    previous_status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    candidates_path = ROOT / "job_candidates.json"
    try:
        candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    except Exception:
        candidates = {"updatedAt": checked_at, "items": []}
    existing = {(x.get("sourceId"), x.get("contentHash")) for x in candidates.get("items", [])}
    for row in changed_sources:
        key = (row.get("id"), row.get("contentHash"))
        if key in existing:
            continue
        candidates.setdefault("items", []).append({
            "sourceId": row.get("id"), "source": row.get("name"), "url": row.get("url"),
            "detectedAt": checked_at, "contentHash": row.get("contentHash"),
            "keywordHits": row.get("keywordHits", []), "reason": "官方招聘入口页面内容发生变化，建议核验是否新增/调整2027届岗位。",
            "status": "待核验"
        })
    candidates["updatedAt"] = checked_at
    candidates["items"] = candidates.get("items", [])[-200:]
    candidates_path.write_text(json.dumps(candidates, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"checked {len(urls)} unique URLs / {len(jobs)} jobs; states={counts}; changed_sources={len(changed_sources)}")


if __name__ == "__main__":
    main()
