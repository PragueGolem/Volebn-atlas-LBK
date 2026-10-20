(() => {
  'use strict';

  const els = {
    status: document.getElementById('status'),
    election: document.getElementById('election'),
    mode: document.getElementById('mode'),
    party: document.getElementById('party'),
    partyWrap: document.getElementById('partyWrap'),
    candidate: document.getElementById('candidate'),
    candidateWrap: document.getElementById('candidateWrap'),
    comparison: document.getElementById('comparison'),
    comparisonWrap: document.getElementById('comparisonWrap'),
    metric: document.getElementById('metric'),
    metricWrap: document.getElementById('metricWrap'),
    precinct: document.getElementById('precinct'),
    resetView: document.getElementById('resetView'),
    legendTitle: document.getElementById('legendTitle'),
    legend: document.getElementById('legend'),
    metricNote: document.getElementById('metricNote'),
    detailEmpty: document.getElementById('detailEmpty'),
    detailContent: document.getElementById('detailContent'),
    detailTitle: document.getElementById('detailTitle'),
    detailStats: document.getElementById('detailStats'),
    detailRows: document.getElementById('detailRows'),
    detailTableTitle: document.getElementById('detailTableTitle'),
    detailNameHead: document.getElementById('detailNameHead'),
    detailPctHead: document.getElementById('detailPctHead')
  };

  const colors = ['#edf3f8','#d7e4ef','#b6cede','#86aec7','#4f87aa','#225b7d'];
  const divergingNeg = '#b91c1c';
  const divergingPos = '#166534';
  const missingColor = '#e5e7eb';

  let metadata = null;
  let results = [];
  let map = null;
  let geoLayer = null;
  let fullBounds = null;
  let currentGeo = null;
  let currentRows = [];
  let precinctIndex = new Map();
  let metricValues = new Map();
  let selectedLayer = null;

  const geoCache = new Map();

  function fmtInt(v){ return Number(v || 0).toLocaleString('cs-CZ', {maximumFractionDigits:0}); }
  function fmtPct(v){ return `${Number(v || 0).toLocaleString('cs-CZ',{minimumFractionDigits:1,maximumFractionDigits:2})} %`; }
  function normalize(s){ return String(s || '').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase(); }
  function option(select,value,label){ const o=document.createElement('option'); o.value=value; o.textContent=label; select.appendChild(o); }
  function uniq(values){ return [...new Set(values.filter(Boolean))].sort((a,b)=>String(a).localeCompare(String(b),'cs')); }

  function rowsForElection(id){ return results.filter(r => r.election_id === id); }
  function rowsForCurrentElection(){ return rowsForElection(els.election.value); }

  function initMap(){
    map = L.map('map').setView([50.767,15.056],13);
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 19,
      attribution: 'Tiles © Esri'
    }).addTo(map);
  }

  async function loadJson(url){
    const r = await fetch(url, {cache:'no-store'});
    if(!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
    return r.json();
  }

  async function loadGeo(election){
    const path = election.geo;
    if(geoCache.has(path)) return geoCache.get(path);
    const g = await loadJson(path);
    geoCache.set(path,g);
    return g;
  }

  function updateModeVisibility(){
    const mode = els.mode.value;
    els.partyWrap.classList.toggle('hidden', mode === 'compare' || mode === 'turnout');
    els.candidateWrap.classList.toggle('hidden', mode !== 'candidate');
    els.comparisonWrap.classList.toggle('hidden', mode !== 'compare');
    els.metricWrap.classList.toggle('hidden', mode === 'compare' || mode === 'turnout' || mode === 'candidate');
  }

  function updateElection(){
    const eid = els.election.value;
    currentRows = rowsForElection(eid);
    buildPrecinctIndex();
    updatePartyOptions();
    updatePrecinctOptions();
  }

  function updatePartyOptions(){
    const previous = els.party.value;
    const names = uniq(currentRows.map(r=>r.list_name));
    els.party.innerHTML='';
    names.forEach(n=>option(els.party,n,n));
    if(names.includes(previous)) els.party.value=previous;
    else {
      const pirate=names.find(n=>normalize(n).includes('pirat'));
      els.party.value=pirate || names[0] || '';
    }
    updateCandidateOptions();
  }

  function updateCandidateOptions(){
    const previous = els.candidate.value;
    const rows = currentRows.filter(r=>r.list_name===els.party.value);
    const people = new Map();
    rows.forEach(r=>(r.candidates||[]).forEach(c=>people.set(String(c.no),c)));
    els.candidate.innerHTML='';
    [...people.entries()].sort((a,b)=>Number(a[0])-Number(b[0])).forEach(([no,c])=>option(els.candidate,no,`${no}. ${c.name}`));
    if([...els.candidate.options].some(o=>o.value===previous)) els.candidate.value=previous;
  }

  function updateComparisonOptions(){
    const prev=els.comparison.value;
    els.comparison.innerHTML='';
    Object.entries(metadata.comparison||{}).forEach(([id,c])=>option(els.comparison,id,c.label));
    if([...els.comparison.options].some(o=>o.value===prev)) els.comparison.value=prev;
  }

  function updatePrecinctOptions(){
    const prev=els.precinct.value;
    const nums=uniq(currentRows.map(r=>String(r.precinct_no))).sort((a,b)=>Number(a)-Number(b));
    els.precinct.innerHTML='';
    option(els.precinct,'','Všechny okrsky');
    nums.forEach(n=>option(els.precinct,n,`Okrsek ${n}`));
    if([...els.precinct.options].some(o=>o.value===prev)) els.precinct.value=prev;
  }

  function buildPrecinctIndex(){
    precinctIndex = new Map();
    currentRows.forEach(r=>{
      const key=String(r.precinct_key||'');
      if(!key) return;
      if(!precinctIndex.has(key)) precinctIndex.set(key,[]);
      precinctIndex.get(key).push(r);
    });
  }

  function selectedCandidateVotes(row){
    const c=(row.candidates||[]).find(x=>String(x.no)===String(els.candidate.value));
    return c ? Number(c.votes||0) : 0;
  }

  function compareValueForKey(key){
    const cfg=metadata.comparison?.[els.comparison.value];
    if(!cfg) return null;
    const rows22=rowsForElection('kv2022').filter(r=>String(r.precinct_key)===String(key));
    const rows26=rowsForElection('kv2026').filter(r=>String(r.precinct_key)===String(key));
    if(!rows22.length || !rows26.length) return null;
    const valid22=Number(rows22[0].valid_votes||0);
    const valid26=Number(rows26[0].valid_votes||0);
    const votes22=rows22.filter(r=>cfg.from.includes(r.list_name)).reduce((s,r)=>s+Number(r.votes||0),0);
    const votes26=rows26.filter(r=>r.list_name===cfg.to).reduce((s,r)=>s+Number(r.votes||0),0);
    const share22=valid22>0?votes22/valid22*100:0;
    const share26=valid26>0?votes26/valid26*100:0;
    return {share22,share26,delta:share26-share22};
  }

  function computeMetrics(){
    metricValues=new Map();
    const mode=els.mode.value;
    for(const [key,rows] of precinctIndex.entries()){
      const base=rows[0];
      let value=null;
      if(mode==='turnout'){
        const registered=Number(base.registered_voters||0);
        const issued=Number(base.issued_envelopes||0);
        value=registered>0?issued/registered*100:0;
      } else if(mode==='party'){
        const row=rows.find(r=>r.list_name===els.party.value);
        if(row){
          value=els.metric.value==='votes'?Number(row.votes||0):(Number(row.valid_votes||0)>0?Number(row.votes||0)/Number(row.valid_votes)*100:0);
        }
      } else if(mode==='candidate'){
        const row=rows.find(r=>r.list_name===els.party.value);
        if(row) value=selectedCandidateVotes(row);
      } else if(mode==='compare'){
        const cmp=compareValueForKey(key);
        value=cmp?cmp.delta:null;
      }
      metricValues.set(key,value);
    }
  }

  function numericValues(){ return [...metricValues.values()].filter(v=>Number.isFinite(v)); }
  function quantileBreaks(values,n){
    if(!values.length) return Array(n+1).fill(0);
    const sorted=values.slice().sort((a,b)=>a-b); const out=[];
    for(let i=0;i<=n;i++){
      const idx=(sorted.length-1)*(i/n), lo=Math.floor(idx), hi=Math.ceil(idx);
      out.push(lo===hi?sorted[lo]:sorted[lo]+(sorted[hi]-sorted[lo])*(idx-lo));
    }
    return out;
  }

  function colorFor(v,breaks){
    if(v===null || v===undefined || !Number.isFinite(v)) return missingColor;
    if(els.mode.value==='compare'){
      const vals=numericValues(); const maxAbs=Math.max(1,...vals.map(x=>Math.abs(x)));
      const t=Math.min(1,Math.abs(v)/maxAbs);
      const from=v>=0?[235,248,239]:[254,242,242];
      const to=v>=0?[22,101,52]:[185,28,28];
      const rgb=from.map((x,i)=>Math.round(x+(to[i]-x)*t));
      return `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
    }
    for(let i=0;i<colors.length;i++) if(v<=breaks[i+1] || i===colors.length-1) return colors[i];
    return colors[colors.length-1];
  }

  function formatMetric(v){
    if(v===null || v===undefined || !Number.isFinite(v)) return 'bez dat';
    if(els.mode.value==='compare') return `${v>=0?'+':''}${v.toLocaleString('cs-CZ',{minimumFractionDigits:1,maximumFractionDigits:2})} p. b.`;
    if(els.mode.value==='party' && els.metric.value==='votes') return fmtInt(v);
    if(els.mode.value==='candidate') return `${fmtInt(v)} hlasů`;
    return fmtPct(v);
  }

  function updateLegend(breaks){
    els.legend.innerHTML='';
    let title='';
    if(els.mode.value==='turnout') title='Volební účast (%)';
    else if(els.mode.value==='candidate') title='Hlasy kandidáta';
    else if(els.mode.value==='compare') title='Změna 2022 → 2026 (p. b.)';
    else title=els.metric.value==='votes'?'Počet hlasů':'Podíl hlasů (%)';
    els.legendTitle.textContent=title;

    function row(color,text){
      const r=document.createElement('div'); r.className='legendRow';
      const s=document.createElement('span'); s.className='legendSwatch'; s.style.background=color;
      const t=document.createElement('span'); t.textContent=text;
      r.append(s,t); els.legend.appendChild(r);
    }

    if(els.mode.value==='compare'){
      row(divergingNeg,'pokles proti agregátu 2022');
      row('#f3f4f6','beze změny');
      row(divergingPos,'nárůst proti agregátu 2022');
      els.metricNote.textContent='U LOL + Piráti jde o rozdíl proti součtu jejich podpory v roce 2022, nikoli o kauzální koaliční efekt.';
    } else {
      for(let i=0;i<colors.length;i++){
        if(breaks[i]===undefined || breaks[i+1]===undefined) continue;
        row(colors[i],`${formatMetric(breaks[i])} – ${formatMetric(breaks[i+1])}`);
      }
      row(missingColor,'bez dat / nekandiduje');
      els.metricNote.textContent='Intervaly jsou kvantily libereckých volebních okrsků.';
    }
  }

  function renderMap(){
    computeMetrics();
    const vals=numericValues();
    const breaks=quantileBreaks(vals,colors.length);
    updateLegend(breaks);
    if(geoLayer) map.removeLayer(geoLayer);
    geoLayer=L.geoJSON(currentGeo,{
      style:f=>{
        const key=String(f.properties?.precinct_key||'');
        const v=metricValues.get(key);
        return {color:'#536273',weight:.8,opacity:1,fillColor:colorFor(v,breaks),fillOpacity:.62};
      },
      onEachFeature:(f,layer)=>{
        const p=f.properties||{}; const key=String(p.precinct_key||'');
        const v=metricValues.get(key);
        layer.bindTooltip(`<b>Okrsek ${p.precinct_no||''}</b><br>${formatMetric(v)}`);
        layer.on('click',()=>{
          if(selectedLayer) selectedLayer.setStyle({weight:.8,color:'#536273'});
          selectedLayer=layer; layer.setStyle({weight:2.2,color:'#111827'});
          els.precinct.value=String(p.precinct_no||'');
          showDetail(key);
        });
      }
    }).addTo(map);
    fullBounds=geoLayer.getBounds();
    if(fullBounds.isValid()) map.fitBounds(fullBounds.pad(.03));
  }

  function stat(k,v){ return `<div class="stat"><span class="k">${k}</span><span class="v">${v}</span></div>`; }

  function showDetail(key){
    const rows=precinctIndex.get(key)||[];
    if(!rows.length){ els.detailContent.classList.add('hidden'); els.detailEmpty.classList.remove('hidden'); return; }
    const base=rows[0];
    els.detailEmpty.classList.add('hidden'); els.detailContent.classList.remove('hidden');
    els.detailTitle.textContent=`Okrsek ${base.precinct_no}`;
    const turnout=Number(base.registered_voters||0)>0?Number(base.issued_envelopes||0)/Number(base.registered_voters)*100:0;
    els.detailStats.innerHTML=stat('Voliči v seznamu',fmtInt(base.registered_voters))+stat('Vydané obálky',fmtInt(base.issued_envelopes))+stat('Účast',fmtPct(turnout))+stat('Platné kandidátské hlasy',fmtInt(base.valid_votes));
    els.detailRows.innerHTML='';

    if(els.mode.value==='candidate'){
      const row=rows.find(r=>r.list_name===els.party.value);
      const candidates=(row?.candidates||[]).slice().sort((a,b)=>Number(b.votes||0)-Number(a.votes||0));
      els.detailTableTitle.textContent=`Kandidáti – ${els.party.value}`;
      els.detailNameHead.textContent='Kandidát'; els.detailPctHead.textContent='';
      candidates.forEach(c=>{
        const tr=document.createElement('tr'); if(String(c.no)===String(els.candidate.value)) tr.className='selectedRow';
        tr.innerHTML=`<td>${c.no}. ${c.name}</td><td>${fmtInt(c.votes)}</td><td></td>`; els.detailRows.appendChild(tr);
      });
    } else if(els.mode.value==='compare'){
      const cmp=compareValueForKey(key);
      els.detailTableTitle.textContent='Komparace 2022–2026';
      els.detailNameHead.textContent='Ukazatel'; els.detailPctHead.textContent='%';
      const cfg=metadata.comparison?.[els.comparison.value];
      const entries=[['Agregát 2022',cmp?.share22],['Výsledek 2026',cmp?.share26],['Změna (p. b.)',cmp?.delta]];
      entries.forEach(([name,val])=>{const tr=document.createElement('tr');tr.innerHTML=`<td>${name}</td><td></td><td>${name.includes('Změna')?(val>=0?'+':'')+Number(val||0).toLocaleString('cs-CZ',{minimumFractionDigits:1,maximumFractionDigits:2}):fmtPct(val)}</td>`;els.detailRows.appendChild(tr);});
      if(cfg?.label) els.detailTableTitle.textContent=cfg.label;
    } else {
      els.detailTableTitle.textContent='Výsledky všech kandidátek';
      els.detailNameHead.textContent='Kandidátka'; els.detailPctHead.textContent='%';
      rows.slice().sort((a,b)=>Number(b.votes||0)-Number(a.votes||0)).forEach(r=>{
        const pct=Number(r.valid_votes||0)>0?Number(r.votes||0)/Number(r.valid_votes)*100:0;
        const tr=document.createElement('tr'); if(r.list_name===els.party.value) tr.className='selectedRow';
        tr.innerHTML=`<td>${r.list_name}</td><td>${fmtInt(r.votes)}</td><td>${fmtPct(pct)}</td>`; els.detailRows.appendChild(tr);
      });
    }
  }

  async function refreshGeoAndMap(){
    const election=metadata.elections.find(e=>e.id===els.election.value);
    if(!election) return;
    currentGeo=await loadGeo(election);
    renderMap();
    els.status.textContent=`${currentRows.length.toLocaleString('cs-CZ')} řádků výsledků · ${currentGeo.features.length} okrsků`;
  }

  async function refreshAll(){
    updateModeVisibility();
    if(els.mode.value==='compare') els.election.value='kv2026';
    updateElection();
    updateComparisonOptions();
    await refreshGeoAndMap();
  }

  els.election.addEventListener('change',refreshAll);
  els.mode.addEventListener('change',refreshAll);
  els.party.addEventListener('change',()=>{ updateCandidateOptions(); renderMap(); });
  els.candidate.addEventListener('change',renderMap);
  els.comparison.addEventListener('change',renderMap);
  els.metric.addEventListener('change',renderMap);
  els.precinct.addEventListener('change',()=>{
    if(!els.precinct.value){ if(fullBounds?.isValid()) map.fitBounds(fullBounds.pad(.03)); return; }
    const key=`563889:${els.precinct.value}`; showDetail(key);
    if(geoLayer){ geoLayer.eachLayer(l=>{if(String(l.feature?.properties?.precinct_key)===key){map.fitBounds(l.getBounds().pad(.2)); l.fire('click');}}); }
  });
  els.resetView.addEventListener('click',()=>{els.precinct.value='';if(fullBounds?.isValid())map.fitBounds(fullBounds.pad(.03));});

  async function init(){
    try{
      initMap();
      [metadata,results]=await Promise.all([loadJson('metadata.json'),loadJson('results.json')]);
      els.election.innerHTML=''; metadata.elections.forEach(e=>option(els.election,e.id,e.label));
      if(metadata.elections.some(e=>e.id==='kv2026')) els.election.value='kv2026';
      updateComparisonOptions();
      await refreshAll();
    }catch(err){
      console.error(err);
      els.status.textContent='Chyba načítání dat';
      els.detailEmpty.innerHTML=`<div class="errorBox"><b>Atlas nelze načíst.</b><br>${String(err.message||err)}<br><br>Nejdřív spusť 1_VYTVORIT_DATA.bat a potom 2_SPUSTIT_ATLAS.bat.</div>`;
    }
  }

  init();
})();
