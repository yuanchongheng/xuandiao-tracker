#!/usr/bin/env python3
"""Idempotent cross-file data cleanup after discovery/auto-publication."""
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
