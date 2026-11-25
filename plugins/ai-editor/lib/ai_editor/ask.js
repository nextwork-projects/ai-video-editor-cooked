// Claude's questions in this page (askhook.py). Loaded by home.html and review.html; uses each page's own
// colour tokens, so it follows the review page's dark mode. Polls GET /ask every second.
(()=>{
// Alerts (pure, so tests/test_alerts.mjs runs them in node): a question chimes once per id across reloads and tabs
// (the ids already chimed live in localStorage); a video chimes once when its phase goes from Claude working to
// anything but a question. A question mid-make keeps the phase from before it, so the answer does not chime.
const WORK=['notes','stills','rendering','cutting'];
const firstTime=(seen,id)=>seen.includes(id)?null:[id,...seen].slice(0,30);
function finished(prev,now){const done=[],next={};
  for(const [d,ph] of Object.entries(now)){const was=prev[d];next[d]=ph==='ask'&&was?was:ph;if(WORK.includes(was)&&!WORK.includes(ph)&&ph!=='ask')done.push(d)}
  return {done,next}}
if(typeof document==='undefined'){module.exports={firstTime,finished};return}
const css=`#askq{position:fixed;inset:0;z-index:9999;display:none;align-items:center;justify-content:center;padding:16px;background:rgba(12,10,9,.36);backdrop-filter:blur(2px)}
#askq.on{display:flex}
#askq .aq-card{--a-panel:var(--panel,#fff);--a-ink:var(--ink,#0C0A09);--a-line:var(--line,#E7E5E4);--a-muted:var(--muted,var(--t3,#78716C));
 --a-body:var(--body,var(--t2,#57534E));--a-soft:var(--chip,var(--soft,#F5F5F4));--a-onink:var(--onink,#fff);
 width:100%;max-width:560px;max-height:calc(100vh - 32px);overflow:auto;background:var(--a-panel);color:var(--a-ink);border:1px solid var(--a-line);
 border-radius:20px;padding:26px 26px 18px;box-shadow:0 12px 40px rgba(0,0,0,.18);font:14px/20px system-ui,-apple-system,"Segoe UI",sans-serif;text-align:left}
#askq .aq-top{display:flex;justify-content:space-between;gap:12px;font-size:13px;line-height:16px;color:var(--a-muted)}
#askq .aq-hd{display:inline-block;margin-top:14px;padding:3px 9px;border-radius:7px;background:var(--a-soft);color:var(--a-body);font-size:12px;line-height:16px;font-weight:600}
#askq h2{margin:10px 0 18px;font-size:20px;line-height:27px;font-weight:600;letter-spacing:-.01em;color:var(--a-ink)}
#askq .aq-opts{display:flex;flex-direction:column;gap:8px}
#askq .aq-opt{display:flex;gap:12px;align-items:flex-start;width:100%;margin:0;padding:13px 16px;border:1px solid var(--a-line);border-radius:14px;background:none;color:inherit;font:inherit;text-align:left;cursor:pointer}
#askq .aq-opt:hover,#askq .aq-opt:focus-visible{border-color:var(--a-ink);outline:none}
#askq .aq-opt.aq-sel{border:1.5px solid var(--a-ink);padding:12.5px 15.5px}
#askq .aq-opt b{display:block;font-size:15px;line-height:20px;font-weight:600}
#askq .aq-opt span{display:block;margin-top:2px;color:var(--a-body);font-size:13px;line-height:18px}
#askq .aq-box{width:18px;height:18px;margin-top:1px;flex-shrink:0;border:1.5px solid var(--a-line);border-radius:5px;display:flex;align-items:center;justify-content:center}
#askq .aq-sel .aq-box{background:var(--a-ink);border-color:var(--a-ink);color:var(--a-onink)}
#askq .aq-other{display:flex;gap:8px;margin-top:14px}
#askq input{flex:1;min-width:0;height:44px;margin:0;padding:0 14px;border:1px solid var(--a-line);border-radius:12px;background:none;color:inherit;font:inherit}
#askq input:focus{outline:none;border:1.5px solid var(--a-ink);padding:0 13.5px}
#askq .aq-send{height:44px;margin:0;padding:0 20px;border:0;border-radius:12px;background:var(--a-ink);color:var(--a-onink);font:inherit;font-weight:600;cursor:pointer;flex-shrink:0}
#askq .aq-send:disabled{opacity:.35;cursor:default}
#askq .aq-clip{width:44px;height:44px;margin:0;padding:0;border:1px solid var(--a-line);border-radius:12px;background:none;color:var(--a-body);display:grid;place-items:center;cursor:pointer;flex-shrink:0}
#askq .aq-clip:hover,#askq .aq-clip:focus-visible{border-color:var(--a-ink);color:var(--a-ink);outline:none}
#askq .aq-pics{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}#askq .aq-pics:empty{display:none}
#askq .aq-pics span{position:relative}#askq .aq-pics img{height:56px;max-width:120px;object-fit:cover;border-radius:8px;border:1px solid var(--a-line);display:block}
#askq .aq-pics button{position:absolute;top:-7px;right:-7px;width:20px;height:20px;margin:0;padding:0;border:0;border-radius:50%;background:var(--a-ink);color:var(--a-onink);font:12px/20px system-ui,sans-serif;cursor:pointer}
#askq .aq-card.aq-drag{border-color:var(--a-ink)}
#askq .aq-wide{width:100%;margin-top:12px}
#askq .aq-foot{margin-top:16px;padding:0;border:0;text-align:center}
#askq .aq-hint{display:block;color:var(--a-muted);font-size:13px;line-height:18px}
#askq .aq-term{border:0;background:none;margin:0;padding:4px;color:var(--a-muted);font:inherit;font-size:13px;text-decoration:underline 1px;text-underline-offset:3px;cursor:pointer}
#askq .aq-done{padding:18px 0 10px;font-size:15px;color:var(--a-body);text-align:center}
#askbar{position:fixed;left:50%;bottom:20px;transform:translateX(-50%);z-index:9999;display:none;align-items:center;gap:10px;margin:0;padding:11px 18px;border:1px solid var(--line,#E7E5E4);border-radius:999px;background:var(--panel,#fff);color:var(--ink,#0C0A09);font:600 14px/20px system-ui,-apple-system,"Segoe UI",sans-serif;box-shadow:0 8px 28px rgba(0,0,0,.16);cursor:pointer}
#askterm{position:fixed;left:50%;top:16px;transform:translateX(-50%);z-index:9998;display:none;max-width:min(560px,calc(100vw - 32px));gap:12px;align-items:flex-start;padding:12px 16px;border-radius:14px;background:var(--ink,#0C0A09);color:var(--onink,#fff);font:14px/20px system-ui,-apple-system,"Segoe UI",sans-serif;box-shadow:0 12px 40px rgba(0,0,0,.25)}
#askterm.on{display:flex}#askterm b{display:block;font-weight:600}#askterm span{display:block;opacity:.75;font-size:13px;line-height:18px}#askterm i{width:9px;height:9px;margin-top:6px;border-radius:50%;background:#F59E0B;flex-shrink:0;animation:aqp 1.2s ease-in-out infinite}
@keyframes aqp{50%{opacity:.35}}
#askbar.on{display:flex}#askbar i{width:8px;height:8px;border-radius:50%;background:currentColor}#askbar span{font-weight:400;color:var(--muted,var(--t3,#78716C))}
@media (max-width:520px){#askq{align-items:flex-end}#askq .aq-card{padding:22px 18px 14px;border-radius:18px}#askq h2{font-size:18px;line-height:25px}}`;
const CLIP='<svg width="16" height="16" viewBox="0 0 16 16"><path d="M13 7.5l-5.3 5.3a3.2 3.2 0 01-4.5-4.5l5.6-5.6a2.1 2.1 0 013 3l-5.5 5.5a1 1 0 01-1.5-1.5L9.9 4.6" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>';
const TYPES=/^image\/(png|jpeg|gif|webp)$/,MAXB=15<<20,MAXN=6;   // the review notes' limits (askhook.save_images)
const TICK='<svg width="11" height="11" viewBox="0 0 12 12"><path d="M2 6.2l2.6 2.6L10 3.4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const st=document.createElement('style');st.textContent=css;document.head.appendChild(st);
const el=document.createElement('div');el.id='askq';el.setAttribute('role','dialog');el.setAttribute('aria-modal','true');el.setAttribute('aria-label','Claude has a question');
el.addEventListener('keydown',e=>{if(e.key==='Escape'&&A){e.preventDefault();fold()}e.stopPropagation()});   // the page's own shortcuts stay off while typing here
document.body.appendChild(el);
// Esc folds the card into a bar that reopens it: the question is never lost
const bar=document.createElement('button');bar.id='askbar';bar.type='button';bar.innerHTML='<i></i>Claude is asking you something<span>Open</span>';
const term=document.createElement('div');term.id='askterm';term.setAttribute('role','status');document.body.appendChild(term);
// Claude waits in a Terminal window (a permission prompt, a question no page took): say so on every page, chime once
let TT=null;
function terminal(t){
  if(!t){if(TT){term.classList.remove('on');if(document.title===TT)document.title=title0;TT=null}return}
  term.innerHTML=`<i></i><div><b>Claude needs you in the Terminal window</b><span>${esc(t.message||'Go back to Claude Code to answer it.')}</span></div>`;term.classList.add('on');
  if(!A&&document.title!==TITLE&&document.title!=='(1) Go to the Terminal'){title0=document.title;document.title=TT='(1) Go to the Terminal'}
  if(askedNow('t'+t.at))alert1('Claude needs you in the Terminal',t.message||'');
}
let title0=document.title;
bar.onclick=()=>{bar.classList.remove('on');el.classList.add('on');el.querySelector('button,input')?.focus()};document.body.appendChild(bar);
document.addEventListener('keydown',e=>{if(!A||!el.classList.contains('on'))return;
  if(e.key==='Escape'){e.preventDefault();e.stopPropagation();fold();return}
  // the card is modal: a key pressed outside it (focus left on the page after attaching an image) goes to the Other box,
  // never to the page's shortcuts ('c' opened a note, space played)
  if(!el.contains(e.target)&&!e.metaKey&&!e.ctrlKey&&!e.altKey){e.stopPropagation();el.querySelector('#asko')?.focus()}},true);
function fold(){el.classList.remove('on');bar.classList.add('on')}
// the page's header says so while a question is open (review.html reads data-ask, redraws on "askchange").
// window.askq: the open question {about, elsewhere}; elsewhere (Home only): the video's editor has it as the card, so
// Home shows a row "Claude is asking about <video>" whose Open calls window.askOpen()
function flag(on){const r=document.documentElement;window.askq=on&&A?{about:A.about||'',elsewhere:!!A.elsewhere,all:ALL.map(x=>({id:x.id,about:x.about||'',elsewhere:!!x.elsewhere}))}:null;if(!!r.dataset.ask===on)return;on?r.dataset.ask='1':delete r.dataset.ask;dispatchEvent(new Event('askchange'))}
// the card up (not folded, not Home's row): the page's shortcuts stay off (review.html reads data-ask-open)
new MutationObserver(()=>{const on=el.classList.contains('on')&&!!A,r=document.documentElement;if(!!r.dataset.askOpen!==on)on?r.dataset.askOpen='1':delete r.dataset.askOpen}).observe(el,{attributes:true,attributeFilter:['class']});
// the tab's title holds "(1) Claude is asking" while a question is open: a page that retitles itself (review.html on
// every refresh) is put back before the next paint, its own title kept for after (QA: the title flipped every 5-10 s)
const T0=document.querySelector('title')||document.head.appendChild(document.createElement('title'));
new MutationObserver(()=>{if(A&&document.title!==TITLE){title=document.title;document.title=TITLE}}).observe(T0,{childList:true,characterData:true,subtree:true});
// askOpen(id): Home's row for another open question puts that one on the card
window.askOpen=id=>{if(!A)return;const o=id&&id!==A.id&&ALL.find(x=>x.id===id);if(o){A=o;i=0;ans=[];imgs=[];pics=[];sel=new Set();el.innerHTML='';draw()}bar.classList.remove('on');el.classList.add('on');el.querySelector('button,input')?.focus()};
let A=null,ALL=[],i=0,ans=[],imgs=[],pics=[],sel=new Set(),title=null;
// images on this answer: picked, pasted or dropped; data urls until Send
function showPics(){const b=el.querySelector('.aq-pics');if(!b)return;b.innerHTML=pics.map((p,k)=>`<span><img src="${p}" alt="attached image ${k+1}"><button data-rm="${k}" aria-label="remove image" title="remove">×</button></span>`).join('');el.querySelector('#asko')?.dispatchEvent(new Event('input'))}
function addFiles(fs){[...fs].filter(f=>TYPES.test(f.type)&&f.size<=MAXB).slice(0,MAXN-pics.length).forEach(f=>{const r=new FileReader();r.onload=()=>{if(A&&pics.length<MAXN){pics.push(r.result);showPics();el.querySelector('#asko')?.focus()}};r.readAsDataURL(f)})}
el.addEventListener('paste',e=>{const fs=[...(e.clipboardData?.files||[])];if(A&&fs.length){e.preventDefault();addFiles(fs)}});
el.addEventListener('dragover',e=>{if(!A)return;e.preventDefault();el.querySelector('.aq-card')?.classList.add('aq-drag')});
el.addEventListener('dragleave',e=>{if(!el.contains(e.relatedTarget))el.querySelector('.aq-card')?.classList.remove('aq-drag')});
el.addEventListener('drop',e=>{if(!A)return;e.preventDefault();el.querySelector('.aq-card')?.classList.remove('aq-drag');addFiles(e.dataTransfer.files)});
const TITLE='(1) Claude is asking';   // a background tab shows it in its title
// a soft two-note chime made here (no audio file); Settings turns it off (localStorage, this browser only)
function chime(){try{const c=new AudioContext();[[660,0],[880,.14]].forEach(([f,t])=>{const o=c.createOscillator(),g=c.createGain(),at=c.currentTime+t;o.frequency.value=f;g.gain.setValueAtTime(.0001,at);
  g.gain.exponentialRampToValueAtTime(.05,at+.02);g.gain.exponentialRampToValueAtTime(.0001,at+.4);o.connect(g).connect(c.destination);o.start(at);o.stop(at+.45)});setTimeout(()=>c.close(),900)}catch(e){}}
const soundOn=()=>{try{return localStorage.getItem('ave-sound')!=='0'}catch(e){return true}};
// the chime, and a system notice while the tab is hidden (permission is asked only from Settings' Turn on alerts)
function alert1(title,body){if(soundOn())chime();
  if(document.hidden&&window.Notification&&Notification.permission==='granted')try{const n=new Notification(title,{body,tag:title});n.onclick=()=>{focus();n.close()}}catch(e){}}
window.aveAlert={alert:alert1,chime,soundOn,finished,setSound(on){try{localStorage.setItem('ave-sound',on?'1':'0')}catch(e){}if(on)chime()}};
function askedNow(id){let seen=[];try{seen=JSON.parse(localStorage.getItem('ave-asked')||'[]')}catch(e){}const s=firstTime(Array.isArray(seen)?seen:[],id);
  if(s)try{localStorage.setItem('ave-asked',JSON.stringify(s))}catch(e){}return !!s}
async function send(b){try{await fetch('/ask/answer',{method:'POST',body:JSON.stringify(Object.assign({id:A.id},b))})}catch(e){}}
function close(msg){
  if(msg){el.innerHTML=`<div class="aq-card"><div class="aq-done">${esc(msg)}</div></div>`;setTimeout(()=>{if(!A)el.classList.remove('on')},1400)}else el.classList.remove('on');
  A=null;bar.classList.remove('on');flag(false);if(title!==null&&document.title===TITLE)document.title=title;title=null}
function next(v){ans[i]=v;imgs[i]=pics;pics=[];i++;sel=new Set();el.innerHTML='';if(i<A.questions.length)return draw();
  send(imgs.some(m=>m.length)?{answers:ans,images:imgs}:{answers:ans});close('Sent. Claude has your answer.')}
function draw(){
  const q=A.questions[i],n=A.questions.length,multi=!!q.multiSelect,opts=Array.isArray(q.options)?q.options:[];
  const own=el.querySelector('#asko')?.value||'';
  el.innerHTML=`<div class="aq-card"><div class="aq-top"><span>${A.about?`Claude (${esc(A.about)}) asks`:'Claude has a question'}</span><span>${n>1?`Question ${i+1} of ${n}`:''}</span></div>
  ${q.header?`<div class="aq-hd">${esc(q.header)}</div>`:''}<h2${q.header?'':' style="margin-top:14px"'}>${esc(q.question)}</h2>
  <div class="aq-opts">${opts.map((o,k)=>`<button class="aq-opt${sel.has(k)?' aq-sel':''}" data-k="${k}"${multi?` aria-pressed="${sel.has(k)}"`:''}>${multi?`<i class="aq-box">${sel.has(k)?TICK:''}</i>`:''}<div><b>${esc(o.label)}</b>${o.description?`<span>${esc(o.description)}</span>`:''}</div></button>`).join('')}</div>
  <div class="aq-other"><input id="asko" placeholder="${multi?'Other: add your own words':'Other: type your own answer'}" aria-label="Other answer"><button class="aq-clip" id="askp" aria-label="attach an image" title="attach an image (or paste or drop one)">${CLIP}</button><input type="file" id="aski" accept="image/png,image/jpeg,image/gif,image/webp" multiple hidden>${multi?'':'<button class="aq-send" id="asks" disabled>Send answer</button>'}</div>
  <div class="aq-pics"></div>
  ${multi?'<button class="aq-send aq-wide" id="asks" disabled>Send answer</button>':''}
  <div class="aq-foot"><span class="aq-hint">Or type your answer in the Claude chat</span><button class="aq-term" id="askt">Show it in Claude Code instead</button></div></div>`;
  const $o=el.querySelector('#asko'),$s=el.querySelector('#asks');
  $o.value=own;
  const value=()=>multi?[...sel].sort((a,b)=>a-b).map(k=>opts[k].label).concat($o.value.trim()?[$o.value.trim()]:[]).join(', '):$o.value.trim();
  const ready=()=>$s.disabled=!value()&&!pics.length;
  showPics();ready();
  el.querySelector('#askp').onclick=()=>el.querySelector('#aski').click();
  el.querySelector('#aski').onchange=e=>{addFiles(e.target.files);e.target.value=''};
  el.querySelector('.aq-pics').onclick=e=>{const b=e.target.closest('[data-rm]');if(b){pics.splice(+b.dataset.rm,1);showPics()}};
  el.querySelectorAll('.aq-opt').forEach(b=>b.onclick=()=>{const k=+b.dataset.k;if(!multi)return next(opts[k].label);sel.has(k)?sel.delete(k):sel.add(k);draw()});
  $o.oninput=ready;
  $o.onkeydown=e=>{if(e.key==='Enter'&&!$s.disabled)$s.click()};
  $s.onclick=()=>{if(value()||pics.length)next(value())};
  el.querySelector('#askt').onclick=()=>{send({terminal:true});close('Answer it in Claude Code.')};
  if(!bar.classList.contains('on')&&!(A.elsewhere&&!el.classList.contains('on')))el.classList.add('on');
}
async function poll(){
  let a=null,all=[],shut={};
  try{const r=await fetch('/ask'+(document.visibilityState==='visible'?'?v=1':''));if(!r.ok)return;const j=await r.json();a=j.ask;all=j.all||(a?[a]:[]);shut=j.closed||{};terminal(a?null:j.terminal)}catch(e){return}
  // answered in the Claude chat first (askhook.py reads it there): the card says so and goes
  if(A&&shut[A.id]==='chat'&&!all.some(x=>x.id===A.id)){const on=el.classList.contains('on');close(on?'Answered in the Claude chat.':null)}
  if(!a){ALL=[];if(A)close();return}
  if(document.title!==TITLE){title=document.title;document.title=TITLE}
  const was=ALL.map(x=>x.id).join();ALL=all;
  if(A&&ALL.some(x=>x.id===A.id)){if(was!==ALL.map(x=>x.id).join())flag(true),dispatchEvent(new Event('askchange'));return}
  A=a;i=0;ans=[];imgs=[];pics=[];sel=new Set();el.innerHTML='';bar.classList.remove('on');draw();flag(true);
  if(askedNow(a.id))alert1('Claude has a question',(a.about?a.about+': ':'')+((a.questions||[])[0]||{}).question);
}
poll();setInterval(poll,1000);document.addEventListener('visibilitychange',poll);
addEventListener('pagehide',()=>{try{navigator.sendBeacon('/ask/gone')}catch(e){}});   // a closed tab: Claude's next question goes to the terminal at once
})();
