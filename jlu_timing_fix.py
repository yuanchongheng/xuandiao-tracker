#!/usr/bin/env python3
"""Backfill registration and exam times for formal JLU notices.

Only explicit dates/times found in JLU employment-site article text are written.
If one JLU hostname fails, the same article path is retried on the other JLU host.
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
HEADERS = {"User-Agent": "XuandiaoRadar/1.3", "Accept": "text/html,application/xhtml+xml"}

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
            soup = BeautifulSoup(r.content, "html.parser")
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


def main():
    data = load("data.json")
    status = load("monitor_status.json") if (ROOT / "monitor_status.json").exists() else {}
    stamp = datetime.now(TZ).isoformat(timespec="seconds")
    changed = 0
    errors = []

    for r in data.get("records", []):
        if r.get("sourceTier") != "jlu_fallback" or not is_jlu(r.get("source", "")):
            continue
        try:
            text, used = fetch_text(r["source"])
            year = int((r.get("published") or stamp[:10])[:4])
            timing = parse_timing(text, year)
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
                r["examText"] = "笔试日期由吉林大学就业网正文自动提取；具体安排以原文和准考证为准"
                local_changed = True
            if local_changed:
                r["autoParsedAt"] = stamp
                r["autoParsedFrom"] = used
                if timing.get("context"):
                    r["autoParsedContext"] = timing["context"]
                changed += 1
        except Exception as exc:
            errors.append(f"{r.get('province')} {r.get('title','')[:36]}: {type(exc).__name__}: {str(exc)[:180]}")

    if changed:
        data["asOf"] = stamp
    status["jluTimingBackfilledThisRun"] = changed
    status["jluTimingBackfillErrors"] = errors[:20]
    save("data.json", data)
    save("monitor_status.json", status)
    print(f"JLU timing backfill: changed={changed}, errors={len(errors)}")


if __name__ == "__main__":
    main()
