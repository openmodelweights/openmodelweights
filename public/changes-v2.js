(()=>{
  const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>[...r.querySelectorAll(s)];
  const q=$('#changes-search'),type=$('#changes-type'),dev=$('#changes-developer'),range=$('#changes-range'),count=$('#changes-count'),items=$$('.change-item');
  if(!q)return;
  const norm=v=>(v||'').toString().toLowerCase();
  function run(){
    const query=norm(q.value),t=type.value,d=dev.value,days=Number(range.value||0),cut=days?Date.now()-days*86400000:0;let n=0;
    items.forEach(x=>{const at=Date.parse(x.dataset.at||0)||0;const ok=(!query||norm(x.dataset.search).includes(query))&&(!t||x.dataset.type===t)&&(!d||x.dataset.developer===d)&&(!cut||at>=cut);x.hidden=!ok;if(ok)n++});
    if(count)count.innerHTML='<strong>'+n.toLocaleString()+'</strong> change events shown';
  }
  q.addEventListener('input',run);[type,dev,range].forEach(x=>x?.addEventListener('change',run));run();
})();