#!/usr/bin/env python3
"""Idempotent cross-file data cleanup after discovery/auto-publication."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

from province_utils import province_from_title

ROOT = Path(__file__).resolve().parent
TZ = timezone(timedelta(hours=8))
GZ_OLD = 'https://jdjyw.jlu.edu.cn/portal/article/details?id=1f6b210e15d944a6988d7af33b88cc00'
GZ_NEW = 'https://jdjywpt.jlu.edu.cn/portal/xdsgz/article/details?id=7e49102ce2324d3ebd3c5ff24502892d'
JX_URL = 'https://jdjywpt.jlu.edu.cn/portal/xdsgz/article/details?id=c9a25f39746844109e664b0393355256'
GX_URL = 'https://jdjywpt.jlu.edu.cn/portal/xdsgz/article/details?id=1a930e337de649f1a7bb204e4b06e01c'
JL_URL = 'https://jdjywpt.jlu.edu.cn/portal/xdsgz/article/details?id=d1f6aa165da5437e811e3f64348079a3'
PERSONAL_MARKER = '【你的资格】'
NOTICE_MARKER = '【公告条件】'
PERSONAL_POLICY = (
    '其他高校已发布但吉林大学暂未发现对应公告的省份仍进入总选调信息，并按个人口径标记为当前不可报；'
    '后续吉林大学出现对应公告时自动撤销该标记。'
)

RECENT_JLU_FIXES = {
    JX_URL: {
        'province': '江西',
        'title': '江西省2027年度面向吉林大学选调应届优秀大学毕业生公告',
        'published': '2026-10-15',
        'start': '2026-10-20T09:00:00+08:00',
        'end': '2026-10-26T18:00:00+08:00',
        'exam': '2026-11-15T09:00:00+08:00',
        'examEnd': '2026-11-15T12:00:00+08:00',
        'examText': '11月15日 09:00—12:00；综合能力测试',
        'notes': '吉林大学就业网已发布该通知；网上报名10月20日9:00至10月26日18:00，笔试11月15日9:00—12:00。具体职位、资格及校内推荐流程以原文和附件为准。',
    },
    GX_URL: {
        'province': '广西',
        'title': '广西2027年定向吉林大学招录选调生公告',
        'published': '2026-10-15',
        # 正文写“自本公告发布之日起”报名，未给具体开放时刻。
        'start': '2026-10-15T00:00:00+08:00',
        'startDateOnly': True,
        'end': '2026-11-05T18:00:00+08:00',
        # 正文仅明确笔试、面试整体安排在12月13日至14日，不能猜测笔试具体日/时段。
        'exam': '2026-12-13T00:00:00+08:00',
        'examDateOnly': True,
        'examEnd': '',
        'examText': '笔试、面试安排在12月13日至14日；具体科目时段、考点以准考证为准',
        'notes': '报名自公告发布之日（10月15日）起，11月5日18:00截止；11月16日后查询资格审查结果，12月10日后打印准考证；笔试、面试安排在12月13日至14日。',
    },
    JL_URL: {
        'province': '吉林',
        'title': '吉林省面向吉林大学定向招录2027届选调生公告',
        'published': '2026-10-16',
        'start': '2026-10-19T08:30:00+08:00',
        'end': '2026-10-23T16:00:00+08:00',
        'exam': '2026-11-08T09:00:00+08:00',
        'examEnd': '2026-11-08T11:30:00+08:00',
        'examText': '11月8日 09:00—11:30；综合能力测试',
        'notes': '网上报名10月19日8:30至10月23日16:00；11月5日8:30至7日24:00打印准考证；11月8日9:00—11:30笔试。具体职位及后续面试安排以原文为准。',
    },
}


def load(name, default):
    path = ROOT / name
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def save(name, obj):
    path = ROOT / name
    serialized = json.dumps(obj, ensure_ascii=False, indent=2) + '\n'
    if not path.exists() or path.read_text(encoding='utf-8') != serialized:
        path.write_text(serialized, encoding='utf-8')


def normalize_provinces(items):
    changed = 0
    for item in items:
        detected = province_from_title(item.get('title', ''))
        if detected and item.get('province') != detected:
            item['province'] = detected
            changed += 1
    return changed


def ensure_recent_jlu_notices(data, queue):
    """Repair the three current JLU notices that discovery/timing parsing missed.

    The values below are limited to explicit dates/times in the JLU article text.
    This runs before monitor.py as well as after auto-publication, so the Jiangxi
    article is present in vetted data before discovery and cannot be re-queued as
    an unhandled candidate. Existing enriched fields are preserved except for the
    verified timing/publication fields listed in RECENT_JLU_FIXES.
    """
    records = data.setdefault('records', [])
    changes = 0

    for url, fix in RECENT_JLU_FIXES.items():
        record = next((r for r in records if r.get('source') == url), None)
        if record is None:
            record = {
                'province': fix['province'],
                'title': fix['title'],
                'type': '选调公告',
                'count': '以吉林大学就业网公告及附件为准',
                'published': fix['published'],
                'start': '',
                'end': '',
                'exam': '',
                'examEnd': '',
                'examText': '报名、笔试及后续安排以吉林大学就业网原文和附件为准',
                'school': '吉林大学就业网已发布该通知；适用高校、学历、专业及校内流程以原文和附件为准。',
                'eligibility': '自动收录不推断资格条件；请直接查看吉林大学就业网原文及附件。',
                'notes': '吉林大学就业网自动发布，无需人工二次核验。',
                'source': url,
                'sourceName': '吉林大学就业网（自动发布）',
                'sourceType': '吉林大学备用',
                'verified': fix['published'],
                'sourceTier': 'jlu_fallback',
                'autoPublished': True,
            }
            records.append(record)
            changes += 1

        for key, value in fix.items():
            if record.get(key) != value:
                record[key] = value
                changes += 1

        # Exact-clock notices must not retain stale date-only flags from an older parse.
        if url in (JX_URL, JL_URL):
            if record.pop('startDateOnly', None) is not None:
                changes += 1
            if record.pop('examDateOnly', None) is not None:
                changes += 1

        if record.get('verified') != fix['published']:
            record['verified'] = fix['published']
            changes += 1
        if record.get('sourceTier') != 'jlu_fallback':
            record['sourceTier'] = 'jlu_fallback'
            changes += 1

    covered_note = '吉林大学就业网来源；正式数据已收录并回填公告明确的报名/笔试时间，无需人工二次核验。'
    for candidate in queue.get('candidates', []):
        if candidate.get('url') not in RECENT_JLU_FIXES:
            continue
        if candidate.get('status') != 'auto_covered':
            candidate['status'] = 'auto_covered'
            changes += 1
        if candidate.get('note') != covered_note:
            candidate['note'] = covered_note
            changes += 1

    return changes


def merge_guizhou_duplicate(data, queue):
    """Collapse the two historical JLU URLs for the same Guizhou notice.

    Keep the structured deadlines already verified in the older record, but use the
    newer JLU selected-graduate article as the canonical source. This function is
    deliberately idempotent: a clean canonical record returns zero changes.
    """
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
        # The approved university index records this notice as published on 2026-09-22.
        # Do not invent an earlier publication date merely to satisfy ordering.
        'published': '2026-09-22',
        'source': GZ_NEW,
        'sourceName': '吉林大学就业网转载公告（备用）',
        'sourceType': '吉林大学备用',
        'sourceTier': 'jlu_fallback',
        'verified': '2026-09-22',
        'notes': '报名10月13日9:00开始；省级党政机关/省管企业10月19日14:00截止，市（州）级10月21日14:00截止，县级10月23日14:00截止。不同岗位截止不同，不能把最晚截止时间套用于全部职位。',
    })
    for transient in ('autoPublished', 'publishedEstimated', 'discoveredAt', 'autoParsedAt', 'autoParsedFrom'):
        desired.pop(transient, None)

    current_canonical = next((r for r in matches if r.get('source') == GZ_NEW), None)
    records_need_change = (
        len(matches) != 1
        or current_canonical is None
        or current_canonical != desired
    )
    changes = 0
    if records_need_change:
        first_index = min(records.index(r) for r in matches)
        records[:] = [r for r in records if r.get('source') not in (GZ_OLD, GZ_NEW)]
        records.insert(min(first_index, len(records)), desired)
        changes += 1

    wanted_note = '与已结构化发布的贵州省2027年度党政机关定向选调和省管企业招聘公告为同一公告，已合并，避免重复卡片。'
    for candidate in queue.get('candidates', []):
        if candidate.get('url') not in (GZ_OLD, GZ_NEW):
            continue
        if candidate.get('province') != '贵州':
            candidate['province'] = '贵州'
            changes += 1
        if candidate.get('status') != 'auto_covered':
            candidate['status'] = 'auto_covered'
            changes += 1
        if candidate.get('note') != wanted_note:
            candidate['note'] = wanted_note
            changes += 1
    return changes


def clean_third_title(value):
    title = re.sub(r'[\u200b\ufeff]', '', str(value or '')).strip()
    title = re.sub(r'^【选调生】\s*', '', title)
    title = re.sub(r'\s*发布日期[:：]\s*20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}日?.*$', '', title)
    title = re.sub(r'\s+点击数[:：]?.*$', '', title)
    return title.strip() or str(value or '').strip()


def third_item_day(item):
    text = item.get('title', '')
    match = re.search(r'(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})日?', text)
    if match:
        return f'{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}', False
    discovered = str(item.get('discovered') or '')
    if re.match(r'^20\d{2}-\d{2}-\d{2}', discovered):
        return discovered[:10], True
    return datetime.now(TZ).date().isoformat(), True


def choose_third_item(items):
    def score(item):
        title = clean_third_title(item.get('title', ''))
        raw = item.get('title', '')
        points = 0
        if '公告' in title:
            points += 20
        if '2027' in title:
            points += 8
        if item.get('province') and item['province'] in title:
            points += 8
        if '发布日期' in raw:
            points += 3
        if '点击数' in raw:
            points -= 2
        return points, -len(title), str(item.get('discovered') or '')

    return max(items, key=score)


def base_eligibility(text):
    text = str(text or '').strip()
    if text.startswith(PERSONAL_MARKER) and NOTICE_MARKER in text:
        return text.split(NOTICE_MARKER, 1)[1].strip()
    return text


def reconcile_other_school_coverage(data, third):
    """Keep nationwide publication coverage separate from the user's JLU eligibility.

    If an approved third-tier university source has a 2027 notice but there is no
    JLU notice for that province, the province remains visible in the formal total
    list and is marked as currently unavailable to this JLU-based user. We never
    copy another university's campus deadline into the user's schedule. The status
    is reversible: a later JLU notice removes the personal ineligibility marker and
    any temporary coverage-only card.
    """
    records = data.setdefault('records', [])
    third_items = [item for item in third.get('items', []) if item.get('province')]
    by_province = {}
    for item in third_items:
        by_province.setdefault(item['province'], []).append(item)

    before = json.dumps(records, ensure_ascii=False, sort_keys=True)

    # Recompute generated coverage cards every run so stale cards disappear as
    # soon as a government/JLU/human-reviewed formal record exists.
    records[:] = [record for record in records if not record.get('coverageOnly')]
    jlu_provinces = {
        record.get('province') for record in records
        if record.get('sourceTier') == 'jlu_fallback'
    }
    formal_provinces = {record.get('province') for record in records}

    for province, items in by_province.items():
        if province in formal_provinces:
            continue
        item = choose_third_item(items)
        published, estimated = third_item_day(item)
        title = clean_third_title(item.get('title', ''))
        discovered = str(item.get('discovered') or '')
        verified = discovered[:10] if re.match(r'^20\d{2}-\d{2}-\d{2}', discovered) else published
        record = {
            'province': province,
            'title': title,
            'type': '选调公告（其他高校已发布）',
            'count': '以其他高校官方就业网所载公告及附件为准',
            'published': published,
            'start': '',
            'end': '',
            'exam': '',
            'examEnd': '',
            'examText': '不套用其他高校校内报名/推荐或考试安排；仅作为全国选调发布进度展示',
            'school': '其他高校官方就业网已出现该省2027选调信息；吉林大学就业网暂未发现对应公告。',
            'eligibility': (
                '【你的资格】当前不可报（个人跟踪口径）：吉林大学就业网暂未发现对应公告；此标记不代表官方高校名单排除吉林大学。'
                '【公告条件】其他高校公告仅用于全国选调信息收录，不代表你可按其校内流程报名。'
            ),
            'notes': '全国总信息保留该省发布进度；来源为其他高校官方就业网。不会把该校校内报名、推荐、盖章或考试时间当作你的时间。',
            'source': item.get('url', ''),
            'sourceName': item.get('source') or '其他高校官方就业网（补充来源）',
            'sourceType': '其他高校补充',
            'verified': verified,
            'sourceTier': 'university_third',
            'coverageOnly': True,
            'personalEligibility': 'ineligible_no_jlu',
            'reviewedSource': False,
            'reviewedScope': False,
        }
        if estimated:
            record['publishedEstimated'] = True
        records.append(record)
        formal_provinces.add(province)

    third_provinces = set(by_province)
    for record in records:
        if record.get('coverageOnly'):
            continue
        base = base_eligibility(record.get('eligibility', ''))
        province = record.get('province')
        should_mark = province in third_provinces and province not in jlu_provinces
        if should_mark:
            record['personalEligibility'] = 'ineligible_no_jlu'
            record['eligibility'] = (
                '【你的资格】当前不可报（个人跟踪口径）：其他高校已有该省2027届选调信息，但吉林大学就业网暂未发现对应公告；不代表官方明确排除吉林大学。'
                f'{NOTICE_MARKER}{base}'
            )
        else:
            if record.get('personalEligibility') == 'ineligible_no_jlu':
                record.pop('personalEligibility', None)
            record['eligibility'] = base

    if PERSONAL_POLICY not in data.get('notice', ''):
        data['notice'] = (data.get('notice', '').rstrip('。') + '。' + PERSONAL_POLICY).lstrip('。')

    after = json.dumps(records, ensure_ascii=False, sort_keys=True)
    return int(before != after)


def main():
    data = load('data.json', {'records': []})
    queue = load('review_queue.json', {'candidates': []})
    third = load('third_sources.json', {'items': []})
    sources = load('sources.json', {})
    changed = 0

    changed += normalize_provinces(data.get('records', []))
    changed += normalize_provinces(queue.get('candidates', []))
    changed += normalize_provinces(third.get('items', []))

    for record in data.get('records', []):
        if record.pop('startTimeUnknown', None):
            record['startDateOnly'] = True
            changed += 1
        if record.get('province') == '四川' and '具体开放时刻待核对' in record.get('notes', ''):
            record['notes'] = record['notes'].replace(
                '报名公告仅写10月8日开始，具体开放时刻待核对；',
                '报名公告仅写10月8日开始，未列具体开放时刻；'
            )
            changed += 1

    changed += ensure_recent_jlu_notices(data, queue)
    changed += merge_guizhou_duplicate(data, queue)
    changed += reconcile_other_school_coverage(data, third)

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
