// The editor's keyboard shortcuts, for the review page and home Settings (shortcuts.py serves this file).
// One table: action id, label, group, default keys, options (row: the sheet line it shares with its pair; sf: Shift is
// free, it makes the step bigger; fixed: listed, not changeable). Every key handler asks KM.is(e,'split') instead of
// comparing keys. The user's changes live in $AI_EDITOR_HOME/keys.json (only the changed actions): inlined above this
// file as KM_USER when it is served, then read again from GET /keys every 3 s, so a change made on one page reaches every
// open page. KM.editor(el) draws the shortcut editor into el.
// A combo is [Mod+][Alt+][Shift+]Key: Mod is ⌘ on a Mac and Ctrl elsewhere (either works, as before), a letter is upper
// case, a typed symbol carries its own Shift ("?", "Mod++"). shortcuts.py checks the same shape.
const KM_TABLE=[
["play","Play or pause","Playback",["Space"]],
["back","Play backward","Playback",["J"],{"row":"Back, stop, forward (again: faster)"}],
["stop","Stop","Playback",["K"],{"row":"Back, stop, forward (again: faster)"}],
["fwd","Play forward","Playback",["L"],{"row":"Back, stop, forward (again: faster)"}],
["frame_back","One frame back","Playback",["ArrowLeft",","],{"row":"One frame"}],
["frame_fwd","One frame forward","Playback",["ArrowRight","."],{"row":"One frame"}],
["sec_back","One second back","Playback",["Shift+ArrowLeft"],{"row":"One second"}],
["sec_fwd","One second forward","Playback",["Shift+ArrowRight"],{"row":"One second"}],
["edge_prev","Previous cut","Playback",["ArrowUp"],{"row":"Previous or next cut (the AI's cuts)"}],
["edge_next","Next cut","Playback",["ArrowDown"],{"row":"Previous or next cut (the AI's cuts)"}],
["slower","Slower","Playback",["["],{"row":"Slower or faster"}],
["faster","Faster","Playback",["]"],{"row":"Slower or faster"}],
["split","Split at the playhead (the picked clips, or with none picked the video under it)","Timeline",["S","Mod+B"]],
["delete","Delete what you picked (the clip under the mouse once it moves; a picked keyframe)","Timeline",["Backspace","Delete"]],
["copy","Copy","Timeline",["Mod+C"],{"row":"Copy, paste at the playhead"}],
["paste","Paste at the playhead","Timeline",["Mod+V"],{"row":"Copy, paste at the playhead"}],
["duplicate","Duplicate","Timeline",["Mod+D"]],
["lane","Pick the whole lane","Timeline",["Mod+A"]],
["trim_start","Trim start to the playhead","Timeline",["Q"],{"row":"Trim to the playhead"}],
["trim_end","Trim end to the playhead","Timeline",["W"],{"row":"Trim to the playhead"}],
["nudge_back","Nudge back","Timeline",["Alt+ArrowLeft"],{"row":"Nudge the picked clip (shift: 1 s)","sf":1}],
["nudge_fwd","Nudge forward","Timeline",["Alt+ArrowRight"],{"row":"Nudge the picked clip (shift: 1 s)","sf":1}],
["undo","Undo","Edit",["Mod+Z"],{"row":"Undo or redo"}],
["redo","Redo","Edit",["Mod+Shift+Z"],{"row":"Undo or redo"}],
["note","Write a note","Edit",["C"]],
["mark_in","Mark the start","Edit",["I"],{"row":"Mark a range"}],
["mark_out","Mark the end","Edit",["O"],{"row":"Mark a range"}],
["save_note","Save note","Edit",["Enter"],{"fixed":1}],
["cancel","Cancel or let go","Edit",["Escape"],{"fixed":1}],
["mute","Mute","Video",["M"]],
["safe","Safe zone (vertical)","Video",["Z"]],
["move","Move the picked item on the video (shift: 10 px)","Video",["ArrowLeft","ArrowRight","ArrowUp","ArrowDown"],{"fixed":1}],
["full","Full screen","View",["F"]],
["zoom_in","Zoom in","View",["Mod+=","Mod++"],{"row":"Zoom the timeline"}],
["zoom_out","Zoom out","View",["Mod+-","Mod+_"],{"row":"Zoom the timeline"}],
["fit","Fit the timeline","View",["Shift+Z"]],
["help","This help","View",["?"]]
];
// presets: only the actions with a sure equivalent there, the rest stay at cooked.'s. CapCut splits with ⌘B (cooked.
// already has its Q / W trims, ⌘C / ⌘V / ⌘D and the arrows); Premiere's Add Edit is ⌘K and Resolve's razor ⌘B, Premiere
// zooms the timeline with = and - and fits it with \, Resolve fits with Shift+Z. Both keep J K L, I O and Q W as here.
const KM_PRESETS=[["cooked","cooked.",{}],["capcut","CapCut",{"split":["Mod+B"]}],
 ["premiere","Premiere Pro / Resolve",{"split":["Mod+K","Mod+B"],"zoom_in":["=","Mod+=","Mod++"],"zoom_out":["-","Mod+-","Mod+_"],"fit":["\\","Shift+Z"]}]];
const KM=(()=>{
  const MAC=/Mac|iPhone|iPad/.test(navigator.platform),A={},eds=[];
  KM_TABLE.forEach(([id,label,group,keys,o])=>A[id]=Object.assign({id,label,group,keys},o));
  let user=(typeof KM_USER==='object'&&KM_USER)||{},rec=null,note=null,pre=null,find='';   // rec {id,i}: recording; note: under that row
  const NAMED=new Set(['Space','Enter','Escape','Tab','Backspace','Delete','ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End','PageUp','PageDown','Insert',...Array.from({length:12},(_,i)=>'F'+(i+1))]);
  const RES={'Mod+Q':'quits the browser','Mod+W':'closes the tab','Mod+T':'opens a new tab','Mod+R':'reloads the page','Mod+L':'goes to the address bar','Mod+Tab':'switches apps'};
  const keys=id=>user[id]||A[id].keys,strip=c=>c.replace('Shift+',''),same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
  const norm=o=>JSON.stringify(Object.keys(o).sort().map(k=>[k,o[k]]));
  function comboOf(e){let k=e.key;if(!k||k==='Unidentified'||k==='Dead')return null;
    if(k===' ')k='Space';else if(/^[a-z]$/i.test(k))k=k.toUpperCase();
    else if(e.altKey&&k.length===1&&/^(Key[A-Z]|Digit\d)$/.test(e.code))k=e.code.slice(-1);   // ⌥ on a Mac types a symbol
    else if(k.length>1&&!NAMED.has(k))return null;
    return (e.metaKey||e.ctrlKey?'Mod+':'')+(e.altKey?'Alt+':'')+(e.shiftKey&&(k.length>1||/^[A-Z]$/.test(k))?'Shift+':'')+k}
  const hits=(id,c,sf)=>(sf||A[id].sf)?keys(id).some(x=>strip(x)===strip(c)):keys(id).includes(c);
  function is(e,id){const c=comboOf(e);return !!c&&!!A[id]&&hits(id,c)}
  const KN={Space:'space',Enter:'enter',Escape:'esc',Tab:'tab',ArrowLeft:'←',ArrowRight:'→',ArrowUp:'↑',ArrowDown:'↓',Home:'home',End:'end',PageUp:'page up',PageDown:'page down',Insert:'insert',Backspace:MAC?'⌫':'backspace',Delete:MAC?'⌦':'delete'};
  function fmt(c){const m=c.match(/^((?:Mod\+)?(?:Alt\+)?(?:Shift\+)?)(.+)$/),ms=m[1],k=m[2],n=KN[k]||k;
    if(!ms)return /^[A-Z]$/.test(k)?k.toLowerCase():n;
    if(MAC)return (ms.includes('Alt')?'⌥':'')+(ms.includes('Shift')?'⇧':'')+(ms.includes('Mod')?'⌘':'')+n;
    return [ms.includes('Mod')&&'Ctrl',ms.includes('Alt')&&'Alt',ms.includes('Shift')&&'Shift',n.length>1&&!KN[k]?n:n[0].toUpperCase()+n.slice(1)].filter(Boolean).join('+')}
  // keys stay off while recording, while a dialog, a popover or Claude's question is open, and while the editor shows
  const shown=()=>eds.some(el=>el.isConnected&&el.getClientRects().length>0);
  function off(){try{if(document.querySelector('dialog[open],:popover-open'))return true}catch(x){if(document.querySelector('dialog[open]'))return true}
    return !!document.documentElement.dataset.askOpen||shown()}
  async function post(b){let r,j={};try{r=await fetch('/keys',{method:'POST',body:JSON.stringify(b)});j=await r.json()}catch(x){}
    if(r&&r.ok&&j.keys){user=j.keys;return null}return j.error||'That did not save.'}
  setInterval(async()=>{try{const r=await fetch('/keys');if(!r.ok)return;const j=await r.json();
    if(!same(j.keys||{},user)){user=j.keys||{};if(!rec&&!note&&!pre)draw()}}catch(x){}},3000);
  // ---- the editor
  const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const soon=()=>setTimeout(draw);   // after the click is done: a page's click-outside check still finds the target
  function rows(){const out=[];for(const a of Object.values(A)){const l=out[out.length-1];if(a.row&&l&&l.row===a.row)l.acts.push(a);else out.push({row:a.row,label:a.row||a.label,group:a.group,acts:[a]})}return out}
  const presetOf=()=>(KM_PRESETS.find(p=>norm(p[2])===norm(user))||['own'])[0];
  function chip(a,c,i){const r=rec&&rec.id===a.id&&rec.i===i;
    return a.fixed?`<kbd class="km-k fx">${esc(fmt(c))}</kbd>`:`<button type="button" class="km-k${r?' rec':''}" data-a="${a.id}" data-i="${i}" title="${esc(a.label)}. Click to change.">${r?'Press keys':esc(fmt(c))}</button>`}
  function noteHtml(){if(note.msg)return `<div class="km-note">${esc(note.msg)}</div>`;
    return `<div class="km-note">${esc(fmt(note.combo))} is already ${esc(A[note.other].label)}. Use it here instead?<span><button type="button" data-sw>Swap</button><button type="button" data-nc>Cancel</button></span></div>`}
  function rowHtml(r){const ch=r.acts.some(a=>user[a.id]),ids=r.acts.map(a=>a.id);
    const ks=r.acts.map(a=>{const k=keys(a.id),on=rec&&rec.id===a.id;
      return `<span class="km-a">${k.length?k.map((c,i)=>chip(a,c,i)).join(''):`<button type="button" class="km-k none${on?' rec':''}" data-a="${a.id}" data-i="0" title="${esc(a.label)}">${on?'Press keys':'Change'}</button>`}</span>`}).join('');
    const n=note&&ids.includes(note.id)?noteHtml():rec&&ids.includes(rec.id)?'<div class="km-note">Press the new keys. Esc cancels, backspace clears it.</div>':'';
    return `<div class="km-row"><span class="km-l">${esc(r.label)}</span><span class="km-ks">${ks}</span>${ch?`<button type="button" class="km-rs" data-rs="${ids.join(' ')}">Reset</button>`:'<i></i>'}${n}</div>`}
  function draw(){for(const el of eds){if(!el.isConnected)continue;if(!el._km)wire(el);
    const q=find.trim().toLowerCase(),rs=rows().filter(r=>!q||[r.label,...r.acts.map(a=>a.label),...r.acts.flatMap(a=>keys(a.id).map(fmt))].some(s=>s.toLowerCase().includes(q)));
    let g='',h='';for(const r of rs){if(r.group!==g){g=r.group;h+=`<div class="km-grp">${g}</div>`}h+=rowHtml(r)}
    el.querySelector('.km-list').innerHTML=h||'<div class="km-none">No shortcut has that name.</div>';
    const p=presetOf(),s=el.querySelector('.km-pre');s.innerHTML=KM_PRESETS.map(([k,n])=>`<option value="${k}">${esc(n)}</option>`).join('')+(p==='own'?'<option value="own" disabled>Your own</option>':'');s.value=pre||p;
    const pn=pre&&KM_PRESETS.find(x=>x[0]===pre)[1];
    el.querySelector('.km-pmsg').innerHTML=pre?`<div class="km-note">This replaces your changes with the ${esc(pn)} keys.<span><button type="button" data-pok>Use them</button><button type="button" data-pno>Cancel</button></span></div>`:'';
    el.querySelector('.km-all').disabled=!Object.keys(user).length;const f=el.querySelector('.km-find');if(document.activeElement!==f)f.value=find}}
  async function set(id,list){rec=null;note=null;const err=await post({action:id,combo:list});if(err)note={id,msg:err};draw()}
  async function swap(){const {id,i,combo,other}=note,mine=keys(id).slice(),old=mine[i];if(i<mine.length)mine[i]=combo;else mine.push(combo);
    const theirs=[...new Set(keys(other).map(y=>(A[id].sf||A[other].sf?strip(y)===strip(combo):y===combo)?old:y).filter(Boolean))];
    note=null;const err=await post({action:other,combo:theirs})||await post({action:id,combo:[...new Set(mine)]});if(err)note={id,msg:err};draw()}
  async function apply(k){pre=null;const err=await post({replace:KM_PRESETS.find(x=>x[0]===k)[2]});if(err)note={id:'play',msg:err};draw()}
  function wire(el){el._km=1;el.classList.add('km');
    el.innerHTML=`<div class="km-top"><input class="km-find" type="search" placeholder="Search shortcuts" aria-label="search shortcuts" autocomplete="off" spellcheck="false"><select class="km-pre" aria-label="key preset"></select></div><div class="km-pmsg"></div><div class="km-list"></div><div class="km-foot"><button type="button" class="km-all">Reset all</button></div>`;
    el.querySelector('.km-find').addEventListener('input',e=>{find=e.target.value;draw()});
    el.querySelector('.km-pre').addEventListener('change',e=>{const k=e.target.value;if(k===presetOf())return;rec=null;note=null;if(Object.keys(user).length){pre=k;draw()}else apply(k)});
    el.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;
      if(b.dataset.a){rec={id:b.dataset.a,i:+b.dataset.i};note=null;pre=null;return soon()}
      if(b.dataset.rs!=null){rec=note=null;(async()=>{for(const id of b.dataset.rs.split(' '))if(user[id])await post({reset:id});draw()})();return soon()}
      if(b.classList.contains('km-all')){rec=note=null;post({reset_all:true}).then(draw);return}
      if(b.dataset.sw!=null)return swap();if(b.dataset.nc!=null){note=null;return soon()}
      if(b.dataset.pok!=null)return apply(pre);if(b.dataset.pno!=null){pre=null;return soon()}})}
  // recording: before every other key handler (window, capture). Esc cancels, Backspace clears that key
  addEventListener('keydown',e=>{if(!rec&&!note&&!pre)return;if(!shown()){rec=note=pre=null;soon();return}   // the editor was closed mid-question
    if(!rec){if(e.key==='Escape'){e.preventDefault();e.stopImmediatePropagation();note=null;pre=null;draw()}return}   // a clash or a preset asking: Esc says no
    e.preventDefault();e.stopImmediatePropagation();if(['Shift','Meta','Control','Alt','CapsLock','Fn','OS'].includes(e.key))return;
    const a=A[rec.id],plain=!(e.metaKey||e.ctrlKey||e.altKey||e.shiftKey);
    if(e.key==='Escape'&&plain){rec=null;note=null;return draw()}
    if(e.key==='Backspace'&&plain){const i=rec.i;return set(a.id,keys(a.id).filter((_,j)=>j!==i))}
    let c=comboOf(e);if(!c)return;if(a.sf)c=strip(c);
    if(RES[c]){note={id:a.id,msg:`${fmt(c)} ${RES[c]}. Pick another.`};return draw()}
    if(hits(a.id,c,a.sf)&&keys(a.id)[rec.i]===c){rec=null;note=null;return draw()}
    const o=Object.values(A).find(x=>x.id!==a.id&&!x.fixed&&hits(x.id,c,a.sf));
    if(o){note={id:a.id,i:rec.i,combo:c,other:o.id};rec=null;return draw()}
    const k=keys(a.id).slice();if(rec.i<k.length)k[rec.i]=c;else k.push(c);set(a.id,[...new Set(k)])},true);
  addEventListener('pointerdown',e=>{if(rec&&!e.target.closest('.km-k')){rec=null;note=null;soon()}},true);   // a click anywhere else stops recording
  const st=document.createElement('style');st.textContent=`
.km{display:flex;flex-direction:column;gap:10px;font-size:13px;line-height:18px;color:var(--muted,var(--t3))}
.km-top{display:flex;gap:8px}
.km-find,.km-pre{height:32px;border:1px solid var(--line2,var(--ring));border-radius:8px;background:var(--panel,var(--card));color:var(--ink);font:inherit;font-size:13px}
.km-find{flex:1;min-width:0;padding:0 10px}.km-pre{padding:0 8px;max-width:50%}
.km-find:focus,.km-pre:focus{outline:none;border-color:var(--ink)}
.km-grp{padding:12px 0 4px;font-size:12px;line-height:16px;font-weight:600;color:var(--ink)}
.km-row{display:grid;grid-template-columns:minmax(0,1fr) auto 40px;align-items:center;gap:4px 12px;min-height:34px;padding:4px 0;border-top:1px solid var(--chip,var(--line))}
.km-ks{display:flex;gap:12px;flex-wrap:wrap;justify-content:flex-end}.km-a{display:flex;gap:4px}
.km-k{min-width:26px;height:24px;padding:0 7px;border:1px solid var(--line2,var(--ring));border-radius:6px;background:none;color:var(--ink);font:inherit;font-size:12px;line-height:22px;text-align:center;cursor:pointer;white-space:nowrap}
.km-k:hover{border-color:var(--ink)}.km-k.rec{border-style:dashed;border-color:var(--ink);color:var(--muted,var(--t3))}.km-k.none{color:var(--muted,var(--t3))}
kbd.km-k.fx{border-color:transparent;cursor:default;padding:0 3px;min-width:0}
.km-rs,.km-all{border:0;background:none;padding:0;font:inherit;font-size:12px;color:var(--muted,var(--t3));cursor:pointer;text-align:right}
.km-rs:hover,.km-all:hover:not(:disabled){color:var(--ink)}.km-all:disabled{opacity:.4;cursor:default}
.km-note{grid-column:1/-1;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:2px 0 4px;color:var(--ink)}
.km-note span{display:flex;gap:6px;flex-shrink:0}
.km-note button{height:26px;padding:0 10px;border:1px solid var(--line2,var(--ring));border-radius:6px;background:none;color:var(--ink);font:inherit;font-size:12px;cursor:pointer}
.km-note button:first-child{background:var(--ink);border-color:var(--ink);color:var(--onink)}
.km-pmsg:empty{display:none}.km-none{padding:12px 0}.km-foot{display:flex;justify-content:flex-end;padding-top:4px}`;
  document.head.appendChild(st);
  return {is,off,fmt,keys,editor(el){eds.push(el);draw()},recording:()=>!!rec}})();
