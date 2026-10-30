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


    def test_watchlist_reminders_exclude_other_school_batches(self):
        text = (ROOT / 'index.html').read_text(encoding='utf-8')
        self.assertIn('dataset.records.filter(x=>x.province===province&&!isPersonalIneligible(x))', text)
        self.assertIn("const eligible=records.filter(record=>!isPersonalIneligible(record))", text)
        self.assertIn("provinceProgress(rows,now,true)", text)
        self.assertIn("const ranked=(personal&&eligible.length?eligible:records)", text)
        self.assertIn("provinceUnavailable(rows)?'吉林大学当前不可报 · 等待对应公告'", text)

    def test_national_notices_show_personal_unavailability(self):
        text = (ROOT / 'index.html').read_text(encoding='utf-8')
        self.assertIn("function isPersonalIneligible(record)", text)
        self.assertIn("ineligible_no_jlu", text)
        self.assertIn("ineligible_school_scope", text)
        self.assertIn('tag personal-unavailable', text)

    def test_date_only_calendar_does_not_invent_opening_time(self):
        text = (ROOT / 'index.html').read_text(encoding='utf-8')
        self.assertIn("dateOnly:!!r.startDateOnly", text)
        self.assertNotIn("dateOnly:!!r.startTimeUnknown", text)


    def test_province_progress_shows_verified_score_results_separately(self):
        import json
        text = (ROOT / 'index.html').read_text(encoding='utf-8')
        data = json.loads((ROOT / 'data.json').read_text(encoding='utf-8'))
        self.assertIn("results:'成绩已出'", text)
        self.assertIn("['results','成绩已出']", text)
        self.assertIn("if(r.scoreStatus==='published'&&Number.isFinite(exam)&&now>exam)return 'results';", text)
        self.assertIn("results:4,unknown:5,closed:6,done:7", text)
        self.assertIn("stage==='results'?' province-results-group':''", text)
        self.assertIn("if(stage==='done')", text)
        self.assertIn("releasedCount=records.filter(r=>r.scoreStatus==='published').length", text)
        released = {r['province'] for r in data['records'] if r.get('scoreStatus') == 'published'}
        self.assertEqual(released, {'北京', '湖北', '湖南'})
        # Active batches take precedence, but prior batches' released scores remain visible.
        self.assertIn("stage!=='results'&&releasedCount", text)
    def test_overview_keeps_each_selection_track_clickable(self):
        text = (ROOT / 'index.html').read_text(encoding='utf-8')
        self.assertIn('class="province-batches"', text)
        self.assertIn('class="province-batch-open"', text)
        self.assertIn('data-record="${encodeURIComponent(keyFor(r))}"', text)
        self.assertIn("openDetail(decodeURIComponent(b.dataset.record))", text)
        self.assertIn("records.length>1?", text)


if __name__ == '__main__':
    unittest.main()
