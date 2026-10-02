(()=>{
  const $=(s,r=document)=>r.querySelector(s);
  const slots=[1,2,3,4].map(i=>$('#compare-'+i));
  const output=$('#compare-output'),diff=$('#differences-only'),share=$('#share-comparison'),summary=$('#compare-summary'),msg=$('#compare-message');
  const esc=s=>(s??'').toString().replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
  const join=v=>Array.isArray(v)&&v.length?v.join(', '):'Not declared';
  const gb=v=>typeof v==='number'?'~'+v.toLocaleString(undefined,{maximumFractionDigits:1})+' GB':'Not calculated';
  const date=v=>v?String(v).slice(0,10):'Not declared';
  const compact=n=>{n=Number(n||0);if(n>=1e9)return (n/1e9).toFixed(1)+'B';if(n>=1e6)return (n/1e6).toFixed(1)+'M';if(n>=1e3)return (n/1e3).toFixed(1)+'K';return n.toLocaleString()};
  const context=m=>typeof m.model?.context==='object'?(m.model.context.display||'Not declared'):(m.model?.context||'Not declared');
  const runtimes=m=>[...new Set([...(m.runtime_support?.declared||[]),...(m.runtime_support?.mentioned_in_model_card||[])])].join(', ')||'None observed';
  const precision=m=>Object.entries(m.weights?.precision_availability||{}).filter(([,v])=>v?.available).map(([k])=>k.toUpperCase()).join(', ')||'None observed';
  const base=m=>join(m.lineage?.base_model?.models);
  const recipe=m=>m.training_assets?.training_recipe?.status||'Not classified';
  const data=m=>{const d=m.training_assets?.data_disclosure||{};return d.datasets?.length?d.datasets.join(', '):(d.status||'Not classified')};
  const rows=[
    ['Identity','Developer',m=>m.developer],
    ['Identity','Parameters',m=>m.model?.parameters||'Not declared'],
    ['Identity','Modality',m=>m.model?.modality||'Not declared'],
    ['Scale','Context',context],
    ['Legal','License',m=>m.license?.name||'Not declared'],
    ['Legal','Commercial use',m=>m.license?.commercial_use?.label||'Not classified'],
    ['Weights','Access',m=>m.weights?.access||'Not declared'],
    ['Weights','Exact weight files',m=>(m.weights?.file_count??0).toString()],
    ['Weights','Formats',m=>join(m.weights?.formats)],
    ['Weights','Precision observed',precision],
    ['Hardware','BF16 / FP16 weights',m=>gb(m.hardware?.weight_only_gb?.bf16_fp16)],
    ['Hardware','FP8 / INT8 weights',m=>gb(m.hardware?.weight_only_gb?.fp8_int8)],
    ['Hardware','INT4 weights',m=>gb(m.hardware?.weight_only_gb?.int4)],
    ['Lineage','Family',m=>m.family||'Not declared'],
    ['Lineage','Declared base model',base],
    ['Training','Training recipe',recipe],
    ['Training','Data disclosure',data],
    ['Runtime','Runtime support',runtimes],
    ['Freshness','Repository created',m=>date(m.hub?.created_at)],
    ['Freshness','Publisher updated',m=>date(m.hub?.last_modified)],
    ['Freshness','Last checked',m=>date(m.verification?.checked_at)],
    ['Freshness','Last full field verification',m=>date(m.verification?.full_verified_at||m.verification?.checked_at)],
    ['Popularity','Downloads',m=>compact(m.hub?.downloads)],
    ['Popularity','Likes',m=>compact(m.hub?.likes)]
  ];
  let models=[],map=new Map();
  const selected=()=>slots.map(s=>s.value).filter(Boolean).map(id=>map.get(id)).filter(Boolean);
  const setUrl=()=>{const ids=slots.map(s=>s.value).filter(Boolean),u=new URL(location.href);if(ids.length)u.searchParams.set('models',ids.join(','));else u.searchParams.delete('models');history.replaceState(null,'',u)};
  function applyDiff(){
    document.querySelectorAll('.compare-row[data-same="true"]').forEach(r=>r.hidden=!!diff.checked);
  }
  function render(){
    const ms=selected();setUrl();
    if(ms.length<2){output.innerHTML='<div class="compare-empty"><strong>Select at least two models.</strong><p>Choose up to four verified records to build the comparison.</p></div>';if(summary)summary.textContent='';return}
    let different=0;
    let html='<div class="compare-table" style="--compare-cols:'+ms.length+'"><div class="compare-corner">Field</div>';
    ms.forEach(m=>html+='<div class="compare-model-head"><span>'+esc(m.developer)+'</span><strong>'+esc(m.name)+'</strong><a href="/models/'+encodeURIComponent(m.id)+'/">Verified record →</a></div>');
    rows.forEach(([section,label,fn])=>{
      const vals=ms.map(fn),same=vals.every(v=>v===vals[0]);if(!same)different++;
      const cls=same?'same':'different';
      html+='<div class="compare-row '+cls+'" data-same="'+same+'"><div class="compare-label '+cls+'"><span>'+esc(section)+'</span><strong>'+esc(label)+'</strong></div>'+
        vals.map((v,i)=>'<div class="compare-value '+cls+'" data-model="'+esc(ms[i].name)+'">'+esc(v)+'</div>').join('')+'</div>';
    });
    html+='</div>';output.innerHTML=html;
    if(summary)summary.innerHTML='<strong>'+different+'</strong> of '+rows.length+' fields differ · differences are highlighted, not ranked';
    applyDiff();
  }
  fetch('/registry.json',{cache:'no-store'}).then(r=>r.json()).then(reg=>{
    models=[...(reg.models||[])].sort((a,b)=>(a.developer+' '+a.name).localeCompare(b.developer+' '+b.name));map=new Map(models.map(m=>[m.id,m]));
    const raw=new URL(location.href).searchParams.get('models');
    let ids=raw?raw.split(',').filter(id=>map.has(id)).slice(0,4):['qwen3-32b','mistral-small-4-119b-a6b'].filter(id=>map.has(id));
    if(ids.length<2)ids=models.slice(0,2).map(m=>m.id);
    slots.forEach((s,i)=>{s.innerHTML='<option value="">'+(i<2?'Select a model…':'None')+'</option>'+models.map(m=>'<option value="'+esc(m.id)+'">'+esc(m.developer+' · '+m.name)+'</option>').join('');s.value=ids[i]||'';s.addEventListener('change',render)});
    render();
  }).catch(()=>output.innerHTML='<div class="compare-empty"><strong>Registry could not be loaded.</strong><p>Please retry in a moment.</p></div>');
  diff?.addEventListener('change',applyDiff);
  share?.addEventListener('click',async()=>{setUrl();try{await navigator.clipboard.writeText(location.href);share.textContent='Link copied';setTimeout(()=>share.textContent='Copy comparison link',1600)}catch{if(msg){msg.hidden=false;msg.textContent=location.href}}});
})();