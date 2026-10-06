#!/usr/bin/env python3
"""Site-specific parsers and personal relevance scoring for the qiuzhao job pool.

Parsers are intentionally conservative: they only emit a candidate when the source
page itself exposes a plausible job/category. Dynamic portals that return only a
shell page simply produce no candidates; update_job_pool.py still monitors their
content hash for changes.
"""
from __future__ import annotations

import hashlib
import re
from html import unescape
from urllib.parse import urljoin

from bs4 import BeautifulSoup

PROFILE = {
    "graduation_year": "2027",
    "degree": "硕士",
    "majors": ["产业经济学", "贸易经济", "应用经济学", "经济学", "国际贸易", "经济与贸易"],
    "skills": ["Stata", "Python", "R", "MATLAB", "Excel", "数据分析", "面板数据", "回归分析"],
    "strengths": ["经营", "贸易", "行业研究", "产业研究", "市场研究", "运营", "企业管理", "投资研究", "战略规划", "供应链"],
    "english": "CET-6",
}

POSITIVE_RULES = [
    (re.compile(r"产业经济|产业研究|行业研究|能源市场|投资研究|战略规划|规划投资"), 18, "产业/研究高度匹配"),
    (re.compile(r"贸易|国际商务|国际经营|大宗|供应链|采购|航运经营"), 17, "贸易/供应链匹配"),
    (re.compile(r"经营|运营|企业管理|综合管理|管理培训|管培|业务管理|职能管理"), 14, "经营管理匹配"),
    (re.compile(r"经济金融|金融|信贷|投资|客户经理"), 10, "经济金融匹配"),
    (re.compile(r"数据|分析|计量|市场研究|经营分析|计划发展"), 10, "数据分析能力可迁移"),
    (re.compile(r"市场|营销|客户|业务拓展|商务"), 8, "市场商务匹配"),
    (re.compile(r"产业经济学|贸易经济|应用经济学|经济学|国际贸易|经济与贸易"), 12, "专业直接匹配"),
]

# These are explicit hard-school-background patterns that the current profile does
# not satisfy. We do NOT infer rejection from vague wording such as “重点高校优先”.
HARD_BLOCK_RULES = [
    (re.compile(r"本硕(?:学校|院校)?.{0,12}(?:均|须|要求).{0,8}(?:985|211|双一流)"), "明确要求本硕均为985/211/双一流"),
    (re.compile(r"本科(?:毕业)?院校.{0,12}(?:须|要求|为).{0,8}(?:985|211|双一流)"), "明确限制本科院校层次"),
    (re.compile(r"本科阶段.{0,18}(?:985|211|双一流).{0,8}(?:必须|须|要求)"), "明确限制本科阶段院校/学科"),
]

NEGATIVE_RULES = [
    (re.compile(r"博士|博士后"), 22, "学历方向偏博士"),
    (re.compile(r"计算机|软件工程|人工智能|通信工程|电气工程|机械工程|化学工程|材料学"), 12, "专业偏理工技术"),
    (re.compile(r"长期海外|常驻海外"), 5, "长期海外属性"),
]

JOB_HINT = re.compile(r"岗|管培|培训生|研究|贸易|经营|运营|投资|战略|供应链|营销|商务|管理")
HIGH_VALUE = re.compile(r"产业|行业研究|贸易|国际商务|经营|运营|投资|战略|供应链|市场|营销|经济|金融|管理")
JOB_CODE = re.compile(r"[（(]?(J\d{4,})[）)]?", re.I)


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(text or "")).strip()


def stable_id(source_id: str, title: str, code: str = "") -> str:
    raw = f"{source_id}|{code.lower()}|{clean(title).lower()}"
    return f"auto-{source_id}-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12]}"


def score_candidate(text: str) -> dict:
    text = clean(text)
    hard_blocks = [reason for pattern, reason in HARD_BLOCK_RULES if pattern.search(text)]
    if hard_blocks:
        return {"score": 0, "eligibility": "blocked", "reasons": hard_blocks[:3]}

    score = 52
    reasons: list[str] = []
    for pattern, points, reason in POSITIVE_RULES:
        if pattern.search(text):
            score += points
            reasons.append(reason)
    for pattern, points, reason in NEGATIVE_RULES:
        if pattern.search(text):
            score -= points
            reasons.append(reason)

    if re.search(r"硕士|硕研|研究生", text):
        score += 4
        reasons.append("学历匹配")
    if re.search(r"2027届|2027年", text):
        score += 3
    if re.search(r"CET-6|英语六级|六级", text, re.I):
        score += 3
        reasons.append("英语条件匹配")

    score = max(35, min(98, score))
    eligibility = "likely" if score >= 72 else "review"
    # Preserve order while removing duplicates.
    reasons = list(dict.fromkeys(reasons))[:4]
    return {"score": score, "eligibility": eligibility, "reasons": reasons or ["需人工核对专业与学历条件"]}


def _candidate(source: dict, title: str, url: str, *, code: str = "", org: str = "", region: str = "", detail: str = "", kind: str = "岗位") -> dict:
    title = clean(title)
    detail = clean(detail)
    score = score_candidate(" ".join([title, org, region, detail]))
    return {
        "id": stable_id(source["id"], title, code),
        "sourceId": source["id"],
        "source": source["name"],
        "kind": kind,
        "title": title,
        "jobCode": code,
        "org": clean(org),
        "region": clean(region),
        "url": url,
        "detail": detail[:800],
        "matchScore": score["score"],
        "eligibility": score["eligibility"],
        "matchReasons": score["reasons"],
    }


def parse_zhiye(source: dict, html: str, base_url: str) -> list[dict]:
    """Parse Beisen/Zhiye pages such as Xiamen ITG.

    The server-rendered public page exposes job titles like 贸易运营岗(J13647).
    We prefer anchor text because it gives us a direct detail URL when available.
    """
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        text = clean(a.get_text(" ", strip=True))
        m = JOB_CODE.search(text)
        if not m or not JOB_HINT.search(text):
            continue
        code = m.group(1).upper()
        title = clean(JOB_CODE.sub("", text).strip(" -—|：:"))
        if not title:
            title = text
        if code in seen:
            continue
        seen.add(code)
        context = clean(a.parent.get_text(" ", strip=True) if a.parent else text)
        out.append(_candidate(source, title, urljoin(base_url, a["href"]), code=code, detail=context))

    # Some Zhiye templates render titles in non-anchor elements. Fall back to text.
    if not out:
        for text in soup.stripped_strings:
            text = clean(text)
            m = JOB_CODE.search(text)
            if not m or not JOB_HINT.search(text):
                continue
            code = m.group(1).upper()
            if code in seen:
                continue
            seen.add(code)
            title = clean(JOB_CODE.sub("", text).strip(" -—|：:")) or text
            out.append(_candidate(source, title, base_url, code=code, detail=text))
    return out


def parse_51job_categories(source: dict, html: str, base_url: str) -> list[dict]:
    """Parse static 51job campaign pages that expose job categories rather than jobs."""
    soup = BeautifulSoup(html, "html.parser")
    texts = [clean(x) for x in soup.stripped_strings]
    out: list[dict] = []
    seen: set[str] = set()
    for text in texts:
        if len(text) > 36 or len(text) < 3:
            continue
        if not re.search(r"类$|岗$|生$", text):
            continue
        if not HIGH_VALUE.search(text):
            continue
        if text in seen:
            continue
        seen.add(text)
        out.append(_candidate(source, text, base_url, kind="岗位类别", detail="官方校招专题页公开的岗位类别；进入网申系统后继续筛具体岗位。"))
    return out


def parse_generic_jobs(source: dict, html: str, base_url: str) -> list[dict]:
    """Conservative fallback for static official pages.

    It only emits short anchor/text labels containing both a job hint and a profile-
    relevant term; this avoids turning menus/paragraphs into fake jobs.
    """
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        text = clean(a.get_text(" ", strip=True))
        if not (4 <= len(text) <= 60 and JOB_HINT.search(text) and HIGH_VALUE.search(text)):
            continue
        if re.search(r"招聘首页|校园招聘|社会招聘|登录|注册|个人中心|关于我们", text):
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(_candidate(source, text, urljoin(base_url, a["href"]), detail=text))

    return out[:80]


def parse_source(source: dict, html: str, final_url: str) -> list[dict]:
    parser = source.get("parser", "generic")
    if parser == "zhiye":
        return parse_zhiye(source, html, final_url)
    if parser == "51job_categories":
        return parse_51job_categories(source, html, final_url)
    if parser == "monitor_only":
        return []
    return parse_generic_jobs(source, html, final_url)
