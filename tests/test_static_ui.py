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


    def test_watchlist_tracks_specific_notice_batches_without_cross_reminders(self):
        text = (ROOT / 'index.html').read_text(encoding='utf-8')
        self.assertIn("const WATCH_KEY='xd_watched_batches_v2'", text)
        self.assertIn("const recordsByKey=new Map(dataset.records.map(r=>[keyFor(r),r]))", text)
        self.assertIn("if(!record||isPersonalIneligible(record))return [];", text)
        self.assertIn("const stage=recordProgress(record,now),events=watchEvents(record,now)", text)
        self.assertIn("const groups=[['open','报名中']", text)
        self.assertIn("['done','笔试已过']", text)
        self.assertIn("data-watch-key", text)
        self.assertIn("toggleWatchKey(decodeURIComponent(b.dataset.watchKey))", text)
        self.assertNotIn("watchedProvinces", text)
        self.assertNotIn("toggleProvinceWatch", text)


    def test_national_notices_show_personal_unavailability(self):
        text = (ROOT / 'index.html').read_text(encoding='utf-8')
        self.assertIn("function isPersonalIneligible(record)", text)
        self.assertIn("ineligible_no_jlu", text)
        self.assertIn("pending_school_scope", text)
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
        self.assertIn("toggleWatchKey(decodeURIComponent(b.dataset.watchKey))", text)
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

    def test_schedule_renders_pending_and_excluded_scope_labels(self):
        import shutil
        import subprocess
        node = shutil.which('node')
        if not node:
            self.skipTest('Node.js is not installed')
        javascript = r"""
        const fs=require('fs'),vm=require('vm'),assert=require('assert');
        const html=fs.readFileSync('index.html','utf8');
        const schedule=html.slice(html.indexOf('const cDateFmt='),html.indexOf('function scoreProgress('));
        const labels=html.match(/function personalEligibilityLabel\(r\).*$/m)[0];
        const unavailable=html.match(/function isPersonalIneligible\(record\).*$/m)[0];
        const elements=new Map(),opened=[];
        const records=[
          {province:'山东',title:'待核实批次',start:'2100-11-09T09:00:00+08:00',personalEligibility:'ineligible_no_jlu'},
          {province:'贵州',title:'不在范围批次',start:'2100-11-09T10:00:00+08:00',personalEligibility:'ineligible_school_scope'},
          {province:'天津',title:'已核实批次',start:'2100-11-09T11:00:00+08:00',personalEligibility:'eligible_jlu'}
        ];
        const ctx={TZ:'Asia/Shanghai',getResults:()=>records,keyFor:r=>r.title,
          escapeHTML:x=>String(x),openDetail:key=>opened.push(key),
          $:id=>{if(!elements.has(id))elements.set(id,{innerHTML:'',textContent:'',querySelectorAll:()=>[]});return elements.get(id)}
        };
        vm.createContext(ctx);
        vm.runInContext(labels+'\n'+unavailable+'\n'+schedule,ctx);
        vm.runInContext('renderSchedule()',ctx);
        const timeline=elements.get('timelineList').innerHTML;
        assert(timeline.includes('吉大高校范围待核实'));
        assert(timeline.includes('吉大不在本批高校范围'));
        assert.equal((timeline.match(/class="timeline-item"/g)||[]).length,3);
        assert.equal((timeline.match(/class="timeline-detail"/g)||[]).length,3);
        assert(elements.get('calendarBoard').innerHTML.includes('2100-11-09'));
        const agenda=elements.get('selectedDayEvents').innerHTML;
        assert(agenda.includes('吉大高校范围待核实'));
        assert(agenda.includes('吉大不在本批高校范围'));
        // Rendering also binds each timeline button to its own notice.
        const button={dataset:{key:encodeURIComponent(records[0].title)}};
        elements.get('timelineList').querySelectorAll=()=>[button];
        vm.runInContext('renderSchedule()',ctx);
        button.onclick();
        assert.deepEqual(opened,[records[0].title]);
        """
        result = subprocess.run([node, '-e', javascript], capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_batch_watch_migration_and_isolated_toggle_in_node(self):
        import shutil
        import subprocess
        node = shutil.which('node')
        if not node:
            self.skipTest('Node.js is not installed')
        javascript = r"""
        const fs=require('fs'),vm=require('vm'),assert=require('assert');
        const html=fs.readFileSync('index.html','utf8');
        const before=html.indexOf("const WATCH_KEY='xd_watched_batches_v2'");
        const beforeEnd=html.indexOf('function validData(d){',before);
        const watch=html.indexOf('function saveWatch(){',beforeEnd);
        const after=html.indexOf('let provinceDoneExpanded=true;',watch);
        assert(before>=0&&beforeEnd>before&&watch>beforeEnd&&after>watch);
        const src=html.slice(before,beforeEnd)+html.slice(watch,after);
        const sc={province:'四川',type:'定向',title:'四川定向选调',exam:'2026-10-24T00:00:00+08:00',end:'2026-10-14T18:00:00+08:00',source:'https://example.org/sc1',verified:'2026-10-24'};
        const sb={province:'四川',type:'基层',title:'四川基层选调',start:'2026-11-03T00:00:00+08:00',end:'2026-11-09T18:00:00+08:00',exam:'2026-12-06T00:00:00+08:00',source:'https://example.org/sc2',verified:'2026-10-29',personalEligibility:'ineligible_no_jlu'};
        const ln={province:'辽宁',type:'定向',title:'辽宁定向选调',source:'https://example.org/ln',verified:'2026-10-21'};
        const records=[sc,sb,ln],storage=new Map([
          ['xd_watched_provinces_v1',JSON.stringify(['四川','辽宁'])],
          ['xd_application_progress_v1',JSON.stringify({'四川':'正在报名','辽宁':'已报名'})]
        ]);
        const elements=new Map();
        const ctx={
          dataset:{provinces:['四川','辽宁'],records},localStorage:{
            getItem:k=>storage.has(k)?storage.get(k):null,
            setItem:(k,v)=>storage.set(k,v)
          },
          validData:()=>false,keyFor:r=>r.province+'|'+r.title,
          recordProgress:r=>r.title==='四川定向选调'?'done':r.title==='四川基层选调'?'soon':'unknown',
          isPersonalIneligible:r=>!!r&&r.personalEligibility==='ineligible_no_jlu',
          personalEligibilityLabel:r=>r.personalEligibility==='ineligible_no_jlu'?'吉大高校范围待核实':'',
          progressNote:()=> '当前批次',shortProgressDate:()=> '11月3日',
          dateFmt:t=>t,provinceStages:{done:'笔试已过',soon:'即将报名',unknown:'时间待核'},
          safeUrl:x=>x,escapeHTML:x=>String(x).replace(/&/g,'&amp;').replace(/</g,'&lt;'),
          renderProvinces:()=>{},openDetail:()=>{},
          $:id=>{if(!elements.has(id))elements.set(id,{innerHTML:'',textContent:'',querySelectorAll:()=>[]});return elements.get(id)},
          document:{querySelectorAll:()=>[]},state:{}
        };
        vm.createContext(ctx);
        vm.runInContext(src,ctx);
        let watched=JSON.parse(storage.get('xd_watched_batches_v2'));
        assert(watched.includes('@province|四川')&&!watched.includes('四川|四川定向选调'));
        assert(watched.includes('辽宁|辽宁定向选调'));
        vm.runInContext('renderWatchlist()',ctx);
        assert(elements.get('watchGrid').innerHTML.includes('请选择具体批次'));
        vm.runInContext("toggleWatchKey('四川|四川定向选调')",ctx);
        watched=JSON.parse(storage.get('xd_watched_batches_v2'));
        assert(watched.includes('四川|四川定向选调')&&!watched.includes('四川|四川基层选调'));
        assert(!watched.includes('@province|四川'));
        assert.equal(vm.runInContext("applicationProgress['四川|四川定向选调']",ctx),'正在报名');
        let rendered=elements.get('watchGrid').innerHTML;
        assert(rendered.includes('四川定向选调')&&!rendered.includes('四川基层选调'));
        assert(rendered.includes('笔试已过'));
        vm.runInContext("toggleWatchKey('四川|四川基层选调')",ctx);
        watched=JSON.parse(storage.get('xd_watched_batches_v2'));
        assert(watched.includes('四川|四川定向选调')&&watched.includes('四川|四川基层选调'));
        rendered=elements.get('watchGrid').innerHTML;
        assert(rendered.includes('四川定向选调')&&rendered.includes('四川基层选调'));
        assert(rendered.includes('即将报名')&&rendered.includes('笔试已过'));
        assert.equal(vm.runInContext("applicationProgress['四川|四川定向选调']",ctx),'正在报名');
        assert.equal(vm.runInContext("applicationProgress['四川|四川基层选调']",ctx),'关注中');
        const blocked=vm.runInContext("watchEvents(dataset.records[1],Date.parse('2026-10-30T12:00:00+08:00'))",ctx);
        assert.equal(blocked.length,0);
        vm.runInContext("toggleWatchKey('四川|四川基层选调')",ctx);
        watched=JSON.parse(storage.get('xd_watched_batches_v2'));
        assert(watched.includes('四川|四川定向选调')&&!watched.includes('四川|四川基层选调'));
        // Reloaded data must never re-migrate the old province bookmark into both batches.
        const reloaded=vm.createContext({...ctx});
        vm.runInContext(src,reloaded);
        const reloadedKeys=JSON.parse(vm.runInContext("JSON.stringify([...watchedItems])",reloaded));
        assert.equal(reloadedKeys.filter(x=>x.startsWith('四川|')).length,1);
        assert(!reloadedKeys.includes('@province|四川'));
        """
        result = subprocess.run([node, '-e', javascript], capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


    def test_announcement_search_prioritizes_actionable_batches(self):
        import shutil
        import subprocess
        node = shutil.which('node')
        if not node:
            self.skipTest('Node.js is not installed')
        javascript = r"""
        const assert=require('assert/strict'),fs=require('fs'),vm=require('vm');
        const html=fs.readFileSync('index.html','utf8');
        const start=html.indexOf('function getResults()');
        const end=html.indexOf('// All calendar days',start);
        const status=html.match(/^function statusOf\(r\).*$/m)[0];
        const fixedTime=Date.parse('2026-11-20T12:00:00+08:00');
        const record=(title,province,start,end,published)=>({
          title,province,start:start&&start+'T09:00:00+08:00',
          end:end&&end+'T18:00:00+08:00',published
        });
        const records=[
          record('旧批次','吉林','2026-09-01','2026-09-08','2026-09-01'),
          record('近日截止','山东','2026-11-19','2026-11-21','2026-11-18'),
          record('暂未定','广东','','','2026-11-20'),
          record('即将报名','山东','2026-11-23','2026-11-24','2026-11-19'),
          record('近期结束','北京','2026-11-13','2026-11-19','2026-11-11'),
          record('稍后截止','辽宁','2026-11-18','2026-11-22','2026-11-14')
        ];
        const ctx={Date:{now:()=>fixedTime},dateOf:value=>value?new Date(value):null,
          dataset:{records},state:{province:'全部',sort:'deadline',filter:'all',query:'',onlyFavorites:false}};
        vm.createContext(ctx);
        vm.runInContext(status+'\n'+html.slice(start,end),ctx);
        const titles=()=>vm.runInContext("getResults().map(item=>item.title).join(',')",ctx);
        assert.equal(titles(),'近日截止,稍后截止,即将报名,暂未定,近期结束,旧批次');
        ctx.state.province='山东';
        assert.equal(titles(),'近日截止,即将报名');
        ctx.state.filter='soon';
        assert.equal(titles(),'即将报名');
        ctx.state.filter='all';
        ctx.state.sort='latest';
        assert.equal(titles(),'即将报名,近日截止');
        """
        result = subprocess.run([node, '-e', javascript], capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_reference_links_load_when_monitoring_data_is_unavailable(self):
        import shutil
        import subprocess
        node = shutil.which('node')
        if not node:
            self.skipTest('Node.js is not installed')
        javascript = r"""
        const assert=require('assert/strict'),fs=require('fs'),vm=require('vm');
        const html=fs.readFileSync('index.html','utf8');
        const start=html.indexOf('async function loadSource(');
        const end=html.indexOf('\nrenderAll();',start);
        const scripts=html.slice(start,end);
        const feed={items:[{title:'高校通知'}]};
        const calls=[];
        const ctx={monitoring:null,candidates:null,thirdFeed:null,
          fetch:async url=>{
            if(url.includes('monitor_status'))throw new Error('unavailable');
            if(url.includes('review_queue'))return {ok:true,json:async()=>({candidates:[]})};
            return {ok:true,json:async()=>feed};
          },
          renderCandidates:()=>calls.push('candidates'),
          renderSupplement:()=>calls.push('supplement'),
          renderMonitoring:()=>calls.push('monitor')
        };
        vm.createContext(ctx);
        vm.runInContext(scripts+'\nloadMonitoring()',ctx).then(()=>{
          assert.equal(ctx.monitoring,null);
          assert.equal(ctx.candidates.length,0);
          assert.equal(ctx.thirdFeed,feed);
          assert.deepEqual(calls.sort(),['candidates','monitor','supplement']);
        }).catch(error=>{console.error(error);process.exitCode=1});
        """
        result = subprocess.run([node, '-e', javascript], capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


if __name__ == '__main__':
    unittest.main()
