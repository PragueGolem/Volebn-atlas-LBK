(() => {
  'use strict';

  const CITY = '563889';
  const AGG_ID = '__LOL_PIRATI_2022__';
  const AGG_LABEL = 'Liberec otevřený lidem + Piráti (součet 2022)';
  const AGG_PARTIES = ['Liberec otevřený lidem', 'Česká pirátská strana'];

  const els = {
    status: document.getElementById('status'),
    election: document.getElementById('election'),
    party: document.getElementById('party'),
    precinct: document.getElementById('precinct'),
    resetView: document.getElementById('resetView'),
    legend: document.getElementById('legend'),
    detailEmpty: document.getElementById('detailEmpty'),
    detailContent: document.getElementById('detailContent'),
    detailTitle: document.getElementById('detailTitle'),
    detailStats: document.getElementById('detailStats'),
    detailRows: document.getElementById('detailRows')
  };

  const colors = ['#edf3f8','#d7e4ef','#b6cede','#86aec7','#4f87aa','#225b7d'];
  const missingColor = '#e5e7eb';

  let metadata = null;
  let results = [];
  let map = null;
  let geoLayer = null;
  let currentGeo = null;
  let currentRows = [];
  let precinctIndex = new Map();
  let values = new Map();
  let fullBounds = null;
  let selectedLayer = null;
  const geoCache = new Map();

  const fmtInt = v => Number(v || 0).toLocaleString('cs-CZ', {maximumFractionDigits:0});
  const fmtPct = v => `${Number(v || 0).toLocaleString('cs-CZ',{minimumFractionDigits:1,maximumFractionDigits:2})} %`;
  const normalize = s => String(s || '').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();

  function option(select,value,label){
    const o=document.createElement('option'); o.value=value; o.textContent=label; select.appendChild(o);
  }

  function initMap(){
    map=L.map('map').setView([50.767,15.056],13);
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',{
      maxZoom:19, attribution:'Tiles © Esri'
    }).addTo(map);
  }

  async function loadJson(url){
    const r=await fetch(url,{cache:'no-store'});
    if(!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
    return r.json();
  }

  async function loadGeo(election){
    const path=election.geo;
    if(geoCache.has(path)) return geoCache.get(path);
    const g=await loadJson(path); geoCache.set(path,g); return g;
  }

  function rowsForElection(id){ return results.filter(r=>r.election_id===id); }

  function buildPrecinctIndex(){
    precinctIndex=new Map();
    currentRows.forEach(r=>{
      const n=Number(r.precinct_no);
      if(!Number.isFinite(n)) return;
      if(!precinctIndex.has(n)) precinctIndex.set(n,[]);
      precinctIndex.get(n).push(r);
    });
  }

  function partyNames(){
    return [...new Set(currentRows.map(r=>r.list_name).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'cs'));
  }

  function updatePartyOptions(){
    const previous=els.party.value;
    els.party.innerHTML='';
    const names=partyNames();
    names.forEach(n=>option(els.party,n,n));
    if(els.election.value==='kv2022') option(els.party,AGG_ID,AGG_LABEL);
    const opts=[...els.party.options].map(o=>o.value);
    if(opts.includes(previous)) els.party.value=previous;
    else {
      const pirate=names.find(n=>normalize(n).includes('pirat'));
      els.party.value=pirate || names[0] || '';
    }
  }

  function updatePrecinctOptions(){
    const prev=els.precinct.value;
    els.precinct.innerHTML=''; option(els.precinct,'','Všechny okrsky');
    [...precinctIndex.keys()].sort((a,b)=>a-b).forEach(n=>option(els.precinct,String(n),`Okrsek ${n}`));
    if([...els.precinct.options].some(o=>o.value===prev)) els.precinct.value=prev;
  }

  function selectedRows(rows){
    if(els.party.value===AGG_ID) return rows.filter(r=>AGG_PARTIES.includes(r.list_name));
    return rows.filter(r=>r.list_name===els.party.value);
  }

  function shareForPrecinct(rows){
    if(!rows?.length) return null;
    const picked=selectedRows(rows);
    if(!picked.length) return null;
    const valid=Number(rows[0].valid_votes||0);
    const votes=picked.reduce((s,r)=>s+Number(r.votes||0),0);
    return valid>0?votes/valid*100:null;
  }

  function computeValues(){
    values=new Map();
    for(const [n,rows] of precinctIndex.entries()) values.set(n,shareForPrecinct(rows));
  }

  function quantileBreaks(nums,n){
    if(!nums.length) return Array(n+1).fill(0);
    const a=nums.slice().sort((x,y)=>x-y), out=[];
    for(let i=0;i<=n;i++){
      const idx=(a.length-1)*(i/n), lo=Math.floor(idx), hi=Math.ceil(idx);
      out.push(lo===hi?a[lo]:a[lo]+(a[hi]-a[lo])*(idx-lo));
    }
    return out;
  }

  function colorFor(v,breaks){
    if(v===null || !Number.isFinite(v)) return missingColor;
    for(let i=0;i<colors.length;i++) if(v<=breaks[i+1] || i===colors.length-1) return colors[i];
    return colors[colors.length-1];
  }

  function updateLegend(breaks){
    els.legend.innerHTML='';
    function add(color,text){
      const r=document.createElement('div');r.className='legendRow';
      const s=document.createElement('span');s.className='legendSwatch';s.style.background=color;
      const t=document.createElement('span');t.textContent=text;r.append(s,t);els.legend.appendChild(r);
    }
    for(let i=0;i<colors.length;i++){
      if(!Number.isFinite(breaks[i]) || !Number.isFinite(breaks[i+1])) continue;
      add(colors[i],`${fmtPct(breaks[i])} – ${fmtPct(breaks[i+1])}`);
    }
    add(missingColor,'bez dat / nekandiduje');
  }

  function normKey(k){ return String(k||'').toUpperCase().replace(/[^A-Z0-9]/g,''); }
  function prop(props,names){
    const keys=Object.keys(props||{});
    for(const name of names){
      const nk=normKey(name);
      const hit=keys.find(k=>normKey(k)===nk);
      if(hit) return props[hit];
    }
    return null;
  }

  // The original LBK GeoJSON uses municipality_code, precinct and precinct_key.
  function featureMunicipality(f){
    const p=f.properties||{};
    const direct=prop(p,['municipality_code','OBEC','KOD_OBCE','ZUJ','KOD_OBEC']);
    if(direct!==null && direct!==undefined && String(direct).trim()!=='') return String(direct).replace(/\.0$/,'');
    const key=String(p.precinct_key||p.PRECINCT_KEY||'');
    const m=key.match(/(\d{6})/); return m?m[1]:'';
  }

  function featurePrecinct(f){
    const p=f.properties||{};
    const direct=prop(p,['precinct','precinct_no','OKRSEK','CISLO_OKRSKU','CISLOOKRSKU','OKRSEK_C']);
    if(direct!==null && direct!==undefined && String(direct).trim()!==''){
      const n=Number(String(direct).replace(',','.'));
      if(Number.isFinite(n)) return n;
    }
    const key=String(p.precinct_key||p.PRECINCT_KEY||'');
    if(key){
      const tail=key.split(/[:|/_-]/).filter(Boolean).pop();
      const n=Number(tail);
      if(Number.isFinite(n)) return n;
    }
    for(const [k,v] of Object.entries(p)){
      if(normKey(k).includes('OKR') || normKey(k).includes('PRECINCT')){
        const n=Number(v); if(Number.isFinite(n)) return n;
      }
    }
    return null;
  }

  // Boundaries must never disappear just because a results key failed to match.
  // Any geometry feature belonging to municipality 563889 is drawn; if data do
  // not match, it remains grey instead of being filtered out.
  function isLiberecFeature(f){
    const m=featureMunicipality(f);
    if(m===CITY) return true;
    const key=String(f.properties?.precinct_key||f.properties?.PRECINCT_KEY||'');
    return key.startsWith(`${CITY}:`) || key.startsWith(`${CITY}|`) || key.includes(CITY);
  }

  function renderMap(){
    computeValues();
    const nums=[...values.values()].filter(Number.isFinite);
    const breaks=quantileBreaks(nums,colors.length); updateLegend(breaks);
    if(geoLayer) map.removeLayer(geoLayer);

    let polygons=0;
    const matchedNos=new Set();
    geoLayer=L.geoJSON(currentGeo,{
      filter:f=>{
        const ok=isLiberecFeature(f);
        if(ok) polygons++;
        return ok;
      },
      style:f=>{
        const n=featurePrecinct(f), v=values.get(n);
        if(n!==null && precinctIndex.has(n)) matchedNos.add(n);
        return {color:'#172033',weight:1.5,opacity:1,fillColor:colorFor(v,breaks),fillOpacity:.58};
      },
      onEachFeature:(f,layer)=>{
        const n=featurePrecinct(f), v=values.get(n);
        layer.bindTooltip(`<b>Okrsek ${n ?? '?'}</b><br>${v===null || v===undefined?'bez dat':fmtPct(v)}`,{sticky:true});
        layer.on('mouseover',()=>{ if(layer!==selectedLayer){layer.setStyle({weight:2.6,color:'#000',fillOpacity:.75});if(layer.bringToFront)layer.bringToFront();} });
        layer.on('mouseout',()=>{ if(layer!==selectedLayer && geoLayer) geoLayer.resetStyle(layer); });
        layer.on('click',()=>{
          if(selectedLayer && geoLayer && selectedLayer!==layer) geoLayer.resetStyle(selectedLayer);
          selectedLayer=layer; layer.setStyle({weight:3,color:'#000',fillOpacity:.82}); if(layer.bringToFront)layer.bringToFront();
          if(n!==null){els.precinct.value=String(n);showDetail(n);}
        });
      }
    }).addTo(map);

    fullBounds=geoLayer.getBounds();
    if(fullBounds.isValid()) map.fitBounds(fullBounds.pad(.02));
    els.status.textContent=`${currentRows.length.toLocaleString('cs-CZ')} řádků výsledků · ${precinctIndex.size} okrsků · ${polygons} polygonů · ${matchedNos.size} napojených`;
  }

  function stat(k,v){ return `<div class="stat"><span class="k">${k}</span><span class="v">${v}</span></div>`; }

  function showDetail(no){
    const rows=precinctIndex.get(Number(no))||[];
    if(!rows.length){els.detailContent.classList.add('hidden');els.detailEmpty.classList.remove('hidden');return;}
    const base=rows[0];
    els.detailEmpty.classList.add('hidden');els.detailContent.classList.remove('hidden');
    els.detailTitle.textContent=`Okrsek ${no}`;
    const turnout=Number(base.registered_voters||0)>0?Number(base.issued_envelopes||0)/Number(base.registered_voters)*100:0;
    els.detailStats.innerHTML=stat('Voliči v seznamu',fmtInt(base.registered_voters))+stat('Vydané obálky',fmtInt(base.issued_envelopes))+stat('Účast',fmtPct(turnout))+stat('Platné kandidátské hlasy',fmtInt(base.valid_votes));
    els.detailRows.innerHTML='';
    rows.slice().sort((a,b)=>Number(b.votes||0)-Number(a.votes||0)).forEach(r=>{
      const pct=Number(r.valid_votes||0)>0?Number(r.votes||0)/Number(r.valid_votes)*100:0;
      const tr=document.createElement('tr');
      if(els.party.value!==AGG_ID && r.list_name===els.party.value) tr.className='selectedRow';
      tr.innerHTML=`<td>${r.list_name}</td><td>${fmtInt(r.votes)}</td><td>${fmtPct(pct)}</td>`;
      els.detailRows.appendChild(tr);
    });
    if(els.party.value===AGG_ID){
      const picked=selectedRows(rows), votes=picked.reduce((s,r)=>s+Number(r.votes||0),0), valid=Number(base.valid_votes||0), pct=valid>0?votes/valid*100:0;
      const tr=document.createElement('tr');tr.className='selectedRow';tr.innerHTML=`<td><b>${AGG_LABEL}</b></td><td><b>${fmtInt(votes)}</b></td><td><b>${fmtPct(pct)}</b></td>`;els.detailRows.prepend(tr);
    }
  }

  async function switchElection(){
    const election=metadata.elections.find(e=>e.id===els.election.value);
    currentRows=rowsForElection(election.id);buildPrecinctIndex();updatePartyOptions();updatePrecinctOptions();
    currentGeo=await loadGeo(election);renderMap();
    els.detailContent.classList.add('hidden');els.detailEmpty.classList.remove('hidden');
  }

  async function init(){
    initMap();
    [metadata,results]=await Promise.all([loadJson('metadata.json'),loadJson('results.json')]);
    els.election.innerHTML='';metadata.elections.forEach(e=>option(els.election,e.id,e.label));
    els.election.value=metadata.elections.some(e=>e.id==='kv2026')?'kv2026':metadata.elections[0].id;
    await switchElection();
    els.election.addEventListener('change',switchElection);
    els.party.addEventListener('change',()=>{renderMap();const n=els.precinct.value;if(n)showDetail(Number(n));});
    els.precinct.addEventListener('change',()=>{const n=Number(els.precinct.value);if(n)showDetail(n);else{els.detailContent.classList.add('hidden');els.detailEmpty.classList.remove('hidden');}});
    els.resetView.addEventListener('click',()=>{if(fullBounds?.isValid())map.fitBounds(fullBounds.pad(.02));});
  }

  init().catch(err=>{console.error(err);els.status.textContent=`Chyba: ${err.message}`;});
})();
