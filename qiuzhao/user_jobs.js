(()=>{
'use strict';
const STORE_KEY='qiuzhao-user-job-edits-v1';
const VERSION=1;

function emptyStore(){return {version:VERSION,custom:[],overrides:{},hidden:[]}}
function load(){
  try{
    const x=JSON.parse(localStorage.getItem(STORE_KEY)||'null');
    if(!x||typeof x!=='object')return emptyStore();
    return {version:VERSION,custom:Array.isArray(x.custom)?x.custom:[],overrides:x.overrides&&typeof x.overrides==='object'?x.overrides:{},hidden:Array.isArray(x.hidden)?x.hidden:[]};
  }catch{return emptyStore()}
}
function save(s){localStorage.setItem(STORE_KEY,JSON.stringify(s))}
function clone(x){return JSON.parse(JSON.stringify(x))}
function apply(base){
  const s=load(), hidden=new Set(s.hidden||[]);
  const out=[];
  (base||[]).forEach(j=>{
    if(hidden.has(j.id))return;
    const patch=s.overrides?.[j.id]||{};
    out.push({...j,...patch,_userSource:'base',_userEdited:Object.keys(patch).length>0});
  });
  (s.custom||[]).forEach(j=>{if(j&&j.id&&!hidden.has(j.id))out.push({...j,_userSource:'custom',_userEdited:true})});
  return out;
}
function uid(){return 'user-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2,7)}
function injectStyle(){
  if(document.getElementById('userJobStyle'))return;
  const style=document.createElement('style');style.id='userJobStyle';style.textContent=`
  .user-job-btn{background:#fff;border:1px solid var(--line,#e4e8ed);border-radius:10px;padding:9px 12px;cursor:pointer;font-weight:750}.user-job-btn.primary{background:#174c66;color:#fff;border-color:#174c66}.user-job-edit{border:1px solid var(--line,#e4e8ed);background:#f7f9fb;border-radius:8px;padding:6px 9px;font-size:12px;cursor:pointer;white-space:nowrap}.user-job-mark{display:inline-block;margin-left:5px;padding:2px 6px;border-radius:999px;background:#f4efff;color:#6b46a3;font-size:10px;font-weight:800}.uj-backdrop{position:fixed;inset:0;background:rgba(15,23,42,.46);z-index:9998;display:flex;align-items:center;justify-content:center;padding:18px}.uj-modal{width:min(760px,96vw);max-height:92vh;overflow:auto;background:#fff;border-radius:18px;box-shadow:0 24px 70px rgba(15,23,42,.28);padding:20px}.uj-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:14px}.uj-head h2{margin:0;font-size:20px}.uj-head p{margin:5px 0 0;color:#66727e;font-size:12px;line-height:1.5}.uj-x{border:0;background:#f1f3f5;border-radius:9px;padding:7px 10px;cursor:pointer}.uj-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.uj-field{display:flex;flex-direction:column;gap:5px}.uj-field.full{grid-column:1/-1}.uj-field label{font-size:12px;font-weight:800;color:#465563}.uj-field input,.uj-field select,.uj-field textarea{width:100%;border:1px solid #d9e0e6;border-radius:9px;padding:9px 10px;font:inherit;background:#fff}.uj-field textarea{min-height:82px;resize:vertical}.uj-check{display:flex;align-items:center;gap:8px;margin-top:6px}.uj-actions{display:flex;flex-wrap:wrap;justify-content:space-between;gap:9px;margin-top:18px;padding-top:14px;border-top:1px solid #e8edf1}.uj-actions .left,.uj-actions .right{display:flex;flex-wrap:wrap;gap:8px}.uj-actions button{border:1px solid #d9e0e6;background:#fff;border-radius:9px;padding:8px 11px;cursor:pointer}.uj-actions .save{background:#18212b;color:#fff;border-color:#18212b}.uj-actions .danger{color:#a6362f}.uj-list{display:grid;gap:8px}.uj-item{display:flex;align-items:center;justify-content:space-between;gap:12px;border:1px solid #e4e8ed;border-radius:11px;padding:10px 11px}.uj-item-main{min-width:0}.uj-item-title{font-weight:800}.uj-item-sub{font-size:11px;color:#66727e;margin-top:3px}.uj-item-actions{display:flex;gap:6px;white-space:nowrap}.uj-item-actions button{border:1px solid #d9e0e6;background:#fff;border-radius:8px;padding:6px 8px;font-size:12px;cursor:pointer}.uj-empty{padding:16px;color:#66727e;text-align:center}.uj-import{display:none}@media(max-width:640px){.uj-grid{grid-template-columns:1fr}.uj-field.full{grid-column:auto}.uj-item{align-items:flex-start;flex-direction:column}.uj-item-actions{width:100%}}
  `;document.head.appendChild(style);
}
function field(doc,wrap,label,name,type='text',full=false){
  const box=doc.createElement('div');box.className='uj-field'+(full?' full':'');
  const lab=doc.createElement('label');lab.textContent=label;box.appendChild(lab);
  let el;
  if(type==='textarea'){el=doc.createElement('textarea')}else if(type==='select'){el=doc.createElement('select')}else{el=doc.createElement('input');el.type=type}
  el.name=name;box.appendChild(el);wrap.appendChild(box);return el;
}
function modalShell(title,subtitle){
  const bd=document.createElement('div');bd.className='uj-backdrop';
  const m=document.createElement('div');m.className='uj-modal';bd.appendChild(m);
  const head=document.createElement('div');head.className='uj-head';m.appendChild(head);
  const text=document.createElement('div');head.appendChild(text);const h=document.createElement('h2');h.textContent=title;text.appendChild(h);
  const p=document.createElement('p');p.textContent=subtitle||'';text.appendChild(p);
  const x=document.createElement('button');x.className='uj-x';x.textContent='关闭';x.onclick=()=>bd.remove();head.appendChild(x);
  bd.addEventListener('click',e=>{if(e.target===bd)bd.remove()});document.body.appendChild(bd);return {bd,m};
}
function normalJob(j){
  return {id:j.id,category:j.category||'国央企',org:j.org||'',region:j.region||'',role:j.role||'',level:j.level||'扩充',core:!!j.core,deadline:j.deadline||'未公开',url:j.url||'',keyword:j.keyword||'',note:j.note||''};
}
function install(opts){
  if(!opts||!Array.isArray(opts.jobs)||!Array.isArray(opts.baseJobs)||typeof opts.render!=='function')return;
  injectStyle();
  const jobs=opts.jobs, baseJobs=clone(opts.baseJobs), baseMap=new Map(baseJobs.map(j=>[j.id,j]));
  let currentRender=opts.render;
  function refresh(){
    const merged=apply(baseJobs);jobs.splice(0,jobs.length,...merged);currentRender();
  }
  function edit(job){
    const isNew=!job;const original=isNew?normalJob({id:uid(),category:'国央企',level:'扩充',deadline:'未公开'}):normalJob(job);
    const {bd,m}=modalShell(isNew?'添加岗位':'编辑岗位',isNew?'适合录入你自己选择的地区、岗位或非标准网申信息。':'修改只保存在你当前浏览器，不会改公开仓库里的原始岗位数据。');
    const grid=document.createElement('div');grid.className='uj-grid';m.appendChild(grid);
    const cat=field(document,grid,'类型','category','select');['国央企','银行','其他'].forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=v;cat.appendChild(o)});
    const org=field(document,grid,'单位','org');const region=field(document,grid,'地区','region');const role=field(document,grid,'岗位','role');
    const level=field(document,grid,'档位','level','select');['主投','冲刺','稳妥','扩充'].forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=v;level.appendChild(o)});
    const deadline=field(document,grid,'截止时间','deadline');const keyword=field(document,grid,'搜索关键词','keyword', 'text', true);const url=field(document,grid,'官网/投递链接','url','url',true);const note=field(document,grid,'备注','note','textarea',true);
    const coreWrap=document.createElement('label');coreWrap.className='uj-check';const core=document.createElement('input');core.type='checkbox';const ct=document.createElement('span');ct.textContent='标记为核心岗位';coreWrap.append(core,ct);grid.appendChild(coreWrap);
    cat.value=original.category;org.value=original.org;region.value=original.region;role.value=original.role;level.value=original.level;deadline.value=original.deadline;keyword.value=original.keyword;url.value=original.url;note.value=original.note;core.checked=original.core;
    const actions=document.createElement('div');actions.className='uj-actions';m.appendChild(actions);const left=document.createElement('div');left.className='left';const right=document.createElement('div');right.className='right';actions.append(left,right);
    if(!isNew){
      const del=document.createElement('button');del.className='danger';del.textContent=job._userSource==='custom'?'删除这个岗位':'从我的表隐藏';del.onclick=()=>{
        const s=load();if(job._userSource==='custom'){s.custom=s.custom.filter(x=>x.id!==job.id);delete s.overrides[job.id]}else if(!s.hidden.includes(job.id))s.hidden.push(job.id);save(s);bd.remove();refresh();
      };left.appendChild(del);
      if(job._userSource!=='custom'&&(job._userEdited||load().hidden.includes(job.id))){const reset=document.createElement('button');reset.textContent='恢复原始数据';reset.onclick=()=>{const s=load();delete s.overrides[job.id];s.hidden=s.hidden.filter(id=>id!==job.id);save(s);bd.remove();refresh()};left.appendChild(reset)}
    }
    const cancel=document.createElement('button');cancel.textContent='取消';cancel.onclick=()=>bd.remove();right.appendChild(cancel);
    const saveBtn=document.createElement('button');saveBtn.className='save';saveBtn.textContent='保存';saveBtn.onclick=()=>{
      const next={id:original.id,category:cat.value,org:org.value.trim(),region:region.value.trim(),role:role.value.trim(),level:level.value,core:core.checked,deadline:deadline.value.trim()||'未公开',url:url.value.trim(),keyword:keyword.value.trim(),note:note.value.trim()};
      if(!next.org||!next.role){alert('单位和岗位至少需要填写。');return}
      const s=load();
      if(isNew||job?._userSource==='custom'){
        const idx=s.custom.findIndex(x=>x.id===next.id);if(idx>=0)s.custom[idx]=next;else s.custom.push(next);
      }else{
        const base=baseMap.get(next.id)||{};const patch={};['category','org','region','role','level','core','deadline','url','keyword','note'].forEach(k=>{if((base[k]??'')!==(next[k]??''))patch[k]=next[k]});
        if(Object.keys(patch).length)s.overrides[next.id]=patch;else delete s.overrides[next.id];
      }
      s.hidden=s.hidden.filter(id=>id!==next.id);save(s);bd.remove();refresh();
    };right.appendChild(saveBtn);
  }
  function manage(){
    const {bd,m}=modalShell('管理我的岗位修改','这里可以恢复被隐藏的岗位，也可以备份/导入你自己新增和修改的岗位。');
    const list=document.createElement('div');list.className='uj-list';m.appendChild(list);
    function draw(){
      list.innerHTML='';const s=load();const rows=[];
      s.custom.forEach(j=>rows.push({type:'自建',id:j.id,title:`${j.org}｜${j.role}`,sub:j.region||'',job:{...j,_userSource:'custom'}}));
      Object.keys(s.overrides).forEach(id=>{const base=baseMap.get(id);if(base)rows.push({type:'修改',id,title:`${s.overrides[id].org||base.org}｜${s.overrides[id].role||base.role}`,sub:s.overrides[id].region||base.region||'',job:{...base,...s.overrides[id],_userSource:'base',_userEdited:true}})});
      s.hidden.forEach(id=>{const base=baseMap.get(id);if(base)rows.push({type:'隐藏',id,title:`${base.org}｜${base.role}`,sub:base.region||'',hidden:true})});
      if(!rows.length){const e=document.createElement('div');e.className='uj-empty';e.textContent='目前没有自定义修改。';list.appendChild(e);return}
      rows.forEach(r=>{const item=document.createElement('div');item.className='uj-item';const main=document.createElement('div');main.className='uj-item-main';const title=document.createElement('div');title.className='uj-item-title';title.textContent=`[${r.type}] ${r.title}`;const sub=document.createElement('div');sub.className='uj-item-sub';sub.textContent=r.sub;main.append(title,sub);const acts=document.createElement('div');acts.className='uj-item-actions';
        if(r.hidden){const restore=document.createElement('button');restore.textContent='恢复显示';restore.onclick=()=>{const x=load();x.hidden=x.hidden.filter(id=>id!==r.id);save(x);draw();refresh()};acts.appendChild(restore)}else{const e=document.createElement('button');e.textContent='编辑';e.onclick=()=>{bd.remove();edit(r.job)};acts.appendChild(e)}item.append(main,acts);list.appendChild(item)});
    }
    draw();
    const actions=document.createElement('div');actions.className='uj-actions';m.appendChild(actions);const left=document.createElement('div');left.className='left';const right=document.createElement('div');right.className='right';actions.append(left,right);
    const exp=document.createElement('button');exp.textContent='导出我的岗位配置';exp.onclick=()=>{const blob=new Blob([JSON.stringify(load(),null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='秋招我的岗位配置.json';a.click();URL.revokeObjectURL(a.href)};left.appendChild(exp);
    const inp=document.createElement('input');inp.type='file';inp.accept='application/json';inp.className='uj-import';m.appendChild(inp);const imp=document.createElement('button');imp.textContent='导入配置';imp.onclick=()=>inp.click();left.appendChild(imp);inp.onchange=()=>{const f=inp.files?.[0];if(!f)return;const rd=new FileReader();rd.onload=()=>{try{const x=JSON.parse(rd.result);if(!x||!Array.isArray(x.custom)||!x.overrides||!Array.isArray(x.hidden))throw new Error();save({version:VERSION,custom:x.custom,overrides:x.overrides,hidden:x.hidden});draw();refresh()}catch{alert('配置文件格式不正确')}};rd.readAsText(f)};
    const reset=document.createElement('button');reset.className='danger';reset.textContent='清空全部自定义修改';reset.onclick=()=>{if(confirm('确定清空所有新增、修改和隐藏记录吗？投递勾选不会受影响。')){save(emptyStore());draw();refresh()}};left.appendChild(reset);
    const close=document.createElement('button');close.textContent='完成';close.onclick=()=>bd.remove();right.appendChild(close);
  }
  const toolbar=document.querySelector('.toolbar');
  if(toolbar&&!document.getElementById('addUserJobBtn')){
    const add=document.createElement('button');add.id='addUserJobBtn';add.className='user-job-btn primary';add.textContent='＋ 添加岗位';add.onclick=()=>edit(null);
    const manageBtn=document.createElement('button');manageBtn.id='manageUserJobsBtn';manageBtn.className='user-job-btn';manageBtn.textContent='管理我的岗位';manageBtn.onclick=manage;
    toolbar.append(add,manageBtn);
  }
  const header=document.querySelector('table thead tr');if(header&&!header.querySelector('[data-user-edit-col]')){const th=document.createElement('th');th.dataset.userEditCol='1';th.textContent='编辑';header.appendChild(th)}
  function enhanceRows(){
    const visible=typeof opts.getVisibleJobs==='function'?opts.getVisibleJobs():jobs;
    [...document.querySelectorAll('#body tr')].forEach((tr,i)=>{const j=visible[i];if(!j)return;const td=document.createElement('td');const b=document.createElement('button');b.className='user-job-edit';b.textContent='编辑';b.onclick=()=>edit(j);td.appendChild(b);tr.appendChild(td);if(j._userEdited){const org=tr.querySelector('.org');if(org&&!org.querySelector('.user-job-mark')){const mark=document.createElement('span');mark.className='user-job-mark';mark.textContent=j._userSource==='custom'?'自建':'已改';org.appendChild(mark)}}});
  }
  const baseRender=currentRender;currentRender=function(){baseRender();enhanceRows()};
  window.render=currentRender;
  currentRender();
}
window.QIUZHAO_USER_JOBS={apply,install,load};
})();
