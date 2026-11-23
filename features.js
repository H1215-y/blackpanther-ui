'use strict';
let deviceState=null,deviceWorking=false,providerJob=null,providerPolling=false,screenLoading=false;
let screenURL=null,providerInputBusy=false,deviceMessage='';

function renderDevices(){
 const data=deviceState,list=$('device-list');if(!data)return;
 $('devices-status').textContent=!data.ready?'设备控制服务暂未连接':data.pending?'设置正在应用…':state.mode==='direct'?'总开关已关闭；设备设置会在开启后生效':'新设备默认直连。关闭代理仍可正常上网。';
 $('devices-status').classList.toggle('error',!data.ready||!!data.error);
 $('devices-error').textContent=data.error||deviceMessage;
 if(!data.devices.length){list.replaceChildren(text('p','尚未发现设备。设备经过黑豹或与它通信后会出现在这里。','empty'));return}
 list.replaceChildren(...data.devices.map(d=>{
  const card=text('article','','device-card');const copy=text('button','','device-copy');copy.type='button';copy.title='备注设备名称';
  copy.append(text('strong',d.name,'device-name'),text('span',d.ips.join(' · ')||'暂无 IP','device-ip'),text('span',d.mac.toUpperCase(),'device-mac'));
  const recent=d.neighbour==='REACHABLE';copy.append(text('span',recent?'近期有通信':d.seen?'已发现 · 当前在线状态未知':'已保存设备','device-presence'));
  copy.onclick=()=>{$('device-mac').value=d.mac;$('device-name').value=d.name==='未命名设备'?'':d.name;$('device-name-dialog').showModal()};
  const side=text('div','','device-side'),toggle=text('button',d.enabled?'代理':'直连','device-toggle'+(d.enabled?' on':''));
  toggle.type='button';toggle.setAttribute('role','switch');toggle.setAttribute('aria-checked',String(d.enabled));toggle.setAttribute('aria-label',d.name+' 的代理');toggle.disabled=deviceWorking||!data.ready||data.pending;
  toggle.onclick=async()=>{if(deviceWorking)return;deviceWorking=true;renderDevices();deviceMessage='正在应用设备设置…';try{deviceState=await api('device',{mac:d.mac,enabled:!d.enabled});deviceMessage=deviceState.warning||''}catch(e){deviceMessage=e.message;try{deviceState=await api('devices')}catch{}}finally{deviceWorking=false;renderDevices()}};
  side.append(toggle);card.append(copy,side);return card
 }));
}
async function loadDevices(){if(deviceWorking)return;try{deviceState=await api('devices');renderDevices()}catch(e){$('devices-status').textContent=e.message}}
$('open-devices').onclick=()=>{show('devices');loadDevices()};$('refresh-devices').onclick=loadDevices;
$('close-device-name').onclick=()=>$('device-name-dialog').close();
$('device-name-form').onsubmit=async e=>{e.preventDefault();if(deviceWorking)return;deviceWorking=true;const mac=$('device-mac').value,name=$('device-name').value;$('device-name-dialog').close();try{deviceState=await api('device',{mac,name});renderDevices()}catch(err){$('devices-error').textContent=err.message}finally{deviceWorking=false}};

function paintProvider(job){
 $('provider-status').textContent=job.message;
 const manual=['verification','manual'].includes(job.status);
 $('provider-human').hidden=!manual;$('provider-login').hidden=job.status!=='manual';
 $('provider-cancel').hidden=['done','error','cancelled'].includes(job.status);
 $('provider-retry').hidden=!['error','cancelled'].includes(job.status);
 $('provider-list').hidden=job.status!=='done';
 $('provider-status').classList.toggle('error',job.status==='error');
}
let providerPrefs={site:'https://basbax.934676.xyz',email:'',saved:false};
const providerSettings=document.createElement('details');
providerSettings.className='provider-login';providerSettings.open=true;
providerSettings.innerHTML='<summary>官网与保存的账号</summary><p><a href="https://github.com/feiniaoyun" target="_blank" rel="noopener noreferrer">最新官网（GitHub） ↗</a></p><label for="provider-site-local">官网地址</label><input id="provider-site-local" type="url" placeholder="从 GitHub 复制官网地址"><label for="provider-account-local">飞鸟云账号</label><input id="provider-account-local" autocomplete="username"><label for="provider-password-local">密码</label><input id="provider-password-local" type="password" autocomplete="current-password" placeholder="填写后保存到黑豹"><p class="device-note">加密保存在黑豹后台，电脑和手机共用。已存密码不回显；更换官网或账号时请重新填入密码并保存。</p><div class="feature-actions"><button id="provider-save-local" class="small-button">保存到黑豹</button><button id="provider-clear-local" class="small-button">清除保存</button><button id="provider-reopen-local" class="small-button">用此官网重新打开</button></div><p id="provider-local-message" class="device-note"></p>';
$('provider-status').before(providerSettings);
async function loadProviderPrefs(){providerPrefs=await api('provider/settings');$('provider-site-local').value=providerPrefs.site;$('provider-account-local').value=providerPrefs.email;$('provider-password-local').value='';$('provider-password-local').placeholder=providerPrefs.saved?'已保存，留空保留原密码':'填写后保存到黑豹';$('provider-local-message').textContent=providerPrefs.saved?'黑豹已保存账号，导入时会自动登录。':'尚未保存账号，可在下方临时登录。'}
$('provider-save-local').onclick=async()=>{try{await api('provider/settings',{site:$('provider-site-local').value.trim(),email:$('provider-account-local').value.trim(),password:$('provider-password-local').value});await loadProviderPrefs();toast('已保存到黑豹')}catch(e){toast(e.message)}};
$('provider-clear-local').onclick=async()=>{try{await api('provider/settings',{clear:true});await loadProviderPrefs();toast('已清除黑豹保存的账号密码；现有登录窗口可能仍有效')}catch(e){toast(e.message)}};
$('provider-reopen-local').onclick=async()=>{try{if(providerJob)await api('provider/cancel',{id:providerJob});providerJob=null;await beginProvider(true)}catch(e){toast(e.message)}};
async function beginProvider(keepSite=false){
 show('provider');if(keepSite!==true)await loadProviderPrefs();$('provider-status').textContent='正在打开飞鸟云…';
 try{const job=await api('provider/start',{name:'飞鸟云',site:$('provider-site-local').value.trim()||providerPrefs.site});providerJob=job.id;paintProvider(job);pollProvider()}catch(e){$('provider-status').textContent=e.message;$('provider-retry').hidden=false}
}
$('provider-import').onclick=beginProvider;$('provider-retry').onclick=beginProvider;
$('provider-list').onclick=async()=>{await refresh();show('profiles')};
$('provider-cancel').onclick=async()=>{if(!providerJob)return;try{await api('provider/cancel',{id:providerJob});providerJob=null;$('provider-status').textContent='已取消导入';$('provider-human').hidden=true;$('provider-login').hidden=true;$('provider-cancel').hidden=true;$('provider-retry').hidden=false}catch(e){toast(e.message)}};
async function pollProvider(){
 if(providerPolling)return;providerPolling=true;
 try{while(providerJob){const job=await api('provider?id='+encodeURIComponent(providerJob));paintProvider(job);if(['done','error','cancelled'].includes(job.status)){if(job.status==='done')await refresh();break}if(page==='provider'&&['manual','verification'].includes(job.status))await loadProviderScreen();await new Promise(resolve=>setTimeout(resolve,1500))}}
 catch(e){$('provider-status').textContent=e.message;$('provider-retry').hidden=false}
 finally{providerPolling=false}
}
async function loadProviderScreen(){
 if(screenLoading||!providerJob||document.hidden)return;screenLoading=true;
 try{const response=await fetch('/api/provider/screenshot?id='+encodeURIComponent(providerJob),{credentials:'same-origin'});if(!response.ok)return;const next=URL.createObjectURL(await response.blob());const old=screenURL;screenURL=next;$('provider-screen').src=next;if(old)URL.revokeObjectURL(old)}finally{screenLoading=false}
}
async function providerInput(input){
 if(!providerJob||providerInputBusy)return;providerInputBusy=true;
 try{await api('provider/input',{id:providerJob,...input});await loadProviderScreen()}catch(e){toast(e.message)}finally{providerInputBusy=false}
}
let providerPointer=null;
$('provider-screen').onpointerdown=e=>{const r=e.currentTarget.getBoundingClientRect();providerPointer={x:Math.round((e.clientX-r.left)*e.currentTarget.naturalWidth/r.width),y:Math.round((e.clientY-r.top)*e.currentTarget.naturalHeight/r.height)};e.preventDefault()};
$('provider-screen').onpointerup=e=>{if(!providerPointer)return;const r=e.currentTarget.getBoundingClientRect(),point={x:Math.round((e.clientX-r.left)*e.currentTarget.naturalWidth/r.width),y:Math.round((e.clientY-r.top)*e.currentTarget.naturalHeight/r.height)};const start=providerPointer;providerPointer=null;if(Math.hypot(point.x-start.x,point.y-start.y)>8)providerInput({kind:'drag',...start,toX:point.x,toY:point.y});else providerInput({kind:'click',...point})};

$('provider-scroll-down').onclick=()=>providerInput({kind:'scroll',amount:450});$('provider-scroll-up').onclick=()=>providerInput({kind:'scroll',amount:-450});
$('provider-login').onsubmit=async e=>{e.preventDefault();const email=$('provider-email').value,password=$('provider-password').value;$('provider-password').value='';await providerInput({kind:'login',email,password})};
$('provider-send').onclick=async()=>{const value=$('provider-text').value;$('provider-text').value='';await providerInput({kind:'text',text:value})};

setInterval(()=>{if(page==='devices'&&!document.hidden)loadDevices()},5000);

$('provider-enter').onclick=()=>providerInput({kind:'enter'});
$('provider-screen').onpointercancel=()=>{providerPointer=null};
