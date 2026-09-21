#!/usr/bin/env python3
"""Validate data.json, and refresh the offline snapshot inside index.html.

This never derives dates or qualifications: data.json must be manually verified first.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re
from source_policy import source_tier

ROOT = Path(__file__).resolve().parent
EXPECTED = re.compile(r"^const SEED_DATA_PLACEHOLDER = .*;$", re.MULTILINE)


def build(check=False):
    data = json.loads((ROOT / 'data.json').read_text(encoding='utf-8'))
    provinces = data.get('provinces')
    records = data.get('records')
    if not isinstance(provinces, list) or len(provinces) != 31 or len(set(provinces)) != 31:
        raise ValueError('Expected 31 unique provincial jurisdictions')
    if not isinstance(records, list):
        raise ValueError('records must be a list')
    keys = set()
    for entry in records:
        for field in ('province', 'title', 'source', 'verified', 'published', 'eligibility', 'school'):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise ValueError(f'Missing field {field}: {entry}')
        if entry['province'] not in provinces or not entry['source'].startswith('https://'):
            raise ValueError('Invalid province / HTTPS source')
        tier = source_tier(entry['source'])
        if tier is None:
            raise ValueError('Published source must be government website or Jilin University career portal')
        if entry.get('sourceTier') != tier:
            raise ValueError('Incorrect sourceTier: ' + entry['source'])
        if tier == 'government' and entry.get('sourceType') != '官方':
            raise ValueError('Government notice must be labelled 官方')
        if tier == 'jlu_fallback' and entry.get('sourceType') != '吉林大学备用':
            raise ValueError('Jilin University page must be labelled 备用, never 官方')
        datetime.fromisoformat(entry['verified'])
        for field in ('start', 'end', 'exam', 'examEnd'):
            value = entry.get(field)
            if value:
                date = datetime.fromisoformat(value)
                if date.tzinfo is None:
                    raise ValueError(f'{field} missing explicit timezone')
        key = entry['province'] + '|' + entry['title']
        if key in keys:
            raise ValueError('Duplicate record: ' + key)
        keys.add(key)
    if not isinstance(data.get('asOf'), str):
        raise ValueError('asOf is required')
    html = (ROOT / 'index.html').read_text(encoding='utf-8')
    replacement = 'const SEED_DATA_PLACEHOLDER = ' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';'
    found = EXPECTED.findall(html)
    if len(found) != 1:
        raise ValueError('Offline dataset injection marker missing or duplicated')
    if check:
        if found[0] != replacement:
            raise ValueError('Embedded HTML snapshot differs from data.json. Run python build.py')
        print(f'PASS: {len(records)} validated records, 31 regions, embedded HTML data synchronized')
    else:
        (ROOT / 'index.html').write_text(EXPECTED.sub(lambda _: replacement, html, count=1), encoding='utf-8')
        print(f'Updated index.html offline snapshot: {len(records)} vetted records')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    build(check=args.check)
