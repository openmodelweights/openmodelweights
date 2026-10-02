(()=>{
  const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
  const rows=$$('.registry-row'); if(!rows.length)return;
  const els={
    q:$('#model-search'), org:$('#org-filter'), license:$('#license-filter'),
    commercial:$('#commercial-filter'), format:$('#format-filter'), sort:$('#sort-filter'),
    size:$('#page-size'), reset:$('#reset-filters'), count:$('#registry-result-count'),
    empty:$('#no-results'), prev:$('#page-prev'), next:$('#page-next'), page:$('#page-info')
  };
  let page=1;
  const norm=v=>(v||'').toString().trim().toLowerCase();
  const num=(r,k,def=0)=>{const v=Number(r.dataset[k]);return Number.isFinite(v)?v:def};
  const params=new URL(location.href).searchParams;
  const mapping={q:'q',org:'developer',license:'license',commercial:'commercial',format:'format',sort:'sort'};
  Object.entries(mapping).forEach(([k,p])=>{if(els[k]&&params.get(p)!==null)els[k].value=params.get(p)});
  if(params.get('size')&&els.size)els.size.value=params.get('size');

  function syncUrl(){
    const u=new URL(location.href);
    Object.entries(mapping).forEach(([k,p])=>{if(!els[k])return;const v=els[k].value;if(v)u.searchParams.set(p,v);else u.searchParams.delete(p)});
    if(els.size&&els.size.value!=='50')u.searchParams.set('size',els.size.value);else u.searchParams.delete('size');
    history.replaceState(null,'',u);
  }
  function sortRows(list){
    const mode=els.sort?.value||'popular';
    const cmp={
      popular:(a,b)=>num(b,'downloads')-num(a,'downloads')||num(b,'likes')-num(a,'likes'),
      likes:(a,b)=>num(b,'likes')-num(a,'likes'),
      'params-desc':(a,b)=>num(b,'params',-1)-num(a,'params',-1),
      'params-asc':(a,b)=>num(a,'params',1e15)-num(b,'params',1e15),
      'context-desc':(a,b)=>num(b,'context',-1)-num(a,'context',-1),
      'memory-asc':(a,b)=>num(a,'memory',1e15)-num(b,'memory',1e15),
      'created-desc':(a,b)=>num(b,'created',0)-num(a,'created',0),
      'updated-desc':(a,b)=>num(b,'updated',0)-num(a,'updated',0),
      name:(a,b)=>(a.dataset.title||'').localeCompare(b.dataset.title||'')
    }[mode];
    return [...list].sort(cmp||(()=>0));
  }
  function run(resetPage=false){
    if(resetPage)page=1;
    const q=norm(els.q?.value),org=norm(els.org?.value),lic=norm(els.license?.value),com=norm(els.commercial?.value),fmt=els.format?.value||'';
    let matched=rows.filter(r=>
      (!q||norm(r.dataset.search).includes(q))&&
      (!org||norm(r.dataset.org)===org)&&
      (!lic||norm(r.dataset.license)===lic)&&
      (!com||norm(r.dataset.commercial)===com)&&
      (!fmt||(r.dataset.formats||'').split('|').includes(fmt))
    );
    matched=sortRows(matched);
    const container=$('.registry-list');
    matched.forEach(r=>container.appendChild(r));
    const size=Number(els.size?.value||50), pages=Math.max(1,Math.ceil(matched.length/size));
    page=Math.min(page,pages);
    const start=(page-1)*size,end=start+size, visible=new Set(matched.slice(start,end));
    rows.forEach(r=>{const show=visible.has(r);r.hidden=!show;r.style.display=show?'':''});
    if(els.empty)els.empty.hidden=matched.length!==0;
    if(els.count)els.count.innerHTML='<strong>'+matched.length.toLocaleString()+'</strong> of '+rows.length.toLocaleString()+' models';
    if(els.page)els.page.textContent='Page '+page+' of '+pages;
    if(els.prev)els.prev.disabled=page<=1;
    if(els.next)els.next.disabled=page>=pages;
    syncUrl();
  }
  ['q'].forEach(k=>els[k]?.addEventListener('input',()=>run(true)));
  ['org','license','commercial','format','sort','size'].forEach(k=>els[k]?.addEventListener('change',()=>run(true)));
  els.prev?.addEventListener('click',()=>{page=Math.max(1,page-1);run();scrollTo({top:document.querySelector('.registry-section').offsetTop-90,behavior:'smooth'})});
  els.next?.addEventListener('click',()=>{page++;run();scrollTo({top:document.querySelector('.registry-section').offsetTop-90,behavior:'smooth'})});
  els.reset?.addEventListener('click',()=>{['q','org','license','commercial','format'].forEach(k=>{if(els[k])els[k].value=''});if(els.sort)els.sort.value='popular';if(els.size)els.size.value='50';run(true)});
  run();
})();