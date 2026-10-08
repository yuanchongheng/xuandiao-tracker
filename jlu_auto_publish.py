#!/usr/bin/env python3
"""Auto-publish JLU employment-site notices and extract structured timing fields.

JLU notices may enter formal data.json without manual second review. This script
fetches the JLU article itself and extracts registration start/end and exam date
when the wording is explicit. It never guesses a missing clock time.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
TZ = timezone(timedelta(hours=8))
JLU_HOSTS = {"jdjywpt.jlu.edu.cn", "jdjyw.jlu.edu.cn"}
HEADERS = {
    "User-Agent": "XuandiaoRadar/1.2 (public JLU notice parser)",
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
}

INTERVAL_RE = re.compile(
    r"(?:(20\d{2})年)?\s*(\d{1,2})月\s*(\d{1,2})日"
    r"(?:\s*(\d{1,2})[:：](\d{2}))?"
    r"\s*(?:至|—|－|-|到)\s*"
    r"(?:(20\d{2})年)?\s*(\d{1,2})月\s*(\d{1,2})日"
    r"(?:\s*(\d{1,2})[:：](\d{2}))?"
)
EXAM_RE = re.compile(
    r"笔试时间(?:为|是|[:：])?\s*(?:(20\d{2})年)?\s*(\d{1,2})月\s*(\d{1,2})日"
    r"(?:[^。；，]{0,18}?(\d{1,2})[:：](\d{2}))?"
)


def read_json(name: str, default):
    path = ROOT / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def write_json(name: str, data):
    path = ROOT / name
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def is_jlu(url: str) -> bool:
    try:
        p = urlsplit(url)
    except Exception:
        return False
    return p.scheme == "https" and p.hostname in JLU_HOSTS


def clean_title(value: str) -> str:
    return re.sub(r"[\u200b\ufeff]", "", str(value or "")).strip()


def normalized_title(value: str) -> str:
    text = clean_title(value)
    text = re.sub(r"[\s·•—–_()（）\[\]【】《》“”‘’：:，,。.!！?？/\\-]+", "", text)
    return text.removesuffix("公告")


def iso_dt(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> str:
    # datetime validates impossible dates for us.
    return datetime(year, month, day, hour, minute, tzinfo=TZ).isoformat(timespec="seconds")


def fetch_article_text(url: str) -> str:
    if not is_jlu(url):
        raise ValueError("not a JLU employment URL")
    response = requests.get(url, headers=HEADERS, timeout=(8, 18), allow_redirects=True)
    response.raise_for_status()
    if urlsplit(response.url).hostname not in JLU_HOSTS:
        raise ValueError("JLU article redirected outside approved hosts")
    soup = BeautifulSoup(response.content, "html.parser")
    for tag in soup.select("script,style,nav,header,footer,aside,form,iframe,svg,noscript"):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    # JLU rendering occasionally inserts spaces inside years, e.g. 202 7.
    text = re.sub(r"(?<=\d)\s+(?=\d)", "", text)
    return re.sub(r"\s+", " ", text).strip()


def interval_score(text: str, match: re.Match) -> int:
    context = text[max(0, match.start() - 140): min(len(text), match.end() + 130)]
    score = 0
    if "网上报名" in context:
        score += 20
    elif "人选报名" in context or "报名时间" in context:
        score += 18
    elif "报名" in context:
        score += 10
    if "资格初审" in context or "资格审查" in context:
        score -= 5
    if "缴费" in context:
        score -= 8
    if "准考证" in context:
        score -= 10
    if "笔试" in context:
        score -= 10
    if "公示" in context:
        score -= 10
    return score


def extract_timing(text: str, default_year: int) -> dict:
    result = {}
    choices = []
    for match in INTERVAL_RE.finditer(text):
        score = interval_score(text, match)
        if score >= 5:
            choices.append((score, match))
    if choices:
        _, m = max(choices, key=lambda item: item[0])
        y1 = int(m.group(1) or default_year)
        mo1, d1 = int(m.group(2)), int(m.group(3))
        h1 = int(m.group(4)) if m.group(4) is not None else 0
        mi1 = int(m.group(5)) if m.group(5) is not None else 0
        y2 = int(m.group(6) or y1)
        mo2, d2 = int(m.group(7)), int(m.group(8))
        h2 = int(m.group(9)) if m.group(9) is not None else None
        mi2 = int(m.group(10)) if m.group(10) is not None else 0
        if (mo2, d2) < (mo1, d1) and m.group(6) is None:
            y2 += 1
        result["start"] = iso_dt(y1, mo1, d1, h1, mi1)
        result["startTimeUnknown"] = m.group(4) is None
        # A date-only registration end is not safe to turn into a midnight cutoff.
        if h2 is not None:
            result["end"] = iso_dt(y2, mo2, d2, h2, mi2)

    exam = EXAM_RE.search(text)
    if exam:
        year = int(exam.group(1) or default_year)
        month, day = int(exam.group(2)), int(exam.group(3))
        hour = int(exam.group(4)) if exam.group(4) is not None else 0
        minute = int(exam.group(5)) if exam.group(5) is not None else 0
        result["exam"] = iso_dt(year, month, day, hour, minute)
        result["examTimeUnknown"] = exam.group(4) is None
    return result


def infer_type(title: str) -> str:
    if "定向选调" in title:
        return "定向选调"
    if "选调" in title:
        return "选调公告"
    return "招聘通知"


def main() -> int:
    data = read_json("data.json", {"records": []})
    queue_doc = read_json("review_queue.json", {"updated": "", "candidates": []})
    status = read_json("monitor_status.json", {})
    records = data.setdefault("records", [])
    queue = queue_doc.setdefault("candidates", [])
    stamp = now_iso()

    existing_urls = {r.get("source") for r in records if r.get("source")}
    existing_keys = {(r.get("province"), normalized_title(r.get("title"))) for r in records}
    article_cache: dict[str, tuple[str | None, str | None]] = {}
    promoted = covered = timing_updated = 0
    timing_errors = []

    def timing_for(url: str, default_year: int) -> dict:
        if url not in article_cache:
            try:
                article_cache[url] = (fetch_article_text(url), None)
            except Exception as exc:
                article_cache[url] = (None, f"{type(exc).__name__}: {str(exc)[:150]}")
        text, error = article_cache[url]
        if error:
            raise RuntimeError(error)
        return extract_timing(text or "", default_year)

    # First: immediately promote newly discovered JLU notices into formal data.
    for candidate in queue:
        if candidate.get("status") != "pending" or not is_jlu(candidate.get("url", "")):
            continue
        key = (candidate.get("province"), normalized_title(candidate.get("title")))
        if candidate.get("url") in existing_urls or key in existing_keys:
            candidate["status"] = "auto_covered"
            candidate["note"] = "吉林大学就业网来源；正式数据中已有同链接或同标题记录，无需人工二次核验。"
            covered += 1
            continue

        discovered = candidate.get("discovered") or stamp
        day = discovered[:10]
        default_year = int(day[:4])
        timing = {}
        try:
            timing = timing_for(candidate["url"], default_year)
        except Exception as exc:
            timing_errors.append(f"{candidate.get('province')} {candidate.get('title')}: {exc}")

        title = clean_title(candidate.get("title"))
        record = {
            "province": candidate.get("province"),
            "title": title,
            "type": infer_type(title),
            "count": "以吉林大学就业网公告及附件为准",
            "published": day,
            "start": timing.get("start", ""),
            "end": timing.get("end", ""),
            "exam": timing.get("exam", ""),
            "examEnd": "",
            "examText": "报名、笔试及后续安排以吉林大学就业网原文和附件为准",
            "school": "吉林大学就业网已发布该通知；适用高校、学历、专业及校内流程以原文和附件为准。",
            "eligibility": "自动收录不推断资格条件；请直接查看吉林大学就业网原文及附件。",
            "notes": "吉林大学就业网自动发布，无需人工二次核验。报名起止和笔试日期仅在正文有明确表述时自动结构化；未明确内容仍以原文及附件为准。",
            "source": candidate.get("url"),
            "sourceName": "吉林大学就业网（自动发布）",
            "sourceType": "吉林大学备用",
            "verified": day,
            "sourceTier": "jlu_fallback",
            "autoPublished": True,
            "publishedEstimated": True,
            "discoveredAt": discovered,
        }
        if timing.get("startTimeUnknown"):
            record["startTimeUnknown"] = True
        records.append(record)
        existing_urls.add(record["source"])
        existing_keys.add(key)
        candidate["status"] = "auto_published"
        candidate["note"] = "吉林大学就业网来源；已自动加入正式数据。报名和考试时间会从正文自动提取，未明确字段以原文及附件为准。"
        promoted += 1

    # Second: backfill timing for existing JLU records. This fixes older auto-published
    # rows (e.g. a notice was published before timing extraction was introduced).
    for record in records:
        url = record.get("source", "")
        if record.get("sourceTier") != "jlu_fallback" or not is_jlu(url):
            continue
        try:
            default_year = int((record.get("published") or stamp[:10])[:4])
            timing = timing_for(url, default_year)
        except Exception as exc:
            timing_errors.append(f"{record.get('province')} {record.get('title')}: {exc}")
            continue

        changed = False
        if timing.get("start") and not record.get("start"):
            record["start"] = timing["start"]
            changed = True
        if timing.get("end") and not record.get("end"):
            record["end"] = timing["end"]
            changed = True
        if timing.get("exam") and not record.get("exam"):
            record["exam"] = timing["exam"]
            record["examText"] = "笔试日期由吉林大学就业网正文自动提取；具体时段、考点以原文和准考证为准"
            changed = True
        if timing.get("startTimeUnknown") and record.get("start"):
            if record.get("startTimeUnknown") is not True:
                record["startTimeUnknown"] = True
                changed = True
        elif timing.get("start") and record.get("startTimeUnknown"):
            record.pop("startTimeUnknown", None)
            changed = True
        if changed:
            timing_updated += 1

    if promoted or timing_updated:
        data["asOf"] = stamp
        data["notice"] = (
            "来源按政府官网、吉林大学就业网、经批准的其他高校官方就业网三级查找。"
            "吉林大学就业网发现的2027届选调通知自动进入正式数据，无需人工二次核验；"
            "系统会从吉大正文自动提取明确的报名起止和笔试日期，未明确的时刻或条件不作猜测。"
            "政府来源候选和其他高校第三来源仍按原规则处理。"
        )

    queue_doc["updated"] = stamp
    status["pendingCandidates"] = sum(c.get("status") == "pending" for c in queue)
    status["jluAutoPublishedThisRun"] = promoted
    status["jluAutoCoveredThisRun"] = covered
    status["jluTimingUpdatedThisRun"] = timing_updated
    status["jluTimingErrors"] = timing_errors[:20]
    status["warning"] = (
        "吉林大学就业网线索会自动进入正式数据，并自动解析正文中的明确报名起止和笔试日期；"
        "未明确时刻不推断。政府来源候选仍需人工核验，第三来源仅供参考。"
    )
    checked = status.get("checkedAt")
    remaining_new = sum(
        c.get("status") == "pending" and (not checked or c.get("discovered") == checked)
        for c in queue
    )
    # Keep the status card consistent with what still requires action after JLU
    # candidates have been auto-published. Previously newCandidates could say 1
    # while pendingCandidates correctly said 0.
    status["newCandidates"] = remaining_new

    write_json("data.json", data)
    write_json("review_queue.json", queue_doc)
    write_json("monitor_status.json", status)
    (ROOT / "new_candidate_count.txt").write_text(str(remaining_new), encoding="utf-8")
    print(
        f"JLU auto-publish: promoted={promoted}, covered={covered}, "
        f"timing_updated={timing_updated}, pending={status['pendingCandidates']}, "
        f"timing_errors={len(timing_errors)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
