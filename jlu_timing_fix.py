#!/usr/bin/env python3
"""Backfill registration and exam times for formal JLU notices.

Only explicit dates/times found in JLU employment-site article text are written.
If one JLU hostname fails, the same article path is retried on the other JLU host.
For a very small set of manually confirmed JLU notices, KNOWN_TIMINGS provides a
safe fallback when the university site is temporarily unreadable from GitHub Actions.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
TZ = timezone(timedelta(hours=8))
HOSTS = ("jdjywpt.jlu.edu.cn", "jdjyw.jlu.edu.cn")
HEADERS = {"User-Agent": "XuandiaoRadar/1.4", "Accept": "text/html,application/xhtml+xml"}

# Manually confirmed from the corresponding notices. These are fallbacks only:
# normal operation still prefers parsing the JLU article itself.
KNOWN_TIMINGS = {
    ("黑龙江", "黑龙江省2027年度定向选调应届优秀大学毕业生公告"): {
        "start": "2026-10-08T08:30:00+08:00",
        "end": "2026-10-17T17:30:00+08:00",
        "note": "报名时间已确认：10月8日8:30至10月17日17:30。",
    },
    ("四川", "四川省面向吉林大学选调2027届优秀大学毕业生"): {
        "start": "2026-10-08T00:00:00+08:00",
        "startTimeUnknown": True,
        "end": "2026-10-14T18:00:00+08:00",
        "exam": "2026-10-24T00:00:00+08:00",
        "examTimeUnknown": True,
        "note": "报名10月8日开始（具体开放时刻未写明），10月14日18:00截止；笔试10月24日。",
    },
}

TIME = r"(?:(\d{1,2})\s*(?:[:：时])\s*(\d{1,2})\s*分?)?"
INTERVAL = re.compile(
    r"(?:(20\d{2})年)?\s*(\d{1,2})月\s*(\d{1,2})日\s*" + TIME +
    r"\s*(?:至|到|—|－|-|~|～)\s*" +
    r"(?:(20\d{2})年)?\s*(\d{1,2})月\s*(\d{1,2})日\s*" + TIME
)
EXAM = re.compile(
    r"笔试时间(?:为|是|[:：])?\s*(?:(20\d{2})年)?\s*(\d{1,2})月\s*(\d{1,2})日"
    r"(?:[^。；，]{0,24}?(\d{1,2})\s*(?:[:：时])\s*(\d{1,2})\s*分?)?"
)


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def save(name, obj):
    (ROOT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def is_jlu(url):
    try:
        return urlsplit(url).hostname in HOSTS
    except Exception:
        return False


def alternate_urls(url):
    p = urlsplit(url)
    if p.hostname not in HOSTS:
        return []
    out = [url]
    for host in HOSTS:
        if host != p.hostname:
            out.append(urlunsplit((p.scheme, host, p.path, p.query, "")))
    return out


def fetch_text(url):
    errors = []
    for candidate in alternate_urls(url):
        try:
            r = requests.get(candidate, headers=HEADERS, timeout=(8, 18), allow_redirects=True)
            r.raise_for_status()
            if urlsplit(r.url).hostname not in HOSTS:
                raise ValueError("redirect outside JLU hosts")
            # Some JLU responses omit or mislabel charset. Decode explicitly before parsing
            # so Chinese date phrases are not lost to replacement characters.
            encoding = r.apparent_encoding or r.encoding or "utf-8"
            text_html = r.content.decode(encoding, errors="replace")
            soup = BeautifulSoup(text_html, "html.parser")
            for tag in soup.select("script,style,nav,header,footer,aside,form,iframe,svg,noscript"):
                tag.decompose()
            text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
            text = re.sub(r"(?<=\d)\s+(?=\d)", "", text)
            if len(text) < 100:
                raise ValueError("article text too short")
            return text, candidate
        except Exception as exc:
            errors.append(f"{candidate}: {type(exc).__name__}: {str(exc)[:100]}")
    raise RuntimeError(" | ".join(errors))


def score_context(text, m):
    ctx = text[max(0, m.start()-160):min(len(text), m.end()+120)]
    score = 0
    if "网上报名" in ctx: score += 30
    if "人选报名" in ctx: score += 28
    if "报名时间" in ctx: score += 25
    if "报名" in ctx: score += 12
    if "资格初审" in ctx or "资格审查" in ctx: score -= 5
    if "准考证" in ctx: score -= 12
    if "笔试" in ctx: score -= 12
    if "公示" in ctx: score -= 12
    return score, ctx


def iso(y, mo, d, h=0, mi=0):
    return datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0), tzinfo=TZ).isoformat(timespec="seconds")


def parse_timing(text, default_year):
    result = {}
    choices = []
    for m in INTERVAL.finditer(text):
        score, ctx = score_context(text, m)
        if score >= 8:
            choices.append((score, m, ctx))
    if choices:
        _, m, ctx = max(choices, key=lambda x: x[0])
        g = m.groups()
        sy, sm, sd, sh, smin, ey, em, ed, eh, emin = g
        sy = int(sy or default_year)
        ey = int(ey or sy)
        if (int(em), int(ed)) < (int(sm), int(sd)) and g[5] is None:
            ey += 1
        result["start"] = iso(sy, sm, sd, sh or 0, smin or 0)
        result["startTimeUnknown"] = sh is None
        if eh is not None:
            result["end"] = iso(ey, em, ed, eh, emin or 0)
        result["context"] = ctx[:260]

    m = EXAM.search(text)
    if m:
        y, mo, d, h, mi = m.groups()
        result["exam"] = iso(y or default_year, mo, d, h or 0, mi or 0)
        result["examTimeUnknown"] = h is None
    return result


def merge_known(record, timing):
    known = KNOWN_TIMINGS.get((record.get("province"), record.get("title")))
    if not known:
        return timing, False
    merged = dict(timing)
    used = False
    for field in ("start", "end", "exam"):
        if not merged.get(field) and known.get(field):
            merged[field] = known[field]
            used = True
    if "startTimeUnknown" not in merged and "startTimeUnknown" in known:
        merged["startTimeUnknown"] = known["startTimeUnknown"]
    if "examTimeUnknown" not in merged and "examTimeUnknown" in known:
        merged["examTimeUnknown"] = known["examTimeUnknown"]
    if used:
        merged["fallbackNote"] = known.get("note", "")
    return merged, used


def main():
    data = load("data.json")
    status = load("monitor_status.json") if (ROOT / "monitor_status.json").exists() else {}
    stamp = datetime.now(TZ).isoformat(timespec="seconds")
    changed = 0
    errors = []
    fallback_used = []

    for r in data.get("records", []):
        if r.get("sourceTier") != "jlu_fallback" or not is_jlu(r.get("source", "")):
            continue

        timing = {}
        used = ""
        fetch_error = None
        try:
            text, used = fetch_text(r["source"])
            year = int((r.get("published") or stamp[:10])[:4])
            timing = parse_timing(text, year)
        except Exception as exc:
            fetch_error = exc

        timing, fallback = merge_known(r, timing)
        if fallback:
            fallback_used.append(r.get("province", "") + " " + r.get("title", ""))
        elif fetch_error:
            errors.append(f"{r.get('province')} {r.get('title','')[:36]}: {type(fetch_error).__name__}: {str(fetch_error)[:180]}")
            continue

        local_changed = False
        if timing.get("start") and (not r.get("start") or r.get("autoPublished") or r.get("startTimeUnknown")):
            r["start"] = timing["start"]
            if timing.get("startTimeUnknown"):
                r["startTimeUnknown"] = True
            else:
                r.pop("startTimeUnknown", None)
            local_changed = True
        if timing.get("end") and (not r.get("end") or r.get("autoPublished")):
            r["end"] = timing["end"]
            local_changed = True
        if timing.get("exam") and (not r.get("exam") or r.get("autoPublished")):
            r["exam"] = timing["exam"]
            r["examText"] = "笔试日期由吉林大学就业网正文或已确认公告时间回填；具体安排以原文和准考证为准"
            local_changed = True
        if local_changed:
            r["autoParsedAt"] = stamp
            r["autoParsedFrom"] = used or "known_timing_fallback"
            if timing.get("context"):
                r["autoParsedContext"] = timing["context"]
            if timing.get("fallbackNote"):
                r["timingFallbackNote"] = timing["fallbackNote"]
            changed += 1

    if changed:
        data["asOf"] = stamp
    status["jluTimingBackfilledThisRun"] = changed
    status["jluTimingBackfillErrors"] = errors[:20]
    status["jluTimingFallbackUsed"] = fallback_used[:20]
    save("data.json", data)
    save("monitor_status.json", status)
    print(f"JLU timing backfill: changed={changed}, fallbacks={len(fallback_used)}, errors={len(errors)}")


if __name__ == "__main__":
    main()
