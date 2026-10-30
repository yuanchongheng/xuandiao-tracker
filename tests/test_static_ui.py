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


    def test_completed_exams_belong_to_past_section_per_batch(self):
        import json
        text = (ROOT / 'index.html').read_text(encoding='utf-8')
        data = json.loads((ROOT / 'data.json').read_text(encoding='utf-8'))
        self.assertIn("if(now>examEnd)return 'done';", text)
        self.assertIn("if(today>examDay)return 'done';", text)
        self.assertNotIn("return 'results'", text)
        self.assertNotIn("['results','成绩已出']", text)
        self.assertIn("const entries=dataset.records.map(record=>", text)
        self.assertIn("const items=entries.filter(item=>item.stage===stage)", text)
        self.assertIn("let provinceDoneExpanded=true;", text)
        self.assertIn("r?.scoreStatus==='published'&&stage==='done'", text)
        self.assertEqual(len(data['provinces']), 31)
        self.assertEqual(len([r for r in data['records'] if r['province'] == '四川']), 2)

    def test_each_selection_track_opens_own_detail(self):
        text = (ROOT / 'index.html').read_text(encoding='utf-8')
        self.assertIn('data-record="${escapeHTML(encodeURIComponent(keyFor(r)))}"', text)
        self.assertIn("openDetail(decodeURIComponent(b.dataset.record))", text)
        self.assertIn("toggleProvinceWatch(b.dataset.watch)", text)
        self.assertIn("stage==='done'", text)

    def test_progress_classification_of_finished_and_upcoming_exams(self):
        import re
        import shutil
        import subprocess
        node = shutil.which('node')
        if not node:
            self.skipTest('Node.js is not installed')
        html = (ROOT / 'index.html').read_text(encoding='utf-8')
        match = re.search(r'function recordProgress\(r,now=Date\.now\(\)\)\{[\s\S]*?\n\}', html)
        self.assertIsNotNone(match)
        javascript = """
        function localParts(date) {
            const vals={};
            const fmt=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'});
            for (const v of fmt.formatToParts(new Date(date))) if(v.type!=='literal') vals[v.type]=v.value;
            return {key:vals.year+'-'+vals.month+'-'+vals.day};
        }
        """ + match.group(0) + """
        const time=Date.parse('2026-10-30T12:00:00+08:00');
        const cases=[
            [{start:'2026-10-08T00:00:00+08:00',end:'2026-10-14T18:00:00+08:00',exam:'2026-10-24T00:00:00+08:00'},'done'],
            [{start:'2026-11-03T00:00:00+08:00',end:'2026-11-09T18:00:00+08:00',exam:'2026-12-06T00:00:00+08:00'},'soon'],
            [{start:'2026-09-20T09:00:00+08:00',end:'2026-09-29T17:00:00+08:00',exam:'2026-10-11T00:00:00+08:00',scoreStatus:'published'},'done'],
            [{start:'2026-10-08T08:30:00+08:00',end:'2026-10-17T17:30:00+08:00',exam:'2026-11-01T09:00:00+08:00',examEnd:'2026-11-01T11:30:00+08:00'},'preexam'],
            [{start:'',end:'',exam:''},'unknown'],
            [{start:'2026-09-20T09:00:00+08:00',end:'2026-09-29T17:00:00+08:00',exam:'2026-10-30T00:00:00+08:00'},'examday']
        ];
        for(const [record,expected] of cases){
            const actual=recordProgress(record,time);
            if(actual!==expected)throw new Error(expected+' expected, got '+actual+': '+JSON.stringify(record));
        }
        const card={start:'2026-10-08T08:30:00+08:00',end:'2026-10-17T17:30:00+08:00',exam:'2026-11-01T09:00:00+08:00',examEnd:'2026-11-01T11:30:00+08:00'};
        if(recordProgress(card,Date.parse('2026-11-01T10:00:00+08:00'))!=='examday')throw new Error('during exam');
        if(recordProgress(card,Date.parse('2026-11-01T12:00:00+08:00'))!=='done')throw new Error('after exam');
        """
        subprocess.run([node, '-e', javascript], check=True, capture_output=True, text=True)


if __name__ == '__main__':
    unittest.main()
