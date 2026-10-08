import unittest
import monitor
from province_utils import province_from_title


class AuditRegressionTests(unittest.TestCase):
    def test_chongqing_title_is_not_misclassified_as_jilin(self):
        title = '重庆市面向吉林大学定向选调 2027届急需紧缺专业应届优秀大学毕业生公告'
        self.assertEqual(province_from_title(title), '重庆')

    def test_year_prefix_province_is_detected(self):
        self.assertEqual(province_from_title('2027届四川定向选调公告'), '四川')

    def test_jlu_search_requires_relevant_title_not_only_snippet(self):
        rss = """<rss><channel><item><title>吉林大学就业信息更新</title><description>重庆2027定向选调公告</description><link>https://jdjywpt.jlu.edu.cn/portal/xdsgz/article/details?id=x</link></item></channel></rss>"""
        self.assertEqual(monitor.parse_rss(rss.encode(), '重庆', '2027'), [])

    def test_government_result_keeps_priority_over_jlu_search_hit(self):
        rss = """<rss><channel><item><title>重庆2027定向选调公告</title><link>https://www.cq.gov.cn/a</link></item><item><title>重庆2027面向吉林大学定向选调公告</title><link>https://jdjywpt.jlu.edu.cn/portal/xdsgz/article/details?id=x</link></item></channel></rss>"""
        urls = [x['url'] for x in monitor.parse_rss(rss.encode(), '重庆', '2027')]
        self.assertEqual(urls, ['https://www.cq.gov.cn/a'])


if __name__ == '__main__':
    unittest.main()
