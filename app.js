'use strict';
const $=id=>document.getElementById(id);
let state=null,page='home',group='',busy=false,lastError=false;
let testing=false,testJob=null,testResult=null;
let transferred=null,trafficLoading=false;
let nodeDetail=false;
function trafficLabel(n){const units=['B','KiB','MiB','GiB','TiB'];let i=0;while(n>=1024&&i<units.length-1){n/=1024;i++}return (i?n.toFixed(2):String(n))+' '+units[i]+' 已转发'} 
async function refreshTraffic(){if(trafficLoading||busy||!state||page==='login'||document.hidden)return;trafficLoading=true;try{const t=await api('traffic');transferred=t.bytes;state.mode=t.enabled?(state.mode==='direct'?'rule':state.mode):'direct';renderHome()}catch{if(state.mode!=='direct')$('power-detail').textContent='流量暂不可用 · 正在重试'}finally{trafficLoading=false}}
const notice=/^(剩余流量|套餐到期|请使用|防失联|电报群|官网|到期时间)/;
const svgNames={Selector:'手动选择',URLTest:'自动选择',Fallback:'故障转移',Shadowsocks:'SS',Hysteria2:'Hysteria2'};
function toast(message){$('toast').textContent=message;$('toast').hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('toast').hidden=true,4500)}
async function api(path,body){const res=await fetch('/api/'+path,{method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),credentials:'same-origin'});let data;try{data=await res.json()}catch{throw Error('服务暂时不可用，请稍后重试')}if(res.status===401){show('login');throw Error(data.error||'请先连接')}if(!res.ok)throw Error(data.error||'操作未完成');return data}
function show(next){page=next;for(const id of ['login','home','nodes','profiles','devices','provider'])$(id).hidden=id!==next;if(next!=='login')location.hash=next==='home'?'':'#'+next;window.scrollTo(0,0)}
function groups(){const main=primary();const rank=([name,p])=>name===main?-1:p.type==='URLTest'?0:p.type==='Fallback'?1:2;return Object.entries(state?.proxies||{}).filter(([name,p])=>p.all&&name!=='GLOBAL'&&(name!=='PROXY'||main==='PROXY')).sort((a,b)=>rank(a)-rank(b))}
function primary(){const proxies=state?.proxies||{},root=proxies.PROXY;const name=root?.now;if(name&&proxies[name]?.all)return name;if(root?.all)return 'PROXY';return Object.keys(proxies).find(n=>/飞鸟云|节点选择|代理选择/.test(n)&&proxies[n].all)||Object.keys(proxies).find(n=>n!=='GLOBAL'&&proxies[n].type==='Selector')||Object.keys(proxies).find(n=>n!=='GLOBAL'&&proxies[n].all)||'PROXY'}
function routeLabel(name){const p=state.proxies[name];if(!p)return '尚未选择';const selected=p.now;return (selected&&state.proxies[selected]?.all?selected+' · ':'')+displayLeaf(name)}
function renderNodeSummary(){$('node-summary').hidden=true}
function leaf(name){let seen=new Set();while(state.proxies[name]?.now&&!seen.has(name)){seen.add(name);name=state.proxies[name].now}return name||'尚未选择'}
function displayLeaf(name){const value=leaf(name);return notice.test(value)?'服务商提示项':value}
function label(name){const p=state.proxies[name];if(!p)return notice.test(name)?'服务商提示项':name;return p.all?(svgNames[p.type]||p.type)+' · '+displayLeaf(name):name}
function text(tag,content,cls){let e=document.createElement(tag);e.textContent=content;if(cls)e.className=cls;return e}
function renderHome(){const on=state.mode!=='direct';$('power').classList.toggle('on',on);$('power').setAttribute('aria-pressed',String(on));$('power-title').textContent=on?'运行中':'已停止';$('power-detail').textContent=on?(transferred===null?'正在读取转发量…':trafficLabel(transferred)):'点此启动';$('open-nodes').hidden=!on;const name=primary();const current=state.proxies[name]?.now||name;renderNodeSummary();const active=state.profiles.find(p=>p.active);$('profile-summary').textContent=active?active.name+' · 已启用':'尚未启用订阅';$('status-line').textContent='已连接黑豹';}
function renderNodes(){
 const all=groups();if(!all.some(([n])=>n===group))group=primary();
 $('group-tabs').hidden=true;
 $('nodes').querySelector('.back').setAttribute('aria-label',nodeDetail?'返回分组':'返回首页');
 $('nodes').querySelector('h1').textContent=nodeDetail?group:'代理';
 $('test-nodes').hidden=!nodeDetail;
 const grid=$('node-grid');grid.classList.toggle('group-list',!nodeDetail);
 $('node-hint').hidden=!nodeDetail;
 if(!nodeDetail){
  grid.replaceChildren(...all.map(([name,p])=>{
   const row=text('button','','group-row');row.type='button';row.setAttribute('aria-label',name+'，当前 '+(notice.test(p.now||'')?'服务商提示项':p.now||'未选择'));
   const info=text('span','','group-info');info.append(text('strong',name),text('span',svgNames[p.type]||p.type,'group-type'));
   const current=text('span',notice.test(p.now||'')?'服务商提示项':p.now||'未选择','group-current');
   row.append(info,current,text('span','›','group-arrow'));
   row.onclick=()=>{group=name;nodeDetail=true;renderNodes();window.scrollTo(0,0)};return row
  }));return;
 }
 const p=state.proxies[group];if(!p?.all){grid.replaceChildren(text('p','没有可用节点','empty'));return}
 const now=p.now;$('node-hint').textContent='当前：'+routeLabel(group)+(p.type==='Selector'?'':' · 自动测速选择，可点节点临时使用');
 const nodes=p.all.filter(n=>!notice.test(n));
 grid.replaceChildren(...nodes.map(name=>{
  const n=state.proxies[name]||{},b=document.createElement('button');b.className='node'+(now===name?' selected':'');b.dataset.name=name;b.setAttribute('aria-pressed',String(now===name));b.append(text('span',name,'node-name'));
  const meta=text('span','','node-meta');meta.append(text('span',n.all?label(name):(svgNames[n.type]||n.type||'节点'),'node-kind'));
  const last=n.history?.at(-1);const value=last?(last.delay>0?String(last.delay):'超时'):'—';
  meta.append(text('span',value,'delay'+(last?(last.delay>0?(last.delay<600?' good':last.delay<1500?' medium':' slow'):' timeout'):'')));b.append(meta);
  b.onclick=()=>action('正在切换节点…',async()=>{await api('select',{group,node:name});toast(group+'已切换为 '+name)});return b
 }));paintTest();
}
function paintTest(){
 const button=$('test-nodes');button.disabled=testing;button.classList.toggle('testing',testing);button.setAttribute('aria-label',testing?'正在测速':'测速');button.title=testing?'正在测速':'测速';
 if(!testResult||testResult.group!==group)return;
 if(!testResult.done)$('node-hint').textContent='测速 '+testResult.completed+' / '+testResult.total+' · 可继续浏览';
 for(const card of $('node-grid').children){const result=testResult.results[card.dataset.name];if(!result)continue;const delay=card.querySelector('.delay');if(!delay)continue;delay.className='delay';
  if(result.status==='done'){delay.textContent=String(result.delay);delay.classList.add(result.delay<600?'good':result.delay<1500?'medium':'slow')}
  else if(result.status==='timeout'){delay.textContent='超时';delay.classList.add('timeout')}
  else {delay.textContent=result.status==='testing'?'测速中':'…';delay.classList.add('pending')}
 }
}
async function startTest(){
 if(testing)return;const target=group;testing=true;testResult={group:target,completed:0,total:0,done:false,results:{}};
 for(const n of state.proxies[target]?.all||[])if(!notice.test(n))testResult.results[n]={status:'pending'};testResult.total=Object.keys(testResult.results).length;paintTest();
 try{const started=await api('test',{group:target});testJob=started.id;
  while(testJob){const result=await api('test?id='+encodeURIComponent(testJob));testResult=result;paintTest();if(result.done){testJob=null;break}await new Promise(resolve=>setTimeout(resolve,700))}
  toast('测速完成');
 }catch(e){toast(e.message);testResult=null;testJob=null}
 finally{testing=false;paintTest();if(page==='nodes'&&testResult?.group===group)$('node-hint').textContent='测速完成 · 单位 ms'}
}
function formatBytes(n){n=Number(n);if(!Number.isFinite(n))return '';return (n/1073741824).toFixed(1)+' GB'}
function timeLabel(v){if(!v)return '尚无更新时间';let t=typeof v==='number'?new Date(v<1e12?v*1000:v):new Date(v);if(!Number.isFinite(t.getTime()))return '已保存';let days=Math.floor((Date.now()-t)/86400000);return days>0?days+' 天前更新':'最近更新';}
const refreshIcon='<svg class="ui-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M17.65 6.35A7.95 7.95 0 0 0 12 4a8 8 0 1 0 7.93 9h-2.02A6 6 0 1 1 12 6c1.66 0 3.14.69 4.22 1.78L13 11h7V4z"/></svg>';
let profileWorking='',profileStatus='';
function renderProfiles(){
 const list=$('profile-list'),items=state.profiles.filter(p=>p.type==='remote'||p.active);
 $('update-all').disabled=busy;$('update-all').classList.toggle('rotating',profileWorking==='all');
 $('profile-status').textContent=profileStatus;$('profile-status').hidden=!profileStatus;
 if(!items.length){list.replaceChildren(text('p','还没有订阅，点击右上角 ＋ 添加','empty'));return}
 list.replaceChildren(...items.map(p=>{
  const card=text('article','','profile compact'+(p.active?' is-active':''));
  const select=text('button','','profile-select');select.type='button';select.setAttribute('role','radio');select.setAttribute('aria-checked',String(!!p.active));select.setAttribute('aria-label','使用 '+p.name);select.disabled=busy;
  select.append(text('span','','radio'));
  const copy=text('span','','profile-text');copy.append(text('span',p.name,'profile-name'),text('span',p.type==='remote'?'URL':'本地配置','profile-sub'));
  const usage=p.subscriptionInfo||p.subscriptionUserinfo||p.usage;
  if(usage&&typeof usage==='object'){const used=(Number(usage.upload)||0)+(Number(usage.download)||0),total=Number(usage.total)||0;if(total){copy.append(text('span',formatBytes(used)+' / '+formatBytes(total),'profile-sub'));const bar=text('span','','usage'),fill=document.createElement('i');fill.style.width=Math.min(100,Math.max(0,used/total*100))+'%';bar.append(fill);copy.append(bar)}}
  select.append(copy);select.onclick=()=>{if(!p.active)profileAction(p.id,'正在切换 '+p.name+'…',async()=>{await api('activate',{id:p.id});group='';return '已使用 '+p.name})};card.append(select);
  const side=text('div','','profile-side');side.append(text('span',timeLabel(p.updatedAt||p.updated),'profile-updated'));
  if(p.type==='remote'){const b=text('button','','icon-button profile-update');b.innerHTML=refreshIcon;b.title='更新 '+p.name;b.setAttribute('aria-label','更新 '+p.name);b.disabled=busy;b.classList.toggle('rotating',profileWorking===p.id||profileWorking==='all');b.onclick=()=>profileAction(p.id,'正在更新 '+p.name+'…',async()=>{await api('update',{id:p.id});return p.name+' 更新完成'});side.append(b)}
  card.append(side);return card
 }));
}
async function profileAction(id,message,fn){if(busy)return;busy=true;profileWorking=id;profileStatus=message;renderProfiles();try{profileStatus=await fn()||'操作完成';await refresh()}catch(e){profileStatus=e.message}finally{busy=false;profileWorking='';renderProfiles()}}
async function refresh(){state=await api('state');lastError=false;renderHome();renderNodes();renderProfiles()}
async function action(message,fn){if(busy)return;busy=true;$('busy-text').textContent=message;$('busy').hidden=false;try{await fn();await refresh()}catch(e){toast(e.message)}finally{busy=false;$('busy').hidden=true}}
$('login-form').onsubmit=async e=>{e.preventDefault();await action('正在连接…',async()=>{await api('login',{secret:$('secret').value});$('secret').value='';await refresh();show('home')})};
$('power').onclick=()=>action(state.mode==='direct'?'正在开启代理…':'正在关闭代理…',async()=>{const enabled=state.mode==='direct';await api('mode',{enabled});transferred=0;toast(enabled?'代理已开启，连接已重建':'代理已关闭，DNS 保持运行')});
$('open-nodes').onclick=()=>{nodeDetail=false;renderNodes();show('nodes')};$('open-profiles').onclick=()=>{renderProfiles();show('profiles')};document.querySelectorAll('.back').forEach(b=>b.onclick=()=>{if(page==='nodes'&&nodeDetail){nodeDetail=false;renderNodes();window.scrollTo(0,0)}else show('home')});
$('test-nodes').onclick=startTest;
$('add-profile').onclick=()=>$('import-dialog').showModal();$('close-import').onclick=()=>$('import-dialog').close();
$('import-form').onsubmit=async e=>{e.preventDefault();let url;try{url=subscriptionUrl($('profile-url').value)}catch(err){toast(err.message);return}const name=$('profile-name').value;$('import-dialog').close();await profileAction('import','正在导入订阅…',async()=>{await api('import',{name,url});$('import-form').reset();return '订阅已添加，点卡片使用'})};
$('update-all').innerHTML=refreshIcon;


$('update-all').onclick=()=>profileAction('all','正在更新订阅…',async()=>{let failed=0,success=0;for(const p of state.profiles.filter(p=>p.type==='remote')){profileStatus='正在更新 '+p.name+'…';renderProfiles();try{await api('update',{id:p.id});success++}catch{failed++}}return '已更新 '+success+' 个订阅'+(failed?'，'+failed+' 个失败，原配置已保留':'')});
addEventListener('hashchange',()=>{const next=location.hash.slice(1)||'home';if(state&&['home','nodes','profiles','devices','provider'].includes(next)&&next!==page)show(next)});
(async()=>{try{await refresh();const next=location.hash.slice(1);show(['nodes','profiles','devices'].includes(next)?next:'home')}catch(e){if(page!=='login'){show('login');toast(e.message)}}})();
setInterval(async()=>{if(!busy&&!testing&&state&&page!=='login'&&!document.hidden){try{await refresh()}catch(e){if(!lastError){lastError=true;toast(e.message)}$('status-line').textContent='连接暂时中断，正在重试'}}},15000);

setInterval(refreshTraffic,1000);
refreshTraffic();


function subscriptionUrl(value){let raw=value.trim();if(/^(clash|clashmeta|clashmi):/i.test(raw)){const parsed=new URL(raw);raw=parsed.searchParams.get('url')||parsed.searchParams.get('config')||''}let url;try{url=new URL(raw)}catch{throw Error('请粘贴网站复制的订阅地址')}if(!['http:','https:'].includes(url.protocol)||url.username||url.password)throw Error('订阅地址需要以 https:// 或 http:// 开头');return url.href}

$('close-provider').onclick=()=>$('provider-dialog').close();
$('provider-form').onsubmit=async e=>{e.preventDefault();let url;try{url=subscriptionUrl($('provider-url').value)}catch(err){$('provider-error').textContent=err.message;return}const name=$('provider-name').value.trim()||'飞鸟云';$('provider-dialog').close();await profileAction('import','正在导入服务商订阅…',async()=>{await api('import',{name,url});$('provider-url').value='';return '服务商订阅已添加，点卡片使用'})};
