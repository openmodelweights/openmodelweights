(()=>{
  const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)], norm=v=>(v||"").toString().toLowerCase();
  const search=$("#license-search");
  if(search){const status=$("#commercial-filter"),items=$$(".license-record");const run=()=>{const q=norm(search.value),st=status.value;items.forEach(x=>x.hidden=!((!q||norm(x.dataset.search).includes(q))&&(!st||x.dataset.status===st)))};search.addEventListener("input",run);status.addEventListener("change",run);run()}
  const hs=$("#hardware-search");
  if(hs){const p=$("#hardware-precision"),b=$("#hardware-budget"),d=$("#hardware-developer"),rows=$$(".hardware-row");const run=()=>{const q=norm(hs.value),pv=p.value,bv=Number(b.value||0),dv=d.value;rows.forEach(x=>{const mem=Number(x.dataset[pv]||Infinity);x.hidden=!((!q||norm(x.dataset.search).includes(q))&&(!dv||x.dataset.developer===dv)&&(!bv||mem<=bv))});$("#hardware-count").textContent=rows.filter(x=>!x.hidden).length};[hs,p,b,d].forEach(x=>x.addEventListener(x.tagName==="INPUT"?"input":"change",run));run()}
  const fs=$("#format-search");
  if(fs){const f=$("#format-filter"),rows=$$(".format-row");const run=()=>{const q=norm(fs.value),fv=f.value;rows.forEach(x=>x.hidden=!((!q||norm(x.dataset.search).includes(q))&&(!fv||x.dataset.formats.split("|").includes(fv))));$("#format-count").textContent=rows.filter(x=>!x.hidden).length};fs.addEventListener("input",run);f.addEventListener("change",run);run()}
  const cs=$("#changes-search");
  if(cs){const t=$("#changes-type"),d=$("#changes-developer"),items=$$(".change-item");const run=()=>{const q=norm(cs.value),tv=t.value,dv=d.value;items.forEach(x=>x.hidden=!((!q||norm(x.dataset.search).includes(q))&&(!tv||x.dataset.type===tv)&&(!dv||x.dataset.developer===dv)))};cs.addEventListener("input",run);t.addEventListener("change",run);d.addEventListener("change",run);run()}
})();