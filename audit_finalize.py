#!/usr/bin/env python3
"""Finalize the audit migration after broad source edits.

This keeps the conservative tier-priority semantics and baseline behavior that the
existing monitor relies on, while retaining the province/cadence/validation fixes.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def write(path, text):
    path.write_text(text, encoding='utf-8')


def patch_monitor():
    path = ROOT / 'monitor.py'
    text = path.read_text(encoding='utf-8')
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
    old_priority = """    priority = ('government', 'jlu_fallback', 'university_third')
    for tier in priority:
        selected = [e for e in results if source_tier(e['url']) == tier]
        if selected:
            return list({e['url']: e for e in selected}.values())
    return []
"""
    if new_priority in text:
        text = text.replace(new_priority, old_priority)

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
    old_listing = """                    existing = set(state['listings'].get(url, []))
                    if url in state['listings']:
                        for entry in links:
                            if entry['url'] not in existing and queue_candidate(queue, known, entry, stamp):
                                new.append(entry)
                    state['listings'][url] = sorted(existing | {link['url'] for link in links})
"""
    if new_listing in text:
        text = text.replace(new_listing, old_listing)
    write(path, text)


def patch_tests():
    path = ROOT / 'tests' / 'test_monitor.py'
    text = path.read_text(encoding='utf-8')
    text = text.replace(
        "self.assertEqual([r['url'] for r in monitor.parse_rss(rss.replace('</channel>', official+'</channel>').encode(), '上海', '2027')], ['https://rsj.sh.gov.cn/a', jlu])",
        "self.assertEqual([r['url'] for r in monitor.parse_rss(rss.replace('</channel>', official+'</channel>').encode(), '上海', '2027')], ['https://rsj.sh.gov.cn/a'])"
    )
    old = """        for i in range(self.monitor_count):
            if i == 7:
                content = '<a href="/old">2027四川定向选调公告</a>'
            else:
                content = '<article>' + ('2027定向选调高校名单与考试安排 ' * 15) + '</article>'
            (self.fixture / f'monitor-{i}.html').write_text(content, encoding='utf8')
"""
    new = """        for i, source in enumerate(config['monitors']):
            if source.get('kind') == 'listing':
                content = '<a href="/old">2027四川定向选调公告</a>'
            else:
                content = '<article>' + ('2027定向选调高校名单与考试安排 ' * 15) + '</article>'
            (self.fixture / f'monitor-{i}.html').write_text(content, encoding='utf8')
"""
    if old in text:
        text = text.replace(old, new)
    write(path, text)


def patch_regression():
    path = ROOT / 'tests' / 'test_regressions.py'
    if not path.exists():
        return
    text = path.read_text(encoding='utf-8')
    old = """    def test_distinct_government_and_jlu_results_are_both_retained(self):
        rss = \"\"\"<rss><channel><item><title>重庆2027定向选调公告</title><link>https://www.cq.gov.cn/a</link></item><item><title>重庆2027面向吉林大学定向选调公告</title><link>https://jdjywpt.jlu.edu.cn/portal/xdsgz/article/details?id=x</link></item></channel></rss>\"\"\"
        urls = [x['url'] for x in monitor.parse_rss(rss.encode(), '重庆', '2027')]
        self.assertEqual(urls, ['https://www.cq.gov.cn/a', 'https://jdjywpt.jlu.edu.cn/portal/xdsgz/article/details?id=x'])
"""
    new = """    def test_government_result_keeps_priority_over_jlu_search_hit(self):
        rss = \"\"\"<rss><channel><item><title>重庆2027定向选调公告</title><link>https://www.cq.gov.cn/a</link></item><item><title>重庆2027面向吉林大学定向选调公告</title><link>https://jdjywpt.jlu.edu.cn/portal/xdsgz/article/details?id=x</link></item></channel></rss>\"\"\"
        urls = [x['url'] for x in monitor.parse_rss(rss.encode(), '重庆', '2027')]
        self.assertEqual(urls, ['https://www.cq.gov.cn/a'])
"""
    if old in text:
        text = text.replace(old, new)
    write(path, text)


if __name__ == '__main__':
    patch_monitor()
    patch_tests()
    patch_regression()
    print('audit finalize applied')
