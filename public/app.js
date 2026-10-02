(()=>{
  const q=document.querySelector('#model-search');
  const o=document.querySelector('#org-filter');
  const s=document.querySelector('#status-filter');
  const rows=[...document.querySelectorAll('.registry-row')];
  const empty=document.querySelector('#no-results');
  const count=document.querySelector('#registry-result-count');
  if(!q)return;
  const p=new URLSearchParams(location.search).get('q');
  if(p)q.value=p;
  const norm=v=>(v||'').toString().trim().toLowerCase();
  function run(){
    const z=norm(q.value),ov=norm(o?.value),sv=norm(s?.value);
    let n=0;
    rows.forEach(r=>{
      const name=norm(r.dataset.name),org=norm(r.dataset.org),status=norm(r.dataset.status);
      const ok=(!z||name.includes(z))&&(!ov||org===ov)&&(!sv||status===sv);
      r.hidden=!ok;
      r.style.display=ok?'':'none';
      if(ok)n++;
    });
    if(empty)empty.hidden=n!==0;
    if(count)count.innerHTML='<strong>'+n+'</strong> of '+rows.length+' models';
  }
  q.addEventListener('input',run);
  q.addEventListener('search',run);
  o?.addEventListener('change',run);
  s?.addEventListener('change',run);
  run();
})();