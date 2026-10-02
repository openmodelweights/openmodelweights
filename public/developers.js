(() => {
  const input=document.getElementById('developer-search');
  const clear=document.getElementById('developer-search-clear');
  const cards=[...document.querySelectorAll('.developer-card[data-developer-search]')];
  const count=document.getElementById('developer-count');
  const empty=document.getElementById('developer-empty');
  if(!input||!cards.length)return;
  const apply=()=>{
    const q=input.value.trim().toLowerCase();
    let visible=0;
    for(const card of cards){
      const show=!q||card.dataset.developerSearch.includes(q);
      card.hidden=!show;
      if(show)visible++;
    }
    count.innerHTML='<strong>'+visible+'</strong> '+(visible===1?'developer':'developers');
    empty.hidden=visible!==0;
    clear.hidden=!q;
  };
  input.addEventListener('input',apply);
  input.addEventListener('search',apply);
  clear?.addEventListener('click',()=>{input.value='';apply();input.focus();});
  apply();
})();