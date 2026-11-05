// 运行时：场景模式 / 多窗口选主 / WebRTC 镜像 / 资源降级 / 设置入口
// 本片段由 scripts/build-display.mjs 按顺序拼入同一模块作用域。
const SCENE_MODE=/[?&]scene\b/.test(location.search);
if(SCENE_MODE)document.body.classList.add('scene-only');


const sceneChan=new SceneChannel();
let viewPC=null,viewStream=null,lastViewSeen=0,pendingViewIce=[];
function closeViewConnection(){viewPC?.close();viewPC=null;viewStream?.getTracks().forEach(t=>t.stop());viewStream=null;pendingViewIce=[];}
setInterval(()=>{if(mirrorConnected&&Date.now()-lastViewSeen>12000){closeViewConnection();mirrorConnected=false;setSceneDetached(false);updateYieldNote()}},3000);
const peerSid=Date.now().toString(36)+Math.random().toString(36).slice(2,7),peerBorn=Date.now(),peers=new Map();
function peerRank(p){return p.born-(p.scene?1e12:0)}
function myRank(){return peerBorn-(SCENE_MODE?1e12:0)}
function iAmLeader(){const now=Date.now();for(const[sid,p]of[...peers]){if(now-p.t>6000){peers.delete(sid);continue}if(peerRank(p)<myRank()||(peerRank(p)===myRank()&&sid<peerSid))return false}return true}
function printAllowed(){return iAmLeader()}
let mirrorConnected=false;
// —— 可选素材缺失降级（M2）——
// 仓库只入库几何与代码；约 33MB 的 AI 生图贴图 / 音频需 scripts/vendor-assets.sh 还原。
// 缺文件时保持纯色材质与静音，不因 404 黑屏，也不把误导性的「请重启服务」推给用户。
const missingAssets=new Set();
const assetStatus=document.createElement('div');
assetStatus.setAttribute('role','status');
assetStatus.style.cssText='position:fixed;left:12px;bottom:12px;z-index:80;display:none;max-width:min(460px,calc(100vw - 24px));color:#ffd9a8;background:#26332be6;border:1px solid #55604a;border-radius:6px;padding:7px 10px;font-size:11px;line-height:1.6';
document.body.append(assetStatus);
function markMissingAsset(name){
  if(SCENE_MODE)return; // OBS 采集的独立场景窗口保持画面干净
  missingAssets.add(name);
  assetStatus.style.display='block';
  assetStatus.textContent='可选素材缺失（'+[...missingAssets].join('、')+'）：已降级为纯色材质 / 静音，3D 打印仍可用。还原：bash scripts/vendor-assets.sh';
}

function updateYieldNote(){const el=document.getElementById('yield-note');if(!el)return;let t='';
if(mirrorConnected)t+='📺 画面已移至独立窗口：OBS 直接抓取该窗口';
if(!SCENE_MODE&&peers.size)t+=(t?'；':'')+'🎬 另一打印窗口接管打印中：本窗口只计数，不重复打印';
el.textContent=t}
if(sceneChan){sceneChan.onmessage=ev=>{const m=ev.data||{};
if(m&&m.type==='who'&&m.sid&&m.sid!==peerSid){peers.set(m.sid,{t:Date.now(),born:m.born,scene:!!m.scene});updateYieldNote()}
else if(m&&m.type==='view-request'&&iAmLeader()){lastViewSeen=Date.now();
  (async()=>{try{
    if(viewPC){try{viewPC.close()}catch(e){}viewPC=null}
    if(!viewStream){viewStream=renderer.domElement.captureStream(0);viewStream.getVideoTracks().forEach(t=>t.contentHint='detail')}
    pendingViewIce=[];viewPC=new RTCPeerConnection();const inputChannel=viewPC.createDataChannel('controls',{ordered:false,maxRetransmits:0});inputChannel.onmessage=e=>{try{const m=JSON.parse(e.data);if(m.type==='view-camera-change')sceneChan.onmessage({data:m})}catch(e){}};
    viewStream.getVideoTracks().forEach(t=>{try{viewPC.addTrack(t,viewStream)}catch(e){}});
    viewPC.onicecandidate=e=>{if(e.candidate)try{sceneChan.postMessage({type:'view-ice',candidate:{candidate:e.candidate.candidate,sdpMid:e.candidate.sdpMid,sdpMLineIndex:e.candidate.sdpMLineIndex}})}catch(e){}};
    for(const sender of viewPC.getSenders()){const params=sender.getParameters();if(!params.encodings?.length)params.encodings=[{}];params.encodings[0].scaleResolutionDownBy=1;params.encodings[0].maxBitrate=40000000;params.encodings[0].maxFramerate=targetFps;params.degradationPreference='maintain-resolution';try{await sender.setParameters(params)}catch(e){}}
    const codecs=RTCRtpSender.getCapabilities?.('video')?.codecs||[];const preferred=codecs.filter(c=>c.mimeType.toLowerCase()==='video/h264');if(preferred.length)for(const transceiver of viewPC.getTransceivers())transceiver.setCodecPreferences([...preferred,...codecs.filter(c=>!preferred.includes(c))]);
    const offer=await viewPC.createOffer();await viewPC.setLocalDescription(offer);
    mirrorConnected=true;lastViewSeen=Date.now();updateYieldNote();
    try{sceneChan.postMessage({type:'view-offer',sdp:{type:offer.type,sdp:offer.sdp}})}catch(e){}
  }catch(e){console.warn('[view]',e)}})();
}
else if(m&&m.type==='view-stats'){const el=document.getElementById('output-fps');if(el)el.textContent='目标 '+targetFps+' FPS · 实际解码：'+m.fps+' FPS · '+m.width+'×'+m.height}
else if(m&&m.type==='view-camera-request'){sceneChan.postMessage({type:'view-camera',p:camera.position.toArray(),t:controls.target.toArray(),fov:camera.fov})}
else if(m&&m.type==='view-camera-change'&&Array.isArray(m.p)&&Array.isArray(m.t)&&m.p.length===3&&m.t.length===3&&[...m.p,...m.t].every(Number.isFinite)){const damping=controls.enableDamping;controls.enableDamping=false;controls.update();camera.position.fromArray(m.p);controls.target.fromArray(m.t);controls.update();controls.enableDamping=damping;clearTimeout(cameraSaveTimer);cameraSaveTimer=setTimeout(()=>{try{localStorage.setItem('printer-view-last',JSON.stringify({p:camera.position.toArray(),t:controls.target.toArray()}))}catch(e){}},300)}
else if(m&&m.type==='view-answer'&&viewPC&&m.sdp){lastViewSeen=Date.now();viewPC.setRemoteDescription(m.sdp).then(async()=>{for(const c of pendingViewIce.splice(0))await viewPC.addIceCandidate(c)}).catch(()=>{})}
else if(m&&m.type==='view-ice'&&viewPC&&m.candidate){lastViewSeen=Date.now();viewPC.remoteDescription?viewPC.addIceCandidate(m.candidate).catch(()=>{}):pendingViewIce.push(m.candidate)}
else if(m&&(m.type==='view-ping'||m.type==='view-ready')){lastViewSeen=Date.now();setSceneDetached(true);if(!mirrorConnected){mirrorConnected=true;updateYieldNote()}}
else if(m&&m.type==='view-bye'){closeViewConnection();mirrorConnected=false;setSceneDetached(false);updateYieldNote()}};setInterval(()=>{try{sceneChan.postMessage({type:'who',sid:peerSid,born:peerBorn,scene:SCENE_MODE})}catch(e){}},2000);setInterval(updateYieldNote,2500)}









const $=id=>document.getElementById(id),stage=$('stage'),scene=new THREE.Scene();
// —— 控制台设置（展示端只读，不写）：由 /__api/settings 提供品牌与打印规则，控制台优先。——
let pcSettings=null;
function mediaUrl(id){ if(!id) return ''; if(/^https?:/i.test(id)||id.charAt(0)==='/') return id; if(/\.svg$/i.test(id)) return '/avatars/'+id; return /^[a-z0-9._-]+\.(?:png|jpe?g|webp)$/i.test(id) ? '/media/'+id : id; }
const machineAudio=new PrinterAudio();
