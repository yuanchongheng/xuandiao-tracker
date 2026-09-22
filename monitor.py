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
    """Exact allowlist for three tiers; a host is never evidence of article authenticity."""
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
        # The RSS *search provider* is separate from candidate announcement hosts.
        # A former unconditional source-domain check rejected all 31 Bing RSS feeds.
        original_host = urlsplit(canonical_url(url)).hostname
        final_host = urlsplit(canonical_url(response.url)).hostname
        if original_host in ("www.bing.com", "bing.com"):
            if final_host not in ("www.bing.com", "bing.com"):
                raise ValueError("Search feed redirected outside approved Bing domains")
        elif not approved_candidate(response.url):
            raise ValueError("Source redirected outside approved government/university domains")
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


def parse_rss(content, province, year, *, allowed_tiers=("government", "jlu_fallback")):
    """Search matches are leads only; prefer government > JLU > selected other universities.

    Third-tier links require province, year and recruitment keyword IN THE TITLE:
    an unrelated page mentioning another province in a sidebar is not a notice.
    """
    root = ElementTree.fromstring(content)
    results = []
    for item in root.findall(".//item"):
        title = re.sub(r"\s+", " ", item.findtext("title") or "").strip()[:160]
        url = (item.findtext("link") or "").strip()
        summary = BeautifulSoup(item.findtext("description") or "", "html.parser").get_text(" ", strip=True)[:300]
        tier = source_tier(url)
        if tier not in allowed_tiers:
            continue
        relevant = title if tier == 'university_third' else title + ' ' + summary
        if year not in relevant or province not in relevant or not KEYWORD.search(relevant):
            continue
        if not approved_candidate(url):
            continue
        try:
            url = canonical_url(url)
        except ValueError:
            continue
        results.append({"title": title, "province": province, "url": url, "kind": "search",
                        "source": "Bing RSS（搜索线索，未经人工核验）"})
    priority = ('government', 'jlu_fallback', 'university_third')
    for tier in priority:
        selected = [e for e in results if source_tier(e['url']) == tier]
        if selected:
            return list({e['url']: e for e in selected}.values())
    return []


def queue_candidate(queue, known, entry, timestamp, *, fingerprint=""):
    url = canonical_url(entry["url"])
    if source_tier(url) == "university_third":
        raise ValueError("Third-tier leads belong to third_sources.json, not review_queue.json")
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


def supplement_item(entry, timestamp):
    """A third-tier search hit is a separately displayed reference, not a review item."""
    url = canonical_url(entry['url'])
    if source_tier(url) != 'university_third':
        raise ValueError('Supplement must originate from an approved third-tier host')
    return {'id': hashlib.sha256(url.encode()).hexdigest()[:20],
            'province': entry['province'], 'title': entry['title'], 'url': url,
            'source': entry.get('source', ''), 'kind': entry.get('kind', 'search'),
            'discovered': entry.get('discovered') or timestamp,
            'sourceTier': 'university_third', 'sourceLabel': '其他高校官方就业网 · 补充参考（未核实）',
            'note': '其他高校发布的补充参考，仅确认搜索到该链接；尚未核实正文、附件、适用高校、报名及考试时间。不要套用其他学校的校内截止时间。'}


def store_supplement(items, urls, entry, timestamp):
    item = supplement_item(entry, timestamp)
    if item['url'] in urls:
        return False
    urls.add(item['url'])
    items.append(item)
    return True


def third_query_for_batch(third_config, province, timestamp):
    """Cycle through exact-host groups every six hours, avoiding oversized Bing queries."""
    groups = third_config['query_batches']
    hour = datetime.fromisoformat(timestamp).hour
    batch_index = (hour // 6) % len(groups)
    sites = ' OR '.join('site:' + host for host in groups[batch_index])
    return third_config['query_template'].format(province=province, sites=sites), batch_index


def run(discovery=True, fixture_dir=None):
    config = read_json("sources.json", {})
    vetted = read_json("data.json", {})
    if not config.get("monitors") or not vetted.get("records"):
        raise ValueError("Missing source configuration or curated records")
    for item in config['monitors']:
        for endpoint in [item] + item.get('fallbacks', []):
            if not approved_candidate(endpoint['url']):
                raise ValueError('Configured source disallowed by three-tier policy: ' + endpoint['url'])
            if endpoint.get('kind', item['kind']) not in ('article', 'listing'):
                raise ValueError('Invalid source kind')
    third_config = config.get('discovery', {}).get('third_source', {})
    if third_config.get('enabled'):
        hosts = third_config.get('hosts', [])
        batches = third_config.get('query_batches', [])
        if (not hosts or not batches or len(set(hosts)) != len(hosts) or
                sorted(host for batch in batches for host in batch) != sorted(hosts)):
            raise ValueError('Third-tier hosts and query batches must match without duplicates')
        if any(source_tier('https://' + host + '/') != 'university_third' for host in hosts):
            raise ValueError('Third-tier search host is not on the reviewed allowlist')
        if any(source_tier(index['url']) != 'university_third' or
               urlsplit(index['url']).hostname not in config.get('sourcePolicy', {}).get('otherUniversityHosts', [])
               for index in third_config.get('indexes', [])):
            raise ValueError('Third-tier index host is not on the approved host list')
    state = read_json("watch_state.json", {"articles": {}, "listings": {}, "search": {}})
    for k in ("articles", "listings", "search"):
        state.setdefault(k, {})
    queued = read_json("review_queue.json", {"updated": "", "candidates": []})
    queue = queued.setdefault("candidates", [])
    third_feed = read_json("third_sources.json", {"updated": "", "items": []})
    supplements = third_feed.setdefault("items", [])
    stamp = now_iso()
    supplement_urls = {c['url'] for c in supplements if source_tier(c.get('url', '')) == 'university_third'}
    # Migrate historical third-tier records from older review_queue.json versions.
    # This is safe to repeat, preserves the original discovery time and never
    # presents migrated school announcements as verified official dates.
    remaining = []
    for entry in queue:
        if source_tier(entry.get('url', '')) == 'university_third':
            store_supplement(supplements, supplement_urls, entry, stamp)
        else:
            remaining.append(entry)
    queue[:] = remaining
    known = {c["id"] for c in queue}
    errors, new, supplement_new = [], [], []
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
    third_attempted = 0
    third_succeeded = 0
    third_found = 0
    third_index_success = 0
    third_index_attempted = 0
    third_index_links_found = 0
    third_active_batch = None
    third_batch_hosts = []
    eligible_for_index = set()
    # A listing backup does not prove the article was retrieved. When a source
    # is failed or only covered by a listing, third-tier search may provide a
    # lead even if Bing lists the inaccessible government original.
    healthy_by_province = set()
    deficient_provinces = set()
    for source, health in zip(config['monitors'], source_health):
        province = source['province']
        if province == '全国':
            continue
        if health['state'] == 'ok' or (
            health['state'] == 'fallback' and health.get('used', {}).get('kind') == 'article'
        ):
            healthy_by_province.add(province)
        else:
            deficient_provinces.add(province)
    if discovery and config.get('discovery', {}).get('enabled'):
        details = config['discovery']
        third = details.get('third_source', {})
        if third.get('enabled'):
            _, third_active_batch = third_query_for_batch(third, '全国', stamp)
            third_batch_hosts = third['query_batches'][third_active_batch]
        vetted_urls = {canonical_url(r['source']) for r in vetted['records'] if r.get('source', '').startswith('https://')}
        for i, province in enumerate(details['provinces']):
            query = details['query_template'].format(province=province)
            url = details['url_template'].format(query=quote(query))
            primary_results = []
            primary_search_ok = False
            try:
                content = content_at(url, f'search-{i}.xml')
                primary_results = parse_rss(content, province, config['year'])
                primary_search_ok = True
                previous = set(state['search'].get(province, []))
                has_gov = any(r['province'] == province and source_tier(r['source']) == 'government' for r in vetted['records'])
                for entry in primary_results:
                    if has_gov and source_tier(entry['url']) == 'jlu_fallback':
                        continue
                    if entry['url'] not in vetted_urls and queue_candidate(queue, known, entry, stamp):
                        new.append(entry)
                state['search'][province] = sorted(previous | {entry['url'] for entry in primary_results})
                discovery_count += 1
            except Exception as exc:
                errors.append(f'{province}一级/二级搜索: {str(exc)[:180]}')
            # An index may still surface leads when Bing itself is unavailable;
            # neither an inaccessible government site nor a search error means
            # that the official announcement does not exist.
            eligible = (third.get('enabled') and province not in healthy_by_province
                        and (not primary_results or province in deficient_provinces))
            if not eligible:
                continue
            eligible_for_index.add(province)
            if not primary_search_ok:
                continue  # Don't call the same broken Bing endpoint twice.
            third_attempted += 1
            alt_query, _ = third_query_for_batch(third, province, stamp)
            alt_url = details['url_template'].format(query=quote(alt_query))
            try:
                alt_content = content_at(alt_url, f'third-search-{i}.xml')
                alt_results = parse_rss(alt_content, province, config['year'],
                                        allowed_tiers=('university_third',))
                third_succeeded += 1
                third_found += len(alt_results)
                state.setdefault('third_search', {})[province] = sorted(
                    set(state.get('third_search', {}).get(province, [])) | {entry['url'] for entry in alt_results})
                for entry in alt_results:
                    if entry['url'] not in vetted_urls and store_supplement(supplements, supplement_urls, entry, stamp):
                        supplement_new.append(entry)
            except Exception as exc:
                errors.append(f'{province}第三来源搜索: {str(exc)[:180]}')

        # Directly check a small, vetted set of university recruitment indexes
        # ONCE per run (not once per province). This supplements RSS without
        # crawling the candidate articles or guessing their registration dates.
        if eligible_for_index:
            for j, index in enumerate(third.get('indexes', [])):
                third_index_attempted += 1
                try:
                    index_url = canonical_url(index['url'])
                    if source_tier(index_url) != 'university_third':
                        raise ValueError('Index is not an approved third-tier university site')
                    raw = content_at(index_url, f'third-index-{j}.html')
                    links = listing_links(raw, index_url, '全国', config['year'])
                    third_index_success += 1
                    third_index_links_found += len([entry for entry in links if entry['province'] in eligible_for_index])
                    # Titles found on an index are leads, not proof that the
                    # underlying article or attachment is accessible or valid.
                    for entry in links:
                        if entry['province'] not in eligible_for_index:
                            continue
                        if entry['url'] in vetted_urls:
                            continue
                        entry['source'] = index['name'] + '（高校公告索引，仅供补充参考）'
                        if store_supplement(supplements, supplement_urls, entry, stamp):
                            supplement_new.append(entry)
                except Exception as exc:
                    errors.append(f"第三来源目录 {index.get('name',j)}: {str(exc)[:180]}")

    queue.sort(key=lambda item: item["discovered"], reverse=True)
    supplements.sort(key=lambda item: item.get('discovered', ''), reverse=True)
    queued["updated"] = stamp
    third_feed['updated'] = stamp
    write_json("watch_state.json", state)
    write_json("review_queue.json", queued)
    write_json("third_sources.json", third_feed)
    status = {"checkedAt": stamp, "monitorsConfigured": len(config["monitors"]), "monitorsSucceeded": successes,
              "provincesConfigured": len(config["discovery"]["provinces"]) if discovery else 0,
              "searchesSucceeded": discovery_count, "thirdSearchesAttempted": third_attempted,
              "thirdSearchesSucceeded": third_succeeded, "thirdLinksFound": third_found,
              "thirdIndexesSucceeded": third_index_success, "thirdIndexesAttempted": third_index_attempted,
              "thirdIndexLinksFound": third_index_links_found,
              "thirdSchoolsConfigured": len(config.get("discovery", {}).get("third_source", {}).get("hosts", [])),
              "thirdBatchCount": len(config.get("discovery", {}).get("third_source", {}).get("query_batches", [])),
              "thirdBatchActive": third_active_batch + 1 if third_active_batch is not None else None,
              "thirdHostsInThisRun": third_batch_hosts,
              "newCandidates": len(new), "supplementalNew": len(supplement_new),
              "supplementalTotal": len(supplements),
              "pendingCandidates": sum(x["status"] == "pending" for x in queue), "errors": errors[:80],
              "fallbacksUsed": len(degraded), "fallbackDetails": degraded, "sourceHealth": source_health,
              "warning": "自动检测只能发现线索，非实时、非完整覆盖；招聘条件和日期仅在人工核对后更新。"}
    write_json("monitor_status.json", status)
    report = [f"# 选调雷达监测报告 · {stamp}", "", f"新增待核验线索：{len(new)}；当前待核验总数：{status['pendingCandidates']}。",
              f"原定来源成功：{successes}/{len(config['monitors'])}；备用启用：{len(degraded)}；省份搜索成功：{discovery_count}/{status['provincesConfigured']}。", "",
              f"第三来源检索：{third_succeeded}/{third_attempted}；公告目录：{third_index_success}/{third_index_attempted}；RSS匹配：{third_found}（只作补充参考）", "",
              "## 本轮政府/吉林大学新增待核验线索", ""]
    if not new: report.append("无。")
    for entry in new[:100]:
        report.append(f"- [{entry['province']}] {entry['title']} — {entry['url']}")
    report += ["", "## 本轮其他高校补充来源（独立展示，未核验）", ""]
    if not supplement_new: report.append("无。")
    for entry in supplement_new[:100]:
        report.append(f"- [{entry['province']}] {entry['title']} — {entry['url']}")
    report += ["", "## 抓取错误", ""] + (["- " + e for e in errors] if errors else ["无。"])
    (ROOT / "monitor_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    (ROOT / "new_candidate_count.txt").write_text(str(len(new)), encoding="utf-8")
    print(f"Primary sources: {successes}/{len(config['monitors'])}; backups used={len(degraded)}; "
          f"regional searches={discovery_count}; third batch={third_active_batch + 1 if third_active_batch is not None else 0}/{len(config.get('discovery', {}).get('third_source', {}).get('query_batches', []))}; third searches={third_succeeded}/{third_attempted} "
          f"third leads={third_found + third_index_links_found}; third indexes={third_index_success}/{third_index_attempted}; "
          f"supplemental new={len(supplement_new)} total={len(supplements)}; new={len(new)} pending={status['pendingCandidates']} errors={len(errors)}")
    if errors:
        print("Errors (sources may block automation; not interpreted as no announcements):", *errors[:5], sep="\n - ")
        search_errors = [err for err in errors if "搜索:" in err]
        if search_errors:
            print(f"Regional search failures: {len(search_errors)}; examples:", *search_errors[:2], sep="\n - ")
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
