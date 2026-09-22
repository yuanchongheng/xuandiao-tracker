import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock
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

    def test_source_policy_only_approved_other_university_sites(self):
        self.assertEqual(source_tier('https://rst.hunan.gov.cn/a'), 'government')
        self.assertEqual(source_tier('https://jdjywpt.jlu.edu.cn/portal/xdsgz'), 'jlu_fallback')
        self.assertEqual(source_tier('https://jdjyw.jlu.edu.cn/portal/article/notice'), 'jlu_fallback')
        for host in ('jiuye.uestc.edu.cn', 'www.job.ustc.edu.cn', 'job.hust.edu.cn', 'career.csu.edu.cn'):
            self.assertEqual(source_tier(f'https://{host}/notice'), 'university_third')
        for url in ('https://xds.nankai.edu.cn/a', 'https://job.sdu.edu.cn/a', 'https://fakejiuye.uestc.edu.cn/a', 'https://jiuye.uestc.edu.cn.evil.test/a', 'https://www.gzastv.cn/a', 'https://fakegov.cn/a'):
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

    def test_third_rss_is_only_eligible_without_higher_priority_and_title_scoped(self):
        third = 'https://job.hust.edu.cn/jcfw/2439641.htm'
        jlu = 'https://jdjywpt.jlu.edu.cn/portal/xdsgz/article/details?id=abc'
        rss = f'''<rss><channel>
        <item><title>湖南2027定向选调公告</title><link>{third}</link></item>
        <item><title>湖南2027定向选调公告</title><link>{jlu}</link></item>
        <item><title>2027就业信息</title><description>湖南2027定向选调公告</description><link>https://career.csu.edu.cn/irrelevant</link></item>
        <item><title>湖南2027定向选调公告</title><link>https://evil.edu.cn/a</link></item>
        </channel></rss>'''
        self.assertEqual([x['url'] for x in monitor.parse_rss(rss.encode(),'湖南','2027')], [jlu])
        self.assertEqual([x['url'] for x in monitor.parse_rss(rss.encode(),'湖南','2027', allowed_tiers=('university_third',))], [third])
        gov = '<item><title>湖南2027定向选调公告</title><link>https://rst.hunan.gov.cn/a</link></item>'
        self.assertEqual([x['url'] for x in monitor.parse_rss(rss.replace('</channel>',gov+'</channel>').encode(),'湖南','2027')], ['https://rst.hunan.gov.cn/a'])

    def test_url_must_be_https_public(self):
        for url in ('javascript:alert(1)', 'http://gov.cn/', 'https://localhost/a', 'https://127.0.0.1/a', 'https://user:pass@gov.cn/a'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                monitor.canonical_url(url)

    def test_missing_content_type_accepts_only_actual_markup(self):
        self.assertTrue(monitor.acceptable_page('', b'<!doctype html><html><body>notice</body></html>'))
        self.assertFalse(monitor.acceptable_page('', b''))
        self.assertFalse(monitor.acceptable_page('', b'{"error":"blocked"}'))
        self.assertFalse(monitor.acceptable_page('application/json', b'<html>not a response</html>'))

    def test_bing_rss_transport_does_not_get_rejected_as_an_announcement_host(self):
        session = MagicMock()
        session.__enter__.return_value = session
        response = MagicMock()
        response.__enter__.return_value = response
        response.url = 'https://www.bing.com/search?format=rss&q=test'
        response.headers = {'Content-Type': 'application/rss+xml'}
        response.iter_content.return_value = [b'<rss><channel></channel></rss>']
        session.get.return_value = response
        with patch.object(monitor, 'make_session', return_value=session):
            result = monitor.fetch_bytes('https://www.bing.com/search?format=rss&q=test')
        self.assertTrue(result.startswith(b'<rss>'))

    def test_bing_search_redirect_outside_bing_is_rejected(self):
        session = MagicMock()
        session.__enter__.return_value = session
        response = MagicMock()
        response.__enter__.return_value = response
        response.url = 'https://untrusted.example/search'
        response.headers = {'Content-Type': 'application/rss+xml'}
        response.iter_content.return_value = [b'<rss></rss>']
        session.get.return_value = response
        with patch.object(monitor, 'make_session', return_value=session):
            with self.assertRaisesRegex(ValueError, 'Search feed redirected'):
                monitor.fetch_bytes('https://www.bing.com/search?format=rss&q=test')

    def test_government_page_redirect_outside_allowed_hosts_is_rejected(self):
        session = MagicMock()
        session.__enter__.return_value = session
        response = MagicMock()
        response.__enter__.return_value = response
        response.url = 'https://untrusted.example/notice'
        response.headers = {'Content-Type': 'text/html'}
        response.iter_content.return_value = [b'<html>notice</html>']
        session.get.return_value = response
        with patch.object(monitor, 'make_session', return_value=session):
            with self.assertRaisesRegex(ValueError, 'Source redirected outside'):
                monitor.fetch_bytes('https://rst.hunan.gov.cn/notice.html')

    def test_guizhou_uses_jlu_section_url(self):
        config = json.loads((Path(monitor.__file__).resolve().parent / 'sources.json').read_text(encoding='utf8'))
        gz = next(x for x in config['monitors'] if x['province'] == '贵州')
        self.assertEqual(gz['url'], 'https://jdjyw.jlu.edu.cn/portal/article/details?id=1f6b210e15d944a6988d7af33b88cc00')
        self.assertEqual(len({gz['url'], *(x['url'] for x in gz['fallbacks'])}), 3)
        self.assertEqual(gz['fallbacks'][-1]['kind'], 'listing')
        self.assertEqual(gz['fallbacks'][-1]['url'], 'https://jdjyw.jlu.edu.cn/portal/article/list?cid=797ed1b0210f4f15937da33309184441')
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
        (self.root / 'third_sources.json').write_text(json.dumps({'updated':'','items':[]}), encoding='utf8')
        (self.root / 'watch_state.json').write_text(json.dumps({'articles':{},'listings':{},'search':{}}), encoding='utf8')
        self.fixture = self.root / 'fixtures'
        self.fixture.mkdir()
        for i in range(4):
            (self.fixture / f'third-index-{i}.html').write_text('<html><body>没有符合条件的公告</body></html>', encoding='utf8')
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

    def test_guizhou_article_failure_uses_index_as_degraded_fallback(self):
        list_url = 'https://jdjyw.jlu.edu.cn/portal/article/list?cid=797ed1b0210f4f15937da33309184441'
        html = ('<article>' + '2027年定向选调公告报名资格 ' * 12 + '</article>').encode()
        listing = ('<html><a href="/portal/article/details?id=1f6b210e15d944a6988d7af33b88cc00">'
                   '贵州省2027年度定向部分高校选调优秀毕业生公告</a></html>').encode()
        def stub(url):
            if 'id=1f6b210e15d944a6988d7af33b88cc00' in url:
                raise ValueError('unsupported content-type: (missing); bytes=0')
            return listing if url == list_url else html
        with patch.object(monitor, 'fetch_bytes', side_effect=stub):
            status = monitor.run(discovery=False)
        self.assertEqual(status['sourceHealth'][6]['state'], 'fallback')
        self.assertEqual(status['sourceHealth'][6]['used']['kind'], 'listing')
        self.assertEqual(status['fallbacksUsed'], 1)
        self.assertIn('公告正文及附件仍未读取', status['errors'][-1])
        self.assertNotIn('https://jdjyw.jlu.edu.cn/portal/article/details?id=1f6b210e15d944a6988d7af33b88cc00',
                         json.loads((self.root / 'watch_state.json').read_text())['articles'])

    def test_guizhou_empty_index_does_not_hide_failure(self):
        list_url = 'https://jdjyw.jlu.edu.cn/portal/article/list?cid=797ed1b0210f4f15937da33309184441'
        html = ('<article>' + '2027定向选调信息 ' * 12 + '</article>').encode()
        def stub(url):
            if 'id=1f6b210e15d944a6988d7af33b88cc00' in url:
                raise ValueError('empty article')
            if url == list_url:
                return '<html><body><a href="/notice">2027四川选调公告</a></body></html>'.encode()
            return html
        with patch.object(monitor, 'fetch_bytes', side_effect=stub):
            status = monitor.run(discovery=False)
        self.assertEqual(status['sourceHealth'][6]['state'], 'failed')
        self.assertEqual(status['fallbacksUsed'], 0)
        self.assertEqual(len(status['errors']), 3)

    def test_third_tier_publication_requires_manual_verification(self):
        import build
        self.root.joinpath('index.html').write_bytes((Path(build.__file__).resolve().parent/'index.html').read_bytes())
        data=json.loads((self.root/'data.json').read_text(encoding='utf8'))
        third=dict(data['records'][0])
        third.update({'province':'云南','title':'云南2027高校定向选调（示例测试，不得发布）',
                      'source':'https://job.hust.edu.cn/example',
                      'sourceTier':'university_third','sourceType':'其他高校补充',
                      'sourceName':'华中科技大学就业信息网',
                      'school':'仅按该高校公告和职位表确定','notes':'已核验适用高校、原文附件与校内流程差异'})
        data['records'].append(third)
        (self.root/'data.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf8')
        with patch.object(build,'ROOT',self.root):
            with self.assertRaisesRegex(ValueError,'human source and school-scope review'):
                build.build()
            third['reviewedSource']=True
            third['reviewedScope']=True
            (self.root/'data.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf8')
            build.build()
            build.build(check=True)

    def test_third_fallback_search_only_when_no_higher_priority_coverage(self):
        config=json.loads((self.root/'sources.json').read_text(encoding='utf8'))
        for i, province in enumerate(config['discovery']['provinces']):
            # Healthy monitored provinces don't need the third fallback; all
            # unrecorded provinces with empty primary RSS get a third query.
            (self.fixture/f'search-{i}.xml').write_text('<rss><channel></channel></rss>',encoding='utf8')
            url='https://job.hust.edu.cn/jcfw/2439641.htm'
            rss=(f'<rss><channel><item><title>{province}2027定向选调公告</title><link>{url}</link></item></channel></rss>'
                 if province=='云南' else '<rss><channel></channel></rss>')
            (self.fixture/f'third-search-{i}.xml').write_text(rss,encoding='utf8')
        before=(self.root/'data.json').read_text(encoding='utf8')
        status=monitor.run(discovery=True,fixture_dir=self.fixture)
        self.assertEqual(status['searchesSucceeded'],31)
        self.assertEqual(status['thirdLinksFound'],1)
        self.assertEqual(status['thirdSearchesAttempted'],status['thirdSearchesSucceeded'])
        self.assertEqual(status['newCandidates'],0)
        self.assertEqual(status['supplementalNew'],1)
        self.assertEqual(status['supplementalTotal'],1)
        self.assertEqual(json.loads((self.root/'review_queue.json').read_text(encoding='utf8'))['candidates'],[])
        candidate=json.loads((self.root/'third_sources.json').read_text(encoding='utf8'))['items'][0]
        self.assertEqual(candidate['sourceTier'],'university_third')
        self.assertNotIn('status',candidate)
        self.assertIn('适用高校',candidate['note'])
        self.assertEqual((self.root/'data.json').read_text(encoding='utf8'),before)
        second=monitor.run(discovery=True,fixture_dir=self.fixture)
        self.assertEqual(second['newCandidates'],0)
        self.assertEqual(second['supplementalNew'],0)
        self.assertEqual(second['supplementalTotal'],1)

    def test_direct_university_index_provides_candidate_when_rss_misses(self):
        config=json.loads((self.root/'sources.json').read_text(encoding='utf8'))
        for i,_ in enumerate(config['discovery']['provinces']):
            (self.fixture/f'search-{i}.xml').write_text('<rss><channel></channel></rss>',encoding='utf8')
            (self.fixture/f'third-search-{i}.xml').write_text('<rss><channel></channel></rss>',encoding='utf8')
        (self.fixture/'third-index-0.html').write_text(
            '<a href="/career/news/recruitment/test">云南省2027年定向选调公告</a>',encoding='utf8')
        status=monitor.run(discovery=True,fixture_dir=self.fixture)
        self.assertEqual(status['thirdIndexesSucceeded'],4)
        self.assertEqual(status['thirdIndexesAttempted'],4)
        self.assertEqual(status['newCandidates'],0)
        self.assertEqual(status['supplementalNew'],1)
        self.assertEqual(json.loads((self.root/'review_queue.json').read_text(encoding='utf8'))['candidates'],[])
        c=json.loads((self.root/'third_sources.json').read_text(encoding='utf8'))['items'][0]
        self.assertEqual(c['province'],'云南')
        self.assertEqual(c['sourceTier'],'university_third')
        self.assertEqual(c['kind'],'listing')
        self.assertNotIn('云南', [r['province'] for r in json.loads((self.root/'data.json').read_text())['records']])

    def test_failed_official_can_get_third_lead_without_claiming_success(self):
        config=json.loads((self.root/'sources.json').read_text(encoding='utf8'))
        for i,province in enumerate(config['discovery']['provinces']):
            primary=f'<rss><channel><item><title>{province}2027定向选调公告</title><link>https://rst.hunan.gov.cn/news</link></item></channel></rss>'
            (self.fixture/f'search-{i}.xml').write_text(primary,encoding='utf8')
            third=('<rss><channel><item><title>湖南2027定向选调公告</title><link>https://job.hust.edu.cn/jcfw/2439641.htm</link></item></channel></rss>' if province=='湖南' else '<rss><channel></channel></rss>')
            (self.fixture/f'third-search-{i}.xml').write_text(third,encoding='utf8')
        (self.fixture/'monitor-3.html').unlink()  # Hunan govt fails
        status=monitor.run(discovery=True,fixture_dir=self.fixture)
        self.assertEqual(status['monitorsSucceeded'],7)
        self.assertEqual(status['sourceHealth'][3]['state'],'failed')
        self.assertEqual(status['thirdSearchesAttempted'],1)
        self.assertEqual(status['thirdLinksFound'],1)
        self.assertEqual(status['searchesSucceeded'],31)

    def test_old_third_candidates_migrate_to_independent_feed(self):
        old={'id':'legacy-id','province':'云南','title':'云南2027定向选调公告',
             'url':'https://job.hust.edu.cn/a','kind':'search','source':'旧搜索',
             'discovered':'2026-09-21T12:00:00+08:00','sourceTier':'university_third',
             'status':'pending'}
        primary={'id':'official-id','province':'北京','title':'北京2027定向选调公告',
                 'url':'https://www.beijing.gov.cn/notice','kind':'search','source':'搜索',
                 'discovered':'2026-09-21T12:00:00+08:00','sourceTier':'government',
                 'status':'pending'}
        (self.root/'review_queue.json').write_text(json.dumps({'updated':'', 'candidates':[old,primary]}),encoding='utf8')
        first=monitor.run(discovery=False,fixture_dir=self.fixture)
        queue=json.loads((self.root/'review_queue.json').read_text(encoding='utf8'))['candidates']
        sources=json.loads((self.root/'third_sources.json').read_text(encoding='utf8'))['items']
        self.assertEqual(len(queue),1)
        self.assertEqual(queue[0]['id'],'official-id')
        self.assertEqual(len(sources),1)
        self.assertEqual(sources[0]['discovered'],old['discovered'])
        self.assertNotIn('status',sources[0])
        self.assertEqual(first['supplementalNew'],0)
        monitor.run(discovery=False,fixture_dir=self.fixture)
        self.assertEqual(len(json.loads((self.root/'third_sources.json').read_text(encoding='utf8'))['items']),1)

    def test_third_tier_never_enters_review_queue(self):
        with self.assertRaisesRegex(ValueError, 'third_sources.json'):
            monitor.queue_candidate([],set(),{'province':'湖南','title':'湖南2027定向选调',
                'kind':'search','url':'https://job.hust.edu.cn/example','source':'search'}, monitor.now_iso())

    def test_third_index_and_rss_duplicate_same_url(self):
        config=json.loads((self.root/'sources.json').read_text(encoding='utf8'))
        url='https://jiuye.uestc.edu.cn/career/news/recruitment/test'
        for i,p in enumerate(config['discovery']['provinces']):
            (self.fixture/f'search-{i}.xml').write_text('<rss><channel></channel></rss>',encoding='utf8')
            content=(f'<rss><channel><item><title>{p}2027年定向选调公告</title><link>{url}</link></item></channel></rss>'
                     if p=='云南' else '<rss><channel></channel></rss>')
            (self.fixture/f'third-search-{i}.xml').write_text(content,encoding='utf8')
        (self.fixture/'third-index-0.html').write_text(
            f'<a href="{url}">云南2027年定向选调公告</a>',encoding='utf8')
        result=monitor.run(discovery=True,fixture_dir=self.fixture)
        self.assertEqual(result['supplementalNew'],1)
        self.assertEqual(result['supplementalTotal'],1)
        self.assertEqual(result['newCandidates'],0)
        self.assertEqual(json.loads((self.root/'review_queue.json').read_text(encoding='utf8'))['candidates'],[])

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
