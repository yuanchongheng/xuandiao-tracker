#!/usr/bin/env python3
"""One-time idempotent audit patch for monitor discovery and qiuzhao UI robustness."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def replace_required(text, old, new, label):
    if new in text:
        return text, False
    if old not in text:
        raise RuntimeError(f'missing patch pattern: {label}')
    return text.replace(old, new), True


def patch_monitor():
    path = ROOT / 'monitor.py'
    text = path.read_text(encoding='utf-8')
    changed = False

    old = """    priority = ('government', 'jlu_fallback', 'university_third')
    for tier in priority:
        selected = [e for e in results if source_tier(e['url']) == tier]
        if selected:
            return list({e['url']: e for e in selected}.values())
    return []
"""
    new = """    priority = {'government': 0, 'jlu_fallback': 1, 'university_third': 2}
    # Preserve distinct notices across tiers. The caller de-duplicates a JLU hit
    # only when its normalized title matches a government notice. Dropping every
    # JLU hit merely because one government result exists can hide a separate
    # university-specific announcement.
    results.sort(key=lambda e: (priority.get(source_tier(e['url']), 9), e['url']))
    deduped = {}
    for entry in results:
        deduped.setdefault(entry['url'], entry)
    return list(deduped.values())
"""
    text, did = replace_required(text, old, new, 'parse_rss tier preservation')
    changed |= did

    old = """                    existing = set(state['listings'].get(url, []))
                    if url in state['listings']:
                        for entry in links:
                            if entry['url'] not in existing and queue_candidate(queue, known, entry, stamp):
                                new.append(entry)
                    state['listings'][url] = sorted(existing | {link['url'] for link in links})
"""
    new = """                    existing = set(state['listings'].get(url, []))
                    had_baseline = url in state['listings']
                    # A first-time national JLU index is an approved source and its
                    # current 2027 notices should not disappear into a silent baseline.
                    # Other listing sources keep the conservative baseline-only first run.
                    surface_initial_jlu = (not had_baseline and source['province'] == '全国'
                                           and source_tier(url) == 'jlu_fallback')
                    if had_baseline or surface_initial_jlu:
                        for entry in links:
                            if entry['url'] not in existing and queue_candidate(queue, known, entry, stamp):
                                new.append(entry)
                    state['listings'][url] = sorted(existing | {link['url'] for link in links})
"""
    text, did = replace_required(text, old, new, 'initial national JLU listing')
    changed |= did

    old = '              "warning": "自动检测只能发现线索，非实时、非完整覆盖；招聘条件和日期仅在人工核对后更新。"}\n'
    new = '              "warning": "自动检测只能发现线索，非实时、非完整覆盖；政府来源候选需人工核对，吉林大学就业网通知按自动发布规则处理，第三来源仅供参考。"}\n'
    text, did = replace_required(text, old, new, 'monitor warning')
    changed |= did

    if changed:
        path.write_text(text, encoding='utf-8')
    return changed


def patch_monitor_tests():
    path = ROOT / 'tests' / 'test_monitor.py'
    text = path.read_text(encoding='utf-8')
    changed = False
    old = "self.assertEqual([r['url'] for r in monitor.parse_rss(rss.replace('</channel>', official+'</channel>').encode(), '上海', '2027')], ['https://rsj.sh.gov.cn/a'])"
    new = "self.assertEqual([r['url'] for r in monitor.parse_rss(rss.replace('</channel>', official+'</channel>').encode(), '上海', '2027')], ['https://rsj.sh.gov.cn/a', jlu])"
    text, did = replace_required(text, old, new, 'mixed-tier RSS test')
    changed |= did
    if changed:
        path.write_text(text, encoding='utf-8')
    return changed


def patch_regression_tests():
    path = ROOT / 'tests' / 'test_regressions.py'
    text = path.read_text(encoding='utf-8')
    changed = False
    old = """    def test_government_result_keeps_priority_over_jlu_search_hit(self):
        rss = \"\"\"<rss><channel><item><title>重庆2027定向选调公告</title><link>https://www.cq.gov.cn/a</link></item><item><title>重庆2027面向吉林大学定向选调公告</title><link>https://jdjywpt.jlu.edu.cn/portal/xdsgz/article/details?id=x</link></item></channel></rss>\"\"\"
        urls = [item['url'] for item in monitor.parse_rss(rss.encode(), '重庆', '2027')]
        self.assertEqual(urls, ['https://www.cq.gov.cn/a'])
"""
    new = """    def test_distinct_government_and_jlu_search_hits_are_retained(self):
        rss = \"\"\"<rss><channel><item><title>重庆2027定向选调公告</title><link>https://www.cq.gov.cn/a</link></item><item><title>重庆2027面向吉林大学定向选调公告</title><link>https://jdjywpt.jlu.edu.cn/portal/xdsgz/article/details?id=x</link></item></channel></rss>\"\"\"
        urls = [item['url'] for item in monitor.parse_rss(rss.encode(), '重庆', '2027')]
        self.assertEqual(urls, ['https://www.cq.gov.cn/a', 'https://jdjywpt.jlu.edu.cn/portal/xdsgz/article/details?id=x'])
"""
    text, did = replace_required(text, old, new, 'mixed-tier regression test')
    changed |= did
    if changed:
        path.write_text(text, encoding='utf-8')
    return changed


def patch_qiuzhao_html(path):
    text = path.read_text(encoding='utf-8')
    changed = False

    if 'safeStoredJSON' not in text:
        old = "const KEY='autumn-2027-all-jobs-v3',SORTKEY='autumn-2027-sort-v2';let state=JSON.parse(localStorage.getItem(KEY)||'{}');let mode='all',q='';\nlet savedSort=JSON.parse(localStorage.getItem(SORTKEY)||'null');let sortKey=savedSort?.key||'deadline',sortDir=savedSort?.dir||1;"
        if 'plus/index.html' in str(path):
            old = "const KEY='autumn-2027-all-jobs-v3',SORTKEY='autumn-2027-plus-sort-v1';let state=JSON.parse(localStorage.getItem(KEY)||'{}');let mode='all',q='';\nlet savedSort=JSON.parse(localStorage.getItem(SORTKEY)||'null');let sortKey=savedSort?.key||'deadline',sortDir=savedSort?.dir||1;"
        sort_key = 'autumn-2027-plus-sort-v1' if 'plus/index.html' in str(path) else 'autumn-2027-sort-v2'
        new = f"""function safeStoredJSON(key,fallback){{try{{const raw=localStorage.getItem(key);return raw===null?fallback:JSON.parse(raw)}}catch{{try{{localStorage.removeItem(key)}}catch{{}}return fallback}}}}
const KEY='autumn-2027-all-jobs-v3',SORTKEY='{sort_key}';let state=safeStoredJSON(KEY,{{}});if(!state||Array.isArray(state)||typeof state!=='object')state={{}};let mode='all',q='';
let savedSort=safeStoredJSON(SORTKEY,null);const allowedSort=new Set(['deadline','level','org','region','role']);let sortKey=allowedSort.has(savedSort?.key)?savedSort.key:'deadline',sortDir=[1,-1].includes(savedSort?.dir)?savedSort.dir:1;"""
        text, did = replace_required(text, old, new, f'{path.name} safe localStorage')
        changed |= did

    old = "const mo=+m[1],d=+m[2];if(m[3]!==undefined){let h=+m[3],mi=+m[4];if(h===24)return{known:true,value:new Date(2026,mo-1,d+1,0,mi,0,0).getTime()};return{known:true,value:new Date(2026,mo-1,d,h,mi,0,0).getTime()}}return{known:true,value:new Date(2026,mo-1,d,23,59,59,999).getTime()}"
    new = "const mo=+m[1],d=+m[2],yr=mo>=8?2026:2027;if(m[3]!==undefined){let h=+m[3],mi=+m[4];if(h===24)return{known:true,value:new Date(yr,mo-1,d+1,0,mi,0,0).getTime()};return{known:true,value:new Date(yr,mo-1,d,h,mi,0,0).getTime()}}return{known:true,value:new Date(yr,mo-1,d,23,59,59,999).getTime()}"
    if old in text:
        text = text.replace(old, new)
        changed = True
    elif new not in text:
        raise RuntimeError(f'missing month-only deadline pattern in {path}')

    old = "m=s.match(/^(\\d{1,2})月(上旬|中旬|下旬)/);if(m){const d=m[2]==='上旬'?5:m[2]==='中旬'?15:25;return{known:true,value:new Date(2026,+m[1]-1,d,23,59,59,999).getTime()}}"
    new = "m=s.match(/^(\\d{1,2})月(上旬|中旬|下旬)/);if(m){const mo=+m[1],yr=mo>=8?2026:2027,d=m[2]==='上旬'?5:m[2]==='中旬'?15:25;return{known:true,value:new Date(yr,mo-1,d,23,59,59,999).getTime()}}"
    if old in text:
        text = text.replace(old, new)
        changed = True
    elif new not in text:
        raise RuntimeError(f'missing fuzzy deadline pattern in {path}')

    old = "r.onload=()=>{try{state=JSON.parse(r.result);localStorage.setItem(KEY,JSON.stringify(state));render()}catch{alert('导入文件格式不正确')}};"
    new = "r.onload=()=>{try{const imported=JSON.parse(r.result);if(!imported||Array.isArray(imported)||typeof imported!=='object')throw new Error('invalid state');state=imported;localStorage.setItem(KEY,JSON.stringify(state));render()}catch{alert('导入文件格式不正确')}};"
    if old in text:
        text = text.replace(old, new)
        changed = True
    elif new not in text:
        raise RuntimeError(f'missing import validation pattern in {path}')

    if changed:
        path.write_text(text, encoding='utf-8')
    return changed


def add_static_tests():
    path = ROOT / 'tests' / 'test_static_ui.py'
    content = '''import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class StaticUiRegressionTests(unittest.TestCase):
    def test_qiuzhao_pages_guard_corrupt_local_storage(self):
        for rel in ('qiuzhao/index.html', 'qiuzhao/plus/index.html'):
            text = (ROOT / rel).read_text(encoding='utf-8')
            self.assertIn('safeStoredJSON', text)
            self.assertNotIn("state=JSON.parse(localStorage.getItem(KEY)", text)

    def test_qiuzhao_month_only_deadline_rolls_into_2027(self):
        for rel in ('qiuzhao/index.html', 'qiuzhao/plus/index.html'):
            text = (ROOT / rel).read_text(encoding='utf-8')
            self.assertIn('yr=mo>=8?2026:2027', text)


if __name__ == '__main__':
    unittest.main()
'''
    if path.exists() and path.read_text(encoding='utf-8') == content:
        return False
    path.write_text(content, encoding='utf-8')
    return True


def main():
    changed = []
    if patch_monitor(): changed.append('monitor.py')
    if patch_monitor_tests(): changed.append('tests/test_monitor.py')
    if patch_regression_tests(): changed.append('tests/test_regressions.py')
    if patch_qiuzhao_html(ROOT / 'qiuzhao' / 'index.html'): changed.append('qiuzhao/index.html')
    if patch_qiuzhao_html(ROOT / 'qiuzhao' / 'plus' / 'index.html'): changed.append('qiuzhao/plus/index.html')
    if add_static_tests(): changed.append('tests/test_static_ui.py')
    print('final audit patch: ' + (', '.join(changed) if changed else 'already applied'))


if __name__ == '__main__':
    main()
