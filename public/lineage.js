(()=>{
  const dataEl=document.querySelector("#lineage-data"); if(!dataEl)return;
  const data=JSON.parse(dataEl.textContent),family=document.querySelector("#lineage-family"),dev=document.querySelector("#lineage-developer"),svg=document.querySelector("#lineage-svg"),empty=document.querySelector("#lineage-empty");
  const esc=s=>(s||"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c])),short=s=>s.length>34?s.slice(0,32)+"…":s;
  const render=()=>{const f=family.value,d=dev.value;let children=data.models.filter(m=>(!f||m.family===f)&&(!d||m.developer===d));if(!children.length){svg.innerHTML="";empty.hidden=false;return}empty.hidden=true;
    const repoMap=new Map(data.models.map(m=>[m.repo,m])),parentMap=new Map();children.forEach(c=>(c.parents||[]).forEach(p=>{if(!parentMap.has(p))parentMap.set(p,repoMap.get(p)||{id:"ext-"+p,name:p.split("/").pop(),repo:p,external:true})}));
    const parents=[...parentMap.values()],left=parents.length?parents:[{id:"root",name:"No declared base model",repo:"",external:true}],height=Math.max(420,Math.max(left.length,children.length)*76+60),width=1040;
    svg.setAttribute("viewBox",`0 0 ${width} ${height}`);const spread=(arr,key)=>new Map(arr.map((x,i)=>[key(x),50+i*((height-100)/Math.max(1,arr.length-1))]));const py=spread(left,p=>p.repo||p.id),cy=spread(children,c=>c.id);
    let out='<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" class="lineage-arrow"/></marker></defs>';
    children.forEach(c=>(c.parents||[]).forEach(p=>{out+=`<path class="lineage-edge" d="M 310 ${py.get(p)} C 430 ${py.get(p)},500 ${cy.get(c.id)},620 ${cy.get(c.id)}" marker-end="url(#arrow)"/>`}));
    if(!parents.length)children.forEach(c=>out+=`<path class="lineage-edge muted" d="M 310 50 C 430 50,500 ${cy.get(c.id)},620 ${cy.get(c.id)}" marker-end="url(#arrow)"/>`);
    left.forEach(p=>{const y=py.get(p.repo||p.id),tracked=repoMap.get(p.repo),href=tracked?tracked.url:(p.repo?`https://huggingface.co/${p.repo}`:"#");out+=`<a href="${esc(href)}"><g class="lineage-node ${p.external?"external":""}"><rect x="20" y="${y-24}" width="290" height="48" rx="10"/><text x="36" y="${y+5}">${esc(short(p.name))}</text></g></a>`});
    children.forEach(c=>{const y=cy.get(c.id);out+=`<a href="${esc(c.url)}"><g class="lineage-node"><rect x="620" y="${y-24}" width="390" height="48" rx="10"/><text x="636" y="${y+5}">${esc(short(c.name))}</text></g></a>`});svg.innerHTML=out;document.querySelector("#lineage-summary").textContent=`${children.length} tracked models · ${parents.length} declared parent references`};
  [family,dev].forEach(x=>x.addEventListener("change",render));render();
})();