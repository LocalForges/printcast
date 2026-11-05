// 交互层：动画主循环、直播事件、设置同步、场景事件、面板与控件
// 本片段由 scripts/build-display.mjs 按顺序拼入同一模块作用域。
let nextRenderAt=0;function animate(now){requestAnimate();if(now+0.5<nextRenderAt)return;const frameInterval=1000/targetFps;nextRenderAt=Math.max(nextRenderAt+frameInterval,now);let dt=Math.min((now-last)/1000,.25)*simulationSpeed;last=now;if(!paused){beltOffset+=dt*beltSpeed;beltTexture.offset.x-=dt*beltSpeed/beltLength;rollers.forEach(r=>r.rotation.z-=dt*beltSpeed/.18);beltLines.forEach((b,i)=>b.position.x=beltStart+(i*beltLength/84+beltOffset)%beltLength);for(let i=products.length-1;i>=0;i--){let p=products[i];p.g.position.x+=dt*beltSpeed;if(p.g.position.x+.875*p.factor>=beltEnd-.15){disposeProduct(p);products.splice(i,1)}}if(busy){elapsed+=dt;if(phase==='printing'){let f=Math.min(elapsed/printDuration,1);updateDeposition(f);const pct=Math.round(f*100);if(pct!==lastPct){lastPct=pct;const pp=$('print-progress');if(pp)pp.textContent='当前：'+active.name+' · 打印中 '+pct+'%'}if(f===1){machineAudio.cue('complete');giftSpeech.printing(active.name,true);currentProduct.glintAge=0;phase='reveal';elapsed=0;currentProduct.plane.constant=100;currentProduct.bead.visible=false;currentProduct.filament.geometry.setDrawRange(0,Infinity);count++;$('count').textContent=count;logPrint(active);const pp=$('print-progress');if(pp)pp.textContent='当前：'+active.name+' · 出分 '+active.score+'分';$('score').innerHTML=active.score+' <small>分</small>';updateScreen()}}else if(phase==='reveal'){gantry.position.y=THREE.MathUtils.lerp(gantry.position.y,4.8,.08);if(elapsed>.55){machineAudio.cue('transfer');phase='transfer';elapsed=0;beginTransfer()}}else if(phase==='transfer'){runTransfer(elapsed)}}}if(!busy&&!paused)next();updateHoses();machineAudio.update({phase,paused,elapsed,beltSpeed});updateEffects(Math.min((now-lastGlintTime)/1000,.05));lastGlintTime=now;controls.update();sceneOutput.render(scene,camera);measureRender(now);if(viewPC)viewStream?.getVideoTracks()[0]?.requestFrame()}

const demoEngine=new DemoRules();let queue=demoEngine.queue,count=0,paused=false,busy=false,socket,timer;const placeholder='data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100" height="100" fill="#f2b59c"/><circle cx="50" cy="38" r="20" fill="#fff"/><path d="M15 100c3-40 67-40 70 0" fill="#fff"/></svg>');$('currentImg').src=placeholder;function fallbackAvatar(name){const safe=String(name||'').replace(/[<>\n\r]/g,'').trim()||'客人';let h=0;for(let i=0;i<safe.length;i++)h=(h*31+safe.charCodeAt(i))>>>0;const pals=[['#ffb284','#c96f4a'],['#a9b8f4','#5a6fd6'],['#91cbb1','#4d927b'],['#efa8b9','#d16a86'],['#e6bc6a','#bd8f3a'],['#ba9ee0','#7e5cc0'],['#89b9cd','#4f88a5'],['#d8b992','#a5825c']];const p=pals[h%pals.length];const c=document.createElement('canvas');c.width=c.height=128;const x=c.getContext('2d');const g=x.createLinearGradient(0,0,128,128);g.addColorStop(0,p[0]);g.addColorStop(1,p[1]);x.fillStyle=g;x.fillRect(0,0,128,128);x.fillStyle='rgba(255,255,255,.22)';for(let i=0;i<5;i++){x.beginPath();x.arc((h>>>(i*5))%128,(h>>>(i*7))%128,Math.max(2,10+((h>>>(i*3))%22)),0,7);x.fill()}x.fillStyle='#fff';x.font='800 54px "Microsoft YaHei",sans-serif';x.textAlign='center';x.textBaseline='middle';x.fillText(safe.slice(0,1),64,68);return c.toDataURL('image/png')}
function renderQueue(){$('waiting').textContent=queue.length;$('queue').innerHTML='';if(!queue.length){$('queue').innerHTML='<div class="empty">队列空空的，等待观众加入</div>';return}queue.slice(0,5).forEach((v,i)=>{let row=document.createElement('div');row.className='item';let img=document.createElement('img');img.src=v.avatar||fallbackAvatar(v.name);img.onerror=()=>img.src=placeholder;let name=document.createElement('span');name.textContent=v.name+' · '+(v.size==='large'?'大':'小')+'头像'+(v.total>1?' '+v.copy+'/'+v.total:'')+(v.priority?' · 礼物优先':'');let n=document.createElement('b');n.textContent='#'+(i+1);row.append(img,name,n);$('queue').append(row)})}function liveEvent(type,user,amount=1,label,sourceTag,markLive=true){let r;try{r=demoEngine.event(type,user,'live-'+(++eventId),amount,printOptions(printRules,type,sourceTag))}catch(e){return}if(!r.added)return;const at=r.index;for(let i=at;i<at+r.added;i++){if(sourceTag)queue[i].source=sourceTag;queue[i].live=!!markLive;if(type==='like')queue[i].fromLike=sourceTag!=='评论'}if(sourceTag==='评论'){const jobs=queue.splice(at,r.added);let pos=queue.findIndex(j=>j.fromLike&&!j.priority);if(pos<0)pos=queue.length;queue.splice(pos,0,...jobs)}machineAudio.cue(RULES[type].priority?'gift':'queue');if(RULES[type].priority&&printRules.giftVoice)giftSpeech.say(user.name,label||RULES[type].label,amount);preemptForGift();renderQueue();updateScreen();next()}
let liveRoom='',liveMode=false,lastPct=-1,liveEverConnected=false,lastSnapshotPeople=[],lastLiveFill=0,lastLiveMsgAt=Date.now();const liveStats={like:0,comment:0,gift:0};
function updateLiveStats(){const l=$('stat-likes'),c=$('stat-comments'),g=$('stat-gifts');if(l)l.textContent=liveStats.like;if(c)c.textContent=liveStats.comment;if(g)g.textContent=liveStats.gift}
function setLiveStatus(on){const el=$('live-status');if(!el)return;el.innerHTML=on?'<span style="color:#7fd69a">● 已连接数据桥 '+socket.url+'</span>':'<span style="color:#e08f8f">● 未连接 · 本地演示中</span>';const r=$('live-room');if(r)r.innerHTML=on&&liveRoom?'<a href="https://live.douyin.com/'+liveRoom+'" target="_blank" rel="noopener" style="color:#9fc3e8">打开直播间 '+liveRoom+' ↗</a>':'';const f=$('live-fetch');if(f&&!on)f.innerHTML='抓取：暂停（数据桥未连接，演示数据继续）'}
function add(v){let name=String(v.name||v.nickname||'直播观众').slice(0,40),avatar=v.avatar||v.avatarUrl||'';if(typeof avatar!=='string')avatar='';const type=String(v.type||'comment');if(type==='comment'||type==='like'||type==='gift'||type==='follow'||type==='join')lastLiveMsgAt=Date.now();if(type==='gift'){const n=Math.max(1,Math.min(100,Number(v.count)||1));liveStats.gift++;liveRoom=liveRoom||v.room||'';updateLiveStats();const kind=Object.hasOwn(RULES,v.gift)&&RULES[v.gift].priority?v.gift:'other';if(printRules.gift&&printAllowed())liveEvent(kind,{name,avatar},n,v.raw,'礼物·'+(v.raw||RULES[kind].label));else if(printRules.giftVoice&&printAllowed())giftSpeech.say(name,v.raw||RULES[kind].label,n)}else if(type==='like'){const n=Math.max(1,Math.min(100,Number(v.count)||1));liveStats.like+=n;liveRoom=liveRoom||v.room||'';updateLiveStats();if(printRules.like&&printAllowed())liveEvent('like',{name,avatar},n,null,'点赞')}else if(type==='follow'){if(printRules.follow&&printAllowed())liveEvent('like',{name,avatar},1,null,'关注')}else if(type==='join'){if(printRules.join&&printAllowed())liveEvent('like',{name,avatar},1,null,'进场');if(printRules.joinVoice&&printAllowed())giftSpeech.welcome(name)}else if(type==='hello'){liveRoom=String(v.room||'');$('mode').textContent='● 直播数据';$('status').textContent='数据桥已连接 · 房间 '+liveRoom.slice(0,16);setLiveStatus(true);const ri=$('room-input');if(ri&&document.activeElement!==ri&&!ri.value)ri.value=liveRoom;if(Array.isArray(v.people)&&v.people.length)lastSnapshotPeople=v.people.slice(0,8)}else if(type==='room'){liveRoom=String(v.room||'');setLiveStatus(true);const ri=$('room-input');if(ri&&document.activeElement!==ri)ri.value=liveRoom}else if(type==='ping'){if(v.room){if(!liveRoom)liveRoom=String(v.room);setLiveStatus(true);const ri=$('room-input');if(ri&&document.activeElement!==ri&&!ri.value)ri.value=liveRoom}if(Array.isArray(v.people)&&v.people.length)lastSnapshotPeople=v.people;const st=v.stats,f=$('live-fetch');if(f&&st){const ago=st.lastAgo==null?null:Math.round(st.lastAgo/1000);f.innerHTML='抓取：● 正常 · 弹幕'+st.comment+' · 点赞'+st.like+' · 礼物'+st.gift+' · 观众'+st.roster+'人 · '+(ago==null?'等待直播动态':(ago<5?'刚刚有动态':ago+'秒前有动态'))}}else if(type==='comment'){liveStats.comment++;liveRoom=liveRoom||v.room||'';updateLiveStats();if(printRules.comment&&printAllowed())liveEvent('like',{name,avatar},1,null,'评论');}}
let bridgeConnecting=false;
let autoStartT=0,autoStartN=0;
function autoStartBridge(){const now=Date.now();if(now-autoStartT<15000||autoStartN>=10)return;autoStartT=now;autoStartN++;let rid=(String(liveRoom||'').match(/(\d{5,25})/)||[])[1]||'';if(!rid){try{rid=((localStorage.getItem('printer-live-room')||'').match(/(\d{5,25})/)||[])[1]||''}catch(e){}}try{fetch('/__start-bridge?room='+rid+'&auto=1').then(r=>r.json()).then(j=>{if(j.ok&&!j.already)console.log('[自动] 数据桥已拉起，正在连接直播间…')}).catch(()=>{})}catch(e){}}
async function connectBridge(){if(bridgeConnecting||(socket&&socket.readyState<=1))return;bridgeConnecting=true;let address;try{const r=await fetch('/__bridge-status',{signal:AbortSignal.timeout(4000)});const j=await r.json();if(!j.ok)throw new Error('Bridge offline');address=j.url}catch(e){bridgeConnecting=false;clearTimeout(timer);timer=setTimeout(connectBridge,3000);autoStartBridge();return}bridgeConnecting=false;try{socket=new WebSocket(address);if($('url'))$('url').value=address}catch(e){timer=setTimeout(connectBridge,3000);return}socket.onopen=()=>{lastLiveMsgAt=Date.now();$('mode').textContent='● 直播数据';$('status').textContent='数据桥已连接';setLiveStatus(true);liveMode=true;liveEverConnected=true;for(let i=queue.length-1;i>=0;i--)if(!queue[i].live)queue.splice(i,1);renderQueue();updateScreen();autoDemo=false;const ab=window.__autoDemoButton;if(ab){ab.textContent='自动演示：关';ab.setAttribute('aria-pressed','false')}};socket.onmessage=e=>{try{add(JSON.parse(e.data))}catch(err){}};socket.onclose=()=>{const rs=$('room-open-status');if(rs)rs.textContent='数据桥连接已断开，正在重试 / Bridge disconnected, retrying…';$('mode').textContent='● 测试数据';$('status').textContent='数据桥未连接 · 本地演示';setLiveStatus(false);liveMode=false;autoDemo=true;const ab=window.__autoDemoButton;if(ab){ab.textContent='自动演示：开';ab.setAttribute('aria-pressed','true')}replenishDemo(true);clearTimeout(timer);timer=setTimeout(connectBridge,3000)}}connectBridge();requestAnimate();setInterval(()=>{if(document.hidden&&!paused)animate(performance.now())},250);setInterval(idleTestFill,1000);window.addEventListener('error',e=>{try{window.__pageErrors=(window.__pageErrors||[]).concat(String(e.message).slice(0,140)).slice(-8)}catch(err){}});
const demoNames=['橘子汽水','星星同学','奶油小熊','薄荷拿铁','蓝莓布丁','桃桃乌龙','快乐阿柴','月亮晚安','杨梅吐气','椰奶泡泡','芝士芋泥','焦糖玛奇朵','苏打绿豆','元气布丁','西瓜甜不甜','奶盖十三','柚子茶茶','豆乳盒子','麻薯团子','蛋挞小伙','软糖阿姨','气泡水呀','栗子同学','糯米滋滋'];
function testAvatar(i){const c=document.createElement('canvas');c.width=c.height=256;const x=c.getContext('2d');const colors=['#ffb284','#a9b8f4','#d8b992','#91cbb1','#ba9ee0','#efa8b9','#e6bc6a','#89b9cd','#f4a4a4','#9fd6a8','#d9c2f0','#f0d9a8','#a8d9d4','#f4b8d8','#c4d98a','#e0a8c4'];x.fillStyle=colors[i%colors.length];x.fillRect(0,0,256,256);x.fillStyle='#ffffff30';for(let k=0;k<6;k++){x.beginPath();x.arc(k*58-12,k%2?30:225,35,0,Math.PI*2);x.fill()}const animal=i%3!==1;x.fillStyle=animal?'#fff1da':'#423b51';for(const xx of [76,180]){x.beginPath();x.arc(xx,77,animal?30:24,0,Math.PI*2);x.fill()}x.fillStyle=animal?'#fff1da':'#f6d4bd';x.beginPath();x.ellipse(128,134,78,83,0,0,Math.PI*2);x.fill();x.fillStyle='#353342';for(const xx of [101,155]){x.beginPath();x.ellipse(xx,127,7,10,0,0,Math.PI*2);x.fill()}x.fillStyle='#eea193';for(const xx of [82,174]){x.beginPath();x.ellipse(xx,151,14,8,0,0,Math.PI*2);x.fill()}x.strokeStyle='#57424a';x.lineWidth=5;x.lineCap='round';x.beginPath();x.arc(128,149,18,0.15,Math.PI-.15);x.stroke();if(i%2===0){x.fillStyle='#8d624c';x.beginPath();x.ellipse(128,146,8,6,0,0,Math.PI*2);x.fill()}return c.toDataURL('image/png')}
let demoPeople=demoNames.map((name,i)=>({name,avatar:testAvatar(i)}));
setTimeout(()=>{if(liveEverConnected)return;if(typeof pcSettings!=='undefined'&&pcSettings&&pcSettings.live&&pcSettings.live.demoFill===false)return;const s0=[...demoPeople];for(let i=s0.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[s0[i],s0[j]]=[s0[j],s0[i]]}s0.slice(0,6).forEach(p=>liveEvent('like',p,1,null,'演示',false))},0);
$('demo').textContent='再加一批测试头像';$('demo').onclick=()=>updateScreen();
updateScreen();
$('toggle').onclick=()=>{paused=!paused;machineAudio.cue(paused?'pause':'resume');$('toggle').textContent=paused?'继续打印':'暂停打印';if(!paused)next()};$('skip').onclick=()=>{machineAudio.cue('skip');if(currentProduct){const i=products.indexOf(currentProduct);if(i>=0)products.splice(i,1);disposeProduct(currentProduct)}currentProduct=null;transferState=null;articulateArm();active=null;busy=false;phase='idle';next()};// Explicit opt-in required by browser audio policies.
const soundBar=document.createElement('div');soundBar.style.cssText='display:flex;align-items:center;gap:10px;padding:12px 20px;border-top:1px solid #303642;flex-wrap:wrap';
const soundButton=document.createElement('button');soundButton.className='secondary';soundButton.textContent='开启声音';syncQuickIcon('🔇 打开声音');soundButton.setAttribute('aria-pressed','false');const volumeLabel=document.createElement('label');volumeLabel.textContent='音量 ';volumeLabel.style.cssText='display:flex;align-items:center;gap:10px;color:#abb5c2';const volume=document.createElement('input');volume.type='range';volume.min='0';volume.max='100';volume.value='65';volume.setAttribute('aria-label','音效音量');volume.style.width='120px';volumeLabel.append(volume);const audioStatus=document.createElement('span');audioStatus.style.cssText='font-size:12px;color:#8b98a9';audioStatus.textContent='打印 / 完成 / 输送 / 机械臂 / 互动提示';soundBar.append(soundButton,volumeLabel,audioStatus);document.querySelector('.controls').after(soundBar);
let soundUserMuted=false,soundStarting=false;
async function unlockSound(test=false){if(soundStarting)return;soundStarting=true;try{if(test&&machineAudio.volume===0){machineAudio.setVolume(.65);volume.value='65'}await machineAudio.enable();soundButton.textContent='静音';syncQuickIcon('🔊 关闭声音');soundButton.setAttribute('aria-pressed','true');audioStatus.textContent='音频引擎：'+machineAudio.ctx.state+' · 音量 '+Math.round(machineAudio.volume*100)+'%';if(test)machineAudio.cue('complete')}catch(e){audioStatus.textContent='声音未启动：'+e.message+'；可用下方播放器检查输出'}finally{soundStarting=false}}
soundButton.onclick=()=>{if(machineAudio.enabled&&machineAudio.ctx?.state==='running'){soundUserMuted=true;machineAudio.mute();soundButton.textContent='开启声音';syncQuickIcon('🔇 打开声音');soundButton.setAttribute('aria-pressed','false');audioStatus.textContent='已静音'}else{soundUserMuted=false;unlockSound()}};

// —— 「打印现场」旁的快捷声音开关：一键关闭/打开全部声音（音效 + 互动播报），状态记忆 ——
const quickSound=document.createElement('button');quickSound.className='secondary quick-sound';quickSound.style.cssText='padding:8px 18px;font-size:15px;line-height:1.2;white-space:nowrap';
let quickOn=true;try{quickOn=localStorage.getItem('printer-sound')!=='off'}catch(e){}
function syncQuickIcon(icon){const qb=document.querySelector('.stagehead .quick-sound');if(qb)qb.textContent=icon}
function applyQuickSound(){quickSound.textContent=quickOn?'🔊 关闭声音':'🔇 打开声音';quickSound.title=quickOn?'点击关闭所有声音（音效+播报）':'点击开启所有声音（音效+播报）';quickSound.setAttribute('aria-pressed',String(quickOn));try{localStorage.setItem('printer-sound',quickOn?'on':'off')}catch(e){}}
function syncVoiceLabel(){const st=document.getElementById('speech-toggle');if(st){st.textContent=giftSpeech.enabled?'互动播报：开':'互动播报：关';st.setAttribute('aria-pressed',String(giftSpeech.enabled))}}
async function applyQuickState(){
  if(quickOn){soundUserMuted=false;giftSpeech.enabled=true;syncVoiceLabel();await unlockSound();quickSound.textContent='🔊'}
  else{soundUserMuted=true;machineAudio.mute();giftSpeech.enabled=false;giftSpeech.stop();syncVoiceLabel();quickSound.textContent='🔇';soundButton.textContent='开启声音';syncQuickIcon('🔇 打开声音');soundButton.setAttribute('aria-pressed','false')}
}
quickSound.onclick=()=>{quickOn=!quickOn;applyQuickSound();applyQuickState()};
applyQuickSound();
if(!quickOn){soundUserMuted=true;machineAudio.mute();giftSpeech.enabled=false;syncVoiceLabel()}
document.querySelector('.stagehead').insertBefore(quickSound,document.querySelector('.stagehead small'));
const soundTest=document.createElement('button');soundTest.className='secondary';soundTest.textContent='测试声音';soundTest.onclick=()=>{soundUserMuted=false;unlockSound(true)};
const nativeAudio=document.createElement('audio');nativeAudio.controls=true;nativeAudio.preload='auto';nativeAudio.src='../assets/audio-check.wav';nativeAudio.volume=.7;nativeAudio.style.cssText='height:32px;width:240px';nativeAudio.setAttribute('aria-label','独立声音检查播放器');const nativeLabel=document.createElement('span');nativeLabel.textContent='独立声音检查';nativeLabel.style.fontSize='12px';
const repairAudio=document.createElement('button');repairAudio.className='secondary';repairAudio.textContent='修复声音';repairAudio.onclick=async()=>{soundUserMuted=false;machineAudio.setVolume(.65);volume.value='65';nativeAudio.currentTime=0;nativeAudio.play().then(()=>audioStatus.textContent='检查音正在播放；听不到时请检查标签页静音、系统音量和输出设备').catch(e=>audioStatus.textContent='音频文件播放受阻：'+e.message);try{await machineAudio.rebuild();soundButton.textContent='静音';syncQuickIcon('🔊 关闭声音');soundButton.setAttribute('aria-pressed','true')}catch(e){audioStatus.textContent='音频引擎重建失败：'+e.message}};
nativeAudio.addEventListener('error',()=>{markMissingAsset('audio-check.wav');audioStatus.textContent='声音检查音频缺失，已静音降级。还原：bash scripts/vendor-assets.sh'});
const autoButton=document.createElement('button');autoButton.className='secondary';autoButton.textContent='自动演示：开';autoButton.setAttribute('aria-pressed','true');autoButton.onclick=()=>{autoDemo=!autoDemo;autoButton.textContent=autoDemo?'自动演示：开':'自动演示：关';autoButton.setAttribute('aria-pressed',String(autoDemo));if(autoDemo){replenishDemo(true);next()}};window.__autoDemoButton=autoButton;document.querySelector('.controls').append(autoButton);
volume.oninput=()=>{machineAudio.setVolume(Number(volume.value)/100);audioStatus.textContent=Number(volume.value)===0?'音量为0':`音量 ${volume.value}%`};
function gestureAudio(e){if(!giftSpeech.unlocked){giftSpeech.unlocked=true;if(active)giftSpeech.printing(active.name)}if(e.target===soundButton||e.target===soundTest||soundUserMuted)return;if(!machineAudio.enabled||machineAudio.ctx?.state!=='running')unlockSound()}
document.addEventListener('pointerdown',gestureAudio);document.addEventListener('keydown',gestureAudio);document.addEventListener('visibilitychange',()=>{if(machineAudio.isHidden())machineAudio.silence();else if(machineAudio.enabled&&machineAudio.ctx?.state!=='running')audioStatus.textContent='点击页面恢复声音'});window.addEventListener('pagehide',()=>machineAudio.silence());
audioStatus.textContent='点击页面即启用声音，也可点击“测试声音”';
const speechPanel=document.createElement('div');speechPanel.style.cssText='padding:12px 20px;background:#1a202a;border-top:1px solid #343a46';speechPanel.innerHTML='<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"><button id="speech-toggle" class="secondary" aria-pressed="true">互动播报：开</button><button id="speech-test" class="secondary">试听女声</button><select id="speech-voice" aria-label="播报语音" style="max-width:240px;padding:8px"><option value="">自动选择中文女声</option></select><label>语速 <input id="speech-rate" aria-label="播报语速" type="range" min="0.8" max="1.3" step="0.05" value="1.05" style="width:90px"></label></div><p id="speech-caption" style="font-size:13px;line-height:1.8;margin-top:8px;color:#decab7" aria-live="polite">进场欢迎与礼物感谢均播报昵称和随机祝福。系统语音音色因设备而异。</p>';
soundBar.after(speechPanel);const giftSpeech=new GiftSpeech(text=>$('speech-caption').textContent=text);giftSpeech.rate=1.05;
function refreshVoices(){const select=$('speech-voice'),selected=select.value;select.innerHTML='<option value="">自动选择中文女声</option>';for(const v of giftSpeech.voices().filter(v=>/zh|cmn/i.test(v.lang))){const o=document.createElement('option');o.value=v.voiceURI;o.textContent=v.name+' · '+v.lang;select.append(o)}select.value=selected;const preferred=giftSpeech.preferred();if(preferred&&!giftSpeech.speaking)$('speech-caption').textContent='当前语音：'+preferred.name+'。点击“试听女声”检查音色。'}
if(globalThis.speechSynthesis){speechSynthesis.addEventListener('voiceschanged',refreshVoices);refreshVoices()}else $('speech-caption').textContent='当前浏览器不支持语音合成';
const welcomeButton=document.createElement('button');welcomeButton.className='secondary';welcomeButton.textContent='模拟进入直播间';welcomeButton.onclick=()=>{const p=demoPeople[Number(userSelect.value)]||randomPerson();giftSpeech.welcome(p.name);logDemo(p.name+' 进入直播间');machineAudio.cue('queue')};$('speech-test').after(welcomeButton);
$('speech-voice').onchange=e=>{giftSpeech.stop();giftSpeech.voiceURI=e.target.value};$('speech-rate').oninput=e=>giftSpeech.rate=Number(e.target.value);$('speech-toggle').onclick=()=>{giftSpeech.enabled=!giftSpeech.enabled;if(!giftSpeech.enabled)giftSpeech.stop();$('speech-toggle').textContent=giftSpeech.enabled?'互动播报：开':'互动播报：关';$('speech-toggle').setAttribute('aria-pressed',String(giftSpeech.enabled))};$('speech-test').onclick=()=>{giftSpeech.stop();giftSpeech.enabled=true;$('speech-toggle').textContent='互动播报：开';$('speech-toggle').setAttribute('aria-pressed','true');giftSpeech.say(randomPerson().name,'爱心',1)};window.addEventListener('pagehide',()=>giftSpeech.stop());
// Demo-only panel: no live data connections.
const connectionPanel=$('connect').closest('.panel');connectionPanel.innerHTML=`<div class="panelhead">规则演示台 <small>仅测试数据</small></div><div class="body"><label class="label">测试观众</label><select id="demo-user" style="width:100%;padding:10px"></select><div id="rule-buttons" style="display:flex;gap:7px;flex-wrap:wrap;margin-top:12px"></div><div class="live-rules" aria-label="评论666打印一张小图，爱心一张大图，啤酒两张大图，棒棒糖三张大图"><div class="rule-row comment-rule"><b>评论 666</b><span>打印一张小图</span></div><div class="rule-row"><img src="../assets/generated/original-icons/heart.png" alt="爱心"><span>打印大图一张</span></div><div class="rule-row"><img src="../assets/generated/original-icons/beer.png" alt="啤酒"><span>打印大图两张</span></div><div class="rule-row"><img src="../assets/generated/original-icons/lollipop.png" alt="棒棒糖"><span>打印大图三张</span></div></div><p class="note">评论 666 → 1张小图<br>爱心 → 1张大图<br>啤酒 → 2张大图<br>棒棒糖 → 3张大图<br>礼物立即插队，普通任务保留后重打。</p><label class="label">批量导入头像（仅本地使用）</label><input id="avatar-files" type="file" accept="image/*" multiple><p class="note" id="avatar-source">正在加载截图整理头像与抽象昵称…</p><label class="label">演示速度</label><select id="demo-speed"><option value="1">1×</option><option value="4" selected>4×</option><option value="12">12× 快速验收</option></select><div class="row"><button id="scenario">运行规则演示</button><button id="reset-demo" class="secondary">清空重置</button></div><div id="demo-log" style="font-size:12px;line-height:1.8;color:#c4d0dc;max-height:180px;overflow:auto;margin-top:12px" aria-live="polite"></div></div>`;
addRulesDownload(connectionPanel.querySelector('.live-rules'));
for(const img of connectionPanel.querySelectorAll('.live-rules img')){const fallback=()=>{img.style.visibility='hidden';markMissingAsset('original-icons/*.png')};img.addEventListener('error',fallback,{once:true});if(img.complete&&img.naturalWidth===0)fallback()}
const livePanel=document.createElement('div');livePanel.className='panel';livePanel.innerHTML='<div class="panelhead">直播连接 <small>LIVE ROOM</small></div><div class="body"><div id="live-status" style="font-size:13px;line-height:1.7"><span style="color:#e08f8f">● 未连接 · 本地演示中</span></div><div id="live-room" style="font-size:12px;line-height:1.7"></div><div id="print-progress" style="font-size:12px;line-height:1.7;color:#b9c6d6;margin-top:6px">当前：待命</div><div style="display:flex;gap:6px;margin-top:8px"><input id="room-input" placeholder="直播间号或链接，回车切换" style="flex:1;min-width:0;padding:8px;background:#141a24;border:1px solid #333c4c;border-radius:6px;color:#e8eef6;font-size:12px"><button id="room-set" class="secondary" style="padding:8px 12px;white-space:nowrap">切换</button></div><div style="margin-top:10px"><button id="room-open" style="width:100%">打开直播间窗口</button><div class="row"><button id="capture-start">开始抓取</button><button id="capture-stop" class="secondary">停止抓取</button></div><div id="room-open-status" role="status" style="font-size:12px;line-height:1.7;color:#9fb3c8;margin-top:6px">打开后可自行登录；抓取还需连接数据桥。</div></div><div id="live-fetch" style="font-size:12px;line-height:1.7;color:#9fb3c8;margin-top:6px">抓取状态：连接中…</div><div id="yield-note" style="font-size:12px;line-height:1.7;color:#ffd9a8;margin-top:2px"></div><div class="metrics" style="margin-top:10px"><div class="metric"><small>点赞</small><strong id="stat-likes">0</strong></div><div class="metric"><small>评论</small><strong id="stat-comments">0</strong></div><div class="metric"><small>礼物</small><strong id="stat-gifts">0</strong></div></div><details id="print-rules" open style="margin-top:10px"><summary style="cursor:pointer;color:#d4dce6;font-size:12px;user-select:none">打印规则（修改自动保存）</summary><div id="print-rules-body" style="display:grid;gap:7px;margin-top:9px;font-size:12px;color:#b9c6d6"></div><p class="note" style="margin-top:8px">评论和礼物默认打印；改动立即生效并记住，刷新页面仍保留。</p></details></div>';
const historyPanel=document.createElement('div');historyPanel.className='panel';historyPanel.innerHTML='<div class="panelhead">打印记录 <small>PRINT LOG</small></div><div class="body"><div id="print-history" class="queue" style="max-height:320px;overflow:auto"></div></div>';
connectionPanel.before(livePanel,historyPanel);
const printRules=Object.assign({comment:true,join:false,like:false,follow:false,gift:true,giftVoice:true,joinVoice:true,idleFill:false,demoGapMs:30000},{});
for(const [key,value] of Object.entries(PRINT_DEFAULTS)){if(printRules[key]===undefined)printRules[key]=value}
// —— 控制台设置：展示端只读，不写。轮询 /__api/settings（每 5s）即时同步，无需刷新页面——
// 控制台是唯一权威来源：printer.* / broadcast.scriptedPrint / live.* 全部覆盖本地默认值；
// enqueueAppearance 等逻辑实时读取 pcSettings（如 scriptedPrint），无需重载即可生效。
async function refreshConsoleSettings(){
  try{
    // 统一走 settings-loader：首屏复用 ready，之后 reload 重取并应用品牌层。
    // 展示端不直连 fetch，保证「配置只有一个入口」。
    if(!window.__PC) return;
    const s = await (window.__PC.reload ? window.__PC.reload() : window.__PC.ready);
    if(!s) return;
    pcSettings = s;
    const p = s.printer || {};
    if(p.rules && typeof p.rules==='object') Object.assign(printRules,p.rules);
    for(const k of ['demoGapMs','idleSeconds','idleFill']) if(p[k]!==undefined) printRules[k]=p[k];
    if(typeof p.autoDemo==='boolean'){
      autoDemo=p.autoDemo;
      const btn=window.__autoDemoButton;
      if(btn){ btn.textContent=autoDemo?'自动演示：开':'自动演示：关'; btn.setAttribute('aria-pressed',String(autoDemo)); }
    }
    const live=s.live||{};
    const ri=$('room-input');
    if(ri){
      if(live.defaultRoom&&!ri.value) ri.value=live.defaultRoom;
      ri.setAttribute('data-room-input','');
      ri.placeholder=live.platform==='generic'?'通用推流模式：房间号可留空':'抖音直播间号或链接，回车切换';
    }
    // 展示端规则面板转为只读，并实时反映控制台值（无需刷新）。
    const host=$('print-rules-body');
    if(host){ renderPrintSettings(host,printRules,()=>{}); host.querySelectorAll('input,select').forEach(el=>{el.disabled=true}); }
    const det=$('print-rules');
    if(det){ const sum=det.querySelector('summary'); if(sum) sum.textContent='打印规则（控制台统一设置 · 只读）';
      const note=det.querySelector('.note'); if(note) note.innerHTML='在 <a href="/studio/" style="color:var(--accent)">控制台 /studio</a> 修改后约 5 秒内自动同步到本展示端。'; }
    // 同步品牌 / 展示 / 公告 / 链接等（settings-loader 的 apply）。
    if(window.__PC && window.__PC.apply) window.__PC.apply(s);
  }catch(e){}
}
refreshConsoleSettings();
// 轮询只在页面可见时跑：OBS/投屏常驻后台时不必空转；切回前台立即补一次。
setInterval(()=>{ if(!document.hidden) refreshConsoleSettings(); },5000);
document.addEventListener('visibilitychange',()=>{ if(!document.hidden) refreshConsoleSettings(); });
// —— M1：把出场广播的 view-appearance 接进 3D 打印队列，实现「讲到谁就打谁」——
let appearanceCursor=null; const appearanceClient='renderer-'+Math.random().toString(36).slice(2,10);
const appearanceSeen=new Set();
function enqueueAppearance(ap,seq){
  if(!ap||!ap.name) return;
  if(pcSettings&&pcSettings.broadcast&&pcSettings.broadcast.scriptedPrint===false) return;
  if(!printAllowed()) return;
  const key=seq!=null?'seq:'+seq:null;
  const decision=shouldEnqueue({length:queue.length,seen:appearanceSeen,key});
  if(!decision.ok){
    if(decision.reason==='full'){const y=$('yield-note');if(y)y.textContent='打印队列已满，本次出场暂缓（上限 '+QUEUE_LIMIT+' 件）';}
    return;
  }
  remember(appearanceSeen,key);
  queue.push({name:ap.name,avatar:mediaUrl(ap.avatar),size:'large',priority:false,
    source:'剧本·'+(ap.packTitle||'内容包'),copy:1,total:1,scripted:true,speech:ap.speech||'',
    tags:ap.tags||[],packTitle:ap.packTitle||'',index:ap.index});
  renderQueue(); updateScreen();
  if(pcSettings&&pcSettings.broadcast&&pcSettings.broadcast.speech!==false&&ap.speech&&giftSpeech) giftSpeech.say(ap.name,ap.speech,1);
  next();
}
async function appearanceTick(){
  try{
    const r=await fetch('/__scene-events?client='+appearanceClient+(appearanceCursor===null?'':'&after='+appearanceCursor));
    const d=await r.json(); appearanceCursor=d.cursor;
    let needSettings=false;
    for(const m of (d.messages||[])){
      if(m.type==='view-appearance'&&m.appearance) enqueueAppearance(m.appearance,m.seq);
      else if(m.type==='settings-changed') needSettings=true;
    }
    // 控制台一保存就推送信令：立即重读，不必等 5s 轮询（轮询保留为兜底）。
    if(needSettings) refreshConsoleSettings();
  }catch(e){}
  appearanceTimer=setTimeout(appearanceTick,600);
}
let appearanceTimer=setTimeout(appearanceTick,600);
function sendRoom(raw){const id=String(raw||'').match(/(\d{5,25})/);const i=$('room-input');if(!id){if(i){i.value='';i.placeholder='没识别出房间号，请填直播间号或链接'}return}const room=id[1];try{localStorage.setItem('printer-live-room',room)}catch(e){}const lr=$('live-room');if(socket&&socket.readyState===1){socket.send(JSON.stringify({type:'set-room',room}));if(lr)lr.innerHTML='<span style="color:#d9b96a">正在切换到直播间 '+room+' …</span>'}else if(lr)lr.innerHTML='<span style="color:#e08f8f">数据桥未连接，重连后将使用房间 '+room+'</span>'}
async function openLiveRoomWindow(){
 const raw=$('room-input').value.trim();
 const match=raw.match(/^(?:https?:\/\/live\.douyin\.com\/)?(\d{5,25})(?:[/?#].*)?$/);
 const status=$('room-open-status');
 if(!match){status.textContent='请先输入有效的直播间号或 live.douyin.com 直播链接';$('room-input').focus();return}
 const room=match[1];
 if(window.pywebview?.api){try{status.textContent=await window.pywebview.api.open_live_room(room)}catch(e){status.textContent='打开失败：'+e.message}return}
 try{localStorage.setItem('printer-live-room',room)}catch(e){}
 try{status.textContent='正在打开独立直播窗口…';const j=await(await fetch('/__open-live?room='+room+'&debug=1')).json();status.textContent=j.ok?'独立直播窗口已打开（应用窗口），请在其中登录后点「开始抓取」。':'打开失败：'+(j.error||'')}catch(e){status.textContent='打开失败：'+e.message}
 status.textContent='已请求打开直播间，请在新窗口登录。登录不会自动连接数据桥。';
}
$('room-open').onclick=openLiveRoomWindow;
for(const [id,method] of [['capture-start','start_capture'],['capture-stop','stop_capture']])$(id).onclick=async()=>{
 const status=$('room-open-status');
 if(!window.pywebview?.api){
   const mr=($('room-input').value.match(/(\d{5,25})/)||[]);const room=mr?mr[1]:(String(liveRoom||'').match(/(\d{5,25})/)||[,''])[1];
   $(id).disabled=true;
   try{
     if(method==='start_capture'){
       if(!room){status.textContent='请先在上方填写直播间号，再开始抓取';return}
       status.textContent='正在启动数据桥…';
       const j=await(await fetch('/__start-bridge?room='+room)).json();
       status.textContent=j.ok?(j.already?'数据桥已在运行，正在连接…':'数据桥已启动，正在连接直播评论…'):'启动失败：'+(j.error||'');
       if(j.ok)connectBridge();
     }else{
       status.textContent='正在停止数据桥…';
       const j=await(await fetch('/__stop-bridge')).json();
       status.textContent=j.ok?'抓取已停止，可以继续在直播窗口观看。':'停止失败';
     }
   }catch(e){status.textContent='操作失败：'+e.message}finally{$(id).disabled=false}
   return
 }
 $(id).disabled=true;
 try{status.textContent=await window.pywebview.api[method]($('room-input').value);if(method==='start_capture')connectBridge()}catch(e){status.textContent='操作失败：'+e.message}finally{$(id).disabled=false}
};
const roomSetBtn=$('room-set');if(roomSetBtn)roomSetBtn.onclick=()=>sendRoom($('room-input').value);
const roomInputEl=$('room-input');if(roomInputEl)roomInputEl.onkeydown=e=>{if(e.key==='Enter')sendRoom(e.target.value)};
try{const savedRoom=localStorage.getItem('printer-live-room');if(savedRoom&&roomInputEl)roomInputEl.value=savedRoom}catch(e){}
const printRecords=[];
function renderHistory(){const box=$('print-history');if(!box)return;box.innerHTML='';if(!printRecords.length){box.innerHTML='<div class="empty">还没有打印记录，等第一位观众触发</div>';return}for(const rec of printRecords.slice(0,100)){const row=document.createElement('div');row.className='item';const img=document.createElement('img');img.src=rec.avatar||fallbackAvatar(rec.name);img.onerror=()=>img.src=placeholder;const mid=document.createElement('div');mid.style.cssText='flex:1;min-width:0;line-height:1.5';const nm=document.createElement('span');nm.style.cssText='display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap';nm.textContent=rec.name;const meta=document.createElement('small');meta.style.cssText='display:block;color:#93a1b3;font-size:11px';meta.textContent=rec.source+' · '+(rec.size==='large'?'大图':'小图')+' · '+rec.score+'分 · '+rec.time;mid.append(nm,meta);const sc=document.createElement('b');sc.textContent=rec.score+'分';row.append(img,mid,sc);box.append(row)}}
function logPrint(job){if(!job)return;printRecords.unshift({name:job.name,avatar:job.avatar||'',source:job.source||'',score:job.score,size:job.size,time:new Date().toTimeString().slice(0,8)});if(printRecords.length>400)printRecords.pop();renderHistory()}
renderHistory();
const userSelect=$('demo-user');demoPeople.forEach((p,i)=>{let o=document.createElement('option');o.value=i;o.textContent=p.name;userSelect.append(o)});let eventId=0;
function logDemo(message){let line=document.createElement('div');line.textContent=message;$('demo-log').prepend(line);while($('demo-log').children.length>20)$('demo-log').lastChild.remove()}
function randomPerson(){return demoPeople[Math.floor(Math.random()*demoPeople.length)]}
function triggerDemo(type,amount=1,user=randomPerson()){const r=demoEngine.event(type,user,'demo-'+(++eventId),amount);if(!r.duplicate){machineAudio.cue(RULES[type].priority?'gift':'queue');if(RULES[type].priority)giftSpeech.say(user.name,RULES[type].label,amount)}logDemo(user.name+'：'+RULES[type].label+' → '+r.added+'张'+(r.size==='large'?'大图':'小图'));preemptForGift();renderQueue();updateScreen();next();return r}
for(const [type,label] of Object.entries({like:'评论666·小图1张',heart:'爱心·大图1张',beer:'啤酒·大图2张',lollipop:'棒棒糖·大图3张'})){let b=document.createElement('button');b.className='secondary';b.textContent=label;b.onclick=()=>triggerDemo(type);$('rule-buttons').append(b)}
$('avatar-files').onchange=async e=>{const people=[];for(const file of e.target.files){if(!file.type.startsWith('image/'))continue;try{const avatar=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result);r.onerror=reject;r.readAsDataURL(file)});await new Promise((resolve,reject)=>{const i=new Image();i.onload=resolve;i.onerror=reject;i.src=avatar});people.push({name:file.name.replace(/\.[^.]+$/,''),avatar})}catch{}}if(people.length){demoPeople=people;userSelect.innerHTML='';people.forEach((p,i)=>{const o=document.createElement('option');o.value=i;o.textContent=p.name;userSelect.append(o)});$('avatar-source').textContent='已导入 '+people.length+' 张头像，规则演示随机抽取；未上传到服务器。';logDemo('头像素材已替换')}};
$('demo').onclick=()=>{for(let i=0;i<8;i++)add(randomPerson())};
$('demo-speed').onchange=()=>simulationSpeed=Number($('demo-speed').value);
function resetDemo(){giftSpeech.stop();machineAudio.cue('reset');if(currentProduct)disposeProduct(currentProduct);for(const p of products)disposeProduct(p);products.length=0;currentProduct=null;active=null;queue.length=0;demoEngine.likes.clear();demoEngine.seen.clear();demoEngine.follows.clear();busy=false;paused=false;phase='idle';elapsed=0;count=0;lastLiveMsgAt=Date.now();articulateArm(0);$('count').textContent='0';$('score').textContent='等待打印';$('currentName').textContent='测试已重置';$('currentImg').src=placeholder;$('toggle').textContent='暂停打印';renderQueue();updateScreen();$('demo-log').innerHTML=''}
$('reset-demo').onclick=resetDemo;
$('scenario').onclick=()=>{resetDemo();simulationSpeed=12;$('demo-speed').value='12';for(const type of ['like','heart','beer','lollipop'])triggerDemo(type);logDemo('本轮7张：小图1张，大图6张；头像随机抽取。')};
document.querySelector('footer').textContent='演示材质分档：60–69 胡桃木/古铜圆框 · 70–79 拉丝铝/刻纹银框 · 80–89 深色石材/八角钢框 · 90–95 象牙色陶瓷/黄铜双环。模拟外观，不代表普通FDM可直接打印玻璃或金属。评分为随机娱乐分数。';$('status').textContent='本地规则演示';$('mode').textContent='● 测试数据';

// Saved screenshot-derived avatar atlas; original fictional nicknames, randomized demo order.
let avatarImportVersion=0;const previousImport=$('avatar-files').onchange;$('avatar-files').onchange=e=>{avatarImportVersion++;return previousImport(e)};
async function loadPreparedAvatars(){const version=avatarImportVersion;try{const [entries,atlas]=await Promise.all([fetch('../assets/generated/avatar-names.json').then(r=>{if(!r.ok)throw Error('manifest');return r.json()}),new Promise((resolve,reject)=>{const image=new Image();image.onload=()=>resolve(image);image.onerror=reject;image.src='../assets/generated/avatar-atlas.png'})]);if(version!==avatarImportVersion)return;const people=entries.map(entry=>{let c=document.createElement('canvas');const w=atlas.width/4,h=atlas.height/3;c.width=Math.round(w-4);c.height=Math.round(h-4);let ctx=c.getContext('2d');ctx.imageSmoothingQuality='high';ctx.drawImage(atlas,entry.column*w+2,entry.row*h+2,w-4,h-4,0,0,c.width,c.height);return {name:entry.name,avatar:c.toDataURL('image/png')}});demoPeople=people;userSelect.innerHTML='';people.forEach((p,i)=>{let o=document.createElement('option');o.value=i;o.textContent=p.name;userSelect.append(o)});$('avatar-source').textContent='已载入12张截图整理头像（AI清理重绘），昵称原创虚构，随机抽取演示。';
const gallery=document.createElement('details');gallery.style.cssText='margin-top:12px;color:#bbc4ce;font-size:12px';let summary=document.createElement('summary');summary.textContent='查看 / 保存12张头像';gallery.append(summary);let grid=document.createElement('div');grid.style.cssText='display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:10px';for(const p of people){const a=document.createElement('a');a.href=p.avatar;a.download=p.name+'.png';a.style.cssText='color:#d4dce6;text-decoration:none;text-align:center;line-height:1.5';let img=document.createElement('img');img.src=p.avatar;img.alt=p.name;img.style.cssText='width:100%;border-radius:50%;display:block';const caption=document.createElement('span');caption.textContent=p.name;a.append(img,caption);grid.append(a)}gallery.append(grid);$('avatar-source').after(gallery);const shuffled=[...people];for(let i=shuffled.length-1;i>0;i--){let j=Math.floor(Math.random()*(i+1));[shuffled[i],shuffled[j]]=[shuffled[j],shuffled[i]]}if(!liveMode){shuffled.slice(0,6).forEach(p=>liveEvent('like',p,1,null,'演示',false));logDemo('已随机加入演示头像，每次刷新顺序不同。')}else logDemo('直播模式：跳过演示头像填充')}catch{ markMissingAsset('avatar-atlas.png');$('avatar-source').textContent='预设头像缺失，已回退到内置测试头像（演示仍可用）。还原：bash scripts/vendor-assets.sh'}}loadPreparedAvatars();

// —— 独立场景窗口：右上角可折叠设置（默认收起，OBS 采集画面干净）——
if(SCENE_MODE){
  const bar=document.createElement('div');bar.style.cssText='position:fixed;top:10px;right:10px;z-index:60;display:flex;flex-direction:column;align-items:flex-end;gap:8px';
  const gear=document.createElement('button');gear.textContent='⚙ 场景设置';gear.style.cssText='padding:7px 12px;background:rgba(13,17,24,.55);border:1px solid rgba(80,92,110,.6);border-radius:8px;color:#cfd8e3;font-size:12px;cursor:pointer';
  const panel=document.createElement('div');panel.style.cssText='display:none;flex-direction:column;gap:9px;padding:12px 14px;background:rgba(13,17,24,.85);border:1px solid #333c4c;border-radius:10px;backdrop-filter:blur(6px);min-width:230px';
  gear.onclick=()=>{const open=panel.style.display==='none';panel.style.display=open?'flex':'none';gear.style.background=open?'rgba(13,17,24,.9)':'rgba(13,17,24,.55)'};
  const row=(label,el)=>{const r=document.createElement('div');r.style.cssText='display:flex;align-items:center;justify-content:space-between;gap:12px;color:#c9d3de;font-size:12px';const l=document.createElement('span');l.textContent=label;r.append(l,el);panel.append(r)};
  const selStyle='padding:6px 8px;background:#141a24;border:1px solid #333c4c;border-radius:6px;color:#e8eef6;font-size:12px';
  const btnStyle='padding:6px 10px;background:#272e38;border:1px solid transparent;border-radius:6px;color:#c8cfd8;font-size:12px;cursor:pointer';
  const qs=document.createElement('select');qs.style.cssText=selStyle;
  for(const k of ['lite','1','2','4','2x']){const o=document.createElement('option');o.value=k;o.textContent=QUALITY_PRESETS[k].label;qs.append(o)}
  qs.value=qualityKey;qs.onchange=()=>{qualityKey=qs.value;applyQuality()};
  row('画质',qs);
  const aa=document.createElement('select');aa.style.cssText=btnStyle;for(const [value,mode] of Object.entries(AA_MODES)){const o=document.createElement('option');o.value=value;o.textContent=mode.label;aa.append(o)}aa.value=aaMode;aa.onchange=()=>{aaMode=aa.value;applyAA()};row('抗锯齿',aa);
  const np=document.createElement('button');np.style.cssText=btnStyle;const syncNP=()=>{np.textContent=overlayOn?'显示':'隐藏'};np.onclick=()=>{overlayOn=!overlayOn;applyOverlay();syncNP()};syncNP();row('状态牌',np);
  const rs=document.createElement('select');rs.style.cssText=selStyle;
  for(const[id,label]of [["home", "温馨家庭"], ["study", "日光书房"], ["night", "雨夜工作角"], ["workshop", "复古手作室"], ["garden", "清新植物房"]]){const o=document.createElement('option');o.value=id;o.textContent=label;rs.append(o)}
  try{rs.value=localStorage.getItem('printer-room')||'home'}catch(e){};rs.onchange=()=>setRoom(rs.value);row('房间场景',rs);
  const os=document.createElement('select');os.style.cssText=selStyle;
  const ORIENTS=[['landscape','横屏 1280×720'],['landscape-1080p','横屏 1920×1080（1080P）'],['portrait','竖屏 720×1280'],['portrait-1080p','竖屏 1080×1920（1080P）']];
  for(const[v,label]of ORIENTS){const o=document.createElement('option');o.value=v;o.textContent=label;os.append(o)}
  let orient='landscape';try{orient=localStorage.getItem('printer-orient')||'landscape'}catch(e){}
  os.value=orient;os.onchange=()=>{orient=os.value;try{localStorage.setItem('printer-orient',orient)}catch(e){}const SZ={landscape:[1280,720],'landscape-1080p':[1920,1080],portrait:[720,1280],'portrait-1080p':[1080,1920]};const[w,h]=SZ[orient]||[1280,720];if(window.pywebview?.api&&window.pywebview.api.resize_scene){sceneChan?.postMessage({type:'view-size',width:w,height:h})}else{try{window.resizeTo(w,h)}catch(e){}}};
  row('画面方向',os);
  const dv=document.createElement('button');dv.textContent='恢复初始视角';dv.style.cssText=btnStyle;dv.onclick=()=>applyView({id:'',p:defaultCamPos,t:defaultCamTarget});panel.append(dv);
  bar.append(gear,panel);document.body.append(bar);
  // 采集纯净模式：⚙ 按钮 3 秒无鼠标活动自动淡出，移动鼠标即重现（面板展开时不淡出）。
  gear.style.transition='opacity .45s';let gearTimer=0;
  const showGear=v=>{gear.style.opacity=v?'1':'0';gear.style.pointerEvents=v?'auto':'none'};
  const idleGear=()=>{if(panel.style.display!=='none')return;showGear(false)};
  window.addEventListener('mousemove',()=>{showGear(true);clearTimeout(gearTimer);gearTimer=setTimeout(idleGear,3000)});
  bar.addEventListener('mouseleave',idleGear);
  gearTimer=setTimeout(idleGear,3000);
  // 直播采集纯净画面：隐藏左上角 AI 背景角标与 LIVE PREVIEW 角标，只留 3D 渲染本身。
  generatedStatus.style.display='none';
  const lv=document.querySelector('.canvas .live');if(lv)lv.style.display='none';
  document.querySelectorAll('.canvas .overlay').forEach(o=>o.style.display='none');
}
