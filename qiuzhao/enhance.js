(()=>{
const PROFILE_RULES=[
  {label:'产业/行业研究',re:/产业|行业研究|能源市场|投资研究|战略规划|研究|规划投资/,points:6},
  {label:'贸易/国际商务',re:/贸易|国际商务|国际经营|大宗|采购|供应链|航运经营/,points:6},
  {label:'经营/运营管理',re:/经营|运营|企业管理|综合管理|管理培训|管培|业务管理|职能/,points:5},
  {label:'经济金融',re:/经济金融|信贷|金融|客户经理|银行|投资/,points:4},
  {label:'数据分析',re:/数据|分析|计量|计划|风险|市场研究|经营分析/,points:4},
  {label:'市场/客户',re:/市场|营销|客户|业务拓展|商务/,points:3}
];
const LEVEL_BASE={'主投':79,'冲刺':74,'稳妥':69,'扩充':60};
let healthData=null,candidateData=null;
function fitInfo(j){
  const text=[j.org,j.role,j.keyword,j.note].join(' ');
  let score=LEVEL_BASE[normalizedLevel(j)]||60, bonus=0, reasons=[];
  PROFILE_RULES.forEach(r=>{if(r.re.test(text)){bonus+=r.points;reasons.push(r.label)}});
  score+=Math.min(15,bonus);
  if(j.core)score+=3;
  if(/专业并非直接列名|专业偏好更高|长期海外属性较强|需接受业绩|学历要求较高/.test(text))score-=5;
  if(/专业直接包含产业经济学|本科贸易经济|专业匹配度高|经济学\/经贸|经济学、金融学、国际贸易/.test(text))score+=4;
  score=Math.max(55,Math.min(97,score));
  if(!reasons.length)reasons=[j.category==='银行'?'经济金融背景':'经管背景'];
  return {score,reasons:[...new Set(reasons)].slice(0,2)};
}
function urgencyInfo(j){
  const d=deadlineValue(j.deadline);
  if(!d.known)return {known:false,days:null,label:'截止待核',cls:'urgency-unknown'};
  const days=Math.ceil((d.value-Date.now())/86400000);
  if(days<0)return {known:true,days,label:'已过期',cls:'urgency-expired'};
  if(days<=3)return {known:true,days,label:days===0?'今天截止':`${days}天内`,cls:'urgency-hot'};
  if(days<=7)return {known:true,days,label:'7天内',cls:'urgency-week'};
  if(days<=14)return {known:true,days,label:'两周内',cls:'urgency-ok'};
  return {known:true,days,label:`${days}天`,cls:'urgency-ok'};
}
function queryMatches(j){
  const text=[j.category,j.org,j.region,j.role,normalizedLevel(j),j.keyword,j.note].join(' ').toLowerCase();
  const query=q.trim().toLowerCase();
  return !query||text.includes(query);
}
const baseMatch=match;
match=function(j){
  if(mode==='highfit')return !state[j.id]&&fitInfo(j).score>=80&&queryMatches(j);
  if(mode==='urgent'){
    const u=urgencyInfo(j);
    return !state[j.id]&&u.known&&u.days>=0&&u.days<=7&&queryMatches(j);
  }
  return baseMatch(j);
};
const baseCompareJobs=compareJobs;
compareJobs=function(a,b){
  if(sortKey==='fit'){
    const d=(fitInfo(a).score-fitInfo(b).score)*sortDir;
    return d||collator.compare(a.org||'',b.org||'');
  }
  return baseCompareJobs(a,b);
};
function priorityScore(j){
  if(state[j.id])return -999;
  const u=urgencyInfo(j);
  if(u.known&&u.days<0)return -999;
  let score=fitInfo(j).score+(j.core?4:0);
  if(u.known){if(u.days<=3)score+=16;else if(u.days<=7)score+=10;else if(u.days<=14)score+=5;}else score+=1;
  return score;
}
function installUI(){
  const stats=document.querySelector('.stats');
  if(stats&&!document.getElementById('highFitRemain'))stats.insertAdjacentHTML('beforeend','<div class="stat"><b id="highFitRemain">0</b><span>高匹配未投</span></div>');
  const toolbar=document.querySelector('.toolbar');
  if(toolbar&&!toolbar.querySelector('[data-mode="highfit"]')){
    const firstSearch=toolbar.querySelector('#search');
    const wrap=document.createDocumentFragment();
    const b1=document.createElement('button');b1.dataset.mode='highfit';b1.textContent='高匹配未投';
    const b2=document.createElement('button');b2.dataset.mode='urgent';b2.textContent='7天内截止';
    wrap.append(b1,b2);toolbar.insertBefore(wrap,firstSearch);
    [b1,b2].forEach(btn=>btn.onclick=()=>{mode=btn.dataset.mode;document.querySelectorAll('[data-mode]').forEach(x=>x.classList.remove('active'));btn.classList.add('active');render()});
  }
  const sort=document.getElementById('sortSelect');
  if(sort&&!sort.querySelector('option[value="fit:-1"]'))sort.insertAdjacentHTML('afterbegin','<option value="fit:-1">匹配度：高→低</option><option value="fit:1">匹配度：低→高</option>');
  const header=document.querySelector('table thead tr');
  if(header&&!header.querySelector('[data-sort="fit"]')){
    const th=document.createElement('th');th.className='sortable';th.dataset.sort='fit';th.innerHTML='匹配<span class="sort-arrow"></span>';
    header.children[4].after(th);
    th.onclick=()=>{if(sortKey==='fit')sortDir*=-1;else{sortKey='fit';sortDir=-1}render()};
  }
  const toolbarNode=document.querySelector('.toolbar');
  if(toolbarNode&&!document.getElementById('priorityPanel')){
    const panel=document.createElement('section');panel.id='priorityPanel';panel.className='priority-panel';
    panel.innerHTML='<div class="priority-head"><div><h2>今日优先投递</h2><span>综合个人匹配、核心标记与截止时间自动排序</span></div><span>仅作排序提示，最终以岗位资格条件为准</span></div><div id="priorityList" class="priority-list"></div>';
    toolbarNode.parentNode.insertBefore(panel,toolbarNode);
  }
  if(toolbarNode&&!document.getElementById('healthPanel')){
    const panel=document.createElement('section');panel.id='healthPanel';panel.className='health-panel';
    panel.innerHTML='<div class="health-head"><div><h2>岗位池巡检</h2><span id="healthTime">等待首次自动巡检</span></div><span>官网受限不等于入口失效，异常项需要人工复核</span></div><div class="health-grid"><div class="health-stat"><b id="healthOk" class="health-ok">—</b><span>正常岗位入口</span></div><div class="health-stat"><b id="healthRestricted" class="health-warn">—</b><span>官网限制自动访问</span></div><div class="health-stat"><b id="healthError" class="health-bad">—</b><span>异常待复核</span></div><div class="health-stat"><b id="candidateCount">—</b><span>候选变更待核验</span></div></div>';
    toolbarNode.parentNode.insertBefore(panel,toolbarNode);
  }
}
function healthFor(j){return healthData&&healthData.jobs?healthData.jobs[j.id]:null}
function healthLabel(h){
  if(!h)return {state:'unknown',label:'未巡检'};
  if(h.state==='ok')return {state:'ok',label:'官网正常'};
  if(h.state==='restricted')return {state:'restricted',label:'官网限流'};
  return {state:'error',label:'需复核'};
}
function enhanceRows(){
  const visible=jobs.filter(match).slice().sort(compareJobs);
  const rows=[...document.querySelectorAll('#body tr')];
  rows.forEach((tr,i)=>{
    const j=visible[i];if(!j)return;
    const f=fitInfo(j),u=urgencyInfo(j),h=healthLabel(healthFor(j));
    const fitTd=document.createElement('td');fitTd.className='fit-wrap';
    fitTd.innerHTML=`<span class="fit-pill ${f.score>=80?'fit-high':f.score>=70?'fit-mid':'fit-low'}">${f.score}分</span><div class="fit-reason">${f.reasons.map(esc).join(' · ')}</div>`;
    tr.children[4].after(fitTd);
    const deadlineTd=tr.children[7];
    if(deadlineTd)deadlineTd.insertAdjacentHTML('beforeend',`<div><span class="urgency ${u.cls}">${esc(u.label)}</span></div>`);
    const orgTd=tr.children[2];
    if(orgTd)orgTd.insertAdjacentHTML('beforeend',`<div class="source-health ${h.state}"><span class="source-dot"></span>${esc(h.label)}</div>`);
  });
}
function updatePriority(){
  const box=document.getElementById('priorityList');if(!box)return;
  const list=jobs.filter(j=>priorityScore(j)>0).slice().sort((a,b)=>priorityScore(b)-priorityScore(a)).slice(0,5);
  if(!list.length){box.innerHTML='<div class="priority-empty">当前没有待投且仍在有效期内的岗位。</div>';return;}
  box.innerHTML=list.map((j,i)=>{const f=fitInfo(j),u=urgencyInfo(j);return `<article class="priority-item"><div class="priority-rank">TOP ${i+1} · ${f.score}分 · ${esc(u.label)}</div><div class="priority-org">${esc(j.org)}</div><div class="priority-role">${esc(j.role)}</div><div class="priority-meta"><span class="badge ${levelClass(j)}">${esc(normalizedLevel(j))}</span><a class="priority-link" href="${j.url}" target="_blank" rel="noopener">去官网 ↗</a></div></article>`}).join('');
}
function updateEnhancedStats(){
  const el=document.getElementById('highFitRemain');
  if(el)el.textContent=jobs.filter(j=>!state[j.id]&&fitInfo(j).score>=80).length;
}
function updateHealthPanel(){
  if(!healthData)return;
  const counts=healthData.counts||{};
  const set=(id,val)=>{const el=document.getElementById(id);if(el)el.textContent=val};
  set('healthOk',counts.ok??0);set('healthRestricted',counts.restricted??0);set('healthError',counts.error??0);
  const waiting=(candidateData?.items||[]).filter(x=>x.status==='待核验').length;set('candidateCount',waiting);
  const t=document.getElementById('healthTime');
  if(t&&healthData.generatedAt){const d=new Date(healthData.generatedAt);t.textContent=`最近巡检：${Number.isNaN(d.getTime())?healthData.generatedAt:d.toLocaleString('zh-CN',{hour12:false})}`}
}
async function loadHealth(){
  try{
    const [statusRes,candidateRes]=await Promise.all([fetch('./job_status.json',{cache:'no-store'}),fetch('./job_candidates.json',{cache:'no-store'})]);
    if(statusRes.ok)healthData=await statusRes.json();
    if(candidateRes.ok)candidateData=await candidateRes.json();
    updateHealthPanel();render();
  }catch(err){console.warn('qiuzhao health data unavailable',err)}
}
const baseRender=render;
render=function(){baseRender();enhanceRows();updatePriority();updateEnhancedStats();updateHealthPanel()};
installUI();render();loadHealth();
})();
