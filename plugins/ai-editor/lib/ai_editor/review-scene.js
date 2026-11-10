// The edit page on a scene (SCENE.md): when GET /scene answers, the player is CookedLive.mountScene and every item on
// screen is picked, moved, resized, rotated, cropped, trimmed and deleted here, CapCut's way. Each change is made on a
// copy of the scene first (drawn at once with player.update), then sent as ops to POST /scene/ops, the diff of the scene
// before and after (one undo, its journal id `j` with the page's edPush / /timeline/restore). review.html calls SC.check()
// on every live fetch, SC.tl() for the timeline rows and SC.key() first on every key. Loaded before review.html's script:
// it only uses that script's globals ($, v, S, post, edPush, ...) once it runs.
var SC={on:false,s:null,pl:null,sel:new Set(),crop:false,edit:null,last:'',busy:0,mov:0};
{const st=document.createElement('style');st.textContent=`
body.scene #tside{display:flex}body.scene.scnoside #tside{display:none}body.scene .left{padding-left:16px;padding-right:16px}#railinsp{display:none}body.scene #railinsp{display:flex}   /* the panel stays put while open, so a pick never moves the video; its × closes it until a rail tool or Properties opens it again */
#scl{display:none;width:100%;height:100%;background:var(--film)}body.scene #scl{display:block}body.scene #live,body.scene #v{display:none!important}
body.scene #hits,body.scene #tlayer,body.scene #tedit,body.scene #clayer,body.scene #cplayer{display:none!important}
#scover{display:none;position:absolute;left:0;top:0;transform-origin:0 0;z-index:6;touch-action:none}body.scene #scl,#scover{-webkit-user-select:none;user-select:none}#scover .sced{-webkit-user-select:text;user-select:text}   /* a pick never selects the words: only the in-place editor does */body.scene #scover{display:block}
.scbox{position:absolute;outline:calc(1.5px / var(--k)) solid #FFFFFF;box-shadow:0 0 0 calc(2.5px / var(--k)) rgba(0,0,0,.35);pointer-events:none}.scbox.sub{outline-style:dashed}
.scbox i{position:absolute;width:calc(12px / var(--k));height:calc(12px / var(--k));margin:calc(-6px / var(--k)) 0 0 calc(-6px / var(--k));border-radius:calc(3px / var(--k));background:#FFFFFF;box-shadow:0 0 0 calc(1px / var(--k)) rgba(0,0,0,.45);pointer-events:auto}
.scbox i::after{content:"";position:absolute;inset:calc(-6px / var(--k))}
.scbox i[data-h=e]::after,.scbox i[data-h=w]::after{inset:0 calc(-6px / var(--k))}.scbox i[data-h=n]::after,.scbox i[data-h=s]::after{inset:calc(-6px / var(--k)) 0}   /* a side handle draws over the corners but takes no more than its own height: on a one-line text both stay reachable */
.scbox i[data-h=nw],.scbox i[data-h=se]{cursor:nwse-resize}.scbox i[data-h=ne],.scbox i[data-h=sw]{cursor:nesw-resize}.scbox i[data-h=n],.scbox i[data-h=s]{cursor:ns-resize}.scbox i[data-h=e],.scbox i[data-h=w]{cursor:ew-resize}
.scbox i[data-h=rot]{border-radius:50%;cursor:grab}.scbox i[data-h=rot]::before{content:"";position:absolute;left:50%;top:100%;width:calc(1.5px / var(--k));height:calc(18px / var(--k));background:#FFFFFF}
.scbox i[data-h=rot].dn::before{top:auto;bottom:100%}.scbox.crop i{background:#FFD60A}.scghost{position:absolute;outline:calc(1px / var(--k)) dashed rgba(255,255,255,.6);background:rgba(0,0,0,.35);pointer-events:none}
.scg{position:absolute;background:#FF2D92;pointer-events:none}
.sced{position:absolute;outline:calc(1.5px / var(--k)) solid #0A84FF;white-space:pre-wrap;overflow-wrap:anywhere;caret-color:#FFFFFF;cursor:text}
.eitem.sc{cursor:grab;overflow:visible}.eitem.sc>span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0;pointer-events:none}.eitem.sc.sel{outline:2px solid #FFFFFF;outline-offset:1px;z-index:2}
.eitem.sc::before,.eitem.sc::after{content:"";position:absolute;top:0;bottom:0;width:8px;cursor:ew-resize;z-index:2}.eitem.sc::before{left:-1px}.eitem.sc::after{right:-1px}
.eitem.sc img{height:18px;width:auto;max-width:32px;border-radius:3px;margin-right:4px;pointer-events:none}.eitem.sc.shp{background:#4A3B2A;border-color:#8A6A44;color:#FFFFFF;padding:0 6px}
.eitem.sc.cut0{border-left:3px solid #FFD60A}.sck{display:none;position:absolute;top:50%;width:7px;height:7px;margin:-3.5px 0 0 -3.5px;transform:rotate(45deg);background:#FFD60A;pointer-events:none}.eitem.sc.sel .sck{display:block}   /* keys show on the picked item only, as CapCut does */
.scj{position:absolute;top:0;bottom:0;width:2px;margin-left:-1px;z-index:4;background:#FFD60A;pointer-events:none}.scj::after{content:"";position:absolute;left:-5px;top:-8px;width:12px;height:16px;pointer-events:auto;cursor:help}   /* a 2 px line on each AI cut; its top end takes the hover, the edges stay free to trim */
.scj>b{display:none;position:absolute;left:-5px;top:-7px;width:12px;height:7px;border-radius:3px 3px 0 0;background:#FFD60A;pointer-events:none}.scj.t>b,.scj:hover>b{display:block}   /* the tab: on hover, or when the joins are far enough apart (zoomed in) */
.scj>span{display:none;position:fixed;font-style:normal;z-index:9;width:max-content;max-width:300px;flex-direction:column;gap:6px;padding:10px 12px;border-radius:8px;background:var(--panel);border:1px solid var(--line2);box-shadow:0 8px 24px rgba(0,0,0,.4);font-size:12px;font-weight:500;line-height:16px;color:var(--strong);white-space:normal;cursor:default}
.scj:hover>span{display:flex}.scj>span{pointer-events:auto}.scj em{font-style:normal;color:var(--muted)}.scj>span::after{content:"";position:absolute;left:0;right:0;top:100%;height:10px}.scj button{align-self:flex-start;height:28px;padding:0 10px;border-radius:7px;border:1px solid var(--line2);font-size:12px;font-weight:600;color:var(--ink)}.scj button:hover{border-color:var(--ink)}
#edtracks[data-ld="scv"] .newl[data-row="scv"],#edtracks[data-ld="sca"] .newl[data-row="sca"]{display:flex}#edtracks[data-ld] .edwrap{--nl:30px}.etrack.scdrop{outline:2px dashed var(--ink);outline-offset:-2px}
.scadd{display:flex;flex-wrap:wrap;gap:4px;padding:8px 0 0 4px}.scadd button{height:24px;padding:0 7px;white-space:nowrap;border-radius:6px;border:1px solid var(--line2);font-size:11px;font-weight:600;color:var(--body)}.scadd button:hover{border-color:var(--ink);color:var(--ink)}
/* the inspector, CapCut desktop's right panel in cooked.'s tokens: tabs, a few visual controls per tab, sliders with the
   number beside them, one 24 px keyframe column at the end of each animatable row, the rest in folds */
#ibody .ihead{margin:0 0 12px}
.sctabs{display:flex;gap:2px;margin:0 0 4px;border-bottom:1px solid var(--line)}.sctabs button{flex:1;min-width:0;height:36px;font-size:12px;font-weight:500;color:var(--muted);border-bottom:2px solid transparent;margin-bottom:-1px;white-space:nowrap}
.sctabs button:hover{color:var(--ink)}.sctabs button.on{color:var(--strong);font-weight:600;border-bottom-color:var(--ink)}
#ibody .scgrp{display:flex;flex-direction:column;gap:12px;padding:14px 0;border-bottom:1px solid var(--line)}#ibody .scfold .scgrp{border:0;padding-top:4px}
#ibody details.scfold{border-bottom:1px solid var(--line)}
#ibody details>summary{display:flex;align-items:center;justify-content:space-between;height:40px;list-style:none;cursor:pointer;font-size:12px;line-height:16px;font-weight:500;color:var(--muted);-webkit-user-select:none;user-select:none}
#ibody details>summary:hover{color:var(--ink)}#ibody details>summary::-webkit-details-marker{display:none}#ibody details>summary::after{content:"";width:5px;height:5px;margin-right:10px;border:solid currentColor;border-width:0 1.5px 1.5px 0;transform:rotate(-45deg)}
#ibody details[open]>summary::after{transform:translateY(-2px) rotate(45deg)}
.scc{display:flex;flex-direction:column;gap:6px}.sch{display:flex;align-items:center;justify-content:space-between;font-size:12px;line-height:16px;color:var(--muted)}
.scrow{display:flex;align-items:center;gap:8px;min-height:32px}.sct{flex:1;min-width:0;font-size:12px;color:var(--muted);white-space:nowrap}.scline .sct{flex:1}.scline .scf{flex:0 0 96px}
.scf{flex:1 1 0;min-width:0;display:flex;align-items:center;gap:6px;height:32px;padding:0 8px;border-radius:8px;background:var(--chip);border:1px solid transparent;font-size:13px;color:var(--strong)}
.scf:hover{border-color:var(--line)}.scf:focus-within{border-color:var(--line2)}.scl{flex-shrink:0;font-size:12px;color:var(--muted);-webkit-user-select:none;user-select:none}.scl[data-scrub]{cursor:ew-resize}
.scrow>.scf.scn{flex:0 0 72px}.scrow .sct+.scf.scn,.scrow .sct~.scf.scn{flex:0 0 72px}
.scf input[type=number]{flex:1;min-width:0;width:100%;height:100%;border:0;padding:0;background:none;color:inherit;font:inherit;font-variant-numeric:tabular-nums;outline:none;-moz-appearance:textfield;text-align:right}
.scf input::-webkit-inner-spin-button,.scf input::-webkit-outer-spin-button{-webkit-appearance:none;margin:0}.scf em{font-style:normal;font-size:12px;color:var(--quiet)}
.scf.sel{position:relative}.scf select{flex:1;min-width:0;height:100%;border:0;padding:0 14px 0 0;background:none;color:inherit;font:inherit;outline:none;-webkit-appearance:none;appearance:none;cursor:pointer}
.scf.sel::after{content:"";position:absolute;right:11px;top:50%;width:5px;height:5px;margin-top:-4px;border:solid var(--muted);border-width:0 1.5px 1.5px 0;transform:rotate(45deg);pointer-events:none}.scf select option{background:var(--panel);color:var(--strong)}
.scrg{flex:1;min-width:0;height:16px;margin:0;-webkit-appearance:none;appearance:none;background:none;cursor:pointer}
.scrg::-webkit-slider-runnable-track{height:3px;border-radius:2px;background:var(--track)}.scrg::-webkit-slider-thumb{-webkit-appearance:none;width:14px;height:14px;margin-top:-5.5px;border-radius:50%;background:var(--ink);border:2px solid var(--panel);box-shadow:0 0 0 1px var(--line2)}
.scrg:focus{outline:none}.scrg:focus-visible::-webkit-slider-thumb{box-shadow:0 0 0 3px var(--line2)}
.sctile{display:grid;place-items:center;border-radius:8px;background:var(--chip);color:var(--strong);font-size:12px;outline:1.5px solid transparent;outline-offset:-1.5px}.sctile:hover{outline-color:var(--line2)}.sctile.on{outline-color:var(--ink)}
.sctile em{font-style:normal;font-size:11px;line-height:14px;color:var(--muted)}.sctile.on em{color:var(--strong)}
.sclooks{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.sclook{height:64px;gap:2px;padding:8px 0 6px;grid-template-rows:1fr auto}
.sclook span{font-family:'TikTok Sans',system-ui,sans-serif;font-weight:700;font-size:15px;line-height:20px;color:#FFFFFF;padding:0 5px}.sclook{background:#3A3836}.sclook em{color:rgba(255,255,255,.7)}.sclook.on em{color:#FFFFFF}
.scl-outline{-webkit-text-stroke:3px #000;paint-order:stroke fill}.scl-box,.scl-block{background:#FFFFFF;color:#000!important;border-radius:4px}.scl-block{padding:3px 8px!important;border-radius:6px!important}.scl-dark{background:#000;border-radius:4px}.scl-shadow{text-shadow:0 2px 6px rgba(0,0,0,.9)}
#ibody .sclook.on{outline-color:var(--ink)}
.scfonts{display:grid;grid-template-columns:1fr 1fr;gap:6px}.scfonts .sctile{height:34px;font-size:14px;font-weight:600;padding:0 8px}.scfonts .sctile span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
.scseg{display:flex;gap:2px;padding:2px;border-radius:8px;background:var(--chip)}.scseg .sctile{flex:1;height:28px;padding:0 10px;background:none;border-radius:6px;outline:0;color:var(--muted);font-weight:500}.scseg .sctile:hover{color:var(--ink)}
.scseg .sctile.on{background:var(--panel);color:var(--strong);box-shadow:0 1px 2px rgba(0,0,0,.18)}.scseg svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:1.6;stroke-linecap:round}.scseg.scfull{width:100%}
.scrow .scseg{flex:0 0 auto}.scrow .scf.sel{flex:1}
.scsws{display:flex;gap:8px;flex-wrap:wrap}.scsw{position:relative;width:26px;height:26px;border-radius:50%;background:var(--c);box-shadow:inset 0 0 0 1px rgba(128,128,128,.45);cursor:pointer}
.scsw.on::after{content:"";position:absolute;inset:-4px;border-radius:50%;box-shadow:0 0 0 1.5px var(--ink)}.scown{background:conic-gradient(#FF3B30,#FFD60A,#34C759,#0A84FF,#AF52DE,#FF3B30)}
.scown::before{content:"";position:absolute;inset:6px;border-radius:50%;background:var(--c);box-shadow:0 0 0 2px var(--panel)}.scown input{position:absolute;inset:0;opacity:0;width:100%;height:100%;cursor:pointer;padding:0;border:0}
.scchips{display:flex;gap:6px}.scchips .sctile{flex:1;height:28px;font-weight:500}
.scanims{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.scanims .sctile{height:72px;padding:8px 0 6px;grid-template-rows:1fr auto;gap:4px}
.scap{display:grid;place-items:center;width:52px;height:34px;border-radius:6px;background:var(--panel);overflow:hidden}.scap b{font-size:13px;font-weight:700;color:var(--strong)}
.sctile:hover .sca-fade.in,.sctile.on .sca-fade.in{animation:scaFi 1.2s infinite}.sctile:hover .sca-fade.out,.sctile.on .sca-fade.out{animation:scaFi 1.2s infinite reverse}
.sctile:hover .sca-pop.in,.sctile.on .sca-pop.in{animation:scaPop 1.2s infinite}.sctile:hover .sca-pop.out,.sctile.on .sca-pop.out{animation:scaPop 1.2s infinite reverse}
.sctile:hover .sca-slide-up.in,.sctile.on .sca-slide-up.in{animation:scaUp 1.2s infinite}.sctile:hover .sca-slide-up.out,.sctile.on .sca-slide-up.out{animation:scaUp 1.2s infinite reverse}
.sctile:hover .sca-cut,.sctile.on .sca-cut{animation:scaCut 1.2s steps(1) infinite}.sca-none{opacity:.35}
@keyframes scaFi{0%{opacity:0}60%,100%{opacity:1}}@keyframes scaPop{0%{transform:scale(.3)}45%{transform:scale(1.15)}60%,100%{transform:scale(1)}}@keyframes scaUp{0%{transform:translateY(16px);opacity:0}60%,100%{transform:none;opacity:1}}@keyframes scaCut{0%{opacity:0}35%,100%{opacity:1}}
.scswr{flex:1;min-width:0;display:flex;align-items:center;justify-content:space-between;height:32px;font-size:12px;color:var(--muted);cursor:pointer}
.scswi{-webkit-appearance:none;appearance:none;position:relative;flex-shrink:0;width:28px;height:16px;margin:0;border-radius:8px;background:var(--track);cursor:pointer;transition:background .15s}
.scswi::before{content:"";position:absolute;left:2px;top:2px;width:12px;height:12px;border-radius:50%;background:var(--quiet);transition:transform .15s,background .15s}.scswi:checked{background:var(--ink)}.scswi:checked::before{transform:translateX(12px);background:var(--onink)}
#ibody textarea.scta{width:100%;min-height:60px;border:1px solid transparent;border-radius:8px;background:var(--chip);color:var(--strong);padding:8px;font:inherit;font-size:13px;line-height:18px;resize:vertical;outline:none}#ibody textarea.scta:focus{border-color:var(--line2)}
#ibody .scgrp .ifull,#ibody #scdel{height:32px;font-size:12px;font-weight:500;color:var(--body)}#ibody #scdel{margin-top:14px}#ibody .scgrp .ifull:hover,#ibody #scdel:hover{color:var(--ink)}
.scsk{width:24px;flex-shrink:0}.sckey{width:24px;height:24px;flex-shrink:0;border-radius:6px;display:grid;place-items:center;color:var(--quiet)}.sckey::before{content:"";width:7px;height:7px;transform:rotate(45deg);border:1.5px solid currentColor}.sckey.has{color:var(--strong)}.sckey.on{color:#FFD60A}.sckey.on::before{background:currentColor}.sckey:hover{background:var(--hover);color:var(--ink)}.sckey.on:hover{color:#FFD60A}
#scl video{background:transparent}   /* the page's video{background} would paint a clip with alpha black */
.eitem.sc .scby{position:absolute;right:3px;top:3px;width:11px;height:11px;color:#D97757;pointer-events:none;filter:drop-shadow(0 0 1px rgba(0,0,0,.6))}
/* the picked clip's keyframe lane: a thin row per animated property under its track, a diamond per key */
.ehd.sckh{height:18px;margin-top:2px;padding-left:14px;font-size:11px;font-weight:500}.sckl{position:relative;height:18px;margin-top:2px;border-radius:4px;background:rgba(255,214,10,.06)}
.sckl.none{display:flex;align-items:center;padding-left:8px;font-size:11px;color:var(--muted);cursor:pointer}.sckl.none:hover{color:var(--ink)}
.scln{position:absolute;top:50%;height:1px;background:rgba(255,214,10,.35);pointer-events:none}
.sckd{position:absolute;top:50%;width:9px;height:9px;margin:-4.5px 0 0 -4.5px;transform:rotate(45deg);border-radius:1px;background:#FFD60A;cursor:grab;z-index:3}.sckd::after{content:"";position:absolute;inset:-5px}
.sckd:hover{background:#FFFFFF}.sckd.on{background:#FFFFFF;box-shadow:0 0 0 2px #FFD60A}
/* the AI's cuts on the ruler: a yellow tick each, at any zoom; hover for what was taken out */
body.scene .edleft{width:156px}.eruler .scj{top:auto;bottom:0;height:6px;width:3px;margin-left:-1.5px;border-radius:1px;z-index:5}.eruler .scj::after{left:-5px;top:-4px;width:13px;height:16px;cursor:pointer}.eruler .scj>b{display:none!important}.eruler .scj>span{top:auto;border-left:1px solid var(--line2)}
#sccuts{position:fixed;z-index:30;width:340px;max-height:60vh;overflow:auto;padding:6px;border-radius:12px;background:var(--raise,var(--panel));border:1px solid var(--line);box-shadow:var(--pop,0 8px 24px rgba(0,0,0,.4))}
#sccuts h4{margin:6px 8px 6px;font-size:12px;line-height:16px;font-weight:600;color:var(--strong)}#sccuts h4 em{font-style:normal;font-weight:500;color:var(--muted)}
.sccr{display:grid;grid-template-columns:52px 1fr auto;gap:2px 8px;align-items:center;padding:6px 8px;border-radius:8px;cursor:pointer;font-size:12px;line-height:16px}.sccr:hover,.sccr.cur{background:var(--hover)}
.sccr .num{color:var(--muted)}.sccr b{font-weight:600;color:var(--strong)}.sccr em{grid-column:2/3;font-style:normal;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sccr button{grid-row:1/3;grid-column:3;height:26px;padding:0 9px;border-radius:7px;border:1px solid var(--line2);font-size:12px;font-weight:600;color:var(--ink)}.sccr button:hover{border-color:var(--ink)}
.tzoom .scbtn{display:none}body.scene .tzoom .scbtn{display:grid;place-items:center}body.scene #scdelb{margin-right:6px}.tzoom .scbtn svg{width:15px;height:15px}
.sckds{border:1px solid rgba(255,214,10,.4);border-radius:8px;padding:4px 8px;margin-bottom:8px}
/* an audio clip: its waveform, its fades shaded, a handle on each top corner to drag a fade (on the picked clip, or on hover) */
.eitem.sc.snd svg.wv{pointer-events:none}.scfd{position:absolute;top:0;bottom:0;background:rgba(0,0,0,.45);pointer-events:none}.scfd.in{left:0;clip-path:polygon(0 0,100% 0,0 100%)}.scfd.out{right:0;clip-path:polygon(0 0,100% 0,100% 100%)}
.scfh{display:none;position:absolute;top:-4px;width:9px;height:9px;margin-left:-4.5px;border-radius:50%;background:#FFFFFF;box-shadow:0 0 0 1px rgba(0,0,0,.5);cursor:ew-resize;z-index:3}.scfh[data-fd=out]{margin:0 -4.5px 0 0}.scfh::after{content:"";position:absolute;inset:-5px}
.eitem.sc.snd.sel .scfh,.eitem.sc.snd:hover .scfh{display:block}
/* the volume line on a clip with sound (CapCut's, Premiere's): drag it up or down; between the trim edges, under the fade handles */
.eitem.sc.vid svg.wv{position:absolute;left:0;right:0;bottom:1px;width:100%;height:60%;opacity:.7;pointer-events:none}
.scvl{position:absolute;left:8px;right:8px;height:11px;margin-top:-5.5px;cursor:ns-resize;z-index:2}.scvl::before{content:"";position:absolute;left:0;right:0;top:4.75px;height:1.5px;border-radius:1px;background:rgba(255,255,255,.85);box-shadow:0 0 2px rgba(0,0,0,.5)}
.scvl:hover::before,.scvl.on::before{background:#FFFFFF;top:4.5px;height:2px}
/* clips with sound sit on taller rows, CapCut's: the waveform fills the height, the volume line always across it */
.etrack.tall,.ehd.tall{height:46px}.etrack.tall>.eitem{height:42px}.etrack.tall>.eitem.sc.vid svg.wv{height:70%}.etrack.tall>.eitem.sc>span{position:absolute;left:6px;bottom:3px;right:6px;line-height:14px}
.eitem.sc .scvlab{position:absolute;left:50%;bottom:calc(100% + 4px);transform:translateX(-50%);padding:2px 6px;border-radius:5px;background:#000000;border:1px solid var(--line2);color:#FFFFFF;font-size:11px;line-height:14px;font-weight:600;font-style:normal;white-space:nowrap;pointer-events:none;z-index:6}`;document.head.appendChild(st)}
// the mark on a clip Claude added or changed (scene.py ops, by "claude"), until the user changes it
const SCBY='<svg class="scby" viewBox="0 0 24 24" aria-label="Claude made this"><title>Claude made this</title><path fill="currentColor" d="M12 1.5l1.8 7.2 6.4-3.9-3.9 6.4 7.2 1.8-7.2 1.8 3.9 6.4-6.4-3.9L12 22.5l-1.8-7.2-6.4 3.9 3.9-6.4L.5 12l7.2-1.8-3.9-6.4 6.4 3.9z"/></svg>';
// ---- the scene: items, values at a time (keys), the diff that becomes ops
const scCopy=x=>JSON.parse(JSON.stringify(x));
const scAll=s=>(s||SC.s).tracks.flatMap((tr,ti)=>tr.items.map((it,ii)=>({it,tr,ti,ii})));
const scGet=id=>scAll().find(o=>o.it.id===id);
const scVis=it=>!/^(audio|captions)$/.test(it.type);
const EASE={linear:u=>u,in:u=>u*u*u,out:u=>1-(1-u)**3,inout:u=>(1-Math.cos(Math.PI*u))/2,hold:()=>0};   // SceneEdit's: power2 (cubic), sine.inOut
function scVal(it,p,t){const k=it.keys&&it.keys[p];const b=p==='scale'?1:it[p]??(p==='opacity'?1:p==='x'?SC.s.width/2:p==='y'?SC.s.height/2:0);if(!k||!k.length)return b;const u=t-it.start;
  if(u<=k[0][0])return k[0][1];for(let i=1;i<k.length;i++)if(u<k[i][0]){const[a,va,e]=k[i-1],[c,vc]=k[i];return va+(vc-va)*(EASE[e]||EASE.linear)((u-a)/(c-a||1))}return k[k.length-1][1]}
// a change to an animated prop is a key at the playhead (CapCut's way); any other prop changes the item
function scSet(it,p,x,t){const k=it.keys&&it.keys[p];if(!k||!k.length){if(p==='scale')(it.keys=it.keys||{}).scale=[[+(t-it.start).toFixed(3),x,'inout']];else it[p]=x;return}const u=+(t-it.start).toFixed(3),f=1/(SC.s.fps||30);   // scale has no plain field: one key holds it
  const i=k.findIndex(q=>Math.abs(q[0]-u)<f/2);if(i>=0)k[i][1]=x;else{k.push([u,x,'inout']);k.sort((a,b)=>a[0]-b[0])}}
// a text's drawn size (as SceneEdit lays it: as wide as its words up to w), measured on a copy of the player's own
// element for it with this item's size, wrap width, padding and words, so the handles sit on the words as drawn
const TXB={};function scTextBox(it){const W=SC.s.width,fs=it.size||Math.min(W,SC.s.height)*.05,b=it.box,pd=b?(Array.isArray(b.pad)?b.pad:[b.pad??fs*.25,b.pad??fs*.1]):[0,0],mw=it.w||W;
  const sig=[it.id,it.text,it.font,it.weight,fs,mw,it.line_height,JSON.stringify(b)].join('|');if(TXB[sig])return TXB[sig];
  const e=document.querySelector(`#scl [data-sc="${CSS.escape(it.id)}"]`);let c,w,h;
  if(e){c=e.cloneNode(true);c.removeAttribute('data-sc');c.style.visibility='hidden';e.parentElement.appendChild(c)}
  else{c=document.createElement('div');c.innerHTML='<span></span>';c.style.cssText=`position:absolute;visibility:hidden;left:-9999px;top:0;width:max-content;box-sizing:border-box;white-space:pre-wrap;overflow-wrap:anywhere;font-family:'${it.font||'TikTok Sans'}',system-ui,sans-serif;font-weight:${it.weight||700}`;document.body.appendChild(c)}
  Object.assign(c.style,{fontSize:fs+'px',maxWidth:mw+'px',lineHeight:String(it.line_height??1.2),padding:b?`${pd[1]}px ${pd[0]}px`:'0'});   // a box (per line or one block) pads the element itself
  const sp=c.querySelector('span');if(sp)sp.textContent=it.text||'';
  const rs=[c.getBoundingClientRect(),...(sp?sp.getClientRects():[])],k=rs[0].width?c.offsetWidth/rs[0].width:1;   // a box behind each line can reach past the element: its line boxes count
  const L=Math.min(...rs.map(r=>r.left)),T=Math.min(...rs.map(r=>r.top)),Rr=Math.max(...rs.map(r=>r.right)),B=Math.max(...rs.map(r=>r.bottom)),c0=rs[0];
  const r=[(Rr-L)*k,(B-T)*k,((L+Rr)/2-(c0.left+c0.right)/2)*k,((T+B)/2-(c0.top+c0.bottom)/2)*k];c.remove();if(e)TXB[sig]=r;return r}   // [w, h, and the line boxes' centre off the element's]
function scGeo(it,t){const s=it.type==='card'?1:scVal(it,'scale',t),x=scVal(it,'x',t),y=scVal(it,'y',t),r=scVal(it,'rotation',t);   // CardItem draws no scale
  if(it.type==='text'){const z=scTextBox({...it,w:scVal(it,'w',t)||it.w}),a=r*Math.PI/180;return {x:x+(z[2]*Math.cos(a)-z[3]*Math.sin(a))*s,y:y+(z[2]*Math.sin(a)+z[3]*Math.cos(a))*s,w:z[0]*s,h:z[1]*s,r,s}}
  return {x,y,w:(scVal(it,'w',t)||SC.s.width)*s,h:(scVal(it,'h',t)||SC.s.height)*s,r,s}}
const scDur=s=>Math.max(.1,...scAll(s).map(o=>o.it.end||0));
// the AI's cuts on a track: its clips with something taken out just before them (SCENE.md, The AI's cuts)
const scCuts=tr=>tr.items.filter(i=>i.cut&&i.cut.before&&i.cut.before.dur>0).sort((a,b)=>a.start-b.start);
const scMainCuts=()=>{const tr=SC.s&&SC.s.tracks.find(t=>t.kind==='visual'&&scCuts(t).length);return tr?scCuts(tr):[]};
// keyframes as the lane groups them: Position is x and y, Size w and h. A diamond stands for every key the clip has at
// that time (the AI's zoom is scale, x and y together): a move, an ease or a delete takes them all, so a zoom never drifts. scLanes: the groups an item animates, each with
// its key times (from the item's start, inside the clip: a split part keeps its neighbour's keys outside it)
const KG=[['scale','Scale',['scale']],['pos','Position',['x','y']],['size','Size',['w','h']],['rotation','Rotation',['rotation']],['opacity','Opacity',['opacity']]];
const scHalf=()=>.5/(SC.s.fps||30);
function scLanes(it){const d=it.end-it.start,f=scHalf();return KG.map(([g,l,ps])=>{const ts=[];
  ps.forEach(p=>(it.keys&&it.keys[p]||[]).forEach(k=>{if(k[0]>=-f&&k[0]<=d+f&&!ts.some(u=>Math.abs(u-k[0])<f))ts.push(k[0])}));return {g,l,ps,ts:ts.sort((a,b)=>a-b)}}).filter(x=>x.ts.length)}
const scFrame=t=>{const f=SC.s.fps||30;return Math.ceil(t*f-.05)/f};   // the frame a key shows on (times are kept to the ms)
const scKeysAt=(it,ps,u)=>ps.flatMap(p=>(it.keys&&it.keys[p]||[]).filter(k=>Math.abs(k[0]-u)<scHalf()));
const scKd=()=>{const k=SC.kd;return k&&SC.sel.size===1&&SC.sel.has(k.id)&&scGet(k.id)?k:null};
// a field being typed in keeps the keys and never lets the inspector follow a new pick: any press on the video or the rows lets go of it first (its change saves)
const scBlur=()=>{const a=document.activeElement;if(a&&a!==document.body&&a.closest&&a.closest('#tside'))a.blur()};
function scOpenInsp(){SC.pick=1;if(SC.noside)scSide(true);if(tool!=='insp')openTool('insp');$('ibody')._h=null;SC.insp()}
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
  for(const k of Object.keys(a.assets||{}))if(!(b.assets||{})[k])ops.push({op:'asset',id:k,asset:null});   // after the items that used it: the undo of an add
  return ops}
// ---- on and off: the scene from GET /scene, the player from CookedLive.mountScene
const SCQ=()=>alt?'?alt='+encodeURIComponent(alt):'',EHS={};   // a version (a trial reel) edits its own scene, with its own undo
SC.check=async function(){const want=!!(S&&view&&isCur()&&S.stage==='edit'&&!S.stills&&!S.raw&&!cmp&&!previewOn);const k=want?key(S)+'|'+alt:'';
  if(k===SC.last)return SC.on;SC.last=k;if(!want)return SC.off();
  if((SC.alt??'')!==alt){EHS[SC.alt??'']={u:EH.u,r:EH.r};const h=EHS[alt]||{u:[],r:[]};EH.u=h.u;EH.r=h.r;SC.alt=alt;SC.sel.clear();SC.crop=false}
  try{const r=await fetch('/scene'+SCQ());const j=r.ok?await r.json():null;if(!j||!Array.isArray(j.tracks))return SC.off();SC.s=j;
    if(!window.CookedLive||!CookedLive.mountScene)await import('/live/live.js');if(!SC.pl)SC.pl=CookedLive.mountScene($('scl'),SC.s);else SC.pl.update(SC.s);
    if(!SC.on){SC.on=true;if(LV.on){LV.on=false;LV.shim&&LV.shim.pause();document.body.classList.remove('live')}document.body.classList.add('scene');v.use(SC.pl);SC.size();SC.draw();SC.insp()}
    $('edtracks')._h=null;renderEdTracks();return true}catch(e){console.warn('scene mode off:',e);return SC.off()}};
SC.off=function(){if(SC.on){SC.on=false;document.body.classList.remove('scene');v.use(null);SC.pl&&SC.pl.pause();SC.sel.clear();SC.crop=false;$('edtracks')._h=null;$('scover').innerHTML=''}return false};
SC.fetch=async function(){try{const j=await (await fetch('/scene'+SCQ())).json();if(j&&j.tracks){SC.s=j;SC.show()}}catch(e){}};
// the scene drawn: the player at once, the boxes, the rows, the inspector, the transcript's struck words
SC.show=function(fast){if(!SC.on)return;const s=SC.edit?scCopy(SC.s):SC.s;if(SC.edit){const o=scAll(s).find(o=>o.it.id===SC.edit);if(o)o.it.opacity=0}
  s.duration=scDur(SC.s);SC.pl.update(s);SC.draw();if(fast)return;$('edtracks')._h=null;SC.tl();SC.insp();SC.txSync();if($('sccuts'))SC.cutsDraw()};
SC.size=function(){const o=$('scover'),r=$('scl').getBoundingClientRect(),P=o.parentElement.getBoundingClientRect(),W=SC.s.width,H=SC.s.height,k=Math.min(r.width/W,r.height/H)||1;
  SC.k=k;o.style.cssText=`width:${W}px;height:${H}px;left:${r.left-P.left+(r.width-W*k)/2}px;top:${r.top-P.top+(r.height-H*k)/2}px;transform:scale(${k});--k:${k}`};
new ResizeObserver(()=>{if(SC.on){SC.size();SC.draw()}}).observe($('scl'));
const scNow=()=>v.currentTime;
const scAt=t=>scAll().filter(o=>scVis(o.it)&&o.tr.kind==='visual'&&!o.tr.hidden&&o.it.start<=t+1e-4&&t<o.it.end);   // bottom first
function scHit(px,py,t){return scAt(t).filter(o=>{const g=scGeo(o.it,t),a=-g.r*Math.PI/180,dx=px-g.x,dy=py-g.y,lx=dx*Math.cos(a)-dy*Math.sin(a),ly=dx*Math.sin(a)+dy*Math.cos(a);
  return Math.abs(lx)<=g.w/2&&Math.abs(ly)<=g.h/2}).reverse()}   // top first
SC.draw=function(guides){if(!SC.on)return;guides=guides||SC.drag&&SC.gd;const t=scNow(),o=$('scover'),ids=[...SC.sel].filter(id=>{const q=scGet(id);return q&&scVis(q.it)&&q.it.start<=t+1e-4&&t<q.it.end});
  let h='';
  ids.forEach((id,n)=>{const it=scGet(id).it,g=scGeo(it,t),cr=SC.crop&&ids.length===1&&/^(video|image)$/.test(it.type),c=it.crop||{l:0,t:0,r:0,b:0};
    if(cr){const fw=g.w/Math.max(.02,1-c.l-c.r),fh=g.h/Math.max(.02,1-c.t-c.b);h+=`<div class="scghost" style="left:${g.x-g.w/2-c.l*fw}px;top:${g.y-g.h/2-c.t*fh}px;width:${fw}px;height:${fh}px;transform-origin:${g.w/2+c.l*fw}px ${g.h/2+c.t*fh}px;transform:rotate(${g.r}deg)"></div>`}
    const hs=ids.length>1?[]:it.type==='text'?['nw','ne','se','sw','e','w']:['nw','ne','se','sw','n','e','s','w'],P={nw:[0,0],n:[50,0],ne:[100,0],e:[100,50],se:[100,100],s:[50,100],sw:[0,100],w:[0,50]};
    h+=`<div class="scbox${cr?' crop':''}${n?' sub':''}" data-b="${esc(id)}" style="left:${g.x-g.w/2}px;top:${g.y-g.h/2}px;width:${g.w}px;height:${g.h}px;transform:rotate(${g.r}deg)">${hs.map(k=>`<i data-h="${k}" style="left:${P[k][0]}%;top:${P[k][1]}%"></i>`).join('')}${hs.length&&!cr?`<i data-h="rot" class="${g.y-g.h/2<30/SC.k?'dn':''}" style="left:50%;top:${g.y-g.h/2<30/SC.k?`calc(100% + 26px / var(--k))`:'calc(-26px / var(--k))'}"></i>`:''}</div>`});
  for(const[a,p]of guides||[])h+=a==='x'?`<i class="scg" style="left:${p-1/SC.k}px;top:0;width:${2/SC.k}px;height:100%"></i>`:`<i class="scg" style="top:${p-1/SC.k}px;left:0;height:${2/SC.k}px;width:100%"></i>`;
  const ed=o.querySelector('.sced');o.innerHTML=h;if(ed)o.appendChild(ed)};
v.addEventListener('timeupdate',()=>{if(SC.on&&!SC.drag)SC.draw()});v.addEventListener('seeked',()=>{if(SC.on&&!SC.drag){SC.draw();SC.insp();SC.cutsCur()}});
// ---- one change: made on a copy (fn), shown at once, sent as the ops between the two
SC.commit=async function(before,what){const after=scCopy(SC.s),ops=scDiff(before,after);if(!ops.length)return;SC.busy++;
  try{const r=await post('/scene/ops',{ops,alt});if(!r.ok)throw new Error(r.error||'That did not save.');
    edPush(what,()=>SC.send(scDiff(after,before)),()=>SC.send(scDiff(before,after)));if(r.scene&&!SC.drag)SC.s=r.scene}catch(e){toast(e.message);SC.s=before}finally{SC.busy--}SC.show()};
SC.send=async ops=>{const r=await post('/scene/ops',{ops,alt});JQ.length=0;if(r.scene)SC.s=r.scene;SC.show()};
SC.change=function(what,fn){const b=scCopy(SC.s);fn(SC.s);SC.show();return SC.commit(b,what)};
const scId=p=>p+Math.random().toString(36).slice(2,8);
// ---- the video: press and drag moves what is under the pointer, handles resize, rotate and crop
const scPt=e=>{const r=$('scover').getBoundingClientRect();return [(e.clientX-r.left)/SC.k,(e.clientY-r.top)/SC.k]};
$('scover').addEventListener('pointerdown',e=>{if(e.button||!SC.on||e.target.closest('.sced'))return;e.preventDefault();e.stopPropagation();SC.edDone();scBlur();if(!e.target.closest('[data-h]'))SC.kd=null;v.pause();SC.zone='v';
  const t=scNow(),[px,py]=scPt(e),hd=e.target.closest('[data-h]');let id;SC.pick=1;
  if(hd)id=e.target.closest('[data-b]').dataset.b;
  else{const hs=scHit(px,py,t).filter(o=>!o.tr.locked&&!o.it.locked),base=(SC.s.tracks.find(x=>x.kind==='visual')||{}).id;
    if(!hs.length||SC.sel.size&&!e.shiftKey&&hs.every(o=>o.tr.id===base&&!SC.sel.has(o.it.id))){SC.sel.clear();SC.crop=false;SC.show();return}   // a missed click picks none; the footage takes a click with nothing picked
    const i=hs.findIndex(o=>SC.sel.has(o.it.id));id=(e.metaKey||e.ctrlKey)&&i>=0?hs[(i+1)%hs.length].it.id:i>=0&&!(e.metaKey||e.ctrlKey)?hs[i].it.id:hs[0].it.id;
    if(e.shiftKey){SC.sel.has(id)?SC.sel.delete(id):SC.sel.add(id)}else if(!SC.sel.has(id)||(e.metaKey||e.ctrlKey)){SC.sel.clear();SC.sel.add(id)}}
  const before=scCopy(SC.s),b0=scCopy(SC.s),g0={};SC.sel.forEach(k=>{const q=scGet(k);if(q)g0[k]=scGeo(q.it,t)});const G=g0[id]||scGeo(scGet(id).it,t),h=hd&&hd.dataset.h;
  if(e.altKey&&!h){const ns=[];[...SC.sel].forEach(k=>{const q=scAll(b0).find(o=>o.it.id===k);if(!q)return;const c={...scCopy(q.it),id:scId('i'),name:(q.it.name||q.it.type)+' copy'};q.tr.items.splice(q.ii+1,0,c);ns.push(c.id);g0[c.id]=g0[k]});SC.sel=new Set(ns)}   // Alt-drag: the copies move, the originals stay
  const L=h!=='rot'&&(()=>{const xs=[SC.s.width/2],ys=[SC.s.height/2];
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
  const sx=/e/.test(h)?1:/w/.test(h)?-1:0,sy=/s/.test(h)?1:/^n/.test(h)?-1:0,alt=ev.altKey,m=alt?2:1,s=G.s||1,cs=Math.cos(a),sn=Math.sin(a);
  const put=(w,hh,o=[0,0])=>{const cx=(alt||!sx?0:sx*(w-G.w)/2)-o[0]*s,cy=(alt||!sy?0:sy*(hh-G.h)/2)-o[1]*s;   // the opposite corner or side stays put (Alt: the centre); o: a text's line boxes off its centre
    scSet(it,'x',+(G.x+cx*cs-cy*sn).toFixed(2),t);scSet(it,'y',+(G.y+cx*sn+cy*cs).toFixed(2),t)};
  if(SC.crop&&/^(video|image)$/.test(it.type)){const c={l:0,t:0,r:0,b:0,...(it.crop||{})},fw=G.w/Math.max(.02,1-c.l-c.r),fh=G.h/Math.max(.02,1-c.t-c.b),n={...c};
    if(sx>0)n.r=Math.min(1-c.l-.05,Math.max(0,c.r-lx/fw));if(sx<0)n.l=Math.min(1-c.r-.05,Math.max(0,c.l+lx/fw));if(sy>0)n.b=Math.min(1-c.t-.05,Math.max(0,c.b-ly/fh));if(sy<0)n.t=Math.min(1-c.b-.05,Math.max(0,c.t+ly/fh));
    const w=fw*(1-n.l-n.r),hh=fh*(1-n.t-n.b);it.crop=Object.fromEntries(Object.entries(n).map(([k,x])=>[k,+x.toFixed(4)]));
    put(w,hh);scSet(it,'w',+(w/s).toFixed(2),t);scSet(it,'h',+(hh/s).toFixed(2),t);return SC.draw()}
  // the moving edges land on the guides (the centre, other items' edges) while it is not rotated
  let w=G.w+sx*lx*m,hh=G.h+sy*ly*m,ax=null;
  if(!free&&!G.r&&L){const th=6/SC.k,edge=(c,g,d,v)=>alt?c+d*v/2:c-d*g/2+d*v,size=(c,g,d,p)=>alt?2*d*(p-c):d*(p-(c-d*g/2));
    const near=(e,ps)=>ps.reduce((b,p)=>Math.abs(p-e)<=th&&(b==null||Math.abs(p-e)<Math.abs(b-e))?p:b,null);
    const px=sx?near(edge(G.x,G.w,sx,w),L.xs):null,py=sy?near(edge(G.y,G.h,sy,hh),L.ys):null;
    if(px!=null){w=size(G.x,G.w,sx,px);gd.push(['x',px]);ax='x'}if(py!=null){hh=size(G.y,G.h,sy,py);gd.push(['y',py]);ax=ax||'y'}}
  SC.gd=gd;
  if(sx&&sy&&(it.type==='text'||!sh)){   // a corner keeps the shape (Shift frees it on pictures, clips and cards); a text scales as one
    const f=Math.max(8/Math.min(G.w,G.h),ax==='x'?w/G.w:ax==='y'?hh/G.h:(w*G.w+hh*G.h)/(G.w*G.w+G.h*G.h));w=G.w*f;hh=G.h*f}
  w=Math.max(8,w);hh=Math.max(8,hh);
  if(it.type==='text'){const o=(scAll(b0).find(q=>q.it.id===it.id)||{it}).it,w0=scVal(o,'w',t)||o.w||SC.s.width,f=w/G.w;
    if(sx&&sy){it.size=+((o.size||64)*f).toFixed(2);scSet(it,'w',+(w0*f).toFixed(2),t);if(o.box)it.box={...o.box,pad:Array.isArray(o.box.pad)?o.box.pad.map(x=>+(x*f).toFixed(2)):o.box.pad!=null?+(o.box.pad*f).toFixed(2):o.box.pad,radius:o.box.radius!=null?+(o.box.radius*f).toFixed(2):o.box.radius};
      if(o.outline)it.outline={...o.outline,width:+(o.outline.width*f).toFixed(2)}}
    else scSet(it,'w',+Math.max(it.size||16,w/s).toFixed(2),t);   // a side: the wrap width only
    const z=scTextBox({...it,w:scVal(it,'w',t)});put(z[0]*s,sx&&sy?z[1]*s:G.h,[z[2],z[3]]);return SC.draw(gd)}
  put(w,hh);scSet(it,'w',+(w/s).toFixed(2),t);scSet(it,'h',+(hh/s).toFixed(2),t);SC.draw(gd)};
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
  const head=(tr,cls)=>{const au=tr.kind==='audio',off=au?tr.muted:tr.hidden,nc=scCuts(tr).length;return `<div class="ehd${cls||''}" title="${esc(tr.name||tr.id)}"><span>${esc(tr.name||tr.id)}</span>${nc?`<button data-sccuts="${tr.id}" title="The AI's ${nc} cuts: what was taken out, Bring back" aria-label="list the cuts"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M9 6h11M9 12h11M9 18h11"/><path d="M4 6h.01M4 12h.01M4 18h.01" stroke-width="3"/></svg></button>`:''}${tr.kind==='visual'&&tr.items.some(i=>i.type==='video')?`<button data-sct="magnet" data-tk="${tr.id}" class="${scMag(tr)?'on':''}" title="${scMag(tr)?'Magnet on: a trim moves everything after it':'Magnet off: a trim leaves a gap'}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3v8a6 6 0 0 0 12 0V3"/><path d="M6 7h4M14 7h4"/></svg></button>`:''}<button data-sct="${au?'muted':'hidden'}" data-tk="${tr.id}" class="${off?'on':''}" title="${au?(off?'Unmute':'Mute'):(off?'Show':'Hide')} this track">${lico((au?LICO.spk:LICO.eye)+(off?LICO.off:''))}</button><button data-sct="locked" data-tk="${tr.id}" class="${tr.locked?'on':''}" title="${tr.locked?'Unlock':'Lock'} this track">${lico(tr.locked?LICO.lock:LICO.open)}</button></div>`};
  const item=(it,tr)=>{const a=it.start,b=it.end,k=it.keys?[...new Set(Object.values(it.keys).flat().map(q=>q[0]))]:[],A=it.asset&&SC.s.assets[it.asset]||{},src=A.src;
    const nm=it.type==='text'&&it.text||it.name||(it.type==='captions'?'Captions':src?String(src).split('/').pop():it.type),au=it.type==='audio',d=b-a||1;
    const vl=/^(video|audio)$/.test(it.type)?`${au?'':scWave(it,d*pps)}<b class="scvl${SC.vl&&SC.vl.id===it.id?' on':''}" style="top:${scVlTop(it.volume??1)}%" title="Volume ${scDbTxt(scDb(it.volume??1))}: drag up or down"></b>${SC.vl&&SC.vl.id===it.id?`<em class="scvlab">${scDbTxt(scDb(it.volume??1))}</em>`:''}`:'';
    const fd=au?`${scWave(it,d*pps)}${it.fade_in>0?`<i class="scfd in" style="width:${Math.min(100,it.fade_in/d*100)}%"></i>`:''}${it.fade_out>0?`<i class="scfd out" style="width:${Math.min(100,it.fade_out/d*100)}%"></i>`:''}<b class="scfh" data-fd="in" title="Drag to fade in" style="left:max(9px,${Math.min(100,(it.fade_in||0)/d*100)}%)"></b><b class="scfh" data-fd="out" title="Drag to fade out" style="right:max(9px,${Math.min(100,(it.fade_out||0)/d*100)}%)"></b>`:'';
    return `<div class="eitem sc ${SCCLS[it.type]||'img'}${SC.sel.has(it.id)?' sel':''}" data-sid="${esc(it.id)}" data-lkey="${esc(it.id)}" style="left:${pc(a)}%;width:${pc(b)-pc(a)}%" title="${esc(nm)} · ${fmtx(a)}–${fmtx(b)} · drag to move, an edge to trim${/video|audio/.test(it.type)?', Alt-drag to slip':''}${au?', a top corner to fade':''}${/video|audio/.test(it.type)?', the line for volume':''}">${it.type==='image'&&(A.url||src)?`<img src="${esc(A.url||'/live/media/'+encodeURI(src))}" alt="">`:''}${fd}${vl}<span>${esc(nm)}</span>${k.map(u=>`<i class="sck" style="left:${u/(b-a||1)*100}%"></i>`).join('')}${it.by==='claude'?SCBY:''}</div>`};
  const pps=Math.max(200,($('edtracks').clientWidth||900)-120)*(zm||1)/T;   // pixels a second at this zoom
  const joins=tr=>{const js=scCuts(tr);return js.map((i,n)=>{const c=i.cut.before,why=String(c.reason||'cut').replace(/^./,m=>m.toUpperCase());
    const room=Math.min(n?i.start-js[n-1].start:1e9,n<js.length-1?js[n+1].start-i.start:1e9)*pps;   // the tab shows once neighbours are 40 px apart
    return `<i class="scj${room>=40?' t':''}" data-cj="${esc(i.id)}" style="left:${pc(i.start)}%"><b></b><span><b>${esc(why)}${c.words?`: "${esc(c.words)}"`:''}</b><em class="num">${fmtx(i.start)} · ${(+c.dur).toFixed(1)} s taken out</em><button data-back="${esc(i.id)}">Bring back</button></span></i>`}).join('')};
  // the picked clip's keyframe lane under its track: one row per animated property, a diamond per key (SC.kd: the one picked)
  const lane=tr=>{const id=SC.lid,q=id&&scGet(id);if(!q||q.tr!==tr||!scVis(q.it))return;const it=q.it,ls=scLanes(it);
    if(!ls.length){L.push('<div class="ehd sckh"><span>Keyframes</span></div>');R.push(`<div class="sckl none" data-kopen="1" title="Open Properties">No keyframes. Press ◇ next to a field in Properties to animate it.</div>`);return}
    for(const l of ls){L.push(`<div class="ehd sckh" title="${l.l} keyframes"><span>${l.l}</span></div>`);
      R.push(`<div class="sckl" data-kid="${esc(it.id)}" data-kg="${l.g}"><i class="scln" style="left:${pc(it.start)}%;width:${pc(it.end)-pc(it.start)}%"></i>${l.ts.map(u=>{const on=SC.kd&&SC.kd.id===it.id&&SC.kd.g===l.g&&Math.abs(SC.kd.u-u)<.5/(SC.s.fps||30);
        return `<i class="sckd${on?' on':''}" data-kg="${l.g}" data-ku="${u}" style="left:${pc(it.start+u)}%" title="${l.l} at ${fmtx(it.start+u)}: ${l.ps.map(p=>+(+scVal(it,p,it.start+u)).toFixed(p==='scale'||p==='opacity'?2:0)).join(', ')}. Click to go there, drag to move, Delete removes it (with every key of the clip at that time)"></i>`}).join('')}</div>`)}};
  const row=(tr,cls)=>{if(tr.kind==='audio'||tr.items.some(i=>i.type==='video'))cls=(cls||'')+' tall';L.push(head(tr,cls));R.push(`<div class="etrack${cls||''}${(tr.kind==='audio'?tr.muted:tr.hidden)?' lhid':''}${tr.locked?' llock':''}" data-sctk="${tr.id}" data-kind="${tr.kind}">${tr.items.map(i=>item(i,tr)).join('')}${joins(tr)}</div>`);lane(tr)};
  const mainT=SC.s.tracks.find(t=>t.kind==='visual'&&scCuts(t).length);
  if(!SC.drag)SC.lid=SC.sel.size===1?[...SC.sel][0]:null;   // a press never opens or closes the lane: the rows would move under the pointer
  L.push('<div class="ehd newl" data-row="scv"></div>');R.push('<div class="etrack newl" data-row="scv" data-new="visual">Drop here for a new track</div>');
  vt.forEach((t,i)=>row(t,i===vt.length-1?' l1':''));ct.forEach(t=>row(t,' l1'));at.forEach((t,i)=>row(t,i?'':' l1'));
  L.push('<div class="ehd newl" data-row="sca"></div>');R.push('<div class="etrack newl" data-row="sca" data-new="audio">Drop here for a new track</div>');
  L.push('<div class="scadd"><button data-addtk="visual" title="Add a video track on top">+ Track</button><button data-addau="1" title="Add a song, a voice-over or any sound file at the playhead">+ Audio</button><button data-addit="text" title="Add a text at the playhead">+ Text</button><button data-addit="shape" title="Add a shape at the playhead">+ Shape</button></div>');
  const h=`<div class="edwrap"><div class="edleft">${L.join('')}</div><div class="edright"><div class="escroll" id="escroll"><div class="einner"><div class="eruler">${ticks.map(x=>`<span style="left:${x/T*100}%">${st<1?fmtx(x):fmt(x)}</span>`).join('')}${mainT?joins(mainT):''}</div>${R.join('')}<b class="eph" id="eph"></b><b class="esnap" id="esnap" hidden><i></i></b></div></div></div></div>`;
  if(E._h!==h){E._h=h;E.innerHTML=h;tscrollTo($('tscroll').scrollLeft);
    // the keyframe lane never grows the timeline (the video would jump on a pick): the rows keep their height without it and scroll
    const wr=E.querySelector('.edwrap'),lh=[...E.querySelectorAll('.edleft .sckh')].reduce((a,x)=>a+x.offsetHeight+2,0);wr.style.height=lh?`calc(${Math.min(wr.scrollHeight-lh,innerHeight*.42)}px + var(--nl,0px))`:''}edPh()};
// a track's buttons, Bring back on a join, + Track
$('edtracks').addEventListener('click',e=>{if(!SC.on)return;const b=e.target.closest('[data-sct],[data-back],[data-addtk],[data-addit],[data-addau],[data-sccuts],[data-kopen]');if(!b)return;e.stopPropagation();
  if(b.dataset.addau){$('scaudfile').dataset.t=scNow();return $('scaudfile').click()}
  if(b.dataset.sccuts)return SC.cutsList(b);if(b.dataset.kopen)return scOpenInsp();if(b.dataset.addit)return b.dataset.addit==='text'?SC.addText(scNow()):SC.addShape(scNow());
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
SC.bringBack=function(id){const q=scGet(id);if(!q||!q.it.cut||!q.it.cut.before)return;const d=q.it.cut.before.dur;return SC.change('bring back a cut',s=>scTrim(s,id,'l',-d))};
// before the rows' own press: a cut's note and its tick on the ruler, a keyframe diamond (click: the playhead goes to it and
// Properties shows it, opened if closed; drag: the key moves in time, one undo), and letting go of a field being typed in
$('edtracks').addEventListener('pointerdown',e=>{if(!SC.on||e.button)return;scBlur();
  if(e.target.closest('.scj>span')){e.stopImmediatePropagation();return}   // its Bring back, never a scrub under it
  const fh=e.target.closest('.scfh');if(fh){e.stopImmediatePropagation();e.preventDefault();SC.fadeDrag(e,fh);return}
  const vl=e.target.closest('.scvl');if(vl){e.stopImmediatePropagation();e.preventDefault();SC.volDrag(e,vl);return}
  const tk=e.target.closest('.eruler .scj');if(tk){e.stopImmediatePropagation();e.preventDefault();const q=scGet(tk.dataset.cj);if(q){v.pause();v.currentTime=q.it.start;edPh();SC.draw()}return}
  const kd=e.target.closest('.sckd');if(!kd){if(e.target.closest('.eitem.sc'))SC.kd=null;return}
  e.stopImmediatePropagation();e.preventDefault();v.pause();const id=kd.parentElement.dataset.kid,g=kd.dataset.kg,u0=+kd.dataset.ku,q=scGet(id);if(!q)return;
  const ps=KEYP,b0=scCopy(SC.s),W0=document.querySelector('#edtracks .einner').getBoundingClientRect().width,T=TO(),x0=e.clientX,d=q.it.end-q.it.start;let moved=false;
  SC.kd={id,g,u:u0};SC.zone='k';v.currentTime=scFrame(q.it.start+u0);SC.drag=1;edHold=1;SC.show();scOpenInsp();
  const mv=ev=>{if(!moved&&Math.abs(ev.clientX-x0)<3)return;moved=true;SC.s=scCopy(b0);const it=scGet(id).it,f=scHalf(),u=+Math.max(0,Math.min(d,u0+(ev.clientX-x0)/W0*T)).toFixed(3);
    ps.forEach(p=>{const k=it.keys&&it.keys[p];if(!k)return;k.forEach(x=>{if(Math.abs(x[0]-u0)<f)x[0]=u});k.sort((a,b)=>a[0]-b[0])});SC.kd.u=u;v.currentTime=scFrame(it.start+u);SC.show(true);SC.tl()};
  const up=async()=>{document.removeEventListener('pointermove',mv,true);document.removeEventListener('pointerup',up,true);SC.drag=0;edHold=0;
    if(moved)await SC.commit(b0,'move a keyframe');else SC.show();scOpenInsp()};
  document.addEventListener('pointermove',mv,true);document.addEventListener('pointerup',up,true)},true);
$('edtracks').addEventListener('pointerdown',e=>{const el=e.target.closest('.eitem.sc');if(SC.on&&!el&&!e.button&&e.target.closest('.etrack')&&SC.sel.size){SC.sel.clear();SC.crop=false;SC.show()}   // an empty row: none picked
  if(!SC.on||!el||e.button)return;e.stopPropagation();e.preventDefault();v.pause();SC.zone='t';
  const id=el.dataset.sid,q=scGet(id);if(!q||q.tr.locked||q.it.locked)return;SC.pick=1;const r=el.getBoundingClientRect(),side=e.clientX-r.left<8?'l':r.right-e.clientX<8?'r':'m',slip=side==='m'&&e.altKey&&/^(video|audio)$/.test(q.it.type);
  if(e.shiftKey||e.metaKey||e.ctrlKey){SC.sel.has(id)?SC.sel.delete(id):SC.sel.add(id)}else if(!SC.sel.has(id)){SC.sel.clear();SC.sel.add(id)}
  const b0=scCopy(SC.s),inn=document.querySelector('#edtracks .einner'),W0=inn.getBoundingClientRect().width,T=TO(),x0=e.clientX,y0=e.clientY,ps=snapPts([...document.querySelectorAll('#edtracks .eitem.sc')].filter(x=>SC.sel.has(x.dataset.sid)));
  let moved=false,dest=null;SC.drag=1;edHold=1;SC.show();
  const mv=ev=>{let dt=(ev.clientX-x0)/W0*T;if(!moved&&Math.abs(ev.clientX-x0)<3&&Math.abs(ev.clientY-y0)<4)return;
    // a clip with sound dragged up or down first: its volume, as dragging the line does (start sideways to move it to another row)
    if(!moved&&side==='m'&&!slip&&/^(video|audio)$/.test(q.it.type)&&Math.abs(ev.clientY-y0)>Math.abs(ev.clientX-x0)*1.5){document.removeEventListener('pointermove',mv,true);document.removeEventListener('pointerup',up,true);SC.drag=0;edHold=0;return SC.volDrag({clientX:x0,clientY:y0},el)}
    moved=true;SC.s=scCopy(b0);const it=scGet(id).it;
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
SC.key=function(e){if(!SC.on||KM.off()||typingIn(e.target)||SC.edit||document.body.classList.contains('edro'))return false;const ids=[...SC.sel].filter(k=>scGet(k));
  if(KM.is(e,'delete')){if(scKd()){e.preventDefault();SC.keyDel();return true}
    const hv=document.querySelector('#edtracks .eitem.sc:hover'),hq=hv&&scGet(hv.dataset.sid),del=hq&&!hq.tr.locked&&!hq.it.locked&&(SC.hmv||!ids.length)?[hq.it.id]:ids;   // the clip under the mouse once it moved off the pick (the old editor's rule), else the picked ones
    if(!del.length)return false;e.preventDefault();SC.del(del);return true}
  if(KM.is(e,'split')){e.preventDefault();SC.split();return true}   // never the old editor's split under it: a scene has no other cuts
  const ar={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[e.key];
  if(ar&&ids.length&&SC.zone==='v'&&!e.altKey&&!(e.metaKey||e.ctrlKey)){e.preventDefault();const n=e.shiftKey?10:1,t=scNow();
    SC.change('nudge',s=>ids.forEach(k=>{const it=scAll(s).find(o=>o.it.id===k).it;if(!scVis(it))return;scSet(it,'x',scVal(it,'x',t)+ar[0]*n,t);scSet(it,'y',scVal(it,'y',t)+ar[1]*n,t)}));return true}
  const up=KM.is(e,'edge_prev');if((up||KM.is(e,'edge_next'))&&scMainCuts().length){e.preventDefault();SC.cutJump(up?-1:1);return true}   // up and down: the AI's cuts
  if(e.key.toLowerCase()==='c'&&!e.metaKey&&!e.ctrlKey&&ids.length===1&&/^(video|image)$/.test(scGet(ids[0]).it.type)){e.preventDefault();SC.crop=!SC.crop;SC.show();return true}
  if(e.key==='Escape'&&scKd()){SC.kd=null;SC.show();return true}
  if(e.key==='Escape'&&(ids.length||SC.crop)){SC.crop?SC.crop=false:SC.sel.clear();SC.show();return true}
  return false};
// split at the playhead: the picked clips, or with none picked the clips under it on the main video track (CapCut's way).
// A split part keeps every key of the clip, moved to its own start, so the picture never jumps at the split
SC.split=function(){const t=scNow(),ids=[...SC.sel].filter(k=>scGet(k)),main=SC.s.tracks.find(x=>x.kind==='visual');
  const hit=(ids.length?ids.map(scGet):main&&!main.locked?main.items.map(it=>({it,tr:main})):[]).filter(o=>o&&!o.tr.locked&&!o.it.locked&&o.it.start+.05<t&&t<o.it.end-.05);
  if(!hit.length){toast(ids.length?'Put the playhead inside the picked clip to split it.':'Put the playhead inside a clip on the Video row to split it.');return}
  return SC.change(hit.length>1?`split ${hit.length} clips`:'split',s=>hit.forEach(o=>{const x=scAll(s).find(q=>q.it.id===o.it.id),it=x.it,n={...scCopy(it),id:scId('i'),start:+t.toFixed(3)};delete n.cut;delete n.by;
    if(it.in!=null)n.in=+((it.in||0)+(t-it.start)*(it.speed||1)).toFixed(3);if(it.keys)for(const[p,k]of Object.entries(it.keys))n.keys[p]=k.map(q=>[+(q[0]-(t-it.start)).toFixed(3),...q.slice(1)]);
    it.end=+t.toFixed(3);x.tr.items.splice(x.ii+1,0,n)})).then(()=>toast(`Split at ${fmtx(t)}.`))};
// delete: on the main track the gap closes and everything after moves up (the server's remove ripples, SCENE.md)
SC.del=function(ids){SC.sel.clear();SC.kd=null;return SC.change(ids.length>1?`delete ${ids.length} items`:'delete',s=>s.tracks.forEach(tr=>tr.items=tr.items.filter(i=>!ids.includes(i.id))))};
// the picked keyframe (every property of its group at that time) taken out; a property left with no key goes back to its plain value
SC.keyDel=function(){const k=scKd();if(!k)return;const ps=KEYP;SC.kd=null;
  return SC.change('delete a keyframe',s=>{const it=scAll(s).find(o=>o.it.id===k.id).it;ps.forEach(p=>{const a=it.keys&&it.keys[p];if(!a)return;it.keys[p]=a.filter(q=>Math.abs(q[0]-k.u)>=scHalf());if(!it.keys[p].length)delete it.keys[p]})})};
SC.cutJump=function(dir){const t=scNow(),ts=scMainCuts().map(i=>i.start),n=dir<0?Math.max(...ts.filter(x=>x<t-.02)):Math.min(...ts.filter(x=>x>t+.02));
  if(!isFinite(n))return toast(dir<0?'That is the first cut.':'That is the last cut.');v.pause();v.currentTime=n;edPh();SC.draw();SC.cutsCur()};
// the mouse off the pick: Delete then takes the clip under it (hmv), as the old editor did
document.addEventListener('pointerdown',e=>{SC.p0=[e.clientX,e.clientY];SC.hmv=0},true);
document.addEventListener('pointermove',e=>{if(SC.p0&&!SC.hmv&&Math.hypot(e.clientX-SC.p0[0],e.clientY-SC.p0[1])>6)SC.hmv=1},true);
// the AI's cuts as a list (the Video row's list button): time, why, the words; a row jumps there, Bring back puts it back
SC.cutsList=function(b){let el=$('sccuts');if(el&&el._for===b.dataset.sccuts){el.remove();return}if(!el){el=document.createElement('div');el.id='sccuts';el.setAttribute('role','dialog');el.setAttribute('aria-label','the cuts');document.body.appendChild(el)}
  el._for=b.dataset.sccuts;el._b=b;SC.cutsDraw();const r=b.getBoundingClientRect(),h=el.offsetHeight;el.style.left=Math.max(8,Math.min(innerWidth-348,r.left))+'px';el.style.top=Math.max(8,r.top-h-8)+'px'};
SC.cutsDraw=function(){const el=$('sccuts');if(!el)return;const tr=SC.s&&SC.s.tracks.find(t=>t.id===el._for),cs=tr?scCuts(tr):[];if(!cs.length){el.remove();return}
  const tot=cs.reduce((a,i)=>a+(+i.cut.before.dur||0),0);
  el.innerHTML=`<h4>${cs.length} cuts <em>· ${tot.toFixed(1)} s taken out · ↑ ↓ jump between them</em></h4>`+cs.map(i=>{const c=i.cut.before;return `<div class="sccr" data-cid="${esc(i.id)}"><span class="num">${fmtx(i.start)}</span><b>${esc(String(c.reason||'cut').replace(/^./,m=>m.toUpperCase()))} <em class="num" style="font-weight:500">${(+c.dur).toFixed(1)} s</em></b><em>${c.words?'"'+esc(c.words)+'"':'No words, a pause'}</em><button data-cback="${esc(i.id)}">Bring back</button></div>`}).join('');SC.cutsCur()};
SC.cutsCur=function(){const el=$('sccuts');if(!el)return;const t=scNow();el.querySelectorAll('.sccr').forEach(r=>{const q=scGet(r.dataset.cid);r.classList.toggle('cur',!!q&&Math.abs(q.it.start-t)<.02)})};
document.addEventListener('click',e=>{const el=$('sccuts');if(!el)return;if(!el.contains(e.target)){if(!e.target.closest('[data-sccuts]'))el.remove();return}
  const bb=e.target.closest('[data-cback]');if(bb){Promise.resolve(SC.bringBack(bb.dataset.cback)).then(()=>SC.cutsDraw());return}
  const r=e.target.closest('.sccr'),q=r&&scGet(r.dataset.cid);if(q){v.pause();v.currentTime=q.it.start;edPh();SC.draw();SC.cutsCur()}});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&$('sccuts')){$('sccuts').remove();e.stopImmediatePropagation()}},true);
// ---- the inspector (the left panel), CapCut desktop's way: the item's name and type, tabs per kind (Text | Animation, Video |
// Audio | Animation | Speed, Audio | Speed), and in each tab a few visual controls: look tiles, fonts drawn in their font, colour
// swatches, sliders with the number beside them, a keyframe diamond at the end of each animatable row. The rarer fields sit in
// an Advanced fold and the timing in a Timing fold (the timeline is where timing is edited). Several picked: what they share.
const SCAN=[['none','None'],['cut','Cut'],['fade','Fade'],['pop','Pop'],['slide-up','Slide up']],SCFONT=['TikTok Sans','Inter','Montserrat','Poppins','Bebas Neue','Georgia'];
const KEYP=['x','y','scale','w','h','rotation','opacity'],SCEASE=[['linear','Linear'],['in','Ease in'],['out','Ease out'],['inout','Ease in and out'],['hold','Hold']];
const SCSW=['#FFFFFF','#000000','#FFD60A','#FF3B30','#0A84FF','#34C759'];
// every field an item has (the schema the panel draws from; several picked share a control only when all have its field)
function scFields(it){const V=scVis(it),F=[],a=p=>F.push(p);
  if(it.type==='text'){a('text');a('font');a('weight');a('size');a('color');a('align');a('line_height');a('box');if(it.box){a('box.color');a('box.pad');a('box.radius')}a('outline');if(it.outline){a('outline.color');a('outline.width')}}
  if(it.type==='shape'){a('fill');a('stroke');if(it.stroke){a('stroke.color');a('stroke.width')}}
  if(V){['x','y','w'].forEach(a);if(it.type!=='text')a('h');if(it.type!=='card')a('scale');a('rotation');a('opacity');if(/^(video|image)$/.test(it.type)){a('fit');['l','t','r','b'].forEach(k=>a('crop.'+k))}
    a('radius');a('shadow');if(it.shadow){a('shadow.blur');a('shadow.y');a('shadow.opacity')}a('border');if(it.border){a('border.width');a('border.color')}a('anim.in');a('anim.out');a('anim.dur')}
  if(/^(video|audio)$/.test(it.type)){a('volume_db');a('speed');a('fade_in');a('fade_out');a('in')}
  a('start');a('end');return F}
const scPath=(it,p)=>p.split('.').reduce((o,k)=>o==null?o:o[k],it);
function scPut(it,p,x,t){if(p==='volume_db'){it.volume=scGain(x);return}const ps=p.split('.');if(ps.length===1){if(KEYP.includes(p))scSet(it,p,x,t);else it[p]=x;return}it[ps[0]]={...(it[ps[0]]||(ps[0]==='crop'?{l:0,t:0,r:0,b:0}:ps[0]==='anim'?{in:'none',out:'none',dur:.3}:{})),[ps[1]]:x}}
// the text looks, as the Text panel names them, sized to the text (the house box: .24em x .06em padding, .18em corners)
const SCLOOK={plain:['Plain',it=>({color:'#FFFFFF',box:null,outline:null,shadow:null})],outline:['Outline',it=>({color:'#FFFFFF',box:null,outline:{color:'#000000',width:Math.max(2,Math.round((it.size||60)*.08))},shadow:null})],
  box:['White box',it=>({color:'#000000',box:{color:'#FFFFFF',pad:[+((it.size||60)*.24).toFixed(2),+((it.size||60)*.06).toFixed(2)],radius:+((it.size||60)*.18).toFixed(2)},outline:null,shadow:null,line_height:1.32})],
  dark:['Black box',it=>({color:'#FFFFFF',box:{color:'#000000',pad:[+((it.size||60)*.24).toFixed(2),+((it.size||60)*.06).toFixed(2)],radius:+((it.size||60)*.18).toFixed(2)},outline:null,shadow:null,line_height:1.32})],
  block:['Block',it=>({color:'#000000',box:{color:'#FFFFFF',pad:[+((it.size||60)*.4).toFixed(2),+((it.size||60)*.22).toFixed(2)],radius:+((it.size||60)*.28).toFixed(2),block:true},outline:null,shadow:null})],
  shadow:['Shadow',it=>({color:'#FFFFFF',box:null,outline:null,shadow:{blur:24,y:8,opacity:.6}})]};
const scLookOf=it=>it.box?(it.box.block?'block':/^#0{6}$/i.test(it.box.color||'')?'dark':'box'):it.outline?'outline':it.shadow?'shadow':'plain';
let scSecs={},scTabs={};try{scSecs=JSON.parse(localStorage.getItem('review-scsec')||'{}')||{};scTabs=JSON.parse(localStorage.getItem('review-sctab')||'{}')||{}}catch(e){}
const scOpen=id=>id in scSecs?!!scSecs[id]:false,scSave=(k,o)=>{try{localStorage.setItem(k,JSON.stringify(o))}catch(e){}};
function scTabsOf(it){const m={text:'Text',shape:'Shape',video:'Video',image:'Image',card:'Card',captions:'Captions'}[it.type];
  return [...(m?[['main',m]]:[]),...(/^(video|audio)$/.test(it.type)?[['audio','Audio']]:[]),...(scVis(it)?[['anim','Animation']]:[]),...(/^(video|audio)$/.test(it.type)?[['speed','Speed']]:[])]}
const SCI={left:'<svg viewBox="0 0 16 16"><path d="M2 4h12M2 8h8M2 12h11"/></svg>',center:'<svg viewBox="0 0 16 16"><path d="M2 4h12M4 8h8M2.5 12h11"/></svg>',right:'<svg viewBox="0 0 16 16"><path d="M2 4h12M6 8h8M3 12h11"/></svg>'};
SC.insp=function(){if(!SC.on||SC.noside)return;const ids=[...SC.sel].filter(k=>scGet(k)),B=$('ibody');
  if(!ids.length){if(tool&&tool!=='insp')return;if(tool!=='insp')openTool('insp');const h='<p class="ihead"><b>Nothing picked</b><span>Click anything on the video or the timeline to change it here.</span></p>';if(B._h!==h)B.innerHTML=B._h=h;return}
  if(tool&&tool!=='insp'&&!SC.pick)return;SC.pick=0;if(tool!=='insp')openTool('insp');const t=scNow(),its=ids.map(k=>scGet(k).it),one=its[0],solo=its.length===1;
  const sh=p=>its.every(i=>scFields(i).includes(p)),val=p=>p==='volume_db'?Math.round(Math.max(SCDBMIN,scDb(one.volume??1))*10)/10:KEYP.includes(p)?scVal(one,p,t):scPath(one,p),
    hk=p=>(one.keys&&one.keys[p]||[]).some(q=>Math.abs(one.start+q[0]-t)<1/(SC.s.fps||30)),has=p=>KEYP.includes(p)&&!!(one.keys&&one.keys[p]&&one.keys[p].length),
    fx=(x,st)=>x==null||x===''||isNaN(+x)?'':String(+(+x).toFixed(st<1?2:0)),A=(p,l)=>` data-p="${p}" aria-label="${l}"`;
  // the diamond at the end of an animatable row: quiet until animated, solid when animated, filled yellow on a key here
  const kb=(ps,l)=>{if(!solo||!scVis(one))return '';if(!ps.length)return '<i class="scsk"></i>';const on=ps.some(hk),hs=ps.some(has);return `<button class="sckey${on?' on':hs?' has':''}" data-kp="${ps}" title="${on?'Remove the keyframe here':hs?'Animated: add a keyframe here (the value now)':'Animate: add a keyframe here, then change the value at another time'}" aria-label="keyframe ${l.toLowerCase()}"></button>`};
  const num=(p,l,st,o={})=>{const k=o.k||1,x=val(p)??o.def;return `<div class="scf scn" title="${l}">${o.pr?`<span class="scl" data-scrub>${o.pr}</span>`:''}<input type="number" id="sci-${p.replace('.','-')}"${A(p,l)} step="${+(st*k).toFixed(4)}"${k!==1?` data-k="${k}"`:''}${o.min!=null?` min="${o.min*k}"`:''}${o.max!=null?` max="${o.max*k}"`:''}${o.ph?` placeholder="${o.ph}"`:''} value="${x==null||x===''?'':fx(x*k,st*k)}">${o.u?`<em>${o.u}</em>`:''}</div>`},
    slider=(p,l,mn,mx,st,o={})=>{if(!sh(p))return '';const x=val(p)??o.def;return `<div class="scc"><div class="sch"><span>${l}</span></div><div class="scrow"><input type="range" class="scrg" id="scr-${p.replace('.','-')}"${A(p,l)} min="${mn}" max="${mx}" step="${st}" value="${x==null?mn:x}">${num(p,l,st,{...o,min:o.min===undefined?mn:o.min,max:o.max===undefined?mx:o.max})}${kb(KEYP.includes(p)?[p]:[],l)}</div></div>`},
    field=(p,l,st,o={})=>sh(p)?`<div class="scrow scline"><span class="sct">${l}</span>${num(p,l,st,o)}</div>`:'',
    tiles=(p,opts,cls,lab,def)=>{if(!sh(p))return '';const x=val(p)??def;return `<div class="${cls}" role="group" aria-label="${lab}">${opts.map(([v,n,inner])=>`<button class="sctile${String(v)===String(x??'')?' on':''}" data-pp="${p}" data-pv="${esc(JSON.stringify(v))}" title="${n}" aria-label="${lab}: ${n}">${inner??n}</button>`).join('')}</div>`},
    swatch=(p,l)=>{if(!sh(p))return '';const x=String(val(p)||'').toUpperCase(),cv=/^#[0-9A-F]{6}$/.test(x)?x:'#FFFFFF',mine=!SCSW.includes(x);return `<div class="scc"><div class="sch"><span>${l}</span></div><div class="scsws" role="group" aria-label="${l}">${SCSW.map(c=>`<button class="scsw${c===x?' on':''}" data-pp="${p}" data-pv="${esc(JSON.stringify(c))}" style="--c:${c}" title="${c}" aria-label="${l} ${c}"></button>`).join('')}<label class="scsw scown${mine?' on':''}" title="Another colour" style="--c:${cv}"><input type="color" id="sci-${p.replace('.','-')}"${A(p,l)} value="${cv.toLowerCase()}"></label></div></div>`},
    tog=(p,l,def,body)=>sh(p)?`<div class="scrow scline"><label class="scswr"><span>${l}</span><input type="checkbox" class="scswi" id="sci-${p}" data-p="${p}" data-tog="${esc(JSON.stringify(def))}" aria-label="${l}"${val(p)?' checked':''}></label></div>${val(p)?body:''}`:'',
    fold=(id,l,body)=>body?`<details class="scfold" data-sec="${id}"${scOpen(id)?' open':''}><summary>${l}</summary><div class="scgrp">${body}</div></details>`:'',
    grp=b=>b.trim()?`<div class="scgrp">${b}</div>`:'';
  const pos=()=>sh('x')?`<div class="scc"><div class="scrow"><span class="sct">Position</span>${num('x','Position X',1,{pr:'X'})}${num('y','Position Y',1,{pr:'Y'})}${kb(['x','y'],'Position')}</div></div>`:'',
    size=()=>sh('w')?`<div class="scrow"><span class="sct">${one.type==='text'?'Wrap width':'Size'}</span>${num('w',one.type==='text'?'Wrap width':'Width',1,{pr:'W'})}${sh('h')?num('h','Height',1,{pr:'H'}):''}${kb(sh('h')?['w','h']:['w'],'Size')}</div>`:'',
    xform=()=>slider('scale','Scale',.05,4,.01,{k:100,u:'%',max:20})+pos()+slider('rotation','Rotation',-180,180,1,{u:'°',min:-3600,max:3600})+slider('opacity','Opacity',0,1,.01,{k:100,u:'%'}),
    more=()=>fold('more','Advanced',size()+field('line_height','Line height',.05)+tog('box','Box',{color:'#000000',pad:16,radius:12},swatch('box.color','Box colour')+field('box.pad','Box padding',1)+field('box.radius','Box corners',1))
      +tog('outline','Outline',{color:'#000000',width:4},swatch('outline.color','Outline colour')+field('outline.width','Outline width',1))+tog('stroke','Stroke',{color:'#FFFFFF',width:4},swatch('stroke.color','Stroke colour')+field('stroke.width','Stroke width',1))
      +field('radius','Corners',1)+tog('shadow','Shadow',{blur:24,y:8,opacity:.4},field('shadow.blur','Shadow blur',1)+field('shadow.y','Shadow Y',1)+field('shadow.opacity','Shadow opacity',.05,{min:0,max:1}))+tog('border','Border',{width:4,color:'#FFFFFF'},field('border.width','Border width',1)+swatch('border.color','Border colour')));
  // the tabs this pick has (several: the ones they all have), the open one remembered per kind
  const tl=scTabsOf(one).filter(([k])=>its.every(i=>scTabsOf(i).some(x=>x[0]===k))),kind=its.every(i=>i.type===one.type)?one.type:'mixed',tab=tl.some(x=>x[0]===scTabs[kind])?scTabs[kind]:(tl[0]||[])[0];
  let body='';
  if(tab==='main'){
    if(sh('text'))body+=grp(`${solo?`<textarea class="scta" id="sci-text" data-p="text" aria-label="Words">${esc(val('text')||'')}</textarea>`:''}
      <div class="sclooks" role="group" aria-label="Look">${Object.entries(SCLOOK).map(([k,[n]])=>`<button class="sctile sclook${its.every(i=>scLookOf(i)===k)?' on':''}" data-look="${k}" title="${n}"><span class="scl-${k}">Aa</span><em>${n}</em></button>`).join('')}</div>`
      +tiles('font',SCFONT.map(f=>[f,f,`<span style="font-family:'${f}',system-ui">${f}</span>`]),'scfonts','Font')
      +slider('size','Size',8,300,1,{max:2000})
      +(sh('weight')?`<div class="scrow"><div class="scf sel" title="Weight"><select id="sci-weight"${A('weight','Weight')}>${[[400,'Regular'],[500,'Medium'],[600,'Semibold'],[700,'Bold'],[800,'Heavy'],[900,'Black']].map(([k,n])=>`<option value="${k}"${+k===+val('weight')?' selected':''}>${n}</option>`).join('')}</select></div>${tiles('align',[['left','Left',SCI.left],['center','Centre',SCI.center],['right','Right',SCI.right]],'scseg','Align')}</div>`:'')
      +swatch('color','Colour'));
    if(sh('fill'))body+=grp(swatch('fill','Fill'));
    body+=grp(xform());
    if(sh('fit'))body+=grp(`<div class="scrow"><span class="sct">Fit</span>${tiles('fit',[['cover','Fill'],['contain','Fit']],'scseg','Fit')}</div>${solo?`<button class="ifull" id="sccrop">${SC.crop?'Done cropping':'Crop on the video (C)'}</button>`:''}`);
    body+=more()}
  if(tab==='audio')body+=grp(slider('volume_db','Volume',SCDBMIN,SCDBMAX,.5,{u:'dB'})+slider('fade_in','Fade in',0,5,.05,{u:'s',max:null})+slider('fade_out','Fade out',0,5,.05,{u:'s',max:null}));
  if(tab==='speed')body+=grp(slider('speed','Speed',.1,4,.05,{u:'x',max:8})+tiles('speed',[[.5,'0.5x'],[1,'1x'],[1.5,'1.5x'],[2,'2x']],'scchips','Speed'));
  if(tab==='anim'){const ad=SC.atab==='out'?'out':'in',p='anim.'+ad;
    body+=grp(`<div class="scseg scfull" role="tablist"><button class="sctile${ad==='in'?' on':''}" data-atab="in">In</button><button class="sctile${ad==='out'?' on':''}" data-atab="out">Out</button></div>`
      +tiles(p,SCAN.map(([k,n])=>[k,n,`<span class="scap"><b class="sca-${k} ${ad}">Abc</b></span><em>${n}</em>`]),'scanims','Animation '+ad,'none')+slider('anim.dur','Duration',0,2,.05,{u:'s',max:10,def:.3}))}
  body+=fold('time','Timing',field('start','Start',.01,{u:'s',min:0})+field('end','End',.01,{u:'s',min:0})+(sh('in')?field('in','Starts in source',.01,{u:'s',min:0}):''));
  const nm=its.length>1?`${its.length} picked`:esc(one.name||(one.type==='text'?one.text:one.type).replace(/^./,m=>m.toUpperCase())),sub=its.length>1?'A change goes on all of them':one.type.replace(/^./,m=>m.toUpperCase());
  const kd=solo&&scKd(),kg=kd&&KG.find(x=>x[0]===kd.g),kk=kd?scKeysAt(one,kg[2],kd.u):[],ke=kk.length?kk[0][2]||'linear':null;   // the keyframe picked on the lane
  const kh=kk.length?`<div class="isec sckds"><div class="tf"><span>${kg[1]} keyframe</span><div class="tfv"><em class="num">${fmtx(one.start+kd.u)}</em></div></div><div class="tf"><span>Ease to the next</span><div class="tfv"><select id="scke" aria-label="ease to the next keyframe">${(SCEASE.some(o=>o[0]===ke)?SCEASE:[[ke,ke],...SCEASE]).map(([k,n])=>`<option value="${k}"${k===ke?' selected':''}>${n}</option>`).join('')}</select></div></div><button class="ifull" id="sckdel">Delete keyframe</button></div>`:'';
  const tabs=tl.length>1?`<div class="sctabs" role="tablist">${tl.map(([k,n])=>`<button role="tab" class="${k===tab?'on':''}" data-tab="${k}" aria-selected="${k===tab}">${n}</button>`).join('')}</div>`:'';
  const h=`<p class="ihead"><b>${nm}</b><span>${sub}</span></p>${tabs}${kh}${body}<button class="ifull" id="scdel">Delete</button>`;
  B.dataset.kind=kind;if(B._h===h||SC.scrub)return;const f=document.activeElement;if(f&&B.contains(f)&&f.dataset.p&&/^(number|textarea|color|select-one)$/.test(f.type))return;B._h=h;B.innerHTML=h};
$('ibody').addEventListener('toggle',e=>{const d=e.target,g=d.dataset&&d.dataset.sec;if(!g||scOpen(g)===d.open)return;scSecs[g]=d.open;scSave('review-scsec',scSecs)},true);
// a slider and its number are the same field: either one moves the other, live; the number may show a scaled value (% for 0-1)
$('ibody').addEventListener('input',e=>{const el=e.target;if(!SC.on||!el.dataset.p||el.dataset.tog!=null)return;if(!SC.ib)SC.ib=scCopy(SC.s);const p=el.dataset.p,t=scNow(),raw=el.value,k=+el.dataset.k||1;
  const x=/^(number|range)$/.test(el.type)?(raw===''?null:+raw/k):p==='weight'?+raw:raw;if(x==null&&el.type==='number')return;
  if(el.type==='color'){const l=el.closest('.scown');if(l)l.style.setProperty('--c',raw)}
  $('ibody').querySelectorAll(`[data-p="${p}"]`).forEach(o=>{if(o===el)return;if(o.type==='range')o.value=x;else if(o.type==='number'){const ok=+o.dataset.k||1,st=+o.step||1;o.value=String(+(x*ok).toFixed(st<1?2:0))}});
  SC.sel.forEach(q=>{q=scGet(q);if(q)scPut(q.it,p,x,t)});SC.show(true)},true);
// drag the short label inside a number field (X, Y, W, H) to change it, as Figma and CapCut do: a step per 2 px, shift for 10
$('ibody').addEventListener('pointerdown',e=>{const h=e.target.closest('[data-scrub]'),inp=h&&h.parentNode.querySelector('input[type=number]');if(!SC.on||!inp||e.button)return;e.preventDefault();
  const x0=e.clientX,v0=+inp.value||0,st=+inp.step||1,mn=inp.min===''?-Infinity:+inp.min,mx=inp.max===''?Infinity:+inp.max,dp=st<1?2:0;let moved=false;h.setPointerCapture(e.pointerId);
  const mv=ev=>{const d=Math.round((ev.clientX-x0)/2);if(!d&&!moved)return;moved=SC.scrub=true;const s=String(+Math.min(mx,Math.max(mn,v0+d*st*(ev.shiftKey?10:1))).toFixed(dp));if(inp.value!==s){inp.value=s;inp.dispatchEvent(new Event('input',{bubbles:true}))}},
    up=()=>{h.removeEventListener('pointermove',mv);h.removeEventListener('pointerup',up);h.removeEventListener('pointercancel',up);SC.scrub=false;if(moved)inp.dispatchEvent(new Event('change',{bubbles:true}));else inp.focus()};
  h.addEventListener('pointermove',mv);h.addEventListener('pointerup',up);h.addEventListener('pointercancel',up)});
$('ibody').addEventListener('change',e=>{if(!SC.on||e.target.id!=='scke')return;const k=scKd(),x=e.target.value;if(!k)return;const ps=KEYP;$('ibody')._h=null;
  SC.change('ease a keyframe',s=>{const it=scAll(s).find(o=>o.it.id===k.id).it;ps.forEach(p=>(it.keys&&it.keys[p]||[]).forEach(q=>{if(Math.abs(q[0]-k.u)<scHalf())q[2]=x}))})},true);
$('ibody').addEventListener('change',e=>{if(!SC.on||!e.target.dataset.p)return;const p=e.target.dataset.p;let b=SC.ib||scCopy(SC.s);SC.ib=null;
  if(e.target.dataset.tog!=null){const on=e.target.type==='checkbox'?e.target.checked:!!e.target.value,d=JSON.parse(e.target.dataset.tog);b=scCopy(SC.s);SC.sel.forEach(k=>{const q=scGet(k);if(q)q.it[p]=on?(q.it[p]||d):null})}
  $('ibody')._h=null;SC.show();SC.commit(b,'change '+p.replace('.',' ').replace('_',' '))},true);
// a tile, swatch, chip or segment sets its field (one undo); a look sets the text's colour, box, outline and shadow together
$('ibody').addEventListener('click',e=>{if(!SC.on)return;const B=$('ibody'),k=e.target.closest('[data-kp]'),t=scNow(),c=e.target.closest('[data-pp],[data-look],[data-tab],[data-atab]');
  if(c&&c.dataset.tab){scTabs[B.dataset.kind]=c.dataset.tab;scSave('review-sctab',scTabs);B._h=null;return SC.insp()}
  if(c&&c.dataset.atab){SC.atab=c.dataset.atab;B._h=null;return SC.insp()}
  if(c){const b=scCopy(SC.s);SC.sel.forEach(id=>{const q=scGet(id);if(!q)return;if(c.dataset.look){if(q.it.type==='text')Object.assign(q.it,SCLOOK[c.dataset.look][1](q.it))}else scPut(q.it,c.dataset.pp,JSON.parse(c.dataset.pv),t)});
    B._h=null;SC.show();return SC.commit(b,c.dataset.look?'text look':'change '+c.dataset.pp.replace('.',' ').replace('_',' '))}
  // a row's diamond keys every property on it (Position: x and y, Size: w and h, as the lanes group them): a key here on any of
  // them takes them all off, else each gets one at the value now
  if(k){const ps=k.dataset.kp.split(','),id=[...SC.sel][0];return SC.change('keyframe',s=>{const it=scAll(s).find(o=>o.it.id===id).it,u=+(t-it.start).toFixed(3),f=1/(s.fps||30)/2,at=p=>(it.keys&&it.keys[p]||[]).findIndex(q=>Math.abs(q[0]-u)<f),off=ps.some(p=>at(p)>=0);
    ps.forEach(p=>{const i=at(p);if(off){if(i<0)return;it.keys[p].splice(i,1);if(!it.keys[p].length){delete it.keys[p];if(!Object.keys(it.keys).length)delete it.keys}return}
      const ks=(it.keys=it.keys||{})[p]=it.keys[p]||[];if(!ks.length&&it[p]==null)it[p]=scVal(it,p,t);ks.push([u,scVal(it,p,t),'inout']);ks.sort((a,b)=>a[0]-b[0])})})}
  if(e.target.id==='sckdel')return SC.keyDel();
  if(e.target.id==='sccrop'){SC.crop=!SC.crop;B._h=null;return SC.show()}
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
// ---- audio, CapCut's way: a library sound, a file from + Audio, a file dropped from Finder. Each is a file in the edit's
// media/ (review.py /scene/sound copies a library sound in, /scene/upload streams a file in), an asset, and an audio item
// at t on the first audio track free there (a new track when every one is busy), as long as the file, up to the scene's end
function scFreeAudio(s,a,b){let tr=s.tracks.find(x=>x.kind==='audio'&&!x.locked&&!x.muted&&!x.items.some(i=>i.start<b-1e-3&&i.end>a+1e-3));
  if(!tr){tr={id:scId('a'),kind:'audio',name:'Audio '+(s.tracks.filter(x=>x.kind==='audio').length+1),muted:false,locked:false,items:[]};s.tracks.push(tr)}return tr}
SC.addAudio=function(src,dur,t){const s0=SC.s,D=scDur(s0),a=+Math.max(0,t).toFixed(3),name=src.split('/').pop().replace(/\.[a-z0-9]+$/i,'');
  let e=a+(dur||3);if(a<D-.1)e=Math.min(e,D);e=+Math.max(a+.1,e).toFixed(3);
  let aid=Object.keys(s0.assets||{}).find(k=>s0.assets[k].src===src);
  if(!aid){const base=name.toLowerCase().replace(/[^a-z0-9]/g,'-').slice(0,24)||'a';aid=base;for(let n=2;(s0.assets||{})[aid];n++)aid=base+'-'+n}
  const it={id:scId('i'),type:'audio',name,asset:aid,in:0,speed:1,volume:1,fade_in:0,fade_out:0,start:a,end:e};
  return SC.change('add '+name,s=>{s.assets=s.assets||{};if(!s.assets[aid])s.assets[aid]={src,kind:'audio',duration:dur};scFreeAudio(s,a,e).items.push(it)})
    .then(()=>{if(!scGet(it.id))return;SC.sel=new Set([it.id]);SC.zone='t';SC.show();toast(`${name} added at ${fmtx(a)}.`)})};
SC.addSound=async function(name,t){const r=await post('/scene/sound',{name});if(!r.ok)return toast(r.error||'That sound was not added.');return SC.addAudio(r.src,r.duration,t)};
SC.addFile=async function(f,t){toast(`Adding ${f.name}...`);
  const r=await new Promise(res=>{const x=new XMLHttpRequest();x.open('POST','/scene/upload?name='+encodeURIComponent(f.name));
    x.upload.onprogress=e=>{if(e.lengthComputable)toast(`Adding ${f.name}... ${Math.round(e.loaded/e.total*100)}%`)};
    x.onload=()=>{let j={};try{j=JSON.parse(x.responseText)}catch(e){}res(j)};x.onerror=()=>res({error:'The upload stopped. Add it again.'});x.send(f)});
  if(!r.ok)return toast(r.error||`${f.name} was not added.`);return SC.addAudio(r.src,r.duration,t)};
{const i=document.createElement('input');i.type='file';i.id='scaudfile';i.hidden=true;i.multiple=true;i.accept='audio/*,video/*,.mp3,.wav,.m4a,.aac,.flac,.ogg,.opus,.mp4,.mov,.m4v,.webm';document.body.appendChild(i);
  i.addEventListener('change',async()=>{const fs=[...i.files],t=+i.dataset.t||0;i.value='';for(const f of fs)await SC.addFile(f,t)})}
// a clip's waveform: the asset's peaks from review.py /scene/peaks (fetched once each), the part the clip plays, about one bar per 3 px
SC.pk={};SC.pkN={};
function scWave(it,px){const A=SC.s.assets[it.asset]||{},k=(alt||'')+'|'+it.asset+'|'+A.src,P=SC.pk[k];
  if(!P){if(!A.url)return '';SC.pk[k]={busy:1};   // an add not saved yet (no url until the server's scene): asked once it is
const redraw=()=>{$('edtracks')._h=null;SC.tl()};   // not saved yet (an add on its way): asked again, 3 times at most
    fetch('/scene/peaks/'+encodeURIComponent(it.asset)+SCQ()).then(r=>r.ok?r.json():Promise.reject()).then(j=>{SC.pk[k]=j;redraw()})
      .catch(()=>{const n=SC.pkN[k]=(SC.pkN[k]||0)+1;setTimeout(()=>{if(n<4)delete SC.pk[k];else SC.pk[k]={peaks:[]};redraw()},1500)});return ''}
  if(!P.peaks||!P.peaks.length)return '';const sp=it.speed||1,i0=Math.floor((it.in||0)*P.rate),i1=Math.min(P.peaks.length,Math.ceil(((it.in||0)+(it.end-it.start)*sp)*P.rate)),sl=P.peaks.slice(i0,i1);
  const n=Math.max(1,Math.min(sl.length,400,Math.round(px/3)));if(!sl.length)return '';const q=[];for(let j=0;j<n;j++){let m=0;for(let x=Math.floor(j*sl.length/n);x<Math.max(Math.floor(j*sl.length/n)+1,Math.floor((j+1)*sl.length/n));x++)m=Math.max(m,sl[x]||0);q.push(m)}
  const g=it.volume??1;return waveSvg(q.map(m=>Math.min(1,m*g)))}   // the bars grow and shrink with the clip's volume
// a fade handle (a top corner of an audio clip) dragged: the fade in or out grows to where it is let go, one undo
SC.fadeDrag=function(e,fh){const el=fh.closest('.eitem.sc'),id=el&&el.dataset.sid,q=id&&scGet(id);if(!q||q.tr.locked||q.it.locked)return;v.pause();
  const k=fh.dataset.fd==='in'?'fade_in':'fade_out',o=k==='fade_in'?'fade_out':'fade_in',b0=scCopy(SC.s),W=el.getBoundingClientRect().width,d=q.it.end-q.it.start,x0=e.clientX,f0=q.it[k]||0;let moved=false;
  SC.sel=new Set([id]);SC.drag=1;edHold=1;SC.show();
  const mv=ev=>{if(!moved&&Math.abs(ev.clientX-x0)<2)return;moved=true;SC.s=scCopy(b0);const it=scGet(id).it,dx=(ev.clientX-x0)/W*d*(k==='fade_in'?1:-1);
    it[k]=+Math.max(0,Math.min(d-(it[o]||0),f0+dx)).toFixed(2);SC.show(true);SC.tl()};
  const up=async()=>{document.removeEventListener('pointermove',mv,true);document.removeEventListener('pointerup',up,true);SC.drag=0;edHold=0;
    if(moved)await SC.commit(b0,k==='fade_in'?'fade in':'fade out');else SC.show()};
  document.addEventListener('pointermove',mv,true);document.addEventListener('pointerup',up,true)};
// volume in dB: 0 dB is the file as it is, up to +12 dB (a gain of ~4, SceneEdit's VMAX), down to silence (below -48 dB)
const SCDBMAX=12,SCDBMIN=-48,scDb=x=>x>0?20*Math.log10(x):-Infinity,scGain=db=>db<=SCDBMIN?0:+(10**(Math.min(SCDBMAX,db)/20)).toFixed(4);
const scDbTxt=db=>{if(db<=SCDBMIN)return '-∞ dB';const r=Math.round(db*2)/2||0;return `${r>0?'+':''}${r} dB`};
const scVlTop=x=>+(100-Math.max(0,Math.min(1,(Math.max(SCDBMIN,scDb(x))-SCDBMIN)/(SCDBMAX-SCDBMIN)))*100).toFixed(1);   // 0 dB a fifth down, silence at the bottom
// the volume line dragged: half a dB a pixel (Shift: a tenth), snaps to 0 dB within 1 dB; every picked clip with sound moves by
// the same dB; heard at once (the player keeps playing), one undo
SC.volDrag=function(e,vl){const el=vl.closest('.eitem.sc'),id=el&&el.dataset.sid,q=id&&scGet(id);if(!q||q.tr.locked||q.it.locked)return;
  if(!SC.sel.has(id))SC.sel=new Set([id]);
  const ok=k=>{const o=scGet(k);return o&&!o.tr.locked&&!o.it.locked&&/^(video|audio)$/.test(o.it.type)},ids=[...SC.sel].filter(ok),b0=scCopy(SC.s),y0=e.clientY;
  const d0=Object.fromEntries(ids.map(k=>[k,Math.max(SCDBMIN,scDb(scGet(k).it.volume??1))]));let moved=false,acc=0,ly=y0;
  SC.vl={id};SC.drag=1;edHold=1;SC.pick=1;SC.show();   // a press on the line picks the clip too: Properties shows it
  const mv=ev=>{if(!moved&&Math.abs(ev.clientY-y0)<2)return;moved=true;acc=Math.max(SCDBMIN-d0[id],Math.min(SCDBMAX-d0[id],acc+(ly-ev.clientY)*(ev.shiftKey?.1:.5)));ly=ev.clientY;
    let t=Math.round(Math.max(SCDBMIN,Math.min(SCDBMAX,d0[id]+acc))*10)/10;if(Math.abs(t)<1)t=0;const dd=t-d0[id];
    SC.s=scCopy(b0);ids.forEach(k=>{const it=scGet(k).it;it.volume=k===id?scGain(t):scGain(Math.min(SCDBMAX,d0[k]+dd))});SC.show(true);SC.tl()};
  const up=async()=>{document.removeEventListener('pointermove',mv,true);document.removeEventListener('pointerup',up,true);SC.drag=0;edHold=0;SC.vl=null;
    if(moved)await SC.commit(b0,'volume');else SC.show()};
  document.addEventListener('pointermove',mv,true);document.addEventListener('pointerup',up,true)};
document.addEventListener('keydown',e=>{if(SC.key(e))e.stopImmediatePropagation()},true);
$('railtext').addEventListener('click',e=>{if(!SC.on)return;e.stopImmediatePropagation();if(SC.noside)scSide(true);SC.addText(scNow())},true);
$('scover').addEventListener('click',e=>e.stopPropagation());
// ---- the transcript follows the clips: a raw word inside a clip of the main track is kept, one in a gap is struck
SC.txSync=function(){if(!SC.on||typeof W==='undefined'||!W.length)return;const main=SC.s.tracks.find(tr=>tr.kind==='visual'&&tr.items.some(i=>i.cut))||null;if(!main)return;
  const rs=main.items.filter(i=>i.type==='video').map(i=>[i.in||0,(i.in||0)+(i.end-i.start)*(i.speed||1)]);
  document.querySelectorAll('#txlines .tw[data-k]').forEach(el=>{const w=W[+el.dataset.k];if(!w||w.s==null)return;el.classList.toggle('cut',!rs.some(([a,b])=>w.s>=a-.02&&w.s<b))})};
// ---- Export: review.html's one Export button (review.py export_job renders the scene when there is one)
// a click round the frame (the black at the sides, the empty stage): none picked
document.addEventListener('pointerdown',e=>{if(!SC.on||e.button||!e.target.closest('#stage')||e.target.closest('#scover,button,input,select,textarea,[contenteditable],.pmenu')||!SC.sel.size&&!SC.crop)return;SC.edDone();SC.sel.clear();SC.crop=false;SC.show()});

// the side panel's ×: closed stays closed (a pick never opens it, so the video never jumps); Properties or any rail tool opens it
try{SC.noside=localStorage.getItem('review-scside')==='0'}catch(e){}
function scSide(open){SC.noside=!open;document.body.classList.toggle('scnoside',!open);try{localStorage.setItem('review-scside',open?'1':'0')}catch(e){}}
document.body.classList.toggle('scnoside',!!SC.noside);
const scOT=openTool;openTool=function(n){if(SC.on&&n&&SC.noside)scSide(true);return scOT(n)};
$('tclose').addEventListener('click',e=>{if(!SC.on)return;e.stopImmediatePropagation();scSide(false);scOT(null)},true);
$('railinsp').onclick=()=>{if(SC.noside||tool!=='insp'){scSide(true);openTool('insp');SC.insp()}else{scSide(false);scOT(null)}};
// the timeline's Split and Delete buttons (beside the zoom, in the one row of controls): the same as S / ⌘B and Delete
{const z=document.querySelector('.tzoom'),mk=(id,tip,svg,f)=>{const b=document.createElement('button');b.id=id;b.type='button';b.className='scbtn';b.setAttribute('aria-label',tip);b.innerHTML=svg;
    b.addEventListener('pointerdown',e=>e.stopPropagation());b.onclick=e=>{e.stopPropagation();if(SC.on)f()};b.onmouseenter=()=>b.title=tip+' ('+KM.keys(id==='scsplit'?'split':'delete').map(KM.fmt).join(' or ')+')';return b};
  const S1='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4 8.1 15.9M14.5 14.5 20 20M8.1 8.1 12 12"/></svg>';
  const S2='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/></svg>';
  if(z){z.prepend(mk('scdelb','Delete the picked clip',S2,()=>{const ids=[...SC.sel].filter(k=>scGet(k));if(scKd())return SC.keyDel();if(!ids.length)return toast('Pick a clip first, then Delete takes it out.');SC.del(ids)}));
    z.prepend(mk('scsplit','Split at the playhead',S1,()=>SC.split()))}}
