(()=>{
  const slots=[1,2,3,4].map(i=>document.querySelector("#compare-"+i));
  const output=document.querySelector("#compare-output");
  const msg=document.querySelector("#compare-message");
  const diff=document.querySelector("#differences-only");
  const share=document.querySelector("#share-comparison");
  const esc=s=>(s??"").toString().replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c]));
  const arr=v=>Array.isArray(v)?v:[];
  const join=v=>arr(v).length?arr(v).join(", "):"Not declared";
  const gb=v=>typeof v==="number"?"~"+v.toLocaleString(undefined,{maximumFractionDigits:1})+" GB":"Not calculated";
  const context=m=>typeof m.model?.context==="object"?(m.model.context.display||"Not declared"):(m.model?.context||"Not declared");
  const runtimes=m=>[...new Set([...(m.runtime_support?.declared||[]),...(m.runtime_support?.mentioned_in_model_card||[])])].join(", ")||"None observed";
  const precision=m=>Object.entries(m.weights?.precision_availability||{}).filter(([,v])=>v?.available).map(([k])=>k.toUpperCase()).join(", ")||"None observed";
  const base=m=>join(m.lineage?.base_model?.models);
  const recipe=m=>m.training_assets?.training_recipe?.status||"Not classified";
  const data=m=>{const d=m.training_assets?.data_disclosure||{};return d.datasets?.length?d.datasets.join(", "):(d.status||"Not classified")};
  const rows=[
    ["Developer",m=>m.developer],
    ["Parameters",m=>m.model?.parameters||"Not declared"],
    ["Modality",m=>m.model?.modality||"Not declared"],
    ["Context",context],
    ["License",m=>m.license?.name||"Not declared"],
    ["Commercial use",m=>m.license?.commercial_use?.label||"Not classified"],
    ["Access",m=>m.weights?.access||"Not declared"],
    ["Exact weight files",m=>(m.weights?.file_count??0).toString()],
    ["Formats",m=>join(m.weights?.formats)],
    ["Precision observed",precision],
    ["BF16 / FP16 weights",m=>gb(m.hardware?.weight_only_gb?.bf16_fp16)],
    ["FP8 / INT8 weights",m=>gb(m.hardware?.weight_only_gb?.fp8_int8)],
    ["INT4 weights",m=>gb(m.hardware?.weight_only_gb?.int4)],
    ["Family",m=>m.family||"Not declared"],
    ["Declared base model",base],
    ["Training recipe",recipe],
    ["Data disclosure",data],
    ["Runtime support",runtimes],
    ["Verification date",m=>m.verification?.checked_at||"Not declared"]
  ];
  let models=[],map=new Map();
  const selected=()=>slots.map(s=>s.value).filter(Boolean).map(id=>map.get(id)).filter(Boolean);
  const setUrl=()=>{const ids=slots.map(s=>s.value).filter(Boolean);const u=new URL(location.href);if(ids.length)u.searchParams.set("models",ids.join(","));else u.searchParams.delete("models");history.replaceState(null,"",u)};
  const applyDiff=()=>document.querySelectorAll(".compare-row[data-same=true]").forEach(r=>r.hidden=diff.checked);
  const render=()=>{const ms=selected();setUrl();if(ms.length<2){output.innerHTML='<div class="compare-empty"><strong>Select at least two models.</strong><p>Choose up to four verified records to build the comparison.</p></div>';return}
    let html='<div class="compare-table" style="--compare-cols:'+ms.length+'"><div class="compare-corner">Field</div>';
    ms.forEach(m=>html+='<div class="compare-model-head"><span>'+esc(m.developer)+'</span><strong>'+esc(m.name)+'</strong><a href="/models/'+encodeURIComponent(m.id)+'/">Open verified record →</a></div>');
    rows.forEach(([label,fn])=>{const vals=ms.map(fn),same=vals.every(v=>v===vals[0]);html+='<div class="compare-row'+(same?' same':'')+'" data-same="'+same+'"><div class="compare-label">'+esc(label)+'</div>'+vals.map(v=>'<div class="compare-value">'+esc(v)+'</div>').join("")+'</div>'});
    html+='</div>';output.innerHTML=html;applyDiff()};
  fetch("/registry.json",{cache:"no-store"}).then(r=>r.json()).then(reg=>{
    models=[...(reg.models||[])].sort((a,b)=>(a.developer+" "+a.name).localeCompare(b.developer+" "+b.name));map=new Map(models.map(m=>[m.id,m]));
    const params=(new URL(location.href)).searchParams.get("models");let ids=params?params.split(",").filter(id=>map.has(id)).slice(0,4):["qwen3-32b","mistral-small-4-119b-a6b"].filter(id=>map.has(id));
    if(ids.length===1){const alt=models.find(m=>m.id!==ids[0]);if(alt)ids.push(alt.id)}
    slots.forEach((s,i)=>{s.innerHTML='<option value="">'+(i<2?"Select a model…":"None")+'</option>'+models.map(m=>'<option value="'+esc(m.id)+'">'+esc(m.developer+" · "+m.name)+'</option>').join("");s.value=ids[i]||"";s.addEventListener("change",render)});render()
  }).catch(()=>{output.innerHTML='<div class="compare-empty"><strong>Registry could not be loaded.</strong><p>Please retry in a moment.</p></div>'});
  diff.addEventListener("change",applyDiff);
  share.addEventListener("click",async()=>{setUrl();try{await navigator.clipboard.writeText(location.href);share.textContent="Link copied";setTimeout(()=>share.textContent="Copy comparison link",1600)}catch{msg.hidden=false;msg.textContent=location.href}});
})();