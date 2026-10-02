(()=>{
  const body=document.body,id=body.dataset.modelId;if(!id)return;
  const $=s=>document.querySelector(s),from=$('#diff-from'),to=$('#diff-to'),out=$('#diff-output'),sum=$('#diff-summary'),swap=$('#diff-swap');
  const esc=v=>(v??'').toString().replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const show=v=>Array.isArray(v)?v.join(', '):(v&&typeof v==='object'?JSON.stringify(v):String(v??'—'));
  function flatten(obj,p='',out={}){
    if(obj&&typeof obj==='object'&&!Array.isArray(obj)){Object.entries(obj).forEach(([k,v])=>flatten(v,p?p+'.'+k:k,out))}
    else out[p]=obj;return out;
  }
  function render(ledger){
    const a=ledger.snapshots.find(x=>x.snapshot_id===from.value),b=ledger.snapshots.find(x=>x.snapshot_id===to.value);if(!a||!b)return;
    const av=flatten(a.fields),bv=flatten(b.fields),keys=[...new Set([...Object.keys(av),...Object.keys(bv)])].sort();
    const changes=keys.filter(k=>JSON.stringify(av[k])!==JSON.stringify(bv[k]));
    sum.innerHTML='<strong>'+changes.length+'</strong> changed evidence fields · '+esc((a.repository_sha||'no SHA').slice(0,12))+' → '+esc((b.repository_sha||'no SHA').slice(0,12));
    if(!changes.length){out.innerHTML='<div class="diff-empty"><strong>No field differences.</strong><p>These snapshots have equivalent structured evidence.</p></div>';return}
    out.innerHTML=changes.map(k=>'<div class="diff-row"><div class="diff-field">'+esc(k)+'</div><div><span>Before</span><code>'+esc(show(av[k]))+'</code></div><div><span>After</span><code>'+esc(show(bv[k]))+'</code></div></div>').join('');
    const u=new URL(location.href);u.searchParams.set('from',a.snapshot_id);u.searchParams.set('to',b.snapshot_id);history.replaceState(null,'',u);
  }
  fetch('/api/v1/evidence/'+encodeURIComponent(id)+'.json',{cache:'no-store'}).then(r=>r.json()).then(ledger=>{
    const snaps=ledger.snapshots||[],opts=snaps.map(s=>'<option value="'+esc(s.snapshot_id)+'">'+esc((s.observed_at||'').slice(0,19))+' · '+esc((s.repository_sha||'no SHA').slice(0,10))+'</option>').join('');
    from.innerHTML=opts;to.innerHTML=opts;
    const q=new URL(location.href).searchParams;
    from.value=q.get('from')&&snaps.some(s=>s.snapshot_id===q.get('from'))?q.get('from'):(snaps.length>1?snaps[snaps.length-2].snapshot_id:snaps[0]?.snapshot_id||'');
    to.value=q.get('to')&&snaps.some(s=>s.snapshot_id===q.get('to'))?q.get('to'):(snaps.at(-1)?.snapshot_id||'');
    from.addEventListener('change',()=>render(ledger));to.addEventListener('change',()=>render(ledger));
    swap.addEventListener('click',()=>{const x=from.value;from.value=to.value;to.value=x;render(ledger)});render(ledger);
  }).catch(()=>out.innerHTML='<p class="note">Evidence ledger could not be loaded.</p>');
})();