#!/usr/bin/env python3
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
