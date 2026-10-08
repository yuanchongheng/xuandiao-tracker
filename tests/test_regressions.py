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

    def test_government_result_keeps_priority_over_jlu_search_hit(self):
        rss = """<rss><channel><item><title>重庆2027定向选调公告</title><link>https://www.cq.gov.cn/a</link></item><item><title>重庆2027面向吉林大学定向选调公告</title><link>https://jdjywpt.jlu.edu.cn/portal/xdsgz/article/details?id=x</link></item></channel></rss>"""
        urls = [item['url'] for item in monitor.parse_rss(rss.encode(), '重庆', '2027')]
        self.assertEqual(urls, ['https://www.cq.gov.cn/a'])

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


if __name__ == '__main__':
    unittest.main()
