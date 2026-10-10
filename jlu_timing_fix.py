#!/usr/bin/env python3
"""Backfill registration and exam times for formal JLU notices.

Only explicit dates/times found in JLU employment-site article text are written.
All equivalent JLU host/path variants are inspected because some endpoints can
return a navigation shell with HTTP 200 but omit the article body. A very small
set of manually confirmed notices provides fallback values when the university
site is temporarily unreadable. Existing identical values are never rewritten.
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
HEADERS = {"User-Agent": "XuandiaoRadar/1.7", "Accept": "text/html,application/xhtml+xml"}

KNOWN_TIMINGS = {
    ("黑龙江", "黑龙江省2027年度定向选调应届优秀大学毕业生公告"): {
        "start": "2026-10-08T08:30:00+08:00",
        "end": "2026-10-17T17:30:00+08:00",
        "note": "报名时间已确认：10月8日8:30至10月17日17:30。",
    },
    ("四川", "四川省面向吉林大学选调2027届优秀大学毕业生"): {
        "start": "2026-10-08T00:00:00+08:00",
        "startDateOnly": True,
        "end": "2026-10-14T18:00:00+08:00",
        "exam": "2026-10-24T00:00:00+08:00",
        "examDateOnly": True,
        "note": "报名10月8日开始（公告未列具体开放时刻），10月14日18:00截止；笔试10月24日。",
    },
    ("安徽", "安徽省2027年度面向吉林大学定向招录选调生公告"): {
        "start": "2026-10-14T09:00:00+08:00",
        "end": "2026-10-21T17:00:00+08:00",
        "exam": "2026-11-14T00:00:00+08:00",
        "examDateOnly": True,
        "note": "报名10月14日9:00开始，10月21日17:00截止；笔试11月14日，具体时间地点见准考证。",
    },
}

TIME = r"(?:(\d{1,2})\s*(?:[:：时])\s*(\d{1,2})\s*分?)?"
INTERVAL = re.compile(
    r"(?:(20\d{2})年)?\s*(\d{1,2})月\s*(\d{1,2})日\s*" + TIME +
    r"\s*(?:至|到|—|－|-|~|～)\s*" +
    r"(?:(20\d{2})年)?\s*(\d{1,2})月\s*(\d{1,2})日\s*" + TIME
)
EXAM_PATTERNS = (
    re.compile(
        r"笔试时间(?:为|是|[:：])?\s*(?:(20\d{2})年)?\s*(\d{1,2})月\s*(\d{1,2})日"
        r"(?:[^。；，]{0,24}?(\d{1,2})\s*(?:[:：时])\s*(\d{1,2})\s*分?)?"
    ),
    re.compile(
        r"笔试[^。；]{0,90}?(?:定于|安排在|于)\s*(?:(20\d{2})年)?\s*(\d{1,2})月\s*(\d{1,2})日"
        r"(?:[^。；，]{0,24}?(\d{1,2})\s*(?:[:：时])\s*(\d{1,2})\s*分?)?"
    ),
)


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def save(name, obj):
    path = ROOT / name
    text = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")


def valid_jlu_url(url):
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == "https" and parsed.hostname in HOSTS
                and not parsed.username and not parsed.password
                and parsed.port in (None, 443))
    except Exception:
        return False


def is_jlu(url):
    return valid_jlu_url(url)


def alternate_urls(url):
    """Return equivalent public JLU article endpoints without weakening TLS/host checks."""
    parsed = urlsplit(url)
    if not valid_jlu_url(url):
        return []
    paths = [parsed.path]
    if parsed.path.startswith("/portal/article/details"):
        paths.append(parsed.path.replace("/portal/article/details", "/portal/xdsgz/article/details", 1))
    elif parsed.path.startswith("/portal/xdsgz/article/details"):
        paths.append(parsed.path.replace("/portal/xdsgz/article/details", "/portal/article/details", 1))
    out = []
    for host in HOSTS:
        for path in paths:
            candidate = urlunsplit(("https", host, path, parsed.query, ""))
            if candidate not in out:
                out.append(candidate)
    return out


def fetch_candidate_text(candidate):
    response = requests.get(candidate, headers=HEADERS, timeout=(8, 18), allow_redirects=True)
    response.raise_for_status()
    if not valid_jlu_url(response.url):
        raise ValueError("redirect outside approved JLU HTTPS endpoints")
    encoding = response.apparent_encoding or response.encoding or "utf-8"
    html = response.content.decode(encoding, errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select("script,style,nav,header,footer,aside,form,iframe,svg,noscript"):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    text = re.sub(r"(?<=\d)\s+(?=\d)", "", text)
    if len(text) < 100:
        raise ValueError("article text too short")
    return text


def score_context(text, match):
    ctx = text[max(0, match.start()-160):min(len(text), match.end()+120)]
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


def iso(year, month, day, hour=0, minute=0):
    return datetime(int(year), int(month), int(day), int(hour or 0), int(minute or 0), tzinfo=TZ).isoformat(timespec="seconds")


def parse_timing(text, default_year):
    result = {}
    choices = []
    for match in INTERVAL.finditer(text):
        score, ctx = score_context(text, match)
        if score >= 8:
            choices.append((score, match, ctx))
    if choices:
        _, match, ctx = max(choices, key=lambda item: item[0])
        sy, sm, sd, sh, smin, ey, em, ed, eh, emin = match.groups()
        sy = int(sy or default_year)
        ey = int(ey or sy)
        if (int(em), int(ed)) < (int(sm), int(sd)) and match.group(6) is None:
            ey += 1
        result["start"] = iso(sy, sm, sd, sh or 0, smin or 0)
        result["startDateOnly"] = sh is None
        if eh is not None:
            result["end"] = iso(ey, em, ed, eh, emin or 0)
        result["context"] = ctx[:260]

    for pattern in EXAM_PATTERNS:
        exam = pattern.search(text)
        if not exam:
            continue
        year, month, day, hour, minute = exam.groups()
        result["exam"] = iso(year or default_year, month, day, hour or 0, minute or 0)
        result["examDateOnly"] = hour is None
        break
    return result


def timing_score(timing):
    # Registration fields are more important than the exam field on the countdown card.
    return 5 * bool(timing.get("end")) + 4 * bool(timing.get("start")) + 2 * bool(timing.get("exam"))


def fetch_best_timing(url, default_year):
    """Parse every equivalent JLU endpoint and keep the richest timing result.

    A JLU route occasionally responds 200 with only a SPA/navigation shell. The old
    implementation accepted the first >100-character page, so a later equivalent
    endpoint containing the real article body was never inspected.
    """
    errors = []
    best = None
    for candidate in alternate_urls(url):
        try:
            text = fetch_candidate_text(candidate)
            timing = parse_timing(text, default_year)
            candidate_result = (timing_score(timing), len(text), timing, candidate)
            if best is None or candidate_result[:2] > best[:2]:
                best = candidate_result
        except Exception as exc:
            errors.append(f"{candidate}: {type(exc).__name__}: {str(exc)[:100]}")
    if best is not None:
        _, _, timing, candidate = best
        return timing, candidate, errors
    raise RuntimeError(" | ".join(errors) or "no approved JLU article endpoint available")


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
    for flag in ("startDateOnly", "examDateOnly"):
        if flag not in merged and flag in known:
            merged[flag] = known[flag]
    if used:
        merged["fallbackNote"] = known.get("note", "")
    return merged, used


def set_if_different(record, key, value):
    if value is None or record.get(key) == value:
        return False
    record[key] = value
    return True


def main():
    data = load("data.json")
    status = load("monitor_status.json") if (ROOT / "monitor_status.json").exists() else {}
    stamp = datetime.now(TZ).isoformat(timespec="seconds")
    changed = 0
    errors = []
    fallback_used = []

    for record in data.get("records", []):
        if record.get("sourceTier") != "jlu_fallback" or not is_jlu(record.get("source", "")):
            continue

        year = int((record.get("published") or stamp[:10])[:4])
        timing = {}
        used_source = ""
        fetch_errors = []
        fetch_error = None
        try:
            timing, used_source, fetch_errors = fetch_best_timing(record["source"], year)
        except Exception as exc:
            fetch_error = exc

        timing, fallback = merge_known(record, timing)
        if fallback:
            fallback_used.append(record.get("province", "") + " " + record.get("title", ""))
        elif fetch_error:
            errors.append(f"{record.get('province')} {record.get('title','')[:36]}: {type(fetch_error).__name__}: {str(fetch_error)[:180]}")
            continue
        elif not timing and (not record.get("start") or not record.get("end")):
            # Surface the silent failure mode instead of reporting a clean run when
            # every successful HTTP response was only a shell or unparseable body.
            detail = " | ".join(fetch_errors[:2]) if fetch_errors else "HTTP succeeded but no registration interval was recognized"
            errors.append(f"{record.get('province')} {record.get('title','')[:36]}: no timing parsed; {detail[:150]}")

        local_changed = False
        local_changed |= set_if_different(record, "start", timing.get("start"))
        local_changed |= set_if_different(record, "end", timing.get("end"))
        if timing.get("exam"):
            if set_if_different(record, "exam", timing["exam"]):
                local_changed = True
            wanted_exam_text = "笔试日期由吉林大学就业网正文或已确认公告时间回填；具体安排以原文和准考证为准"
            local_changed |= set_if_different(record, "examText", wanted_exam_text)

        if timing.get("start"):
            wanted_date_only = bool(timing.get("startDateOnly"))
            if wanted_date_only:
                if record.get("startDateOnly") is not True:
                    record["startDateOnly"] = True
                    local_changed = True
            elif record.pop("startDateOnly", None) is not None:
                local_changed = True
            if record.pop("startTimeUnknown", None) is not None:
                local_changed = True

        if local_changed:
            record["autoParsedAt"] = stamp
            record["autoParsedFrom"] = used_source or "known_timing_fallback"
            if timing.get("context"):
                record["autoParsedContext"] = timing["context"]
            if timing.get("fallbackNote"):
                record["timingFallbackNote"] = timing["fallbackNote"]
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
