// 打印引擎：成品几何、队列、逐层挤出、出分转运、画质与输出尺寸
// 本片段由 scripts/build-display.mjs 按顺序拼入同一模块作用域。
const products=[];let currentProduct=null,phase='idle',elapsed=0,active=null,last=performance.now(),beltOffset=0,loadId=0;
function createProduct(v){let g=new THREE.Group();scene.add(g);g.position.set(.25,0,-.05);let plane=new THREE.Plane(new THREE.Vector3(0,-1,0),.6);const tier=v.score>=90?3:v.score>=80?2:v.score>=70?1:0;
let porcelain=new THREE.MeshPhysicalMaterial({color:[0x98623a,0xc6d0d6,0x252b2c,0xefebe0][tier],metalness:[0,.85,.12,.05][tier],roughness:[.38,.24,.2,.22][tier],clearcoat:[.5,.35,.7,.8][tier],clippingPlanes:[plane]});
if(tier===0){porcelain.map=wood.clone();porcelain.map.needsUpdate=true;porcelain.color.set(0xffffff)}
if(tier===1){porcelain.bumpMap=grain;porcelain.bumpScale=.002}
if(tier>=2){porcelain.bumpMap=grain;porcelain.bumpScale=.001}
box(1.75,.12,.85,0,.64,0,porcelain,g);let stand=box(1.52,.55,.58,0,.91,-.02,porcelain,g);stand.rotation.x=-.16;// Raised medallion: machined edge, inset portrait and convex clear resin.
let rimMat=new THREE.MeshPhysicalMaterial({color:[0xb87843,0xdce4e9,0xc3cbd0,0xeac16b][tier],metalness:1,roughness:[.2,.12,.1,.14][tier],envMapIntensity:2.4,clearcoat:1,clearcoatRoughness:.06,clippingPlanes:[plane]});
let frameBody=mesh(new THREE.CylinderGeometry(tier===2?.735:.69,tier===2?.735:.69,.22,tier===2?8:96),rimMat,g);frameBody.rotation.x=Math.PI/2;frameBody.position.set(0,1.7,-.14);
if(tier===0){torus(.68,.025,0,1.7,.012,porcelain,g)}
if(tier===1){for(let i=0;i<32;i++){let a=i*Math.PI/16;let notch=box(.014,.035,.025,Math.cos(a)*.674,1.7+Math.sin(a)*.674,.012,rimMat,g);notch.rotation.z=a-Math.PI/2}}
if(tier===3){torus(.705,.018,0,1.7,.014,rimMat,g);box(1.72,.045,.78,0,.72,0,rimMat,g);for(let x of [-.7,.7])box(.07,.42,.57,x,.93,-.02,rimMat,g)}
if(tier===2){let lower=mesh(new THREE.CylinderGeometry(.86,.88,.12,8),porcelain,g);lower.scale.z=.48;lower.position.y=.66}

let insetMat=new THREE.MeshStandardMaterial({color:0x292c30,metalness:.55,roughness:.35,clippingPlanes:[plane]});
torus(.635,.025,0,1.7,-.012,insetMat,g);torus(.672,.018,0,1.7,-.002,rimMat,g);torus(.665,.014,0,1.7,-.252,rimMat,g);
let avatarMat=new THREE.MeshStandardMaterial({color:0xffffff,roughness:.85,metalness:0,envMapIntensity:.25,emissive:0xffffff,emissiveIntensity:.16,clippingPlanes:[plane]});
// Radially curved UV surface preserves the full image while catching light like a badge.
const segments=96,rings=18,positions=[],uvs=[],indices=[],radius=.607;
for(let r=0;r<=rings;r++){let rr=r/rings;for(let j=0;j<=segments;j++){let angle=j/segments*Math.PI*2,px=Math.cos(angle)*rr,py=Math.sin(angle)*rr;positions.push(px*radius,py*radius,.065*(1-rr*rr));uvs.push(.5+px*.5,.5+py*.5)}}
for(let r=0;r<rings;r++)for(let j=0;j<segments;j++){let a=r*(segments+1)+j,b=a+segments+1;indices.push(a,b,a+1,b,b+1,a+1)}
let portraitGeo=new THREE.BufferGeometry();portraitGeo.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));portraitGeo.setAttribute('uv',new THREE.Float32BufferAttribute(uvs,2));portraitGeo.setIndex(indices);portraitGeo.computeVertexNormals();
let face=mesh(portraitGeo,avatarMat,g);face.position.set(0,1.7,.006);
// Solid convex cover glass: refraction, Fresnel reflections and a polished rim.
let coverGeometry=portraitGeo.clone();let coverPositions=coverGeometry.attributes.position;
for(let i=0;i<coverPositions.count;i++){let x=coverPositions.getX(i),y=coverPositions.getY(i);let rr=Math.min(1,(x*x+y*y)/(radius*radius));coverPositions.setZ(i,.018+.125*(1-rr))}coverPositions.needsUpdate=true;coverGeometry.computeVertexNormals();
let glassMat=new THREE.MeshPhysicalMaterial({color:0xffffff,metalness:0,roughness:.025,transmission:0,transparent:true,opacity:.12,ior:1.5,specularIntensity:1,envMapIntensity:2.2,clearcoat:1,clearcoatRoughness:.012,depthWrite:false,clippingPlanes:[plane]});
let cover=mesh(coverGeometry,glassMat,g);cover.position.set(0,1.7,.018);cover.castShadow=false;cover.receiveShadow=false;
const glassEdgeMat=new THREE.MeshPhysicalMaterial({color:0xe8f4f2,metalness:0,roughness:.055,transmission:.85,thickness:.035,ior:1.5,envMapIntensity:1.6,clearcoat:1,clearcoatRoughness:.03,depthWrite:false,clippingPlanes:[plane]});
let glassEdge=torus(.607,.012,0,1.7,.036,glassEdgeMat,g);glassEdge.castShadow=false;glassEdge.receiveShadow=false;
// A brief softbox reflection sweeps across the convex glass on completion.
const glintMaterial=new THREE.ShaderMaterial({transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,toneMapped:false,uniforms:{sweep:{value:-1.4},strength:{value:0}},vertexShader:`varying vec2 glassUv;void main(){glassUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`,fragmentShader:`varying vec2 glassUv;uniform float sweep;uniform float strength;void main(){vec2 p=glassUv*2.0-1.0;float edge=1.0-smoothstep(.91,1.0,length(p));float d=abs(p.x+p.y*.38-sweep);float core=exp(-d*d/0.0018);float glow=exp(-d*d/0.022);float a=(core*.5+glow*.16)*edge*strength;gl_FragColor=vec4(vec3(.91,.97,1.0),a);}`});
let glint=mesh(coverGeometry.clone(),glintMaterial,g);glint.position.set(0,1.7,.022);glint.castShadow=glint.receiveShadow=false;glint.visible=false;glint.renderOrder=4;
// A small bevel under the portrait and a stepped plinth give the object weight.
box(1.58,.055,.72,0,.726,.005,porcelain,g);box(1.7,.035,.8,0,.572,0,porcelain,g);box(.48,.14,.22,0,1.15,-.14,porcelain,g);
let labelTex=texture(1024,420,(c,w,h)=>{c.fillStyle=tier===2?'#242a2b':'#f5efe3';c.fillRect(0,0,w,h);c.fillStyle=tier===2?'#fff4dc':'#181b1b';c.textAlign='center';const name=v.name;let font=94;do{c.font='800 '+font+'px "Microsoft YaHei",sans-serif';if(c.measureText(name).width<w-60)break;font-=2}while(font>28);c.fillText(name,w/2,119);c.globalAlpha=.3;c.fillRect(44,148,w-88,3);c.globalAlpha=1;c.font='900 194px "Microsoft YaHei",sans-serif';c.fillText(v.score+'分',w/2,345)});labelTex.anisotropy=renderer.capabilities.getMaxAnisotropy();let label=mesh(new THREE.PlaneGeometry(1.46,.58),new THREE.MeshStandardMaterial({map:labelTex,roughness:.42,metalness:.05,clippingPlanes:[plane]}),g);label.position.set(0,.95,.325);label.rotation.x=-.16;
let entry={g,plane,avatarMat,labelTex,glint,glintAge:null,disposed:false};const applyAvatar=tex=>{if(entry.disposed){tex.dispose();return}tex.colorSpace=THREE.SRGBColorSpace;tex.anisotropy=renderer.capabilities.getMaxAnisotropy();tex.minFilter=THREE.LinearMipmapLinearFilter;tex.magFilter=THREE.LinearFilter;tex.generateMipmaps=true;avatarMat.map=tex;avatarMat.emissiveMap=tex;avatarMat.color.set('#ffffff');avatarMat.needsUpdate=true};new THREE.TextureLoader().load(v.avatar||fallbackAvatar(v.name),applyAvatar,undefined,()=>{ // 头像媒体缺失（用户设置的 avatar 没落到 /media/）时，回退到首字徽章而非白板，并记入缺失资源提示
 if(v.avatar){markMissingAsset(v.avatar)} new THREE.TextureLoader().load(fallbackAvatar(v.name),applyAvatar)});return entry}
function disposeProduct(p){p.disposed=true;p.g.removeFromParent();p.g.traverse(o=>{if(o.isMesh||o.isLineSegments){o.geometry.dispose();if(o.material.map&&o.material.map!==wood&&o.material.map!==grain)o.material.map.dispose();o.material.dispose()}})}
let autoDemo=true;let lastDemoFill=0;function replenishDemo(force){if(!autoDemo||paused||busy||queue.length||!demoPeople.length)return;if(typeof pcSettings!=='undefined'&&pcSettings&&pcSettings.live&&pcSettings.live.demoFill===false)return;const demoGap=Number(printRules.demoGapMs);if(!force&&(demoGap===0||(lastDemoFill&&Date.now()-lastDemoFill<demoGap)))return;lastDemoFill=Date.now();const person=randomPerson();queue.push({...person,size:Math.random()<.3?'large':'small',priority:false,source:'自动演示',copy:1,total:1});renderQueue();updateScreen()}
function idleTestFill(){if(!printRules.idleFill||paused||!demoPeople.length||queue.length>=2||Date.now()-lastLiveMsgAt<printRules.idleSeconds*1000)return;if(typeof pcSettings!=='undefined'&&pcSettings&&pcSettings.live&&pcSettings.live.demoFill===false)return;lastLiveMsgAt=Date.now();liveEvent('like',randomPerson(),1,null,'30秒无互动·测试头像',false)}
function preemptForGift(){
 if(paused||!busy||active?.priority||!queue[0]?.priority)return;
 if(phase==='printing'){
  let at=queue.findIndex(job=>!job.priority);if(at<0)at=queue.length;
  queue.splice(at,0,active);
  if(currentProduct)disposeProduct(currentProduct);
 }else if(currentProduct&&!products.includes(currentProduct)){
  scene.attach(currentProduct.g);currentProduct.g.rotation.set(0,0,0);
  currentProduct.g.position.set(.25,.57*(1-currentProduct.factor)-.105,3.2);
  products.push(currentProduct);
 }
 currentProduct=null;transferState=null;active=null;busy=false;phase='idle';elapsed=0;lastPct=-1;articulateArm(0);
}
function showHud(job){const hud=$('hud');if(!hud)return;if(!job){hud.hidden=true;return;}
  $('hud-name').textContent=job.name||'';
  $('hud-source').textContent=job.scripted?'剧本播放':(job.live?'直播互动':'演示');
  $('hud-speech').textContent=job.speech||'';
  const raw=Array.isArray(job.tags)?job.tags:(job.tags?String(job.tags).split(';').map(s=>s.trim()).filter(Boolean):[]);
  const box=$('hud-tags');box.innerHTML='';raw.forEach(t=>{const s=document.createElement('span');s.className='hud-tag';s.textContent=t;box.append(s)});
  const meta=[];if(job.packTitle)meta.push(job.packTitle);if(job.index!=null)meta.push('第 '+(job.index+1)+' 位');
  $('hud-meta').textContent=meta.join(' · ');hud.hidden=false;}
function hideHud(){const hud=$('hud');if(hud)hud.hidden=true;}
function next(){if(autoDemo)replenishDemo();if(paused||busy||!queue.length){if(!paused&&!busy&&!queue.length)hideHud();return;}busy=true;active=queue.shift();active.score=60+Math.floor(Math.random()*36);currentProduct=createProduct(active);currentProduct.factor=active.size==='large'?(active.priority||String(active.source||'').startsWith('礼物')?1.6:1.35):1;currentProduct.g.scale.setScalar(currentProduct.factor);currentProduct.g.position.y=.57*(1-currentProduct.factor);prepareFilament(currentProduct);machineAudio.cue('start');giftSpeech.printing(active.name);phase='printing';elapsed=0;renderQueue();$('currentName').textContent=active.name;{const ci=$('currentImg');ci.onerror=()=>{ci.onerror=null;ci.src=fallbackAvatar(active.name)};ci.src=active.avatar||fallbackAvatar(active.name);}$('score').textContent='打印中';showHud(active);updateScreen()}
let liveWindow=null;
function setSceneDetached(detached){
 stage.style.display=detached?'none':'';
 liveButton.textContent=detached?'显示独立画面':'弹出画面';
 const status=document.getElementById('room-open-status');
 if(status)status.textContent=detached?'画面已移至独立窗口，主程序继续控制。关闭弹窗可恢复画面。':'画面已回到主程序。';
}

let cameraSaveTimer=0;let smoothMode=true;try{smoothMode=localStorage.getItem('printer-smooth')!=='off'}catch(e){}let renderScaleLimit=Infinity,perfFrames=0,perfStart=performance.now(),renderFps=0;
const frameRates=[24,30,60,90,120];let targetFps=60;try{const saved=Number(localStorage.getItem('printer-target-fps'));if(frameRates.includes(saved))targetFps=saved}catch(e){}
const outputSizes={landscape:[1280,720],'landscape-1080p':[1920,1080],portrait:[720,1280],'portrait-1080p':[1080,1920]};
let outputOrient='landscape';try{outputOrient=localStorage.getItem('printer-orient')||outputOrient}catch(e){}
if(!outputSizes[outputOrient])outputOrient='landscape';
function resizeRenderSurface(){const [w,h]=outputSizes[outputOrient];sceneOutput.configure(w,h,qualityLevel,aaMode,smoothMode?renderScaleLimit:Infinity);renderer.domElement.style.objectFit='contain';}
function resize(){const [w,h]=outputSizes[outputOrient];if(camera.aspect!==w/h){camera.aspect=w/h;camera.updateProjectionMatrix()}resizeRenderSurface()}
window.addEventListener('resize',resize);resize();
const outputTools=document.createElement('div');outputTools.style.cssText='display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:12px 20px;border-top:1px solid #292f3b';
const liveButton=document.createElement('button');liveButton.textContent='弹出画面';
const advancedButton=document.createElement('button');advancedButton.textContent='高级画质设置';advancedButton.className='secondary';advancedButton.setAttribute('aria-expanded','false');
outputTools.append(liveButton,advancedButton);const restartButton=document.createElement('button');
const topRestartButton=document.createElement('button');topRestartButton.id='restart-program-top';
const restartButtons=[restartButton,topRestartButton];
async function restartProgram(){
 if(!window.pywebview?.api){alert('请从桌面快捷方式打开程序后使用完整重启。');return}
 restartButtons.forEach(b=>{b.disabled=true;b.textContent='正在重启…'});
 try{await window.pywebview.api.restart_program()}catch(e){restartButtons.forEach(b=>{b.disabled=false;b.textContent='重启整个程序'});alert('重启失败：'+e.message)}
}
restartButtons.forEach(b=>{b.type='button';b.textContent='重启整个程序';b.className='secondary';b.title='关闭并重新启动整个程序，当前打印进度会重置';b.onclick=restartProgram});
outputTools.append(restartButton);
const topActions=document.createElement('div');topActions.style.cssText='display:flex;align-items:center;justify-content:flex-end;gap:10px;flex-wrap:wrap';
const modeBadge=document.getElementById('mode');modeBadge.before(topActions);topActions.append(topRestartButton,modeBadge);
stage.after(outputTools);
const outputSettings=document.createElement('div');outputSettings.hidden=true;outputSettings.style.cssText='padding:14px 20px;background:#141922;border-top:1px solid #292f3b';outputTools.after(outputSettings);
const sizeLabel=document.createElement('label');sizeLabel.textContent='输出分辨率 / 方向　';
const sizeSelect=document.createElement('select');sizeSelect.id='output-resolution';sizeSelect.style.cssText=qualitySelect.style.cssText;
for(const [value,label] of [['landscape','横屏 1280×720'],['landscape-1080p','横屏 1920×1080'],['portrait','竖屏 720×1280'],['portrait-1080p','竖屏 1080×1920']]){const o=document.createElement('option');o.value=value;o.textContent=label;sizeSelect.append(o)}
sizeSelect.value=outputOrient;sizeLabel.append(sizeSelect);
const qualityLabel=document.createElement('label');qualityLabel.textContent='渲染精细度　';qualityLabel.style.cssText='display:inline-flex;align-items:center;gap:8px;margin:8px 16px';qualityLabel.append(qualitySelect);const aaLabel=document.createElement('label');aaLabel.textContent='抗锯齿　';aaLabel.style.cssText=qualityLabel.style.cssText;aaLabel.append(aaButton);outputSettings.append(sizeLabel,qualityLabel,aaLabel);
const visualPresets={low:{label:'低画质 · 流畅优先',key:'lite',aa:'off',description:'原生分辨率，关闭反射与阴影。'},standard:{label:'标准画质 · 均衡',key:'1',aa:'msaa2',description:'原生分辨率，MSAA 2×，基础反射和阴影。'},high:{label:'高画质 · 推荐',key:'2',aa:'msaa4',description:'1.25× 内部渲染，MSAA 4×，精细反射。'},ultra:{label:'超高画质 · 精细',key:'4',aa:'msaa4',description:'1.5× 内部渲染，MSAA 4×，更精细阴影；开销更高。'}};
const presetLabel=document.createElement('label');presetLabel.textContent='画质预设　';presetLabel.style.cssText=qualityLabel.style.cssText;
const presetSelect=document.createElement('select');presetSelect.id='visual-preset';presetSelect.style.cssText=qualitySelect.style.cssText;
for(const [value,preset] of Object.entries(visualPresets)){const option=document.createElement('option');option.value=value;option.textContent=preset.label;presetSelect.append(option)}
const customOption=document.createElement('option');customOption.value='custom';customOption.textContent='自定义';customOption.disabled=true;presetSelect.append(customOption);
presetLabel.append(presetSelect);outputSettings.prepend(presetLabel);
const presetDescription=document.createElement('p');presetDescription.style.cssText='margin:8px 0;color:#9fc3e8;font-size:12px';outputSettings.append(presetDescription);
function syncVisualPreset(){const match=Object.entries(visualPresets).find(([,p])=>p.key===qualityKey&&p.aa===aaMode);presetSelect.value=match?match[0]:'custom';presetDescription.textContent=match?match[1].description:'自定义画质：保留你选择的渲染倍数和抗锯齿设置。'}
presetSelect.onchange=()=>{const preset=visualPresets[presetSelect.value];if(!preset)return;qualityKey=preset.key;aaMode=preset.aa;applyQuality();applyAA();syncVisualPreset()};
syncVisualPreset();
const fpsLabel=document.createElement('label');fpsLabel.textContent='目标帧率　';fpsLabel.style.cssText=qualityLabel.style.cssText;
const fpsSelect=document.createElement('select');fpsSelect.id='target-fps';fpsSelect.style.cssText=sizeSelect.style.cssText;
for(const fps of frameRates){const option=document.createElement('option');option.value=String(fps);option.textContent=fps+' FPS';fpsSelect.append(option)}
fpsSelect.value=String(targetFps);fpsLabel.append(fpsSelect);outputSettings.append(fpsLabel);
const smoothLabel=document.createElement('label');smoothLabel.style.cssText='display:flex;align-items:center;gap:8px;margin:10px 0';
const smoothToggle=document.createElement('input');smoothToggle.type='checkbox';smoothToggle.checked=smoothMode;smoothToggle.style.cssText='width:18px;height:18px;margin:0';
smoothLabel.append(smoothToggle,document.createTextNode('流畅优先：掉帧时降低超采样，反射最高 30 FPS'));outputSettings.append(smoothLabel);
smoothToggle.onchange=()=>{smoothMode=smoothToggle.checked;renderScaleLimit=Infinity;perfFrames=0;perfStart=performance.now();try{localStorage.setItem('printer-smooth',smoothMode?'on':'off')}catch(e){}resizeRenderSurface()};
const renderNote=document.createElement('p');renderNote.style.cssText='font-size:12px;color:#9fc3e8;margin:8px 0';outputSettings.append(renderNote);
const captureCompatButton=document.createElement('button');captureCompatButton.className='secondary';captureCompatButton.textContent='开启捕获兼容模式并重启';captureCompatButton.style.cssText='margin:8px 0';
const captureCompatNote=document.createElement('p');captureCompatNote.style.cssText='font-size:12px;color:#9fb3c8;line-height:1.6';captureCompatNote.textContent='小窗已使用独立进程和独立浏览器配置。直播伴侣请优先添加“窗口捕获”，重新选择“直播小窗 · printcast”；旧素材需重新选择窗口。仍黑屏时可尝试软件兼容模式，会重启且降低性能。';
let captureCompatEnabled=false;
async function syncCaptureCompatibility(){if(!window.pywebview?.api)return;try{captureCompatEnabled=await window.pywebview.api.get_capture_compatibility();captureCompatButton.textContent=captureCompatEnabled?'关闭捕获兼容模式并重启':'开启捕获兼容模式并重启'}catch(e){}}
window.addEventListener('pywebviewready',syncCaptureCompatibility);syncCaptureCompatibility();
captureCompatButton.onclick=async()=>{if(!window.pywebview?.api){captureCompatNote.textContent='请从桌面快捷方式打开程序使用兼容模式。';return}captureCompatButton.disabled=true;try{await window.pywebview.api.set_capture_compatibility(!captureCompatEnabled);captureCompatButton.textContent='正在重启…'}catch(e){captureCompatButton.disabled=false;captureCompatNote.textContent='设置失败，请先重启整个程序加载新版功能：'+e.message}};
outputSettings.append(captureCompatButton,captureCompatNote);

function measureRender(now){perfFrames++;if(now-perfStart<3000)return;renderFps=perfFrames*1000/(now-perfStart);perfFrames=0;perfStart=now;if(smoothMode&&(!document.hidden||mirrorConnected)){const ratio=sceneOutput.scale,next=nextRenderScale(ratio,renderFps,targetFps);if(next<ratio){renderScaleLimit=next;resizeRenderSurface()}}renderNote.textContent='主渲染 '+Math.round(renderFps)+' FPS · 当前内部倍率 '+sceneOutput.scale.toFixed(2)+'× · 内部 '+sceneOutput.target.width+'×'+sceneOutput.target.height+' · MSAA '+sceneOutput.samples+'×';}

fpsSelect.onchange=async()=>{targetFps=Number(fpsSelect.value);nextRenderAt=0;try{localStorage.setItem('printer-target-fps',String(targetFps))}catch(e){}fpsNote.textContent='目标 '+targetFps+' FPS，等待实际帧率更新…';fpsSelect.disabled=true;try{if(viewPC)for(const sender of viewPC.getSenders()){const params=sender.getParameters();if(params.encodings?.length){params.encodings[0].maxFramerate=targetFps;await sender.setParameters(params)}}}catch(e){fpsNote.textContent='渲染帧率已更新，传输设置失败，请关闭并重新打开弹窗。'}finally{fpsSelect.disabled=false}};

const outputHelp=document.createElement('p');outputHelp.textContent='倍数提高内部渲染精度，让边缘更细腻，不改变输出分辨率，也不代表清晰度成倍增加。4×、8× 占用显卡较高。设置立即生效并自动保存。弹出后主程序收起画面，关闭弹窗后恢复。OBS 选择「直播小窗 · printcast」。声音继续由主窗口播放。帧率为目标上限，实际受屏幕刷新率、显卡性能和画质设置影响。';outputHelp.style.cssText='margin-top:12px;font-size:12px';outputSettings.append(outputHelp);const fpsNote=document.createElement('p');fpsNote.id='output-fps';fpsNote.style.cssText='margin-top:8px;font-size:12px;color:#9fc3e8';fpsNote.textContent='弹窗目标 '+targetFps+' FPS，打开弹窗后显示实际解码帧率。';outputSettings.append(fpsNote);
advancedButton.onclick=()=>{outputSettings.hidden=!outputSettings.hidden;advancedButton.setAttribute('aria-expanded',String(!outputSettings.hidden))};
sizeSelect.onchange=()=>{outputOrient=sizeSelect.value;try{localStorage.setItem('printer-orient',outputOrient)}catch(e){}resize();const [w,h]=outputSizes[outputOrient];if(window.pywebview?.api){sceneChan?.postMessage({type:'view-size',width:w,height:h})}else if(liveWindow&&!liveWindow.closed){try{liveWindow.resizeTo(w+liveWindow.outerWidth-liveWindow.innerWidth,h+liveWindow.outerHeight-liveWindow.innerHeight)}catch(e){}}};
async function openLiveView(){
 const st=$('room-open-status');
 let orient='landscape';try{orient=localStorage.getItem('printer-orient')||orient}catch(e){}
 if(window.pywebview?.api){try{st.textContent=await window.pywebview.api.open_scene_window('/live-view.html?scene=1',orient)}catch(e){st.textContent=e.message}return}
 if(liveWindow&&!liveWindow.closed){liveWindow.focus();return}
 const [popupWidth,popupHeight]=outputSizes[outputOrient];
 liveWindow=window.open('./live-view.html','avatar-printer-live','popup=yes,width='+popupWidth+',height='+popupHeight+',resizable=yes,scrollbars=no');
 st.textContent=liveWindow?'正在打开独立画面，连接成功后主程序将收起画面。OBS 请选择「直播小窗 · printcast」。':'弹窗被拦截，请允许本站弹窗后重试。';
}
liveButton.onclick=openLiveView;
function requestSceneFrame(callback){window.requestAnimationFrame(callback)}
machineAudio.isHidden=()=>document.hidden&&!mirrorConnected;
// Accelerated FDM preview: discrete layers, perimeter toolpath and deposited filament.
let simulationSpeed=4;const printDuration=12,layerCount=72;
function layerPath(layer){let y=.58+(layer+1)/layerCount*1.85;let halfWidth,front,back;
if(y<.73){halfWidth=.84;front=.4;back=-.42}else if(y<1.18){halfWidth=.74;front=.25;back=-.3}else{halfWidth=Math.sqrt(Math.max(.0001,.69*.69-(y-1.7)*(y-1.7)));front=-.015;back=-.24}
const corners=[[-halfWidth,front],[halfWidth,front],[halfWidth,back],[-halfWidth,back],[-halfWidth,front]];let points=[];
for(let i=0;i<4;i++){let a=corners[i],b=corners[i+1];for(let n=0;n<24;n++){let f=n/24;points.push(new THREE.Vector3(.25+a[0]+(b[0]-a[0])*f,y,-.05+a[1]+(b[1]-a[1])*f))}}
points.push(points[0].clone());return points}
function prepareFilament(p){let points=[];p.paths=[];for(let layer=0;layer<layerCount;layer++){let path=layerPath(layer);p.paths.push(path);for(let i=0;i<path.length-1;i++){points.push(path[i].x-.25,path[i].y,path[i].z+.05,path[i+1].x-.25,path[i+1].y,path[i+1].z+.05)}}let geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.Float32BufferAttribute(points,3));geo.setDrawRange(0,0);let line=new THREE.LineSegments(geo,new THREE.LineBasicMaterial({color:0xb9b4a6,transparent:true,opacity:.48}));p.g.add(line);p.filament=line;
p.bead=mesh(new THREE.SphereGeometry(.018,12,8),new THREE.MeshStandardMaterial({color:0xe8dfcd,roughness:.7}),p.g);p.bead.scale.set(1,.5,1)}
function updateDeposition(f){let step=Math.min(layerCount-.0001,f*layerCount),layer=Math.floor(step),fraction=step-layer;let path=currentProduct.paths[layer],index=fraction*(path.length-1),i=Math.floor(index);let pos=path[i].clone().lerp(path[Math.min(i+1,path.length-1)],index-i);currentProduct.plane.constant=currentProduct.g.position.y+(.58+layer/layerCount*1.85)*currentProduct.factor;
currentProduct.filament.geometry.setDrawRange(0,(layer*96+Math.floor(index))*2);currentProduct.bead.position.set(pos.x-.25,pos.y,pos.z+.05);gantry.position.y=currentProduct.g.position.y+pos.y*currentProduct.factor+.715;head.position.x=.25+(pos.x-.25)*currentProduct.factor;head.position.z=-.05+(pos.z+.05)*currentProduct.factor-.04;fan.rotation.z+=.5;}
function updateEffects(dt){if(!fxEnabled)return;const all=new Set(products);if(currentProduct)all.add(currentProduct);for(const p of all){if(p.glintAge===null||!p.glint)continue;if(!paused)p.glintAge+=dt;const f=Math.min(p.glintAge/1.15,1);p.glint.visible=f<1;p.glint.material.uniforms.sweep.value=-1.45+f*2.9;p.glint.material.uniforms.strength.value=Math.sin(Math.PI*f);if(f>=1){p.glintAge=null;p.glint.visible=false}}}
let lastGlintTime=performance.now();
let animScheduled=false;function requestAnimate(){if(animScheduled)return;animScheduled=true;requestSceneFrame(t=>{animScheduled=false;animate(t)})}
window.printerDiagnostics=()=>({camera:camera.position.toArray(),target:controls.target.toArray(),fps:renderFps,output:[renderer.domElement.width,renderer.domElement.height],internal:[sceneOutput.target.width,sceneOutput.target.height],samples:sceneOutput.samples,aa:aaMode,connected:viewPC?.connectionState,rendererCount:document.querySelectorAll('#stage canvas').length});
