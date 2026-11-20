import {jobs} from '../api/entities.js';
import {api} from '../api/client.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {chart} from '../components/common/chart.js';
import {table} from '../components/common/table.js';
import {status} from '../components/common/status.js';
import {esc,fmt,date,notify} from '../utils/dom.js';
import {submit} from '../hooks/forms.js';

const kindLabel=j=>{
 if(j.approved&&j.superseded_by)return '已获业务批准（保留批准时区间）· 已有补报新版本';
 if(j.approved)return '已获业务批准（保留批准时区间）';
 if(j.superseded_by)return '旧版本 · 已有补报新版本';
 if(j.status==='completed')return '待负责人复核';
 return '未完成';
};
const canSupplement=j=>j.result&&j.status==='completed'&&!j.superseded_by;
function versionStrip(chain,current){
 if(chain.length<2)return '';
 return '<div class="version-strip"><span class="eyebrow">VERSION CHAIN</span>'+chain.map(v=>'<a class="version-chip '+(v.id===current.id?'active':'')+'" href="#/results/'+v.id+'" title="v'+v.revision+'">'+'<strong>v'+v.revision+'</strong><small>'+esc(v.approved?(v.superseded_by?'已批准 · 被取代':'已批准'):v.superseded_by?'被取代':v.status)+'</small></a>').join('')+'</div>';
}
function intervalRows(j){
 const rows=j.result?.observations||[];
 if(!rows.length)return '<p class="empty">本次估计没有逐件观测记录。</p>';
 return table([{key:'asset',label:'部件资产号'},{key:'kind_label',label:'观测类型'},{key:'lower',label:'区间下界（上次检查正常）'},{key:'upper',label:'区间上界（发现失效/截止在役）'},{key:'sources',label:'合并记录数'},{key:'supplements',label:'补报次数'}],rows.map(o=>({...o,lower:o.lower==null?'—':o.lower})),'本次估计没有逐件观测记录。');
}
function supplementForm(j){
 if(!canSupplement(j))return '';
 if(session.user.role==='viewer')return '<p class="hint">观察员可查看区间与批准状态，不能提交补报。</p>';
 const candidates=(j.result?.observations||[]).filter(o=>o.kind==='interval');
 if(!candidates.length)return '<p class="hint">本结果没有可补报的区间失效件。</p>';
 return '<form id="supplement-form"><label>补报部件<select name="asset">'+candidates.map(o=>'<option value="'+esc(o.asset)+'" data-lower="'+esc(o.lower??0)+'" data-upper="'+esc(o.upper)+'">'+esc(o.asset)+' · 当前 '+esc(fmt(o.lower??0))+'–'+esc(fmt(o.upper))+' 公里</option>').join('')+'</select></label><div class="parameter-grid"><label>复检确认失效下界（公里）<input type="number" step="any" name="lower_km" required></label><label>复检确认失效上界（公里）<input type="number" step="any" name="upper_km" required></label></div><p class="hint">补报必须与现有区间有交集且真正收窄；收窄后生成新版本，旧版本与已批准区间保持原样。相同补报重复提交不会重复出版本。</p><button type="submit" class="primary" '+(session.user.role==='viewer'?'disabled':'')+'>提交补报并生成新版本</button></form>';
}
function bindSupplement(){
 const form=document.querySelector('#supplement-form');if(!form)return;
 const select=form.querySelector('[name=asset]');
 const fill=()=>{const option=select.selectedOptions[0];if(!option)return;form.querySelector('[name=lower_km]').value=option.dataset.lower;form.querySelector('[name=upper_km]').value=option.dataset.upper;};
 select.addEventListener('change',fill);fill();
 submit(form,async f=>{const asset=String(f.get('asset'));const child=await api('/jobs/'+workspace.selectedJob+'/supplements',{method:'POST',body:JSON.stringify({supplements:[{asset,lower_km:Number(f.get('lower_km')),upper_km:Number(f.get('upper_km'))}]})});workspace.selectedJob=child.id;notify('补报已登记，v'+child.revision+' 正在重新拟合');location.hash='#/results/'+child.id;});
}
export async function results(id){
 workspace.jobs=await jobs.list();const j=id?await jobs.get(id):(workspace.jobs.find(j=>j.id===workspace.selectedJob)||workspace.jobs[0]);
 if(j&&!workspace.jobs.some(x=>x.id===j.id))workspace.jobs.push(j);
 if(!j)return heading('04 / REVIEW','结果复核','尚无分析结果。')+'<div class="empty">先到分析工作台，选择批次并提交一次计算。<a href="#/workbench">前往工作台 ↗</a></div>';
 workspace.selectedJob=j.id;const r=j.result||{};
 let chain=[j];try{chain=await api('/jobs/'+j.id+'/versions');}catch(e){}
 const approveAllowed=session.user.role==='admin'&&j.status==='completed'&&!j.approved&&!j.superseded_by;
 const approvedSnapshot=j.approved?('<p class="hint">批准于 '+esc(j.approved_at?date(j.approved_at):'历史记录')+'（v'+j.revision+'）；此后补报生成的版本不改变本次已批准区间。</p>'):'';
 return heading('04 / REVIEW','结果复核与业务解释',j.name,'<button class="button" id="refresh-results">刷新结果 ↻</button>')+versionStrip(chain,j)+'<div class="result-selector"><label>分析记录<select id="select-job">'+workspace.jobs.map(x=>'<option value="'+x.id+'" '+(x.id===j.id?'selected':'')+'>'+esc(x.name)+' · '+esc(x.status)+'</option>').join('')+'</select></label>'+status(j.status)+'<span>v'+j.revision+'</span><span>'+date(j.created_at)+'</span><span class="approval">'+esc(kindLabel(j))+'</span></div>'+approvedSnapshot+(j.status==='completed'?'<section class="result-lead"><p class="eyebrow">COMPUTED FINDING</p><h2>'+esc(r.summary)+'</h2><div class="metrics">'+(r.metrics||[]).map(m=>'<div><span>'+esc(m.label)+'</span><strong>'+esc(fmt(m.value))+'<small>'+esc(m.unit||'')+'</small></strong></div>').join('')+'</div></section><section class="panel">'+chart(r.chart)+'</section><div class="two-columns"><section class="panel"><div class="section-title"><h2>业务解释</h2><span>由计算结果生成</span></div><ol class="questions">'+(r.findings||[]).map(v=>'<li>'+esc(v)+'</li>').join('')+'</ol>'+(r.warnings||[]).map(v=>'<p class="warning">'+esc(v)+'</p>').join('')+'</section><section class="method-sheet compact"><p class="eyebrow">REPRODUCIBILITY</p><h3>计算口径与参数</h3><p>'+esc(r.method)+'</p><pre>'+esc(JSON.stringify(j.params,null,2))+'</pre>'+(approveAllowed?'<button class="primary" id="approve-job">批准此业务结论</button>':'')+'<p class="hint">仅批准结果可进入定时分发档案。补报生成新版本后，旧版本不能再次批准；已批准版本保留当时的区间。</p>'+((j.supplements||[]).length?'<p class="hint">已累计 '+j.supplements.length+' 次补报，版本链共 '+chain.length+' 版。</p>':'')+'</section></div><section class="panel"><div class="section-title"><h2>估计采用的观测区间</h2><span>按资产合并 · 同件故障记录取交集</span></div>'+intervalRows(j)+'</section><section class="panel"><div class="section-title"><h2>补报复检结果</h2><span>narrower interval → new version</span></div>'+supplementForm(j)+'</section><section class="panel"><div class="section-title"><h2>结果明细</h2><span>'+(r.table?.rows?.length||0)+' 行</span></div>'+table(r.table?.columns||[],r.table?.rows||[])+'</section>':'<section class="panel empty">'+(j.status==='failed'?'计算失败：'+esc(j.error)+'。请返回工作台调整参数或数据。':'后台正在执行计算。点击刷新结果查看最新进展。')+'<a href="#/workbench">返回工作台 ↗</a></section>');
}
export function bindResults(refresh){document.querySelector('#refresh-results')?.addEventListener('click',refresh);document.querySelector('#select-job')?.addEventListener('change',e=>{workspace.selectedJob=Number(e.target.value);location.hash='#/results/'+e.target.value;});document.querySelector('#approve-job')?.addEventListener('click',async()=>{try{await jobs.approve(workspace.selectedJob);notify('已批准，可创建分发计划');await refresh();}catch(e){notify(e.message,true);}});bindSupplement();}
