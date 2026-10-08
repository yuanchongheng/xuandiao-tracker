#!/usr/bin/env python3
"""Apply the policy for registration opening dates published without a clock time.

If an announcement states only the opening calendar date, that date is considered
sufficient. The site displays the date only, treats registration as open from that
calendar day, and does not label the missing hour as something still needing review.
"""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent


def replace_once(text: str, old: str, new: str) -> str:
    if old in text:
        return text.replace(old, new, 1)
    if new in text:
        return text
    raise RuntimeError('Expected index.html pattern not found: ' + old[:100])


def migrate_data() -> int:
    path = ROOT / 'data.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    changed = 0
    for record in data.get('records', []):
        if record.pop('startTimeUnknown', None):
            record['startDateOnly'] = True
            changed += 1
    if changed:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return changed


def patch_index() -> int:
    path = ROOT / 'index.html'
    text = path.read_text(encoding='utf-8')
    original = text

    text = replace_once(
        text,
        "if(r.startTimeUnknown&&now<s+86400000)return 'unknown';",
        ""
    )
    text = replace_once(
        text,
        "if(r.startTimeUnknown&&now>=s&&now<s+86400000)return '今日开放，时刻待核实';",
        ""
    )
    text = replace_once(
        text,
        " // Start date is known, but opening hour is not: never imply registration is already open that day.\n if(r.startTimeUnknown&&localParts(new Date(now).toISOString()).key===localParts(r.start).key)return 'unknown';\n",
        " // A published opening date is sufficient even when the announcement gives no clock time.\n"
    )
    text = replace_once(
        text,
        " if(p.stage==='soon')return `${shortProgressDate(r.start,!!r.startTimeUnknown)} 开始${r.startTimeUnknown?' · 时刻待核':''}`;",
        " if(p.stage==='soon')return `${shortProgressDate(r.start,!!(r.startDateOnly||r.startTimeUnknown))} 开始`;"
    )
    text = replace_once(
        text,
        " if(r.start&&Date.parse(r.start)>now)add(r.start,'start','报名开始',!!r.startTimeUnknown);",
        " if(r.start&&Date.parse(r.start)>now)add(r.start,'start','报名开始',!!(r.startDateOnly||r.startTimeUnknown));"
    )
    text = replace_once(
        text,
        "${dateFmt(r.start)}${r.startTimeUnknown?'（时刻待核实）':''}",
        "${dateFmt(r.start)}"
    )
    text = replace_once(
        text,
        "const info=next?(next.unknown?'日期已知，时刻待核实':next.record.title):(rows.length?'如有变更以原文为准':'暂无已核验公告，不代表官方未发布');",
        "const info=next?next.record.title:(rows.length?'如有变更以原文为准':'暂无已核验公告，不代表官方未发布');"
    )

    if text != original:
        path.write_text(text, encoding='utf-8')
        return 1
    return 0


def main():
    migrated = migrate_data()
    patched = patch_index()
    print(f'start-date policy applied: migrated_records={migrated}, index_patched={patched}')


if __name__ == '__main__':
    main()
