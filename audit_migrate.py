#!/usr/bin/env python3
"""One-time, idempotent repository migration produced by a code audit.

This file exists so large source files can be patched safely inside CI without
replacing them wholesale through the GitHub contents API. Every transformation
is idempotent and fails loudly when an expected legacy pattern is present in an
unexpected form. After the migration is committed successfully this script can
be removed from the workflow/repository.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def write_if_changed(path: Path, text: str) -> bool:
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    if old == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def replace(text: str, old: str, new: str, *, label: str, required: bool = False) -> str:
    if old in text:
        return text.replace(old, new)
    if new in text:
        return text
    if required:
        raise RuntimeError(f"migration pattern missing: {label}")
    return text


def patch_monitor() -> bool:
    path = ROOT / "monitor.py"
    text = path.read_text(encoding="utf-8")
    old = text

    text = replace(
        text,
        "from source_policy import source_label, source_tier\n",
        "from source_policy import source_label, source_tier\nfrom province_utils import PROVINCES, province_from_title, normalized_notice_title\n",
        label="monitor province utils import",
        required=True,
    )
    text = re.sub(r"^PROVINCES = \([^\n]+\)\n", "", text, count=1, flags=re.MULTILINE)

    text = replace(
        text,
        "        parent_text = (link.parent.get_text(\" \", strip=True)[:260] if link.parent and link.parent.name in (\"li\", \"tr\", \"div\", \"p\", \"td\") and len(link.parent.select(\"a\")) == 1 else title)\n",
        "        parent_text = (link.parent.get_text(\" \", strip=True)[:260] if link.parent and link.parent.name in (\"li\", \"tr\", \"div\", \"p\", \"td\") and len(link.parent.select(\"a\")) == 1 else title)\n        display_title = title if year in title and KEYWORD.search(title) else parent_text[:160]\n",
        label="listing display title",
        required=True,
    )
    text = replace(
        text,
        "            detected_province = next((p for p in PROVINCES if p in title or p in parent_text), None)\n",
        "            detected_province = province_from_title(display_title) or province_from_title(parent_text)\n",
        label="national listing province detection",
        required=True,
    )
    text = replace(
        text,
        '        out[url] = {"title": title or parent_text[:120], "province": detected_province, "url": url, "source": base_url, "kind": "listing"}\n',
        '        out[url] = {"title": display_title or parent_text[:120], "province": detected_province, "url": url, "source": base_url, "kind": "listing"}\n',
        label="listing output title",
        required=True,
    )
    text = replace(
        text,
        "        relevant = title if tier == 'university_third' else title + ' ' + summary\n",
        "        # JLU notices are auto-published, so JLU relevance must be proven by the title itself.\n        # Government results still require manual review and may use the search snippet as supporting context.\n        relevant = title if tier in ('jlu_fallback', 'university_third') else title + ' ' + summary\n",
        label="rss JLU title scope",
        required=True,
    )
    old_priority = """    priority = ('government', 'jlu_fallback', 'university_third')
    for tier in priority:
        selected = [e for e in results if source_tier(e['url']) == tier]
        if selected:
            return list({e['url']: e for e in selected}.values())
    return []
"""
    new_priority = """    priority = {'government': 0, 'jlu_fallback': 1, 'university_third': 2}
    # Distinct notices can coexist at different tiers (for example a province-wide
    # government notice and a university-specific JLU notice). Never discard the
    # lower tier merely because any higher-tier result exists.
    results.sort(key=lambda e: (priority.get(source_tier(e['url']), 9), e['url']))
    deduped = {}
    for entry in results:
        deduped.setdefault(entry['url'], entry)
    return list(deduped.values())
"""
    text = replace(text, old_priority, new_priority, label="rss all-tier retention", required=True)

    old_note = '                  "note": "未核验线索：请人工核对招录对象、公告原文、附件、具体报名时刻及岗位差异；不得直接写入正式时间表。"})\n'
    new_note = '                  "note": ("吉林大学就业网线索：按本站规则自动进入正式数据；时间字段仅从明确正文提取，未明确内容不猜测。" if source_tier(url) == "jlu_fallback" else "未核验政府线索：请人工核对招录对象、公告原文、附件、具体报名时刻及岗位差异后再更新正式数据。")})\n'
    text = replace(text, old_note, new_note, label="queue tier-aware note", required=True)

    text = replace(
        text,
        '    """Cycle through exact-host groups every six hours, avoiding oversized Bing queries."""\n',
        '    """Cycle through exact-host groups every three hours, matching the site schedule."""\n',
        label="third batch doc",
        required=True,
    )
    text = replace(
        text,
        "    batch_index = (hour // 6) % len(groups)\n",
        "    batch_index = (hour // 3) % len(groups)\n",
        label="third batch cadence",
        required=True,
    )

    old_listing = """                    existing = set(state['listings'].get(url, []))
                    if url in state['listings']:
                        for entry in links:
                            if entry['url'] not in existing and queue_candidate(queue, known, entry, stamp):
                                new.append(entry)
                    state['listings'][url] = sorted(existing | {link['url'] for link in links})
"""
    new_listing = """                    existing = set(state['listings'].get(url, []))
                    had_baseline = url in state['listings']
                    # A newly configured national JLU index is trusted enough to surface its
                    # existing 2027 links immediately. Otherwise a deleted/reset baseline
                    # could silently hide already-published JLU notices until another source
                    # happens to find them.
                    initial_jlu_index = (not had_baseline and source['province'] == '全国'
                                         and source_tier(url) == 'jlu_fallback')
                    if had_baseline or initial_jlu_index:
                        for entry in links:
                            if entry['url'] not in existing and queue_candidate(queue, known, entry, stamp):
                                new.append(entry)
                    state['listings'][url] = sorted(existing | {link['url'] for link in links})
"""
    text = replace(text, old_listing, new_listing, label="initial JLU index coverage", required=True)

    old_search = """                previous = set(state['search'].get(province, []))
                has_gov = any(r['province'] == province and source_tier(r['source']) == 'government' for r in vetted['records'])
                for entry in primary_results:
                    if has_gov and source_tier(entry['url']) == 'jlu_fallback':
                        continue
                    if entry['url'] not in vetted_urls and queue_candidate(queue, known, entry, stamp):
                        new.append(entry)
"""
    new_search = """                previous = set(state['search'].get(province, []))
                government_keys = {
                    normalized_notice_title(r['title']) for r in vetted['records']
                    if r['province'] == province and source_tier(r['source']) == 'government'
                } | {
                    normalized_notice_title(e['title']) for e in primary_results
                    if source_tier(e['url']) == 'government'
                }
                for entry in primary_results:
                    # Prefer government only for the same normalized announcement title;
                    # do not suppress a distinct university-specific JLU notice merely
                    # because some government notice exists for that province.
                    if (source_tier(entry['url']) == 'jlu_fallback'
                            and normalized_notice_title(entry['title']) in government_keys):
                        continue
                    if entry['url'] not in vetted_urls and queue_candidate(queue, known, entry, stamp):
                        new.append(entry)
"""
    text = replace(text, old_search, new_search, label="distinct JLU result retention", required=True)

    return write_if_changed(path, text) if text != old else False


def patch_jlu_auto_publish() -> bool:
    path = ROOT / "jlu_auto_publish.py"
    text = path.read_text(encoding="utf-8")
    old = text
    needle = """    remaining_new = sum(
        c.get("status") == "pending" and (not checked or c.get("discovered") == checked)
        for c in queue
    )

    write_json("data.json", data)
"""
    repl = """    remaining_new = sum(
        c.get("status") == "pending" and (not checked or c.get("discovered") == checked)
        for c in queue
    )
    # Keep the status card consistent with what still requires action after JLU
    # candidates have been auto-published. Previously newCandidates could say 1
    # while pendingCandidates correctly said 0.
    status["newCandidates"] = remaining_new

    write_json("data.json", data)
"""
    text = replace(text, needle, repl, label="JLU status candidate count", required=True)
    return write_if_changed(path, text) if text != old else False


def patch_tests() -> bool:
    path = ROOT / "tests" / "test_monitor.py"
    text = path.read_text(encoding="utf-8")
    old = text

    text = replace(text, "for hour in (2, 8, 14, 20):", "for hour in (2, 5, 8, 11):", label="batch test hours", required=True)
    text = replace(text, "self.assertEqual(batch, hour//6)", "self.assertEqual(batch, (hour//3) % len(cfg['query_batches']))", label="batch test cadence", required=True)
    text = replace(
        text,
        "self.assertEqual([r['url'] for r in monitor.parse_rss(rss.replace('</channel>', official+'</channel>').encode(), '上海', '2027')], ['https://rsj.sh.gov.cn/a'])",
        "self.assertEqual([r['url'] for r in monitor.parse_rss(rss.replace('</channel>', official+'</channel>').encode(), '上海', '2027')], ['https://rsj.sh.gov.cn/a', jlu])",
        label="rss mixed-tier expectation",
        required=True,
    )

    old_loop = """        index_total = len(json.loads((old_root / 'sources.json').read_text(encoding='utf8'))['discovery']['third_source']['indexes'])
        for i in range(index_total):
"""
    new_loop = """        config = json.loads((old_root / 'sources.json').read_text(encoding='utf8'))
        self.monitor_count = len(config['monitors'])
        index_total = len(config['discovery']['third_source']['indexes'])
        for i in range(index_total):
"""
    text = replace(text, old_loop, new_loop, label="dynamic test monitor config", required=True)
    text = replace(text, "        for i in range(8):\n", "        for i in range(self.monitor_count):\n", label="dynamic monitor fixtures", required=True)
    text = text.replace("self.assertEqual(first['monitorsSucceeded'], 8)", "self.assertEqual(first['monitorsSucceeded'], self.monitor_count)")
    text = text.replace("self.assertEqual(status['monitorsSucceeded'], 7)", "self.assertEqual(status['monitorsSucceeded'], self.monitor_count - 1)")
    text = text.replace("self.assertEqual(status['monitorsSucceeded'],7)", "self.assertEqual(status['monitorsSucceeded'], self.monitor_count - 1)")

    return write_if_changed(path, text) if text != old else False


def patch_readme() -> bool:
    path = ROOT / "README.md"
    text = path.read_text(encoding="utf-8")
    old = text
    text = text.replace(
        "每天北京时间 **02:17、08:17、14:17、20:17** 计划运行",
        "每天北京时间 **02:17、05:17、08:17、11:17、14:17、17:17、20:17、23:17** 计划运行",
    )
    text = text.replace(
        "工作流：检测7个既有文章和1个吉林大学索引的变化",
        "工作流：检查已配置的一、二级公告来源和吉林大学全国索引的变化",
    )
    text = text.replace(
        "RSS（政府官网/JLU 仅作候选）→ 写入待核验 `review_queue.json`",
        "RSS（政府官网/JLU 用于发现）→ 政府线索进入 `review_queue.json`，吉林大学线索按规则自动发布",
    )
    return write_if_changed(path, text) if text != old else False


def patch_index_copy() -> bool:
    path = ROOT / "index.html"
    text = path.read_text(encoding="utf-8")
    old = text
    text = text.replace(
        "自动发现与正式数据分开，监测失败不等于没有公告；管理员核验后才更新日历。",
        "自动发现与正式数据分开，监测失败不等于没有公告；政府来源候选需人工核验，吉林大学就业网通知按本站规则自动入库并仅提取正文明确时间。",
    )
    text = text.replace(
        "17所高校分4批、随每天四次定时任务轮换搜索；另有8个目录每轮尝试检查。",
        "17所高校分4批、随每天八次定时任务每3小时轮换搜索；另有8个目录每轮尝试检查。",
    )
    return write_if_changed(path, text) if text != old else False


def rewrite_start_policy() -> bool:
    path = ROOT / "apply_start_date_policy.py"
    content = '''#!/usr/bin/env python3
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
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
    print(f"start-date policy: migrated_records={changed}")


if __name__ == "__main__":
    main()
'''
    return write_if_changed(path, content)


def write_new_modules() -> list[str]:
    changed = []
    province_utils = '''#!/usr/bin/env python3
"""Shared province and notice-title normalization helpers."""
from __future__ import annotations
import re

PROVINCES = ('北京', '天津', '河北', '山西', '内蒙古', '辽宁', '吉林', '黑龙江', '上海', '江苏', '浙江', '安徽', '福建', '江西', '山东', '河南', '湖北', '湖南', '广东', '广西', '海南', '重庆', '四川', '贵州', '云南', '西藏', '陕西', '甘肃', '青海', '宁夏', '新疆')
ADMIN_FORMS = {
    '北京': ('北京市',), '天津': ('天津市',), '河北': ('河北省',), '山西': ('山西省',),
    '内蒙古': ('内蒙古自治区',), '辽宁': ('辽宁省',), '吉林': ('吉林省',), '黑龙江': ('黑龙江省',),
    '上海': ('上海市',), '江苏': ('江苏省',), '浙江': ('浙江省',), '安徽': ('安徽省',),
    '福建': ('福建省',), '江西': ('江西省',), '山东': ('山东省',), '河南': ('河南省',),
    '湖北': ('湖北省',), '湖南': ('湖南省',), '广东': ('广东省',), '广西': ('广西壮族自治区',),
    '海南': ('海南省',), '重庆': ('重庆市',), '四川': ('四川省',), '贵州': ('贵州省',),
    '云南': ('云南省',), '西藏': ('西藏自治区',), '陕西': ('陕西省',), '甘肃': ('甘肃省',),
    '青海': ('青海省',), '宁夏': ('宁夏回族自治区',), '新疆': ('新疆维吾尔自治区',),
}


def _clean(value: str) -> str:
    text = re.sub(r'[\\u200b\\ufeff]', '', str(value or '')).strip()
    text = re.sub(r'^[\\s\\[\\]【】（）()「」『』《》〈〉·•—–_-]*', '', text)
    text = re.sub(r'^(?:置顶|招聘信息|通知公告)[：:\\s-]*', '', text)
    return text.strip()


def province_from_title(value: str):
    """Infer the target jurisdiction without mistaking a university name for it.

    Strong signals only: title prefix, a province immediately following the year,
    or a full administrative name such as 重庆市/四川省. This intentionally avoids
    matching bare 吉林 inside 吉林大学 when the actual target is 重庆.
    """
    text = _clean(value)
    if not text:
        return None
    for province in sorted(PROVINCES, key=len, reverse=True):
        forms = ADMIN_FORMS.get(province, ())
        if text.startswith((province,) + forms):
            return province
    year_match = re.search(r'20\\d{2}(?:年|届|年度)?[^省市区]{0,8}(' + '|'.join(map(re.escape, sorted(PROVINCES, key=len, reverse=True))) + r')', text)
    if year_match:
        return year_match.group(1)
    hits = []
    for province, forms in ADMIN_FORMS.items():
        for form in forms:
            pos = text.find(form)
            if pos >= 0:
                hits.append((pos, -len(form), province))
    if hits:
        hits.sort()
        return hits[0][2]
    return None


def normalized_notice_title(value: str) -> str:
    text = _clean(value)
    text = re.sub(r'[\\s·•—–_()（）\\[\\]【】《》“”‘’：:，,。.!！?？/\\\\-]+', '', text)
    text = re.sub(r'(?:公告|简章|通知)$', '', text)
    return text
'''
    if write_if_changed(ROOT / "province_utils.py", province_utils):
        changed.append("province_utils.py")

    data_hygiene = '''#!/usr/bin/env python3
"""Idempotent data cleanup after discovery/auto-publication."""
from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from province_utils import province_from_title

ROOT = Path(__file__).resolve().parent
TZ = timezone(timedelta(hours=8))
GZ_OLD = 'https://jdjyw.jlu.edu.cn/portal/article/details?id=1f6b210e15d944a6988d7af33b88cc00'
GZ_NEW = 'https://jdjywpt.jlu.edu.cn/portal/xdsgz/article/details?id=7e49102ce2324d3ebd3c5ff24502892d'


def load(name, default):
    p = ROOT / name
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default


def save(name, obj):
    (ROOT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\\n', encoding='utf-8')


def normalize_provinces(items):
    changed = 0
    for item in items:
        detected = province_from_title(item.get('title', ''))
        if detected and item.get('province') != detected:
            item['province'] = detected
            changed += 1
    return changed


def merge_guizhou_duplicate(data, queue):
    records = data.get('records', [])
    matches = [r for r in records if r.get('source') in (GZ_OLD, GZ_NEW)]
    if not matches:
        return 0
    structured = next((r for r in matches if r.get('start') and r.get('deadlines')), matches[0])
    desired = dict(structured)
    desired.update({
        'province': '贵州',
        'title': '贵州省2027年度党政机关定向选调和省管企业招聘优秀大学毕业生公告',
        'type': '定向选调',
        'published': '2026-09-20',
        'source': GZ_NEW,
        'sourceName': '吉林大学就业网转载公告（备用）',
        'sourceType': '吉林大学备用',
        'sourceTier': 'jlu_fallback',
        'verified': '2026-09-22',
        'notes': '报名10月13日9:00开始；省级党政机关/省管企业10月19日14:00截止，市（州）级10月21日14:00截止，县级10月23日14:00截止。不同岗位截止不同，不能把最晚截止时间套用于全部职位。',
    })
    desired.pop('autoPublished', None)
    desired.pop('publishedEstimated', None)
    desired.pop('discoveredAt', None)
    desired.pop('autoParsedAt', None)
    desired.pop('autoParsedFrom', None)
    # Replace every known duplicate copy with one canonical structured record.
    first_index = min(records.index(r) for r in matches)
    records[:] = [r for r in records if r.get('source') not in (GZ_OLD, GZ_NEW)]
    records.insert(min(first_index, len(records)), desired)
    for candidate in queue.get('candidates', []):
        if candidate.get('url') in (GZ_OLD, GZ_NEW):
            candidate['province'] = '贵州'
            candidate['status'] = 'auto_covered'
            candidate['note'] = '与已结构化发布的贵州省2027年度党政机关定向选调和省管企业招聘公告为同一公告，已合并，避免重复卡片。'
    return max(1, len(matches) - 1)


def main():
    data = load('data.json', {'records': []})
    queue = load('review_queue.json', {'candidates': []})
    third = load('third_sources.json', {'items': []})
    sources = load('sources.json', {})
    changed = 0
    changed += normalize_provinces(data.get('records', []))
    changed += normalize_provinces(queue.get('candidates', []))
    changed += normalize_provinces(third.get('items', []))

    for r in data.get('records', []):
        if r.pop('startTimeUnknown', None):
            r['startDateOnly'] = True
            changed += 1
        if r.get('province') == '四川' and '具体开放时刻待核对' in r.get('notes', ''):
            r['notes'] = r['notes'].replace('报名公告仅写10月8日开始，具体开放时刻待核对；', '报名公告仅写10月8日开始，未列具体开放时刻；')
            changed += 1

    changed += merge_guizhou_duplicate(data, queue)

    third_cfg = sources.get('discovery', {}).get('third_source', {})
    wanted_policy = '每次仅检索一个批次，每3小时轮换，共4个批次；连续4轮约12小时覆盖全部17校搜索批次；直连索引每轮单独检查。'
    if third_cfg and third_cfg.get('batch_policy') != wanted_policy:
        third_cfg['batch_policy'] = wanted_policy
        changed += 1

    if changed:
        stamp = datetime.now(TZ).isoformat(timespec='seconds')
        data['asOf'] = stamp
        queue['updated'] = stamp
        third['updated'] = stamp
    save('data.json', data)
    save('review_queue.json', queue)
    save('third_sources.json', third)
    save('sources.json', sources)
    print(f'data hygiene: changes={changed}')


if __name__ == '__main__':
    main()
'''
    if write_if_changed(ROOT / "data_hygiene.py", data_hygiene):
        changed.append("data_hygiene.py")

    validate_extra = '''#!/usr/bin/env python3
"""Cross-file invariants not covered by build.py."""
import json
from pathlib import Path
from province_utils import PROVINCES, province_from_title, normalized_notice_title
from source_policy import source_tier

ROOT = Path(__file__).resolve().parent


def load(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8'))


def main():
    data = load('data.json')
    queue = load('review_queue.json')
    third = load('third_sources.json')
    sources = load('sources.json')
    seen_sources = set()
    seen_titles = set()
    for r in data.get('records', []):
        for field in ('type', 'count', 'sourceName', 'sourceType'):
            if not isinstance(r.get(field), str) or not r[field].strip():
                raise ValueError(f'missing {field}: {r.get("title")}')
        inferred = province_from_title(r.get('title', ''))
        if inferred and inferred != r.get('province'):
            raise ValueError(f'province/title mismatch: {r.get("province")} vs {inferred}: {r.get("title")}')
        if r.get('autoPublished') and source_tier(r.get('source', '')) != 'jlu_fallback':
            raise ValueError('autoPublished is only allowed for JLU sources')
        if r.get('publishedEstimated') and not r.get('autoPublished'):
            raise ValueError('publishedEstimated requires autoPublished')
        if r.get('startTimeUnknown'):
            raise ValueError('legacy startTimeUnknown must be migrated to startDateOnly')
        if r.get('startDateOnly') and not str(r.get('start', '')).endswith('T00:00:00+08:00'):
            raise ValueError('startDateOnly requires the midnight date sentinel')
        source = r.get('source')
        if source in seen_sources:
            raise ValueError('duplicate formal source URL: ' + source)
        seen_sources.add(source)
        title_key = (r.get('province'), normalized_notice_title(r.get('title', '')))
        if title_key in seen_titles:
            raise ValueError('duplicate normalized formal title: ' + str(title_key))
        seen_titles.add(title_key)

    for c in queue.get('candidates', []):
        inferred = province_from_title(c.get('title', ''))
        if inferred and inferred != c.get('province'):
            raise ValueError('queue province/title mismatch: ' + c.get('title', ''))
        if c.get('status') == 'pending' and source_tier(c.get('url', '')) == 'jlu_fallback':
            raise ValueError('pending JLU candidate remained after auto-publish pipeline')

    for item in third.get('items', []):
        if source_tier(item.get('url', '')) != 'university_third':
            raise ValueError('third_sources contains a non-third-tier URL')

    discovery = sources.get('discovery', {})
    if tuple(discovery.get('provinces', [])) != PROVINCES:
        raise ValueError('discovery province list differs from canonical 31-region list')
    monitors = sources.get('monitors', [])
    urls = [m.get('url') for m in monitors]
    if len(urls) != len(set(urls)):
        raise ValueError('duplicate monitor URLs')
    third_cfg = discovery.get('third_source', {})
    hosts = third_cfg.get('hosts', [])
    flattened = [h for batch in third_cfg.get('query_batches', []) for h in batch]
    if sorted(hosts) != sorted(flattened) or len(flattened) != len(set(flattened)):
        raise ValueError('third-source query batches do not exactly cover configured hosts')
    print(f'PASS extra invariants: {len(data.get("records", []))} records, {len(monitors)} monitors')


if __name__ == '__main__':
    main()
'''
    if write_if_changed(ROOT / "validate_extra.py", validate_extra):
        changed.append("validate_extra.py")

    regression_tests = '''import unittest
import monitor
from province_utils import province_from_title


class AuditRegressionTests(unittest.TestCase):
    def test_chongqing_title_is_not_misclassified_as_jilin(self):
        title = '重庆市面向吉林大学定向选调 2027届急需紧缺专业应届优秀大学毕业生公告'
        self.assertEqual(province_from_title(title), '重庆')

    def test_year_prefix_province_is_detected(self):
        self.assertEqual(province_from_title('2027届四川定向选调公告'), '四川')

    def test_jlu_search_requires_relevant_title_not_only_snippet(self):
        rss = """<rss><channel><item><title>吉林大学就业信息更新</title><description>重庆2027定向选调公告</description><link>https://jdjywpt.jlu.edu.cn/portal/xdsgz/article/details?id=x</link></item></channel></rss>"""
        self.assertEqual(monitor.parse_rss(rss.encode(), '重庆', '2027'), [])

    def test_distinct_government_and_jlu_results_are_both_retained(self):
        rss = """<rss><channel><item><title>重庆2027定向选调公告</title><link>https://www.cq.gov.cn/a</link></item><item><title>重庆2027面向吉林大学定向选调公告</title><link>https://jdjywpt.jlu.edu.cn/portal/xdsgz/article/details?id=x</link></item></channel></rss>"""
        urls = [x['url'] for x in monitor.parse_rss(rss.encode(), '重庆', '2027')]
        self.assertEqual(urls, ['https://www.cq.gov.cn/a', 'https://jdjywpt.jlu.edu.cn/portal/xdsgz/article/details?id=x'])


if __name__ == '__main__':
    unittest.main()
'''
    if write_if_changed(ROOT / "tests" / "test_regressions.py", regression_tests):
        changed.append("tests/test_regressions.py")
    return changed


def main():
    changed = []
    for label, func in (
        ("monitor.py", patch_monitor),
        ("jlu_auto_publish.py", patch_jlu_auto_publish),
        ("tests/test_monitor.py", patch_tests),
        ("README.md", patch_readme),
        ("index.html", patch_index_copy),
        ("apply_start_date_policy.py", rewrite_start_policy),
    ):
        if func():
            changed.append(label)
    changed.extend(write_new_modules())
    print("audit migration changed: " + (", ".join(changed) if changed else "nothing"))


if __name__ == "__main__":
    main()
