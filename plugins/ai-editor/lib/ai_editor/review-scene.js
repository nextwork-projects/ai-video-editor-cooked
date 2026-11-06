// The edit page on a scene (SCENE.md): when GET /scene answers, the player is CookedLive.mountScene and every item on
// screen is picked, moved, resized, rotated, cropped, trimmed and deleted here, CapCut's way. Each change is made on a
// copy of the scene first (drawn at once with player.update), then sent as ops to POST /scene/ops, the diff of the scene
// before and after (one undo, its journal id `j` with the page's edPush / /timeline/restore). review.html calls SC.check()
// on every live fetch, SC.tl() for the timeline rows and SC.key() first on every key. Loaded before review.html's script:
// it only uses that script's globals ($, v, S, post, edPush, ...) once it runs.
var SC={on:false,s:null,pl:null,sel:new Set(),crop:false,edit:null,last:'',busy:0,mov:0};
{const st=document.createElement('style');st.textContent=`
body.scene #tside{display:flex}body.scene #tclose{display:none}body.scene .left{padding-left:16px;padding-right:16px}   /* the panel slot always there: a pick never moves the video */
#scl{display:none;width:100%;height:100%;background:var(--film)}body.scene #scl{display:block}body.scene #live,body.scene #v{display:none!important}
body.scene #hits,body.scene #tlayer,body.scene #tedit,body.scene #clayer,body.scene #cplayer{display:none!important}
#scover{display:none;position:absolute;left:0;top:0;transform-origin:0 0;z-index:6;touch-action:none}body.scene #scover{display:block}
.scbox{position:absolute;outline:calc(1.5px / var(--k)) solid #FFFFFF;box-shadow:0 0 0 calc(2.5px / var(--k)) rgba(0,0,0,.35);pointer-events:none}.scbox.sub{outline-style:dashed}
.scbox i{position:absolute;width:calc(12px / var(--k));height:calc(12px / var(--k));margin:calc(-6px / var(--k)) 0 0 calc(-6px / var(--k));border-radius:calc(3px / var(--k));background:#FFFFFF;box-shadow:0 0 0 calc(1px / var(--k)) rgba(0,0,0,.45);pointer-events:auto}
.scbox i::after{content:"";position:absolute;inset:calc(-6px / var(--k))}
.scbox i[data-h=nw],.scbox i[data-h=se]{cursor:nwse-resize}.scbox i[data-h=ne],.scbox i[data-h=sw]{cursor:nesw-resize}.scbox i[data-h=n],.scbox i[data-h=s]{cursor:ns-resize}.scbox i[data-h=e],.scbox i[data-h=w]{cursor:ew-resize}
.scbox i[data-h=rot]{border-radius:50%;cursor:grab}.scbox i[data-h=rot]::before{content:"";position:absolute;left:50%;top:100%;width:calc(1.5px / var(--k));height:calc(18px / var(--k));background:#FFFFFF}
.scbox i[data-h=rot].dn::before{top:auto;bottom:100%}.scbox.crop i{background:#FFD60A}.scghost{position:absolute;outline:calc(1px / var(--k)) dashed rgba(255,255,255,.6);background:rgba(0,0,0,.35);pointer-events:none}
.scg{position:absolute;background:#FF2D92;pointer-events:none}.scsz{position:absolute;left:60px;top:250px;width:880px;height:1190px;outline:calc(1px / var(--k)) dashed rgba(255,255,255,.45);pointer-events:none}
.sced{position:absolute;outline:calc(1.5px / var(--k)) solid #0A84FF;white-space:pre-wrap;overflow-wrap:anywhere;caret-color:#FFFFFF;cursor:text}
.eitem.sc{cursor:grab;overflow:visible}.eitem.sc>span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0;pointer-events:none}.eitem.sc.sel{outline:2px solid #FFFFFF;outline-offset:1px;z-index:2}
.eitem.sc::before,.eitem.sc::after{content:"";position:absolute;top:0;bottom:0;width:8px;cursor:ew-resize;z-index:2}.eitem.sc::before{left:-1px}.eitem.sc::after{right:-1px}
.eitem.sc img{height:18px;width:auto;max-width:32px;border-radius:3px;margin-right:4px;pointer-events:none}.eitem.sc.shp{background:#4A3B2A;border-color:#8A6A44;color:#FFFFFF;padding:0 6px}
.eitem.sc.cut0{border-left:3px solid #FFD60A}.sck{position:absolute;top:50%;width:7px;height:7px;margin:-3.5px 0 0 -3.5px;transform:rotate(45deg);background:#FFD60A;pointer-events:none}
.scj{position:absolute;top:0;bottom:0;width:2px;margin-left:-1px;z-index:4;background:#FFD60A;pointer-events:none}.scj::after{content:"";position:absolute;left:-5px;top:-8px;width:12px;height:16px;pointer-events:auto;cursor:help}   /* a 2 px line on each AI cut; its top end takes the hover, the edges stay free to trim */
.scj>b{display:none;position:absolute;left:-5px;top:-7px;width:12px;height:7px;border-radius:3px 3px 0 0;background:#FFD60A;pointer-events:none}.scj.t>b,.scj:hover>b{display:block}   /* the tab: on hover, or when the joins are far enough apart (zoomed in) */
.scj>span{display:none;position:fixed;font-style:normal;z-index:9;width:max-content;max-width:300px;flex-direction:column;gap:6px;padding:10px 12px;border-radius:8px;background:var(--panel);border:1px solid var(--line2);box-shadow:0 8px 24px rgba(0,0,0,.4);font-size:12px;font-weight:500;line-height:16px;color:var(--strong);white-space:normal;cursor:default}
.scj:hover>span{display:flex}.scj>span{pointer-events:auto}.scj em{font-style:normal;color:var(--muted)}.scj>span::after{content:"";position:absolute;left:0;right:0;top:100%;height:10px}.scj button{align-self:flex-start;height:28px;padding:0 10px;border-radius:7px;border:1px solid var(--line2);font-size:12px;font-weight:600;color:var(--ink)}.scj button:hover{border-color:var(--ink)}
#edtracks[data-ld="scv"] .newl[data-row="scv"],#edtracks[data-ld="sca"] .newl[data-row="sca"]{display:flex}.etrack.scdrop{outline:2px dashed var(--ink);outline-offset:-2px}
.scadd{display:flex;flex-wrap:wrap;gap:4px;padding:8px 0 0 4px}.scadd button{height:24px;padding:0 7px;white-space:nowrap;border-radius:6px;border:1px solid var(--line2);font-size:11px;font-weight:600;color:var(--body)}.scadd button:hover{border-color:var(--ink);color:var(--ink)}
.sckey{width:24px;height:24px;flex-shrink:0;border-radius:6px;display:grid;place-items:center;color:var(--muted)}.sckey::before{content:"";width:8px;height:8px;transform:rotate(45deg);border:1.5px solid currentColor}.sckey.on{color:#FFD60A}.sckey.on::before{background:currentColor}.sckey:hover{background:var(--hover)}
#ibody textarea.scta{width:100%;min-height:64px;border:1px solid var(--line2);border-radius:8px;background:var(--panel);color:var(--strong);padding:8px;font:inherit;font-size:13px;resize:vertical}
#ibody input[type=color]{width:40px;height:28px;border:1px solid var(--line2);border-radius:6px;background:none;padding:2px}`;document.head.appendChild(st)}
// ---- the scene: items, values at a time (keys), the diff that becomes ops
const scCopy=x=>JSON.parse(JSON.stringify(x));
const scAll=s=>(s||SC.s).tracks.flatMap((tr,ti)=>tr.items.map((it,ii)=>({it,tr,ti,ii})));
const scGet=id=>scAll().find(o=>o.it.id===id);
const scVis=it=>!/^(audio|captions)$/.test(it.type);
const EASE={linear:u=>u,in:u=>u*u,out:u=>1-(1-u)*(1-u),inout:u=>u<.5?2*u*u:1-2*(1-u)*(1-u),hold:()=>0};
function scVal(it,p,t){const k=it.keys&&it.keys[p];const b=p==='scale'?1:it[p]??(p==='opacity'?1:p==='rotation'?0:0);if(!k||!k.length)return b;const u=t-it.start;
  if(u<=k[0][0])return k[0][1];for(let i=1;i<k.length;i++)if(u<k[i][0]){const[a,va,e]=k[i-1],[c,vc]=k[i];return va+(vc-va)*(EASE[e]||EASE.linear)((u-a)/(c-a||1))}return k[k.length-1][1]}
// a change to an animated prop is a key at the playhead (CapCut's way); any other prop changes the item
function scSet(it,p,x,t){const k=it.keys&&it.keys[p];if(!k||!k.length){it[p]=x;return}const u=+(t-it.start).toFixed(3),f=1/(SC.s.fps||30);
  const i=k.findIndex(q=>Math.abs(q[0]-u)<f/2);if(i>=0)k[i][1]=x;else{k.push([u,x,'inout']);k.sort((a,b)=>a[0]-b[0])}}
const TXH={};function scTextH(it){const sig=[it.text,it.font,it.weight,it.size,it.w,it.line_height,(it.box||{}).pad].join('|');if(TXH[sig])return TXH[sig];
  const d=document.createElement('div');d.style.cssText=`position:absolute;visibility:hidden;left:-9999px;top:0;white-space:pre-wrap;overflow-wrap:anywhere;width:${it.w||800}px;font-family:'${it.font||'TikTok Sans'}',system-ui,sans-serif;font-weight:${it.weight||700};font-size:${it.size||64}px;line-height:${it.line_height||1.15}`;
  d.textContent=it.text||' ';document.body.appendChild(d);const h=d.offsetHeight+2*((it.box||{}).pad||0);d.remove();return TXH[sig]=h}
function scGeo(it,t){const s=scVal(it,'scale',t),w=scVal(it,'w',t)||it.w||100;return {x:scVal(it,'x',t),y:scVal(it,'y',t),w:w*s,h:(it.type==='text'?scTextH({...it,w}):scVal(it,'h',t)||100)*s,r:scVal(it,'rotation',t),s}}
const scDur=s=>Math.max(.1,...scAll(s).map(o=>o.it.end||0));
// the ops that take scene a to scene b (SCENE.md): tracks added, track fields, items added, moved, changed, removed
function scDiff(a,b){const ops=[],A={},B={};scAll(a).forEach(o=>A[o.it.id]=o);scAll(b).forEach(o=>B[o.it.id]=o);
  const ta=Object.fromEntries(a.tracks.map(t=>[t.id,t]));
  b.tracks.forEach((t,i)=>{const o=ta[t.id];if(!o)return ops.push({op:'add_track',track:{...t,items:[]},index:i});const p={};
    for(const k of new Set([...Object.keys(o),...Object.keys(t)]))if(k!=='items'&&JSON.stringify(o[k])!==JSON.stringify(t[k]))p[k]=t[k]??null;if(Object.keys(p).length)ops.push({op:'track',track:t.id,props:p})});
  for(const[k,x]of Object.entries(b.assets||{}))if(!(a.assets||{})[k])ops.push({op:'asset',id:k,asset:{src:x.src}});   // a file new to the scene: the server probes it
  for(const[id,o]of Object.entries(B)){const w=A[id];if(!w){ops.push({op:'add',track:o.tr.id,item:o.it,index:o.ii});continue}
    if(w.tr.id!==o.tr.id)ops.push({op:'move',item:id,track:o.tr.id,index:o.ii});const p={};
    for(const k of new Set([...Object.keys(w.it),...Object.keys(o.it)]))if(JSON.stringify(w.it[k])!==JSON.stringify(o.it[k]))p[k]=o.it[k]??null;
    if(Object.keys(p).length)ops.push({op:'set',item:id,props:p})}   // a set never ripples: the page moved every later item itself
  for(const id of Object.keys(A))if(!B[id])ops.push({op:'remove',item:id});
  for(const t of a.tracks)if(!b.tracks.some(x=>x.id===t.id))ops.push({op:'remove_track',track:t.id});
  return ops}
// ---- on and off: the scene from GET /scene, the player from CookedLive.mountScene
SC.check=async function(){const want=!!(S&&view&&isCur()&&S.stage==='edit'&&!S.stills&&!S.raw&&!alt&&!cmp&&!previewOn);const k=want?key(S):'';
  if(k===SC.last)return SC.on;SC.last=k;if(!want)return SC.off();
  try{const r=await fetch('/scene');const j=r.ok?await r.json():null;if(!j||!Array.isArray(j.tracks))return SC.off();SC.s=j;
    if(!window.CookedLive||!CookedLive.mountScene)await import('/live/live.js');if(!SC.pl)SC.pl=CookedLive.mountScene($('scl'),SC.s);else SC.pl.update(SC.s);
    if(!SC.on){SC.on=true;if(LV.on){LV.on=false;LV.shim&&LV.shim.pause();document.body.classList.remove('live')}document.body.classList.add('scene');v.use(SC.pl);SC.size();SC.draw();SC.insp()}
    $('edtracks')._h=null;renderEdTracks();return true}catch(e){console.warn('scene mode off:',e);return SC.off()}};
SC.off=function(){if(SC.on){SC.on=false;document.body.classList.remove('scene');v.use(null);SC.pl&&SC.pl.pause();SC.sel.clear();SC.crop=false;$('edtracks')._h=null;$('scover').innerHTML=''}return false};
SC.fetch=async function(){try{const j=await (await fetch('/scene')).json();if(j&&j.tracks){SC.s=j;SC.show()}}catch(e){}};
// the scene drawn: the player at once, the boxes, the rows, the inspector, the transcript's struck words
SC.show=function(fast){if(!SC.on)return;const s=SC.edit?scCopy(SC.s):SC.s;if(SC.edit){const o=scAll(s).find(o=>o.it.id===SC.edit);if(o)o.it.opacity=0}
  s.duration=scDur(SC.s);SC.pl.update(s);SC.draw();if(fast)return;$('edtracks')._h=null;SC.tl();SC.insp();SC.txSync()};
SC.size=function(){const o=$('scover'),r=$('scl').getBoundingClientRect(),P=o.parentElement.getBoundingClientRect(),W=SC.s.width,H=SC.s.height,k=Math.min(r.width/W,r.height/H)||1;
  SC.k=k;o.style.cssText=`width:${W}px;height:${H}px;left:${r.left-P.left+(r.width-W*k)/2}px;top:${r.top-P.top+(r.height-H*k)/2}px;transform:scale(${k});--k:${k}`};
new ResizeObserver(()=>{if(SC.on){SC.size();SC.draw()}}).observe($('scl'));
const scNow=()=>v.currentTime;
const scAt=t=>scAll().filter(o=>scVis(o.it)&&o.tr.kind==='visual'&&!o.tr.hidden&&o.it.start<=t+1e-4&&t<o.it.end);   // bottom first
function scHit(px,py,t){return scAt(t).filter(o=>{const g=scGeo(o.it,t),a=-g.r*Math.PI/180,dx=px-g.x,dy=py-g.y,lx=dx*Math.cos(a)-dy*Math.sin(a),ly=dx*Math.sin(a)+dy*Math.cos(a);
  return Math.abs(lx)<=g.w/2&&Math.abs(ly)<=g.h/2}).reverse()}   // top first
SC.draw=function(guides){if(!SC.on)return;guides=guides||SC.drag&&SC.gd;const t=scNow(),o=$('scover'),ids=[...SC.sel].filter(id=>{const q=scGet(id);return q&&scVis(q.it)&&q.it.start<=t+1e-4&&t<q.it.end});
  let h=SC.s.width===1080&&SC.s.height===1920&&SC.mov?'<div class="scsz"></div>':'';
  ids.forEach((id,n)=>{const it=scGet(id).it,g=scGeo(it,t),cr=SC.crop&&ids.length===1&&/^(video|image)$/.test(it.type),c=it.crop||{l:0,t:0,r:0,b:0};
    if(cr){const fw=g.w/Math.max(.02,1-c.l-c.r),fh=g.h/Math.max(.02,1-c.t-c.b);h+=`<div class="scghost" style="left:${g.x-g.w/2-c.l*fw}px;top:${g.y-g.h/2-c.t*fh}px;width:${fw}px;height:${fh}px;transform-origin:${g.w/2+c.l*fw}px ${g.h/2+c.t*fh}px;transform:rotate(${g.r}deg)"></div>`}
    const hs=ids.length>1?[]:it.type==='text'?['nw','ne','se','sw','e','w']:['nw','n','ne','e','se','s','sw','w'],P={nw:[0,0],n:[50,0],ne:[100,0],e:[100,50],se:[100,100],s:[50,100],sw:[0,100],w:[0,50]};
    h+=`<div class="scbox${cr?' crop':''}${n?' sub':''}" data-b="${esc(id)}" style="left:${g.x-g.w/2}px;top:${g.y-g.h/2}px;width:${g.w}px;height:${g.h}px;transform:rotate(${g.r}deg)">${hs.map(k=>`<i data-h="${k}" style="left:${P[k][0]}%;top:${P[k][1]}%"></i>`).join('')}${hs.length&&!cr?`<i data-h="rot" class="${g.y-g.h/2<30/SC.k?'dn':''}" style="left:50%;top:${g.y-g.h/2<30/SC.k?`calc(100% + 26px / var(--k))`:'calc(-26px / var(--k))'}"></i>`:''}</div>`});
  for(const[a,p]of guides||[])h+=a==='x'?`<i class="scg" style="left:${p-1/SC.k}px;top:0;width:${2/SC.k}px;height:100%"></i>`:`<i class="scg" style="top:${p-1/SC.k}px;left:0;height:${2/SC.k}px;width:100%"></i>`;
  const ed=o.querySelector('.sced');o.innerHTML=h;if(ed)o.appendChild(ed)};
v.addEventListener('timeupdate',()=>{if(SC.on&&!SC.drag)SC.draw()});v.addEventListener('seeked',()=>{if(SC.on&&!SC.drag){SC.draw();SC.insp()}});
// ---- one change: made on a copy (fn), shown at once, sent as the ops between the two
SC.commit=async function(before,what){const after=scCopy(SC.s),ops=scDiff(before,after);if(!ops.length)return;SC.busy++;
  try{const r=await post('/scene/ops',{ops});if(!r.ok)throw new Error(r.error||'That did not save.');
    edPush(what,()=>SC.send(scDiff(after,before)),()=>SC.send(scDiff(before,after)));if(r.scene&&!SC.drag)SC.s=r.scene}catch(e){toast(e.message);SC.s=before}finally{SC.busy--}SC.show()};
SC.send=async ops=>{const r=await post('/scene/ops',{ops});JQ.length=0;if(r.scene)SC.s=r.scene;SC.show()};
SC.change=function(what,fn){const b=scCopy(SC.s);fn(SC.s);SC.show();return SC.commit(b,what)};
const scId=p=>p+Math.random().toString(36).slice(2,8);
// ---- the video: press and drag moves what is under the pointer, handles resize, rotate and crop
const scPt=e=>{const r=$('scover').getBoundingClientRect();return [(e.clientX-r.left)/SC.k,(e.clientY-r.top)/SC.k]};
$('scover').addEventListener('pointerdown',e=>{if(e.button||!SC.on||e.target.closest('.sced'))return;e.preventDefault();e.stopPropagation();SC.edDone();v.pause();SC.zone='v';
  const t=scNow(),[px,py]=scPt(e),hd=e.target.closest('[data-h]');let id;SC.pick=1;
  if(hd)id=e.target.closest('[data-b]').dataset.b;
  else{const hs=scHit(px,py,t).filter(o=>!o.tr.locked&&!o.it.locked);if(!hs.length){SC.sel.clear();SC.crop=false;SC.show();return}
    const i=hs.findIndex(o=>SC.sel.has(o.it.id));id=(e.metaKey||e.ctrlKey)&&i>=0?hs[(i+1)%hs.length].it.id:i>=0&&!(e.metaKey||e.ctrlKey)?hs[i].it.id:hs[0].it.id;
    if(e.shiftKey){SC.sel.has(id)?SC.sel.delete(id):SC.sel.add(id)}else if(!SC.sel.has(id)||(e.metaKey||e.ctrlKey)){SC.sel.clear();SC.sel.add(id)}}
  const before=scCopy(SC.s),b0=scCopy(SC.s),g0={};SC.sel.forEach(k=>{const q=scGet(k);if(q)g0[k]=scGeo(q.it,t)});const G=g0[id]||scGeo(scGet(id).it,t),h=hd&&hd.dataset.h;
  if(e.altKey&&!h){const ns=[];[...SC.sel].forEach(k=>{const q=scAll(b0).find(o=>o.it.id===k);if(!q)return;const c={...scCopy(q.it),id:scId('i'),name:(q.it.name||q.it.type)+' copy'};q.tr.items.splice(q.ii+1,0,c);ns.push(c.id);g0[c.id]=g0[k]});SC.sel=new Set(ns)}   // Alt-drag: the copies move, the originals stay
  const L=!h&&(()=>{const xs=[SC.s.width/2],ys=[SC.s.height/2];if(SC.s.width===1080&&SC.s.height===1920){xs.push(60,940);ys.push(250,1440)}
    scAt(t).forEach(o=>{if(SC.sel.has(o.it.id)||g0[o.it.id])return;const g=scGeo(o.it,t);xs.push(g.x-g.w/2,g.x,g.x+g.w/2);ys.push(g.y-g.h/2,g.y,g.y+g.h/2)});return {xs,ys}})();
  let moved=false;SC.drag=1;SC.draw();
  const mv=ev=>{const[qx,qy]=scPt(ev),dx=qx-px,dy=qy-py;if(!moved&&Math.hypot(dx,dy)*SC.k<3)return;moved=true;SC.mov=1;SC.s=scCopy(b0);SC.apply(ev,dx,dy,h,G,g0,t,L,b0);SC.show(true)};
  const up=async()=>{document.removeEventListener('pointermove',mv,true);document.removeEventListener('pointerup',up,true);SC.drag=0;SC.mov=0;SC.gd=null;
    if(!moved){SC.s=before;if(e.altKey&&!h)SC.sel=new Set([id]);SC.show();return}
    await SC.commit(before,e.altKey&&!h?'copy':h==='rot'?'rotate':h?(SC.crop?'crop':'resize'):'move')};
  document.addEventListener('pointermove',mv,true);document.addEventListener('pointerup',up,true)},true);
// the drag's effect on the copy of the scene: a move (snapped), a handle, the rotate handle or a crop edge
SC.apply=function(ev,dx,dy,h,G,g0,t,L,b0){const sh=ev.shiftKey,free=ev.metaKey||ev.ctrlKey,gd=[];
  if(!h){if(!free){const th=6/SC.k,bx=[G.x-G.w/2,G.x,G.x+G.w/2],by=[G.y-G.h/2,G.y,G.y+G.h/2];let bxd=null,byd=null;
      for(const a of bx)for(const p of L.xs){const d=p-(a+dx);if(Math.abs(d)<=th&&(bxd==null||Math.abs(d)<Math.abs(bxd[0])))bxd=[d,p]}
      for(const a of by)for(const p of L.ys){const d=p-(a+dy);if(Math.abs(d)<=th&&(byd==null||Math.abs(d)<Math.abs(byd[0])))byd=[d,p]}
      if(bxd){dx+=bxd[0];gd.push(['x',bxd[1]])}if(byd){dy+=byd[0];gd.push(['y',byd[1]])}}SC.gd=gd;
    SC.sel.forEach(k=>{const q=scGet(k),g=g0[k];if(!q||!g)return;scSet(q.it,'x',Math.round(g.x+dx),t);scSet(q.it,'y',Math.round(g.y+dy),t)});SC.draw(gd);return}
  const q=scGet([...SC.sel][0]);if(!q)return;const it=q.it,a=G.r*Math.PI/180,lx=dx*Math.cos(a)+dy*Math.sin(a),ly=-dx*Math.sin(a)+dy*Math.cos(a);
  if(h==='rot')return SC.rot(ev,it,G,t);
  const sx=/e/.test(h)?1:/w/.test(h)?-1:0,sy=/s/.test(h)?1:/^n/.test(h)?-1:0;let w=G.w,hh=G.h;
  if(SC.crop&&/^(video|image)$/.test(it.type)){const c={l:0,t:0,r:0,b:0,...(it.crop||{})},fw=G.w/Math.max(.02,1-c.l-c.r),fh=G.h/Math.max(.02,1-c.t-c.b),n={...c};
    if(sx>0)n.r=Math.min(1-c.l-.05,Math.max(0,c.r-lx/fw));if(sx<0)n.l=Math.min(1-c.r-.05,Math.max(0,c.l+lx/fw));if(sy>0)n.b=Math.min(1-c.t-.05,Math.max(0,c.b-ly/fh));if(sy<0)n.t=Math.min(1-c.b-.05,Math.max(0,c.t+ly/fh));
    w=fw*(1-n.l-n.r);hh=fh*(1-n.t-n.b);it.crop=Object.fromEntries(Object.entries(n).map(([k,x])=>[k,+x.toFixed(4)]))}
  else{w=Math.max(8,G.w+sx*lx);hh=Math.max(8,G.h+sy*ly);
    if(sx&&sy&&(it.type==='text'||sh)){const f=Math.max(.05,((G.w+sx*lx)/G.w+(G.h+sy*ly)/G.h)/2);w=G.w*f;hh=G.h*f;if(it.type==='text')it.size=Math.max(4,Math.round(((scAll(b0).find(o=>o.it.id===it.id)||{it:{}}).it.size||64)*f))}}
  const cx=sx*(w-G.w)/2,cy=sy*(hh-G.h)/2,s=G.s||1;scSet(it,'x',Math.round(G.x+cx*Math.cos(a)-cy*Math.sin(a)),t);scSet(it,'y',Math.round(G.y+cx*Math.sin(a)+cy*Math.cos(a)),t);
  scSet(it,'w',Math.round(w/s),t);if(it.type!=='text')scSet(it,'h',Math.round(hh/s),t);SC.draw()};
SC.rot=function(ev,it,G,t){const[px,py]=scPt(ev);let r=Math.atan2(py-G.y,px-G.x)*180/Math.PI+90;if(ev.shiftKey)r=Math.round(r/15)*15;else for(const s of[0,90,180,-90,-180])if(Math.abs(r-s)<3)r=s;
  r=((r+540)%360)-180;scSet(it,'rotation',Math.round(r*10)/10,t);SC.draw()};
// double-click a text: its words typed in place, saved when you click away (Escape too)
$('scover').addEventListener('dblclick',e=>{if(!SC.on)return;const t=scNow(),[px,py]=scPt(e),o=scHit(px,py,t).find(o=>o.it.type==='text'&&!o.tr.locked);if(!o)return;
  const it=o.it,g=scGeo(it,t),d=document.createElement('div');d.className='sced';d.contentEditable='plaintext-only';d.textContent=it.text||'';
  d.style.cssText=`left:${g.x-g.w/2}px;top:${g.y-g.h/2}px;width:${g.w}px;min-height:${g.h}px;transform:rotate(${g.r}deg);font-family:'${it.font||'TikTok Sans'}',system-ui,sans-serif;font-weight:${it.weight||700};font-size:${(it.size||64)*g.s}px;line-height:${it.line_height||1.15};color:${it.color||'#FFFFFF'};text-align:${it.align||'center'};${it.box?`background:${it.box.color};padding:${it.box.pad||0}px;border-radius:${it.box.radius||0}px;`:''}`;
  SC.edit=it.id;SC.show(true);$('scover').appendChild(d);d.focus();document.getSelection().selectAllChildren(d);
  d.addEventListener('keydown',k=>{k.stopPropagation();if(k.key==='Escape'||k.key==='Enter'&&(k.metaKey||k.ctrlKey)){k.preventDefault();SC.edDone()}});d.addEventListener('blur',()=>setTimeout(SC.edDone))});
SC.edDone=function(){const d=$('scover').querySelector('.sced'),id=SC.edit;if(!id)return;SC.edit=null;if(d)d.remove();const q=scGet(id),x=d?d.innerText.replace(/\n$/,''):null;
  if(q&&x!=null&&x!==q.it.text&&x.trim())SC.change('text',s=>{scAll(s).find(o=>o.it.id===id).it.text=x});else SC.show()};
// ---- the timeline: one row per track. Visual tracks top down as they draw (the top row is on top, the bottom one
// is the first visual track, Resolve's order), then captions, then audio
const SCCLS={video:'vid',image:'img',text:'txt',audio:'snd',captions:'cap',shape:'shp'};
const scMag=tr=>tr.magnet??((SC.s&&SC.s.tracks.find(t=>t.kind==='visual')||{}).id===tr.id);   // on by default for the first visual track only (scene.magnet)
SC.tl=function(){const E=$('edtracks');if(!SC.on||!SC.s)return;const T=TO()||scDur(SC.s),pc=x=>Math.max(0,Math.min(100,x/T*100)),st=tstep(T/zm,10),ticks=[];for(let x=0;x<T;x+=st)ticks.push(x);
  const vt=SC.s.tracks.filter(t=>t.kind==='visual').reverse(),ct=SC.s.tracks.filter(t=>t.kind==='captions'),at=SC.s.tracks.filter(t=>t.kind==='audio'),L=[],R=[];
  const head=(tr,cls)=>{const au=tr.kind==='audio',off=au?tr.muted:tr.hidden;return `<div class="ehd${cls||''}" title="${esc(tr.name||tr.id)}"><span>${esc(tr.name||tr.id)}</span>${tr.kind==='visual'&&tr.items.some(i=>i.type==='video')?`<button data-sct="magnet" data-tk="${tr.id}" class="${scMag(tr)?'on':''}" title="${scMag(tr)?'Magnet on: a trim moves everything after it':'Magnet off: a trim leaves a gap'}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3v8a6 6 0 0 0 12 0V3"/><path d="M6 7h4M14 7h4"/></svg></button>`:''}<button data-sct="${au?'muted':'hidden'}" data-tk="${tr.id}" class="${off?'on':''}" title="${au?(off?'Unmute':'Mute'):(off?'Show':'Hide')} this track">${lico((au?LICO.spk:LICO.eye)+(off?LICO.off:''))}</button><button data-sct="locked" data-tk="${tr.id}" class="${tr.locked?'on':''}" title="${tr.locked?'Unlock':'Lock'} this track">${lico(tr.locked?LICO.lock:LICO.open)}</button></div>`};
  const item=(it,tr)=>{const a=it.start,b=it.end,k=it.keys?[...new Set(Object.values(it.keys).flat().map(q=>q[0]))]:[],A=it.asset&&SC.s.assets[it.asset]||{},src=A.src;
    const nm=it.type==='text'&&it.text||it.name||(it.type==='captions'?'Captions':src?String(src).split('/').pop():it.type);
    return `<div class="eitem sc ${SCCLS[it.type]||'img'}${SC.sel.has(it.id)?' sel':''}" data-sid="${esc(it.id)}" data-lkey="${esc(it.id)}" style="left:${pc(a)}%;width:${pc(b)-pc(a)}%" title="${esc(nm)} · ${fmtx(a)}–${fmtx(b)} · drag to move, an edge to trim${/video|audio/.test(it.type)?', Alt-drag to slip':''}">${it.type==='image'&&(A.url||src)?`<img src="${esc(A.url||'/live/media/'+encodeURI(src))}" alt="">`:''}<span>${esc(nm)}</span>${k.map(u=>`<i class="sck" style="left:${u/(b-a||1)*100}%"></i>`).join('')}</div>`};
  const pps=Math.max(200,($('edtracks').clientWidth||900)-120)*(zm||1)/T;   // pixels a second at this zoom
  const joins=tr=>{const js=tr.items.filter(i=>i.cut&&i.cut.before&&i.cut.before.dur>0);return js.map((i,n)=>{const c=i.cut.before,why=String(c.reason||'cut').replace(/^./,m=>m.toUpperCase());
    const room=Math.min(n?i.start-js[n-1].start:1e9,n<js.length-1?js[n+1].start-i.start:1e9)*pps;   // the tab shows once neighbours are 40 px apart
    return `<i class="scj${room>=40?' t':''}" data-cj="${esc(i.id)}" style="left:${pc(i.start)}%"><b></b><span><b>${esc(why)}${c.words?`: "${esc(c.words)}"`:''}</b><em class="num">${(+c.dur).toFixed(1)} s taken out</em><button data-back="${esc(i.id)}">Bring back</button></span></i>`}).join('')};
  const row=(tr,cls)=>{L.push(head(tr,cls));R.push(`<div class="etrack${cls||''}${(tr.kind==='audio'?tr.muted:tr.hidden)?' lhid':''}${tr.locked?' llock':''}" data-sctk="${tr.id}" data-kind="${tr.kind}">${tr.items.map(i=>item(i,tr)).join('')}${joins(tr)}</div>`)};
  L.push('<div class="ehd newl" data-row="scv"></div>');R.push('<div class="etrack newl" data-row="scv" data-new="visual">Drop here for a new track</div>');
  vt.forEach((t,i)=>row(t,i===vt.length-1?' l1':''));ct.forEach(t=>row(t,' l1'));at.forEach((t,i)=>row(t,i?'':' l1'));
  L.push('<div class="ehd newl" data-row="sca"></div>');R.push('<div class="etrack newl" data-row="sca" data-new="audio">Drop here for a new track</div>');
  L.push('<div class="scadd"><button data-addtk="visual" title="Add a video track on top">+ Track</button><button data-addtk="audio" title="Add an audio track">+ Audio</button><button data-addit="text" title="Add a text at the playhead">+ Text</button><button data-addit="shape" title="Add a shape at the playhead">+ Shape</button></div>');
  const h=`<div class="edwrap"><div class="edleft">${L.join('')}</div><div class="edright"><div class="escroll" id="escroll"><div class="einner"><div class="eruler">${ticks.map(x=>`<span style="left:${x/T*100}%">${st<1?fmtx(x):fmt(x)}</span>`).join('')}</div>${R.join('')}<b class="eph" id="eph"></b><b class="esnap" id="esnap" hidden><i></i></b></div></div></div></div>`;
  if(E._h!==h){E._h=h;E.innerHTML=h;tscrollTo($('tscroll').scrollLeft)}edPh()};
// a track's buttons, Bring back on a join, + Track
$('edtracks').addEventListener('click',e=>{if(!SC.on)return;const b=e.target.closest('[data-sct],[data-back],[data-addtk],[data-addit]');if(!b)return;e.stopPropagation();if(b.dataset.addit)return b.dataset.addit==='text'?SC.addText(scNow()):SC.addShape(scNow());
  if(b.dataset.sct){const id=b.dataset.tk,p=b.dataset.sct;return SC.change({hidden:'hide or show a track',muted:'mute a track',locked:'lock a track',magnet:'magnet'}[p],s=>{const tr=s.tracks.find(x=>x.id===id);tr[p]=p==='magnet'?!scMag(tr):!tr[p]})}
  if(b.dataset.back)return SC.bringBack(b.dataset.back);
  const k=b.dataset.addtk;SC.change('add a track',s=>{const tr={id:scId(k==='audio'?'a':'v'),kind:k,name:k==='audio'?'Audio '+(s.tracks.filter(x=>x.kind==='audio').length+1):'Video '+(s.tracks.filter(x=>x.kind==='visual').length+1),items:[],...(k==='audio'?{muted:false}:{hidden:false}),locked:false};
    const i=k==='audio'?s.tracks.length:s.tracks.map(x=>x.kind).lastIndexOf('visual')+1;s.tracks.splice(i,0,tr)})},true);
// a trim on a magnet track moves everything after the edge on every track by the same amount (SCENE.md, the AI's cuts)
function scRipple(s,skip,p,d){for(const o of scAll(s)){const it=o.it;if(it===skip||o.tr.locked||it.locked)continue;
  if(it.start>=p-1e-3){it.start=+(it.start+d).toFixed(3);it.end=+(it.end+d).toFixed(3)}else if(it.end>p+1e-3)it.end=+Math.max(it.start+.05,it.end+d).toFixed(3);
  if(it.words&&!it.asset)it.words.forEach(w=>{if(w.start>=p-1e-3){w.start=+(w.start+d).toFixed(3);w.end=+(w.end+d).toFixed(3)}});
  if(it.keys&&it.start<p&&it.end>p)for(const k of Object.values(it.keys))k.forEach(q=>{if(it.start+q[0]>=p)q[0]=+(q[0]+d).toFixed(3)})}}
// trim an edge by dt seconds (out: negative on the left, positive on the right). On a magnet track the clip keeps its
// place and the rest moves: the footage before or after it comes back from the raw take
function scTrim(s,id,side,dt){const o=scAll(s).find(o=>o.it.id===id);if(!o)return;const it=o.it,sp=it.speed||1,av=/^(video|audio)$/.test(it.type),mag=scMag(o.tr)&&it.type==='video';
  const cb=x=>x&&x.cut&&x.cut.before,nx=mag&&o.tr.items.find(x=>x!==it&&Math.abs(x.start-it.end)<.02),less=(x,d)=>{const r=(cb(x).dur||0)-d;x.cut={...x.cut,before:r>.04?{...cb(x),dur:+r.toFixed(3)}:null}};   // out to the end of what was taken out, never into the clip beside it
  if(side==='l'){if(av)dt=Math.max(dt,-(it.in||0)/sp);if(mag&&cb(it))dt=Math.max(dt,-cb(it).dur);dt=Math.min(dt,it.end-it.start-.1);if(!mag){dt=Math.max(dt,-it.start);it.start=+(it.start+dt).toFixed(3)}
    if(av)it.in=+Math.max(0,(it.in||0)+dt*sp).toFixed(3);
    if(mag){const p=it.start;it.end=+(it.end-dt).toFixed(3);scRipple(s,it,p+1e-3,-dt);if(cb(it)&&dt<0)less(it,-dt)}}
  else{dt=Math.max(dt,-(it.end-it.start-.1));if(cb(nx))dt=Math.min(dt,cb(nx).dur);const p=it.end;it.end=+(it.end+dt).toFixed(3);if(mag)scRipple(s,it,p,dt);if(cb(nx)&&dt>0)less(nx,dt)}}
// a join's note sits above its tab, outside the rows' scroll box
$('edtracks').addEventListener('mouseover',e=>{const j=e.target.closest('.scj');if(!j)return;const r=j.getBoundingClientRect(),sp=j.querySelector('span');sp.style.left=Math.max(8,r.left-8)+'px';sp.style.bottom=(innerHeight-r.top+6)+'px'});
SC.bringBack=function(id){const q=scGet(id);if(!q||!q.it.cut||!q.it.cut.before)return;const d=q.it.cut.before.dur;SC.change('bring back a cut',s=>scTrim(s,id,'l',-d))};
$('edtracks').addEventListener('pointerdown',e=>{const el=e.target.closest('.eitem.sc');if(!SC.on||!el||e.button)return;e.stopPropagation();e.preventDefault();v.pause();SC.zone='t';
  const id=el.dataset.sid,q=scGet(id);if(!q||q.tr.locked||q.it.locked)return;SC.pick=1;const r=el.getBoundingClientRect(),side=e.clientX-r.left<8?'l':r.right-e.clientX<8?'r':'m',slip=side==='m'&&e.altKey&&/^(video|audio)$/.test(q.it.type);
  if(e.shiftKey||e.metaKey||e.ctrlKey){SC.sel.has(id)?SC.sel.delete(id):SC.sel.add(id)}else if(!SC.sel.has(id)){SC.sel.clear();SC.sel.add(id)}
  const b0=scCopy(SC.s),inn=document.querySelector('#edtracks .einner'),W0=inn.getBoundingClientRect().width,T=TO(),x0=e.clientX,y0=e.clientY,ps=snapPts([...document.querySelectorAll('#edtracks .eitem.sc')].filter(x=>SC.sel.has(x.dataset.sid)));
  let moved=false,dest=null;SC.drag=1;edHold=1;SC.show();
  const mv=ev=>{let dt=(ev.clientX-x0)/W0*T;if(!moved&&Math.abs(ev.clientX-x0)<3&&Math.abs(ev.clientY-y0)<4)return;moved=true;SC.s=scCopy(b0);const it=scGet(id).it;
    if(slip){it.in=+Math.max(0,(it.in||0)-dt*(it.speed||1)).toFixed(3)}
    else if(side==='m'){dt=snapDt(ev,'m',it.start,it.end,dt,ps,W0);dt=Math.max(dt,-Math.min(...[...SC.sel].map(k=>(scGet(k)||{it:{start:0}}).it.start)));
      SC.sel.forEach(k=>{const x=scGet(k);if(x&&!x.tr.locked){x.it.start=+(x.it.start+dt).toFixed(3);x.it.end=+(x.it.end+dt).toFixed(3)}});
      const tk=document.elementsFromPoint(ev.clientX,ev.clientY).find(x=>x.classList&&x.classList.contains('etrack')),E=$('edtracks'),qk=q.tr.kind;
      document.querySelectorAll('.etrack.scdrop').forEach(x=>x.classList.remove('scdrop'));dest=null;
      if(Math.abs(ev.clientY-y0)>10&&SC.sel.size===1&&qk!=='captions'){E.dataset.ld=qk==='audio'?'sca':'scv';
        if(tk&&tk.dataset.new===qk)dest={new:qk};else if(tk&&tk.dataset.sctk&&tk.dataset.kind===qk&&tk.dataset.sctk!==q.tr.id)dest={id:tk.dataset.sctk};if(dest&&tk)tk.classList.add('scdrop')}}
    else{const it0=scAll(b0).find(o=>o.it.id===id).it;dt=snapDt(ev,side,it0.start,it0.end,dt,ps,W0);scTrim(SC.s,id,side,dt);const n=scGet(id).it;v.currentTime=Math.max(0,side==='l'?n.start:n.end-.01)}
    SC.show(true);SC.tl()};
  const up=async()=>{document.removeEventListener('pointermove',mv,true);document.removeEventListener('pointerup',up,true);SC.drag=0;edHold=0;delete $('edtracks').dataset.ld;
    if(!moved){SC.show();return}
    if(dest){const it=scGet(id);it.tr.items.splice(it.ii,1);let tr=dest.id&&SC.s.tracks.find(x=>x.id===dest.id);
      if(!tr){tr={id:scId(dest.new==='audio'?'a':'v'),kind:dest.new,name:dest.new==='audio'?'Audio '+(SC.s.tracks.filter(x=>x.kind==='audio').length+1):'Video '+(SC.s.tracks.filter(x=>x.kind==='visual').length+1),items:[],locked:false,...(dest.new==='audio'?{muted:false}:{hidden:false})};
        SC.s.tracks.splice(dest.new==='audio'?SC.s.tracks.length:SC.s.tracks.map(x=>x.kind).lastIndexOf('visual')+1,0,tr)}
      tr.items.push(it.it);tr.items.sort((a,b)=>a.start-b.start)}
    await SC.commit(b0,slip?'slip':side==='m'?(dest?'move to another track':'move'):'trim')};
  document.addEventListener('pointermove',mv,true);document.addEventListener('pointerup',up,true)},true);
// ---- keys: delete, split, nudge, crop, Escape. Returns true when it took the key (review.html asks first)
SC.key=function(e){if(!SC.on||KM.off()||typingIn(e.target)||SC.edit)return false;const ids=[...SC.sel].filter(k=>scGet(k));
  if(KM.is(e,'delete')&&ids.length){e.preventDefault();SC.change(ids.length>1?`delete ${ids.length} items`:'delete',s=>s.tracks.forEach(tr=>tr.items=tr.items.filter(i=>!ids.includes(i.id))));SC.sel.clear();return true}
  if(KM.is(e,'split')){const t=scNow(),hit=(ids.length?ids.map(scGet):scAll().filter(o=>o.it.type==='video'&&!o.tr.locked)).filter(o=>o&&o.it.start+.05<t&&t<o.it.end-.05);if(!hit.length)return false;e.preventDefault();
    SC.change('split',s=>hit.forEach(o=>{const x=scAll(s).find(q=>q.it.id===o.it.id),it=x.it,n={...scCopy(it),id:scId('i'),start:+t.toFixed(3)};delete n.cut;
      if(it.in!=null)n.in=+((it.in||0)+(t-it.start)*(it.speed||1)).toFixed(3);if(it.keys)for(const[p,k]of Object.entries(it.keys)){n.keys[p]=k.filter(q=>it.start+q[0]>=t).map(q=>[+(q[0]-(t-it.start)).toFixed(3),q[1],q[2]]);it.keys[p]=k.filter(q=>it.start+q[0]<t)}
      it.end=+t.toFixed(3);x.tr.items.splice(x.ii+1,0,n)}));return true}
  const ar={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[e.key];
  if(ar&&ids.length&&SC.zone==='v'&&!e.altKey&&!(e.metaKey||e.ctrlKey)){e.preventDefault();const n=e.shiftKey?10:1,t=scNow();
    SC.change('nudge',s=>ids.forEach(k=>{const it=scAll(s).find(o=>o.it.id===k).it;if(!scVis(it))return;scSet(it,'x',scVal(it,'x',t)+ar[0]*n,t);scSet(it,'y',scVal(it,'y',t)+ar[1]*n,t)}));return true}
  if(e.key.toLowerCase()==='c'&&!e.metaKey&&!e.ctrlKey&&ids.length===1&&/^(video|image)$/.test(scGet(ids[0]).it.type)){e.preventDefault();SC.crop=!SC.crop;SC.show();return true}
  if(e.key==='Escape'&&(ids.length||SC.crop)){SC.crop?SC.crop=false:SC.sel.clear();SC.show();return true}
  return false};
// ---- the inspector (the left panel): every field of the picked item; several picked, the fields they share
const SCAN=[['none','None'],['cut','Cut'],['fade','Fade'],['pop','Pop'],['slide-up','Slide up']],SCFONT=['TikTok Sans','Inter','Montserrat','Poppins','Bebas Neue','Georgia'];
const KEYP=['x','y','w','h','rotation','opacity'];
function scFields(it){const V=scVis(it),F=[];const n=(p,l,st,u,o)=>F.push({p,l,k:'num',st,u,...o}),c=(p,l)=>F.push({p,l,k:'col'}),s=(p,l,opts)=>F.push({p,l,k:'sel',opts}),tg=(p,l,def)=>F.push({p,l,k:'tog',def});
  if(it.type==='text'){F.push({p:'text',l:'Words',k:'txt'});s('font','Font',SCFONT.map(f=>[f,f]));n('size','Size',1,'px');s('weight','Weight',[[400,'Regular'],[500,'Medium'],[600,'Semibold'],[700,'Bold'],[800,'Heavy'],[900,'Black']]);c('color','Colour');
    s('align','Align',[['left','Left'],['center','Centre'],['right','Right']]);n('line_height','Line height',.05,'');tg('box','Box',{color:'#000000',pad:16,radius:12});if(it.box){c('box.color','Box colour');n('box.pad','Box padding',1,'px');n('box.radius','Box radius',1,'px')}
    tg('outline','Outline',{color:'#000000',width:4});if(it.outline){c('outline.color','Outline colour');n('outline.width','Outline width',1,'px')}}
  if(it.type==='shape'){c('fill','Fill');tg('stroke','Stroke',{color:'#FFFFFF',width:4});if(it.stroke){c('stroke.color','Stroke colour');n('stroke.width','Stroke width',1,'px')}}
  if(V){n('x','Position X',1,'px');n('y','Position Y',1,'px');n('w',it.type==='text'?'Wrap width':'Width',1,'px');if(it.type!=='text')n('h','Height',1,'px');n('rotation','Rotation',1,'°');n('opacity','Opacity',.05,'',{min:0,max:1});
    if(/^(video|image)$/.test(it.type)){s('fit','Fit',[['cover','Fill'],['contain','Fit']]);n('crop.l','Crop left',.01,'',{min:0,max:.95});n('crop.t','Crop top',.01,'',{min:0,max:.95});n('crop.r','Crop right',.01,'',{min:0,max:.95});n('crop.b','Crop bottom',.01,'',{min:0,max:.95})}
    n('radius','Corners',1,'px');tg('shadow','Shadow',{blur:24,y:8,opacity:.4});if(it.shadow){n('shadow.blur','Shadow blur',1,'px');n('shadow.y','Shadow Y',1,'px');n('shadow.opacity','Shadow opacity',.05,'')}
    tg('border','Border',{width:4,color:'#FFFFFF'});if(it.border){n('border.width','Border width',1,'px');c('border.color','Border colour')}
    s('anim.in','Animation in',SCAN);s('anim.out','Animation out',SCAN);n('anim.dur','Animation time',.05,'s')}
  if(/^(video|audio)$/.test(it.type)){n('volume','Volume',.05,'',{min:0,max:2});n('speed','Speed',.05,'x',{min:.1,max:8});n('fade_in','Fade in',.05,'s',{min:0});n('fade_out','Fade out',.05,'s',{min:0});n('in','Starts in source',.01,'s',{min:0})}
  n('start','Start',.01,'s',{min:0});n('end','End',.01,'s',{min:0});return F}
const scPath=(it,p)=>p.split('.').reduce((o,k)=>o==null?o:o[k],it);
function scPut(it,p,x,t){const ps=p.split('.');if(ps.length===1){if(KEYP.includes(p))scSet(it,p,x,t);else it[p]=x;return}it[ps[0]]={...(it[ps[0]]||(ps[0]==='crop'?{l:0,t:0,r:0,b:0}:ps[0]==='anim'?{in:'none',out:'none',dur:.3}:{})),[ps[1]]:x}}
SC.insp=function(){if(!SC.on)return;const ids=[...SC.sel].filter(k=>scGet(k)),B=$('ibody');
  if(!ids.length){if(tool&&tool!=='insp')return;if(tool!=='insp')openTool('insp');const h='<p class="ihead"><b>Nothing picked</b><span>Click anything on the video or the timeline to change it here.</span></p>';if(B._h!==h)B.innerHTML=B._h=h;return}
  if(tool&&tool!=='insp'&&!SC.pick)return;SC.pick=0;if(tool!=='insp')openTool('insp');const t=scNow(),its=ids.map(k=>scGet(k).it),one=its[0],fs=scFields(one).filter(f=>f.k!=='txt'||its.length===1).filter(f=>its.every(i=>scFields(i).some(g=>g.p===f.p)));
  const val=f=>KEYP.includes(f.p)?scVal(one,f.p,t):scPath(one,f.p),hk=p=>(one.keys&&one.keys[p]||[]).some(q=>Math.abs(one.start+q[0]-t)<1/(SC.s.fps||30)),kb=f=>KEYP.includes(f.p)&&its.length===1?`<button class="sckey${hk(f.p)?' on':''}" data-kp="${f.p}" title="${hk(f.p)?'Remove the key here':'Add a key here: it animates to the next key'}" aria-label="keyframe ${f.l.toLowerCase()}"></button>`:'';
  const row=f=>{const x=val(f),id='sci-'+f.p.replace('.','-');let c;
    if(f.k==='num')c=`<input type="number" class="inum" id="${id}" data-p="${f.p}" step="${f.st}"${f.min!=null?` min="${f.min}"`:''}${f.max!=null?` max="${f.max}"`:''} value="${x==null?'':+(+x).toFixed(f.st<1?2:0)}"><em>${f.u}</em>`;
    else if(f.k==='col')c=`<input type="color" id="${id}" data-p="${f.p}" value="${/^#[0-9a-f]{6}$/i.test(x||'')?x:'#FFFFFF'}">`;
    else if(f.k==='sel')c=`<select id="${id}" data-p="${f.p}">${(f.opts.some(o=>String(o[0])===String(x))||x==null?f.opts:[[x,x],...f.opts]).map(([k,n])=>`<option value="${k}"${String(k)===String(x??'')?' selected':''}>${n}</option>`).join('')}</select>`;
    else if(f.k==='tog')c=`<select id="${id}" data-p="${f.p}" data-tog="${esc(JSON.stringify(f.def))}"><option value=""${x?'':' selected'}>Off</option><option value="1"${x?' selected':''}>On</option></select>`;
    else return `<div class="tf top"><span>${f.l}</span><div class="tfv"><textarea class="scta" id="${id}" data-p="text">${esc(x||'')}</textarea></div></div>`;
    return `<div class="tf"><span>${f.l}</span><div class="tfv">${c}</div>${kb(f)}</div>`};
  const nm=its.length>1?`${its.length} picked`:esc(one.name||(one.type==='text'?one.text:one.type).replace(/^./,m=>m.toUpperCase())),sub=its.length>1?'A change goes on all of them':`${one.type.replace(/^./,m=>m.toUpperCase())} · ${fmtx(one.start)} to ${fmtx(one.end)}`;
  const h=`<p class="ihead"><b>${nm}</b><span>${sub}</span></p><div class="isec">${fs.map(row).join('')}</div>${its.length===1&&/^(video|image)$/.test(one.type)?`<button class="ifull" id="sccrop">${SC.crop?'Done cropping':'Crop (C)'}</button>`:''}<button class="ifull" id="scdel">Delete</button>`;
  if(B._h===h)return;const f=document.activeElement;if(f&&B.contains(f)&&f.dataset.p)return;B._h=h;B.innerHTML=h};
$('ibody').addEventListener('input',e=>{if(!SC.on||!e.target.dataset.p||e.target.dataset.tog!=null)return;if(!SC.ib)SC.ib=scCopy(SC.s);const p=e.target.dataset.p,t=scNow(),raw=e.target.value;
  const x=e.target.type==='number'?(raw===''?null:+raw):p==='weight'?+raw:raw;if(x==null&&e.target.type==='number')return;
  SC.sel.forEach(k=>{const q=scGet(k);if(q)scPut(q.it,p,x,t)});SC.show(true)},true);
$('ibody').addEventListener('change',e=>{if(!SC.on||!e.target.dataset.p)return;const p=e.target.dataset.p,t=scNow();let b=SC.ib||scCopy(SC.s);SC.ib=null;
  if(e.target.dataset.tog!=null){const on=!!e.target.value,d=JSON.parse(e.target.dataset.tog);b=scCopy(SC.s);SC.sel.forEach(k=>{const q=scGet(k);if(q)q.it[p]=on?(q.it[p]||d):null})}
  $('ibody')._h=null;SC.show();SC.commit(b,'change '+p.replace('.',' ').replace('_',' '))},true);
$('ibody').addEventListener('click',e=>{if(!SC.on)return;const k=e.target.closest('[data-kp]'),t=scNow();
  if(k){const p=k.dataset.kp,id=[...SC.sel][0];return SC.change('keyframe',s=>{const it=scAll(s).find(o=>o.it.id===id).it,u=+(t-it.start).toFixed(3),ks=(it.keys=it.keys||{})[p]=it.keys[p]||[],i=ks.findIndex(q=>Math.abs(q[0]-u)<1/(s.fps||30)/2);
    if(i>=0){ks.splice(i,1);if(!ks.length){delete it.keys[p];if(!Object.keys(it.keys).length)delete it.keys}}else{if(!ks.length&&it[p]==null)it[p]=scVal(it,p,t);ks.push([u,scVal({...it,keys:{}},p,t)||scVal(it,p,t),'inout']);ks.sort((a,b)=>a[0]-b[0])}})}
  if(e.target.id==='sccrop'){SC.crop=!SC.crop;$('ibody')._h=null;return SC.show()}
  if(e.target.id==='scdel'){const ids=[...SC.sel];SC.sel.clear();return SC.change('delete',s=>s.tracks.forEach(tr=>tr.items=tr.items.filter(i=>!ids.includes(i.id))))}},true);
// ---- add: text, a shape, an image or video from Media, a sound; files dropped on the video or the rows (review.html sends them here)
const scTop=(s,kind)=>{let tr=[...s.tracks].reverse().find(x=>x.kind===kind&&!x.locked&&!x.hidden);if(!tr){tr={id:scId(kind==='audio'?'a':'v'),kind,name:kind==='audio'?'Audio':'Overlay',items:[],locked:false};s.tracks.push(tr)}return tr};
SC.add=function(what,item,kind,asset){const t=item.start??scNow(),it={id:scId('i'),start:+t.toFixed(3),end:+(t+(item.dur||3)).toFixed(3),...item};delete it.dur;
  return SC.change('add '+what,s=>{if(asset)(s.assets=s.assets||{})[it.asset]=asset;scTop(s,kind||'visual').items.push(it)}).then(()=>{SC.sel=new Set([it.id]);SC.zone='v';SC.show()})};
SC.addText=t=>SC.add('text',{type:'text',name:'Text',text:'Your text',font:'TikTok Sans',weight:700,size:72,color:'#FFFFFF',align:'center',line_height:1.15,box:null,outline:null,x:SC.s.width/2,y:Math.round(SC.s.height*.4),w:Math.round(SC.s.width*.8),rotation:0,opacity:1,start:t});
SC.addShape=t=>SC.add('shape',{type:'shape',name:'Shape',fill:'#FFFFFF',stroke:null,x:SC.s.width/2,y:SC.s.height/2,w:400,h:400,rotation:0,opacity:1,radius:24,start:t});
SC.addMedia=async function(m,t,px,py){const sz=await medSize(m),vid=/\.(mp4|mov|m4v|webm)$/i.test(m.src),W=SC.s.width,H=SC.s.height,f=Math.min(W*.7/sz[0],H*.4/sz[1]),a=scId('m');
  let d=3;if(vid)d=await new Promise(res=>{const x=document.createElement('video');x.preload='metadata';x.onloadedmetadata=()=>res(Math.min(x.duration||3,30));x.onerror=()=>res(3);x.src='/live/media/'+encodeURI(m.src)});
  return SC.add(vid?'a video':'an image',{type:vid?'video':'image',name:m.src.split('/').pop(),asset:a,...(vid?{in:0,speed:1,volume:1,fade_in:0,fade_out:0}:{}),x:Math.round(px!=null?px/100*W:W/2),y:Math.round(py!=null?py/100*H:H*.35),w:Math.round(sz[0]*f),h:Math.round(sz[1]*f),rotation:0,opacity:1,fit:'cover',start:t,dur:d},'visual',{src:m.src,kind:vid?'video':'image',w:sz[0],h:sz[1],url:'/live/media/'+encodeURI(m.src),...(vid?{duration:d}:{})})};
SC.addSound=(name,t,dur)=>SC.add('a sound',{type:'audio',name:name.split('/').pop().replace(/\.[a-z0-9]+$/i,''),asset:scId('s'),in:0,speed:1,volume:1,fade_in:0,fade_out:0,start:t,dur:dur||3},'audio',{src:name,lib:true,kind:'audio',duration:dur||3});   // a library sound: its name, not a file in the edit (SCENE.md has no library src yet)
document.addEventListener('keydown',e=>{if(SC.key(e))e.stopImmediatePropagation()},true);
$('railtext').addEventListener('click',e=>{if(!SC.on)return;e.stopImmediatePropagation();SC.addText(scNow())},true);
$('scover').addEventListener('click',e=>e.stopPropagation());
// ---- the transcript follows the clips: a raw word inside a clip of the main track is kept, one in a gap is struck
SC.txSync=function(){if(!SC.on||typeof W==='undefined'||!W.length)return;const main=SC.s.tracks.find(tr=>tr.kind==='visual'&&tr.items.some(i=>i.cut))||null;if(!main)return;
  const rs=main.items.filter(i=>i.type==='video').map(i=>[i.in||0,(i.in||0)+(i.end-i.start)*(i.speed||1)]);
  document.querySelectorAll('#txlines .tw[data-k]').forEach(el=>{const w=W[+el.dataset.k];if(!w||w.s==null)return;el.classList.toggle('cut',!rs.some(([a,b])=>w.s>=a-.02&&w.s<b))})};
// ---- Export: review.html's one Export button (review.py export_job renders the scene when there is one)
