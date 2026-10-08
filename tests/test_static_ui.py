import unittest
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
