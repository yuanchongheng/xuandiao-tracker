#!/usr/bin/env python3
"""Validate data.json, and refresh the offline snapshot inside index.html.

This never derives dates or qualifications: data.json must be manually verified first.
"""
import argparse
from datetime import datetime, date
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from source_policy import source_tier

ROOT = Path(__file__).resolve().parent
EXPECTED = re.compile(r"^const SEED_DATA_PLACEHOLDER = .*;$", re.MULTILINE)


def checked_time(value, field):
    """Require a complete timestamp with an explicit timezone; never infer missing times."""
    try:
        parsed = datetime.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f'{field} is not a valid ISO datetime') from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f'{field} missing explicit timezone')
    return parsed


def checked_day(value, field):
    try:
        parsed = date.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f'{field} must be YYYY-MM-DD') from exc
    return parsed


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
        url = urlsplit(entry['source'])
        if (entry['province'] not in provinces or url.scheme != 'https' or
                not url.hostname or url.username or url.password or
                url.port not in (None, 443)):
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
        verified = checked_day(entry['verified'], 'verified')
        published = checked_day(entry['published'], 'published')
        if verified < published:
            raise ValueError('Verification date predates publication: ' + entry['title'])
        times = {field: checked_time(entry[field], field) if entry.get(field) else None
                 for field in ('start', 'end', 'exam', 'examEnd')}
        if times['start'] and times['end'] and times['start'] >= times['end']:
            raise ValueError('Registration end must be later than start: ' + entry['title'])
        if times['examEnd'] and not times['exam']:
            raise ValueError('examEnd requires exam: ' + entry['title'])
        if times['examEnd'] and times['examEnd'] < times['exam']:
            raise ValueError('examEnd cannot precede exam: ' + entry['title'])
        if entry.get('startTimeUnknown') and (not times['start'] or
                                             times['start'].strftime('%H:%M') != '00:00'):
            raise ValueError('Unknown registration start time must use date-only sentinel: ' + entry['title'])
        deadlines = entry.get('deadlines', [])
        if not isinstance(deadlines, list):
            raise ValueError('deadlines must be a list: ' + entry['title'])
        for deadline in deadlines:
            if (not isinstance(deadline, dict) or not isinstance(deadline.get('label'), str)
                    or not deadline['label'].strip()):
                raise ValueError('Each deadline requires a label: ' + entry['title'])
            at = checked_time(deadline.get('at'), 'deadlines.at')
            if times['start'] and at <= times['start']:
                raise ValueError('Deadline must be after registration start: ' + entry['title'])
            if times['end'] and at > times['end']:
                raise ValueError('Job deadline cannot exceed latest published end: ' + entry['title'])
        key = entry['province'] + '|' + entry['title']
        if key in keys:
            raise ValueError('Duplicate record: ' + key)
        keys.add(key)
    checked_time(data.get('asOf'), 'asOf')
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
