import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import monitor
from source_policy import source_tier


class ParsingTests(unittest.TestCase):
    def test_rss_only_candidate_domains_and_year(self):
        rss = '''<rss><channel>
        <item><title>湖南2027年定向选调公告</title><link>https://rst.hunan.gov.cn/a</link></item>
        <item><title>湖南2027定向选调</title><link>https://fraud.example/a</link></item>
        <item><title>湖南2026年定向选调</title><link>https://rst.hunan.gov.cn/old</link></item>
        </channel></rss>'''
        result = monitor.parse_rss(rss.encode(), '湖南', '2027')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['url'], 'https://rst.hunan.gov.cn/a')

    def test_source_policy_excludes_other_universities_and_media(self):
        self.assertEqual(source_tier('https://rst.hunan.gov.cn/a'), 'government')
        self.assertEqual(source_tier('https://jdjywpt.jlu.edu.cn/portal/xdsgz'), 'jlu_fallback')
        self.assertEqual(source_tier('https://jdjyw.jlu.edu.cn/portal/article/notice'), 'jlu_fallback')
        for url in ('https://xds.nankai.edu.cn/a', 'https://job.sdu.edu.cn/a', 'https://www.gzastv.cn/a', 'https://fakegov.cn/a'):
            self.assertIsNone(source_tier(url), url)

    def test_rss_jlu_only_if_no_government_match(self):
        jlu = 'https://jdjywpt.jlu.edu.cn/portal/xdsgz/article/details?id=test'
        rss = f'''<rss><channel>
        <item><title>上海2027选调公告</title><link>{jlu.replace('&', '&amp;')}</link></item>
        <item><title>上海2027选调公告</title><link>https://xds.ecnu.edu.cn/a</link></item>
        <item><title>上海2027选调公告</title><link>https://www.example.cn/a</link></item>
        </channel></rss>'''
        self.assertEqual([r['url'] for r in monitor.parse_rss(rss.encode(), '上海', '2027')], [jlu])
        official = '<item><title>上海2027选调公告</title><link>https://rsj.sh.gov.cn/a</link></item>'
        self.assertEqual([r['url'] for r in monitor.parse_rss(rss.replace('</channel>', official+'</channel>').encode(), '上海', '2027')], ['https://rsj.sh.gov.cn/a'])

    def test_url_must_be_https_public(self):
        for url in ('javascript:alert(1)', 'http://gov.cn/', 'https://localhost/a', 'https://127.0.0.1/a', 'https://user:pass@gov.cn/a'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                monitor.canonical_url(url)

    def test_missing_content_type_accepts_only_actual_markup(self):
        self.assertTrue(monitor.acceptable_page('', b'<!doctype html><html><body>notice</body></html>'))
        self.assertFalse(monitor.acceptable_page('', b''))
        self.assertFalse(monitor.acceptable_page('', b'{"error":"blocked"}'))
        self.assertFalse(monitor.acceptable_page('application/json', b'<html>not a response</html>'))

    def test_guizhou_uses_jlu_section_url(self):
        config = json.loads((Path(monitor.__file__).resolve().parent / 'sources.json').read_text(encoding='utf8'))
        gz = next(x for x in config['monitors'] if x['province'] == '贵州')
        self.assertEqual(gz['url'], 'https://jdjyw.jlu.edu.cn/portal/article/details?id=1f6b210e15d944a6988d7af33b88cc00')
        self.assertEqual(len({gz['url'], *(x['url'] for x in gz['fallbacks'])}), 2)
        listing = next(x for x in config['monitors'] if x['province'] == '全国')
        self.assertEqual(listing['fallbacks'][0]['url'], 'https://jdjyw.jlu.edu.cn/portal/article/list?cid=797ed1b0210f4f15937da33309184441')

    def test_article_strips_navigation(self):
        html = '<nav>random number 123</nav><article>' + ('定向选调 公告 资格条件 ' * 10) + '</article>'
        self.assertNotIn('random number', monitor.article_text(html.encode()))

    def test_listing_extracts_year_matched_links(self):
        html = '''<a href="/notice-27">2027届四川定向选调公告</a>
        <a href="/notice-26">2026届四川定向选调公告</a>'''
        links = monitor.listing_links(html.encode(), 'https://jdjywpt.jlu.edu.cn/', '全国', '2027')
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]['url'], 'https://jdjywpt.jlu.edu.cn/notice-27')
        self.assertEqual(links[0]['province'], '四川')


class MonitorOfflineTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        old_root = Path(monitor.__file__).resolve().parent
        for name in ('sources.json', 'data.json'):
            shutil.copy(old_root / name, self.root / name)
        (self.root / 'review_queue.json').write_text(json.dumps({'updated':'','candidates':[]}), encoding='utf8')
        (self.root / 'watch_state.json').write_text(json.dumps({'articles':{},'listings':{},'search':{}}), encoding='utf8')
        self.fixture = self.root / 'fixtures'
        self.fixture.mkdir()
        for i in range(8):
            if i == 7:
                content = '<a href="/old">2027四川定向选调公告</a>'
            else:
                content = '<article>' + ('2027定向选调高校名单与考试安排 ' * 15) + '</article>'
            (self.fixture / f'monitor-{i}.html').write_text(content, encoding='utf8')
        self.root_patch = patch.object(monitor, 'ROOT', self.root)
        self.root_patch.start()

    def tearDown(self):
        self.root_patch.stop()
        self.folder.cleanup()

    def test_baseline_then_changes_then_idempotent(self):
        first = monitor.run(discovery=False, fixture_dir=self.fixture)
        self.assertEqual(first['newCandidates'], 0)
        self.assertEqual(first['monitorsSucceeded'], 8)
        (self.fixture / 'monitor-0.html').write_text('<article>' + ('更新报名时段请确认附件 ' * 20) + '</article>', encoding='utf8')
        (self.fixture / 'monitor-7.html').write_text('<a href="/old">2027四川定向选调公告</a><a href="/new">2027四川定向选调新增公告</a>', encoding='utf8')
        second = monitor.run(discovery=False, fixture_dir=self.fixture)
        self.assertEqual(second['newCandidates'], 2)
        third = monitor.run(discovery=False, fixture_dir=self.fixture)
        self.assertEqual(third['newCandidates'], 0)
        queue = json.loads((self.root / 'review_queue.json').read_text(encoding='utf8'))
        self.assertEqual(len(queue['candidates']), 2)
        self.assertTrue(all(c['sourceTier'] in ('government', 'jlu_fallback') for c in queue['candidates']))
        original = json.loads((Path(monitor.__file__).resolve().parent / 'data.json').read_text(encoding='utf8'))
        self.assertEqual(json.loads((self.root / 'data.json').read_text(encoding='utf8')), original)

    def test_primary_failure_fallback_does_not_masquerade_as_primary_success(self):
        original = monitor.fetch_bytes
        official = 'https://www.gszg.gov.cn/20260920/ed5b9eee0bf34865afa9f09d30c9d9a4/c.html'
        backup = 'https://jdjyw.jlu.edu.cn/portal/article/details?id=9e01bc05e8bc4b3a8efdaf650667f0c0'
        html = ('<article>' + '2027甘肃定向选调公告报名办法 ' * 12 + '</article>').encode()
        def stub(url):
            if url == official:
                raise ConnectionError('simulated official timeout')
            return html
        with patch.object(monitor, 'fetch_bytes', side_effect=stub):
            status = monitor.run(discovery=False)
        self.assertEqual(status['monitorsSucceeded'], 7)
        self.assertEqual(status['fallbacksUsed'], 1)
        self.assertEqual(status['sourceHealth'][5]['state'], 'fallback')
        self.assertEqual(status['sourceHealth'][5]['used']['url'], backup)
        self.assertEqual(len(status['errors']), 1)
        self.assertEqual(status['newCandidates'], 0)
        self.assertEqual(json.loads((self.root / 'watch_state.json').read_text())['articles'].get(official), None)

    def test_unavailable_primary_and_fallback_are_reported(self):
        def stub(url):
            if 'gszg.gov.cn' in url or 'id=9e01bc05e8bc4b3a8efdaf650667f0c0' in url:
                raise ConnectionError('simulated network refusal')
            return ('<article>' + '2027选调公告及报名条件 ' * 12 + '</article>').encode()
        with patch.object(monitor, 'fetch_bytes', side_effect=stub):
            status = monitor.run(discovery=False)
        self.assertEqual(status['monitorsSucceeded'], 7)
        self.assertEqual(status['fallbacksUsed'], 0)
        self.assertEqual(status['sourceHealth'][5]['state'], 'failed')
        # Primary and both configured backups must each be recorded.
        self.assertEqual(len(status['errors']), 3)

    def test_search_discovers_official_link_without_publishing(self):
        conf = json.loads((self.root / 'sources.json').read_text(encoding='utf8'))
        for i, _ in enumerate(conf['discovery']['provinces']):
            province = conf['discovery']['provinces'][i]
            rss = '<rss><channel><item><title>' + province + '2027定向选调公告</title><link>https://jobs.example.gov.cn/notice-' + str(i) + '</link></item></channel></rss>'
            (self.fixture / f'search-{i}.xml').write_text(rss, encoding='utf8')
        status = monitor.run(discovery=True, fixture_dir=self.fixture)
        self.assertEqual(status['searchesSucceeded'], 31)
        self.assertEqual(status['newCandidates'], 31)
        self.assertEqual(json.loads((self.root / 'data.json').read_text(encoding='utf8'))['records'][0]['province'], '北京')


if __name__ == '__main__':
    unittest.main()
