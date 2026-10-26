import unittest

import jlu_auto_publish
import jlu_timing_fix
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


    def test_2027_heilongjiang_exam_hour_not_guessed(self):
        from pathlib import Path
        import json
        data = json.loads((Path(__file__).resolve().parents[1] / 'data.json').read_text(encoding='utf-8'))
        record = next(r for r in data['records'] if r['province'] == '黑龙江')
        self.assertEqual(record['exam'], '2026-11-01T00:00:00+08:00')
        self.assertTrue(record['examDateOnly'])
        self.assertFalse(record['examEnd'])
        known = jlu_timing_fix.KNOWN_TIMINGS[('黑龙江', '黑龙江省2027年度定向选调应届优秀大学毕业生公告')]
        self.assertEqual(known['exam'], record['exam'])
        self.assertTrue(known['examDateOnly'])
        self.assertNotIn('examEnd', known)

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



if __name__ == '__main__':
    unittest.main()
