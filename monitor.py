#!/usr/bin/env python3
"""Public-page change detection + search discovery. NEVER edits vetted data.json.

Run from project root: python monitor.py [--skip-discovery] [--fixture-dir DIR]
The search feed is third-party discovery, not verification. Pages may block robots.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import sys
from datetime import datetime, timezone, timedelta
from urllib.parse import quote, urljoin, urlsplit, urlunsplit, parse_qsl, urlencode
from xml.etree import ElementTree

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from source_policy import source_label, source_tier

ROOT = Path(__file__).resolve().parent
TZ = timezone(timedelta(hours=8))
PROVINCES = ('北京', '天津', '河北', '山西', '内蒙古', '辽宁', '吉林', '黑龙江', '上海', '江苏', '浙江', '安徽', '福建', '江西', '山东', '河南', '湖北', '湖南', '广东', '广西', '海南', '重庆', '四川', '贵州', '云南', '西藏', '陕西', '甘肃', '青海', '宁夏', '新疆')
TIMEOUT = (7, 12)
MAX_BYTES = 2_000_000
HEADERS = {"User-Agent": "XuandiaoRadar/1.1 (public notice monitor; respectful requests)", "Accept": "text/html,application/xml,text/xml,application/rss+xml;q=0.9"}
KEYWORD = re.compile(r"定向选调|选调生|选调优秀|选调公告|选调工作|选调招聘|选调\d*名", re.I)
CONTENT_SELECTORS = ("article", "#article", ".article-content", "#article-content", "#zoom", ".TRS_Editor", ".article", "main")
SKIP_TAGS = "script,style,nav,header,footer,aside,form,iframe,svg,noscript"


def read_json(name, default):
    path = ROOT / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def write_json(name, data):
    target = ROOT / name
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(target)


def now_iso():
    return datetime.now(TZ).isoformat(timespec="seconds")


def canonical_url(url):
    p = urlsplit(url.strip())
    if p.scheme != "https" or not p.hostname or p.username or p.password or p.port not in (None, 443):
        raise ValueError("Only public HTTPS links are allowed")
    if p.hostname in ("localhost",) or p.hostname.endswith(".local"):
        raise ValueError("Non-public host")
    try:
        ipaddress.ip_address(p.hostname)
    except ValueError:
        pass
    else:
        raise ValueError("IP literal is not an approved public notice host")
    # Drop tracking parameters, fragments, and default ports; keep meaningful search/article query params.
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not (k.startswith("utm_") or k in ("fbclid", "gclid"))]
    return urlunsplit(("https", p.netloc.lower(), p.path or "/", urlencode(q), ""))


def approved_candidate(url):
    """Only government or Jilin University fallback URLs; never asserts article authenticity."""
    try:
        canonical_url(url)
    except ValueError:
        return False
    return source_tier(url) is not None


def make_session():
    # Retry temporary transport errors and 429/5xx, never disable certificate checks.
    retry = Retry(total=2, connect=2, read=1, backoff_factor=0.7,
                  status_forcelist=[429, 500, 502, 503, 504],
                  allowed_methods=frozenset(["GET"]), respect_retry_after_header=True)
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def acceptable_page(content_type, content):
    # A missing MIME header is not itself an error when a genuine markup
    # document was returned; keep JSON, PDF, empty and arbitrary binaries out.
    if not content:
        return False
    if any(x in content_type for x in ("text/html", "application/xhtml+xml", "text/xml", "application/xml", "application/rss+xml")):
        return True
    if content_type and not any(x in content_type for x in ("application/octet-stream", "text/plain")):
        return False
    prefix = content[:2048].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    return any(x in prefix for x in (b"<!doctype html", b"<html", b"<body", b"<article", b"<?xml", b"<rss"))


def fetch_bytes(url):
    # Sources are explicitly configured. Candidate RSS links are never fetched automatically.
    with make_session() as session, session.get(url, headers=HEADERS, timeout=(9, 16), stream=True, allow_redirects=True, verify=True) as response:
        response.raise_for_status()
        canonical_url(response.url)
        if not approved_candidate(response.url):
            raise ValueError("Source redirected outside government/JLU-approved domains")
        content_type = response.headers.get("Content-Type", "").lower()
        chunks = []
        size = 0
        for chunk in response.iter_content(chunk_size=32768):
            size += len(chunk)
            if size > MAX_BYTES:
                raise ValueError("response too large")
            chunks.append(chunk)
        content = b"".join(chunks)
        # Some public sites omit Content-Type. Only permit headerless responses
        # when the bytes actually look like an HTML/XML document, not JSON or
        # a binary login/error response. This does not bypass TLS verification.
        if not acceptable_page(content_type, content):
            raise ValueError("unsupported content-type: " + (content_type[:75] or "(missing)") + "; bytes=" + str(len(content)))
        return content


def soup_for(content):
    return BeautifulSoup(content, "html.parser")


def article_text(content):
    soup = soup_for(content)
    for tag in soup.select(SKIP_TAGS):
        tag.decompose()
    target = next((soup.select_one(x) for x in CONTENT_SELECTORS if soup.select_one(x)), None)
    body = target or soup.body or soup
    text = re.sub(r"\s+", " ", body.get_text(" ", strip=True)).strip()
    if len(text) < 90:
        raise ValueError("article text too short; baseline not changed")
    return text[:150000]


def listing_links(content, base_url, province, year):
    soup = soup_for(content)
    out = {}
    for link in soup.select("a[href]"):
        title = re.sub(r"\s+", " ", link.get_text(" ", strip=True)).strip()[:160]
        parent_text = (link.parent.get_text(" ", strip=True)[:260] if link.parent and link.parent.name in ("li", "tr", "div", "p", "td") and len(link.parent.select("a")) == 1 else title)
        if not KEYWORD.search(title + " " + parent_text):
            continue
        if year not in title + " " + parent_text:
            continue
        # Provincial backup indexes must not treat other regions as coverage.
        if province != '全国' and province not in title + " " + parent_text:
            continue
        try:
            url = canonical_url(urljoin(base_url, link.get("href", "")))
        except ValueError:
            continue
        if url == canonical_url(base_url) or not approved_candidate(url):
            continue
        detected_province = province
        if province == '全国':
            # A national JLU index must never label all its links as one province.
            detected_province = next((p for p in PROVINCES if p in title or p in parent_text), None)
            if not detected_province:
                continue
        out[url] = {"title": title or parent_text[:120], "province": detected_province, "url": url, "source": base_url, "kind": "listing"}
    return list(out.values())


def parse_rss(content, province, year):
    """Only discover likely official-host links, no scraping candidate pages or extracting conditions."""
    root = ElementTree.fromstring(content)
    results = []
    for item in root.findall(".//item"):
        title = re.sub(r"\s+", " ", "".join(item.findtext("title", default=""))).strip()[:160]
        url = (item.findtext("link") or "").strip()
        summary = BeautifulSoup(item.findtext("description") or "", "html.parser").get_text(" ", strip=True)[:300]
        if year not in title + summary or province not in title + summary or not KEYWORD.search(title + " " + summary):
            continue
        if not approved_candidate(url):
            continue
        try:
            url = canonical_url(url)
        except ValueError:
            continue
        results.append({"title": title, "province": province, "url": url, "kind": "search", "source": "Bing RSS（搜索线索，未经人工核验）"})
    # If the search finds a government document, the university fallback is not needed.
    if any(source_tier(e['url']) == 'government' for e in results):
        return [e for e in results if source_tier(e['url']) == 'government']
    return results


def queue_candidate(queue, known, entry, timestamp, *, fingerprint=""):
    url = canonical_url(entry["url"])
    # One entry per announcement; a source-page revision gets a distinct hash.
    identifier = hashlib.sha256((entry["kind"] + "|" + url + "|" + fingerprint).encode()).hexdigest()[:20]
    if identifier in known:
        return False
    known.add(identifier)
    queue.append({"id": identifier, "province": entry["province"], "title": entry["title"], "url": url,
                  "kind": entry["kind"], "source": entry["source"], "discovered": timestamp, "status": "pending",
                  "sourceTier": source_tier(url), "sourceLabel": source_label(url),
                  "note": "未核验线索：请人工核对招录对象、公告原文、附件、具体报名时刻及岗位差异；不得直接写入正式时间表。"})
    return True


def run(discovery=True, fixture_dir=None):
    config = read_json("sources.json", {})
    vetted = read_json("data.json", {})
    if not config.get("monitors") or not vetted.get("records"):
        raise ValueError("Missing source configuration or curated records")
    for item in config['monitors']:
        for endpoint in [item] + item.get('fallbacks', []):
            if not approved_candidate(endpoint['url']):
                raise ValueError('Configured source disallowed by government/JLU-only policy: ' + endpoint['url'])
            if endpoint.get('kind', item['kind']) not in ('article', 'listing'):
                raise ValueError('Invalid source kind')
    state = read_json("watch_state.json", {"articles": {}, "listings": {}, "search": {}})
    for k in ("articles", "listings", "search"):
        state.setdefault(k, {})
    queued = read_json("review_queue.json", {"updated": "", "candidates": []})
    queue = queued.setdefault("candidates", [])
    known = {c["id"] for c in queue}
    stamp = now_iso()
    errors, new = [], []
    successes = 0

    def content_at(url, fixture_name):
        if fixture_dir:
            return (Path(fixture_dir) / fixture_name).read_bytes()
        return fetch_bytes(url)

    degraded = []
    source_health = []
    for i, source in enumerate(config["monitors"]):
        primary_url = canonical_url(source['url'])
        attempts = [source] + source.get('fallbacks', [])
        failure_details = []
        selected = None
        for j, endpoint in enumerate(attempts):
            name = endpoint.get('name', source['name'])
            url = canonical_url(endpoint['url'])
            kind = endpoint.get('kind', source['kind'])
            try:
                # Fixtures may model a failing primary and successful backup independently.
                if fixture_dir and j:
                    content = content_at(url, f"monitor-{i}-fallback-{j}.html")
                else:
                    content = content_at(url, f"monitor-{i}.html")
                if kind == "article":
                    text = article_text(content)
                    digest = hashlib.sha256(text.encode()).hexdigest()
                    old = state["articles"].get(url)
                    if old and digest != old:
                        entry = {"province": source['province'], "title": "已收录公告原文内容变化：" + name,
                                 "url": url, "kind": "article_change", "source": name}
                        if queue_candidate(queue, known, entry, stamp, fingerprint=digest):
                            new.append(entry)
                    state["articles"][url] = digest
                else:
                    links = listing_links(content, url, source['province'], config['year'])
                    if j and source['kind'] == 'article' and not links:
                        raise ValueError('backup index contains no matching province/year notices; article not checked')
                    existing = set(state['listings'].get(url, []))
                    if url in state['listings']:
                        for entry in links:
                            if entry['url'] not in existing and queue_candidate(queue, known, entry, stamp):
                                new.append(entry)
                    state['listings'][url] = sorted(existing | {link['url'] for link in links})
                selected = {"name": name, "url": url, "kind": kind, "primary": j == 0}
                if j == 0:
                    successes += 1
                else:
                    degraded.append(source['name'] + ' → ' + name + ('（目录覆盖，非原文）' if kind != source['kind'] else ''))
                break
            except Exception as exc:
                failure_details.append(f"{name}: {type(exc).__name__}: {str(exc)[:140]}")
        if selected is None:
            errors.extend(failure_details)
            source_health.append({"name": source['name'], "state": "failed", "primaryUrl": primary_url, "failures": failure_details})
        elif not selected['primary']:
            # A fallback is genuinely degraded: never count it as a successful official source.
            limitation = ('；仅监测公告索引，公告正文及附件仍未读取' if selected['kind'] == 'listing' and source['kind'] == 'article' else '')
            errors.append(failure_details[0] + '；已启用备用来源，原定页面仍未成功检查' + limitation)
            source_health.append({"name": source['name'], "state": "fallback", "primaryUrl": primary_url,
                                  "used": selected, "failures": failure_details})
        else:
            source_health.append({"name": source['name'], "state": "ok", "primaryUrl": primary_url})

    discovery_count = 0
    if discovery and config.get("discovery", {}).get("enabled"):
        details = config["discovery"]
        for i, province in enumerate(details["provinces"]):
            query = details["query_template"].format(province=province)
            url = details["url_template"].format(query=quote(query))
            try:
                content = content_at(url, f"search-{i}.xml")
                results = parse_rss(content, province, config["year"])
                previous = set(state["search"].get(province, []))
                vetted_urls = {canonical_url(r["source"]) for r in vetted["records"] if r.get("source", "").startswith("https://")}
                has_government_record = any(r['province'] == province and source_tier(r['source']) == 'government' for r in vetted['records'])
                for entry in results:
                    # Search results are surfaced as unverified even on the first scan, except already published URLs.
                    if has_government_record and source_tier(entry['url']) == 'jlu_fallback':
                        continue
                    if entry["url"] not in vetted_urls and queue_candidate(queue, known, entry, stamp):
                        new.append(entry)
                state["search"][province] = sorted(previous | {entry["url"] for entry in results})
                discovery_count += 1
            except Exception as exc:
                errors.append(f"{province}搜索: {str(exc)[:180]}")

    queue.sort(key=lambda item: item["discovered"], reverse=True)
    queued["updated"] = stamp
    write_json("watch_state.json", state)
    write_json("review_queue.json", queued)
    status = {"checkedAt": stamp, "monitorsConfigured": len(config["monitors"]), "monitorsSucceeded": successes,
              "provincesConfigured": len(config["discovery"]["provinces"]) if discovery else 0,
              "searchesSucceeded": discovery_count, "newCandidates": len(new),
              "pendingCandidates": sum(x["status"] == "pending" for x in queue), "errors": errors[:80],
              "fallbacksUsed": len(degraded), "fallbackDetails": degraded, "sourceHealth": source_health,
              "warning": "自动检测只能发现线索，非实时、非完整覆盖；招聘条件和日期仅在人工核对后更新。"}
    write_json("monitor_status.json", status)
    report = [f"# 选调雷达监测报告 · {stamp}", "", f"新增待核验线索：{len(new)}；当前待核验总数：{status['pendingCandidates']}。",
              f"原定来源成功：{successes}/{len(config['monitors'])}；备用启用：{len(degraded)}；省份搜索成功：{discovery_count}/{status['provincesConfigured']}。", "",
              "## 本轮新增（不得视为已核验公告）", ""]
    if not new: report.append("无。")
    for entry in new[:100]:
        report.append(f"- [{entry['province']}] {entry['title']} — {entry['url']}")
    report += ["", "## 抓取错误", ""] + (["- " + e for e in errors] if errors else ["无。"])
    (ROOT / "monitor_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    (ROOT / "new_candidate_count.txt").write_text(str(len(new)), encoding="utf-8")
    print(f"Primary sources: {successes}/{len(config['monitors'])}; backups used={len(degraded)}; "
          f"regional searches={discovery_count}; new={len(new)} pending={status['pendingCandidates']} errors={len(errors)}")
    if errors:
        print("Errors (sources may block automation; not interpreted as no announcements):", *errors[:5], sep="\n - ")
    return status


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-discovery", action="store_true")
    parser.add_argument("--fixture-dir", help="Offline fixtures for local tests; no network requests")
    args = parser.parse_args()
    try:
        run(discovery=not args.skip_discovery, fixture_dir=args.fixture_dir)
    except Exception as exc:
        print(f"CONFIGURATION ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
