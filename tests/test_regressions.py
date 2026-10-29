import unittest

import jlu_auto_publish
import jlu_timing_fix
import data_hygiene
from source_policy import source_tier
import monitor
from province_utils import province_from_title


class AuditRegressionTests(unittest.TestCase):
    def test_chongqing_title_is_not_misclassified_as_jilin(self):
        title = '重庆市面向吉林大学定向选调 2027届急需紧缺专业应届优秀大学毕业生公告'
        self.assertEqual(province_from_title(title), '重庆')

    def test_university_name_is_not_treated_as_target_province(self):
        self.assertIsNone(province_from_title('吉林大学2027届毕业生就业通知'))
        self.assertEqual(
            province_from_title('吉林大学发布重庆市2027年度定向选调公告'),
            '重庆'
        )

    def test_year_prefix_province_is_detected(self):
        self.assertEqual(province_from_title('2027届四川定向选调公告'), '四川')

    def test_jlu_search_requires_relevant_title_not_only_snippet(self):
        rss = """<rss><channel><item><title>吉林大学就业信息更新</title><description>重庆2027定向选调公告</description><link>https://jdjywpt.jlu.edu.cn/portal/xdsgz/article/details?id=x</link></item></channel></rss>"""
        self.assertEqual(monitor.parse_rss(rss.encode(), '重庆', '2027'), [])

    def test_distinct_government_and_jlu_search_hits_are_retained(self):
        rss = """<rss><channel><item><title>重庆2027定向选调公告</title><link>https://www.cq.gov.cn/a</link></item><item><title>重庆2027面向吉林大学定向选调公告</title><link>https://jdjywpt.jlu.edu.cn/portal/xdsgz/article/details?id=x</link></item></channel></rss>"""
        urls = [item['url'] for item in monitor.parse_rss(rss.encode(), '重庆', '2027')]
        self.assertEqual(urls, ['https://www.cq.gov.cn/a', 'https://jdjywpt.jlu.edu.cn/portal/xdsgz/article/details?id=x'])

    def test_auto_publish_uses_date_only_flag_without_legacy_field(self):
        timing = jlu_auto_publish.extract_timing(
            '网上报名时间为2026年10月8日至10月14日18:00。',
            2026
        )
        self.assertEqual(timing['start'], '2026-10-08T00:00:00+08:00')
        self.assertTrue(timing['startDateOnly'])
        self.assertNotIn('startTimeUnknown', timing)
        self.assertEqual(timing['end'], '2026-10-14T18:00:00+08:00')

    def test_timing_fix_is_date_only_compatible(self):
        timing = jlu_timing_fix.parse_timing(
            '网上报名。考生于2026年10月8日至10月14日18:00报名。',
            2026
        )
        self.assertEqual(timing['start'], '2026-10-08T00:00:00+08:00')
        self.assertTrue(timing['startDateOnly'])
        self.assertEqual(timing['end'], '2026-10-14T18:00:00+08:00')


    def test_2027_heilongjiang_candidate_admit_card_hours_preserved(self):
        from pathlib import Path
        import json
        data = json.loads((Path(__file__).resolve().parents[1] / 'data.json').read_text(encoding='utf-8'))
        record = next(r for r in data['records'] if r['province'] == '黑龙江')
        self.assertEqual(record['exam'], '2026-11-01T09:00:00+08:00')
        self.assertEqual(record['examEnd'], '2026-11-01T11:30:00+08:00')
        self.assertFalse(record.get('examDateOnly', False))
        self.assertIn('本人准考证', record['notes'])
        self.assertIn('本人准考证', record['examText'])
        known = jlu_timing_fix.KNOWN_TIMINGS[('黑龙江', '黑龙江省2027年度定向选调应届优秀大学毕业生公告')]
        self.assertEqual(known['exam'], record['exam'])
        self.assertEqual(known['examEnd'], record['examEnd'])
        self.assertFalse(known['examDateOnly'])
        self.assertTrue(known['examPersonalAdmitCard'])

    def test_2027_heilongjiang_date_only_scrape_keeps_candidate_admit_card(self):
        record = {'province': '黑龙江', 'title': '黑龙江省2027年度定向选调应届优秀大学毕业生公告'}
        scraped = {'exam': '2026-11-01T00:00:00+08:00', 'examDateOnly': True}
        merged, _ = jlu_timing_fix.merge_known(record, scraped)
        self.assertEqual(merged['exam'], '2026-11-01T09:00:00+08:00')
        self.assertEqual(merged['examEnd'], '2026-11-01T11:30:00+08:00')
        self.assertFalse(merged['examDateOnly'])
        self.assertIn('准考证', merged['examText'])

    def test_2027_heilongjiang_explicit_official_hours_not_overridden(self):
        record = {'province': '黑龙江', 'title': '黑龙江省2027年度定向选调应届优秀大学毕业生公告'}
        scraped = {'exam': '2026-11-01T08:30:00+08:00', 'examDateOnly': False}
        merged, _ = jlu_timing_fix.merge_known(record, scraped)
        self.assertEqual(merged['exam'], scraped['exam'])
        self.assertNotIn('examEnd', merged)

    def test_2027_jiangsu_official_jlu_scope_not_conflated_with_personal_marker(self):
        from pathlib import Path
        import json
        data = json.loads((Path(__file__).resolve().parents[1] / 'data.json').read_text(encoding='utf-8'))
        record = next(r for r in data['records'] if r['province'] == '江苏')
        self.assertIn('吉林大学', record['school'])
        self.assertIn('类别III', record['school'])
        self.assertIn('类别I', record['school'])
        self.assertEqual(record['personalEligibility'], 'ineligible_no_jlu')
        self.assertIn('不代表官方明确排除吉林大学', record['eligibility'])
        self.assertTrue(record['startDateOnly'])
        self.assertTrue(record['examDateOnly'])


    def test_sichuan_personal_scope_is_batch_specific(self):
        records = [
            {'province': '四川', 'title': '四川省面向吉林大学选调2027届优秀大学毕业生',
             'sourceTier': 'jlu_fallback', 'eligibility': '已发布急需紧缺专业定向批次'},
            {'province': '四川', 'title': '四川省2027年度选调优秀大学毕业生到基层工作公告',
             'sourceTier': 'government', 'eligibility': '基层选调条件',
             'personalMatchKeywords': ['基层']},
        ]
        data = {'records': records}
        data_hygiene.reconcile_other_school_coverage(data, {'items': []})
        self.assertEqual(records[1]['personalEligibility'], 'ineligible_no_jlu')
        self.assertIn('同省其他批次', records[1]['eligibility'])
        records.append({
            'province': '四川', 'title': '四川省2027年度基层选调面向吉林大学公告',
            'sourceTier': 'jlu_fallback', 'eligibility': '基层选调吉大公告',
        })
        data_hygiene.reconcile_other_school_coverage(data, {'items': []})
        self.assertNotIn('personalEligibility', records[1])
        self.assertEqual(records[1]['eligibility'], '基层选调条件')

    def test_sichuan_official_exam_portal_exact_host(self):
        self.assertEqual(source_tier('https://www.scpta.com.cn/front/News/info/d70ea76551094491ac8249c90eaf0040?t=56'), 'government')
        self.assertIsNone(source_tier('https://not-scpta.com.cn/front/News/info/abc'))
        self.assertIsNone(source_tier('https://scpta.com.cn.evil.example/front/News/info/abc'))

    def test_sichuan_grassroots_dates_do_not_borrow_emergency_batch(self):
        from pathlib import Path
        import json
        data = json.loads((Path(__file__).resolve().parents[1] / 'data.json').read_text(encoding='utf-8'))
        notices = [r for r in data['records'] if r['province'] == '四川']
        self.assertEqual(len(notices), 2)
        grassroots = next(r for r in notices if '基层工作公告' in r['title'])
        self.assertEqual(grassroots['start'], '2026-11-03T00:00:00+08:00')
        self.assertTrue(grassroots['startDateOnly'])
        self.assertEqual(grassroots['end'], '2026-11-09T18:00:00+08:00')
        self.assertEqual(grassroots['exam'], '2026-12-06T00:00:00+08:00')
        self.assertTrue(grassroots['examDateOnly'])
        self.assertEqual(grassroots['personalMatchKeywords'], ['基层'])
        self.assertEqual(grassroots['personalEligibility'], 'ineligible_no_jlu')
        self.assertIn('原文直连无法打开', grassroots['notes'])



if __name__ == '__main__':
    unittest.main()
