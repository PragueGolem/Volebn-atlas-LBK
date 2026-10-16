(() => {
  'use strict';

  const els = {
    status: document.getElementById('status'),
    election: document.getElementById('election'),
    groupMode: document.getElementById('groupMode'),
    group: document.getElementById('group'),
    singleGroupWrap: document.getElementById('singleGroupWrap'),
    customGroupWrap: document.getElementById('customGroupWrap'),
    customGroups: document.getElementById('customGroups'),
    metric: document.getElementById('metric'),
    municipality: document.getElementById('municipality'),
    resetView: document.getElementById('resetView'),
    legendTitle: document.getElementById('legendTitle'),
    legend: document.getElementById('legend'),
    metricNote: document.getElementById('metricNote'),
    detailEmpty: document.getElementById('detailEmpty'),
    detailContent: document.getElementById('detailContent'),
    detailTitle: document.getElementById('detailTitle'),
    detailStats: document.getElementById('detailStats'),
    detailRows: document.getElementById('detailRows')
  };

  const quantileColors = ['#edf3f8', '#d7e4ef', '#b6cede', '#86aec7', '#4f87aa', '#225b7d'];
  const percentLight = '#edf3f8';
  const percentDark = '#174f72';
  const missingColor = '#e5e7eb';

  let metadata = null;
  let results = [];
  let map = null;
  let geoLayer = null;
  let currentGeo = null;
  let currentElectionRows = [];
  let precinctIndex = new Map();
  let metricValues = new Map();
  let breaks = [];
  let percentDomain = { min: 0, max: 1 };
  let selectedLayer = null;
  let fullRegionBounds = null;
  const geoCache = new Map();

  function fmtInt(v) {
    return Number(v || 0).toLocaleString('cs-CZ', { maximumFractionDigits: 0 });
  }

  function fmtPct(v) {
    return `${Number(v || 0).toLocaleString('cs-CZ', { minimumFractionDigits: 1, maximumFractionDigits: 2 })} %`;
  }

  function fmtStrength(v) {
    return Number(v || 0).toLocaleString('cs-CZ', { maximumFractionDigits: 0 });
  }

  function normalizeText(s) {
    return String(s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  }

  function option(select, value, label) {
    const o = document.createElement('option');
    o.value = value;
    o.textContent = label;
    select.appendChild(o);
  }

  function uniqSorted(values) {
    return [...new Set(values.filter(v => String(v || '').trim() !== ''))]
      .sort((a, b) => String(a).localeCompare(String(b), 'cs'));
  }

  function isMunicipal() {
    return els.election.value === 'kv2026';
  }

  function isPercentMetric() {
    return els.metric.value === 'share' || els.metric.value === 'turnout';
  }

  function rowsForElection() {
    const eid = els.election.value;
    let rows = results.filter(r => r.election_id === eid);
    if (eid === 'kv2026') {
      const main = rows.filter(r => r.is_main_contest === true || r.is_main_contest === 'true' || r.is_main_contest === 1);
      if (main.length) rows = main;
    }
    return rows;
  }

  function choosePiratesOrFirst(values) {
    if (!values.length) return '';
    const pirate = values.find(v => normalizeText(v).includes('pirat'));
    return pirate || values[0];
  }

  function updateGroupControls() {
    const mode = els.groupMode.value;
    els.singleGroupWrap.classList.toggle('hidden', mode === 'custom');
    els.customGroupWrap.classList.toggle('hidden', mode !== 'custom');

    // For municipal elections, once a municipality is selected, offer only
    // lists that actually stood in that municipality. For regional/parliamentary
    // elections the list selector remains region-wide.
    const selectedMunicipality = els.municipality.value;
    const rows = (isMunicipal() && selectedMunicipality)
      ? currentElectionRows.filter(r => String(r.municipality_code || '') === selectedMunicipality)
      : currentElectionRows;
    if (mode === 'official') {
      const values = uniqSorted(rows.map(r => r.list_name));
      const previous = els.group.value;
      els.group.innerHTML = '';
      values.forEach(v => option(els.group, v, v));
      els.group.value = values.includes(previous) ? previous : choosePiratesOrFirst(values);
    } else if (mode === 'family') {
      const values = uniqSorted(rows.map(r => r.family_name));
      const previous = els.group.value;
      els.group.innerHTML = '';
      values.forEach(v => option(els.group, v, v));
      els.group.value = values.includes(previous) ? previous : choosePiratesOrFirst(values);
    } else {
      const values = uniqSorted(rows.map(r => r.list_name));
      const selectedBefore = new Set([...els.customGroups.selectedOptions].map(o => o.value));
      els.customGroups.innerHTML = '';
      values.forEach(v => option(els.customGroups, v, v));
      const fallback = choosePiratesOrFirst(values);
      [...els.customGroups.options].forEach(o => {
        o.selected = selectedBefore.size ? selectedBefore.has(o.value) : o.value === fallback;
      });
    }

    const strengthOpt = [...els.metric.options].find(o => o.value === 'strength');
    if (strengthOpt) strengthOpt.disabled = isMunicipal();
    if (isMunicipal() && els.metric.value === 'strength') els.metric.value = 'share';
  }

  function updateMunicipalities() {
    const previous = els.municipality.value;
    const namesByCode = new Map();
    currentElectionRows.forEach(r => {
      if (r.municipality_code) namesByCode.set(String(r.municipality_code), r.municipality_name || r.municipality_code);
    });
    const pairs = [...namesByCode.entries()].sort((a, b) => a[1].localeCompare(b[1], 'cs'));
    els.municipality.innerHTML = '';
    option(els.municipality, '', 'Všechny obce');
    pairs.forEach(([code, name]) => option(els.municipality, code, name));
    if ([...els.municipality.options].some(o => o.value === previous)) els.municipality.value = previous;
  }

  function selectedOfficialNames() {
    const mode = els.groupMode.value;
    if (mode === 'custom') return new Set([...els.customGroups.selectedOptions].map(o => o.value));
    return null;
  }

  function rowMatchesSelection(r) {
    const mode = els.groupMode.value;
    if (mode === 'official') return r.list_name === els.group.value;
    if (mode === 'family') return r.family_name === els.group.value;
    return selectedOfficialNames().has(r.list_name);
  }

  function buildPrecinctIndex() {
    precinctIndex = new Map();
    for (const r of currentElectionRows) {
      const key = String(r.precinct_key || '');
      if (!key) continue;
      if (!precinctIndex.has(key)) precinctIndex.set(key, []);
      precinctIndex.get(key).push(r);
    }
  }

  function aggregateMetrics() {
    metricValues = new Map();
    const metric = els.metric.value;
    const precinctData = [];

    // Always calculate against the entire Liberec Region. Selecting a municipality
    // only changes focus/highlighting, never the statistical denominator.
    for (const [key, rows] of precinctIndex.entries()) {
      if (!rows.length) continue;
      const base = rows[0];
      const selected = rows.filter(rowMatchesSelection);
      const onBallot = selected.length > 0;
      const votes = selected.reduce((sum, r) => sum + Number(r.votes || 0), 0);
      const validVotes = Number(base.valid_votes || 0);
      const registered = Number(base.registered_voters || 0);
      const issued = Number(base.issued_envelopes || 0);
      const share = validVotes > 0 ? votes / validVotes * 100 : 0;
      const turnout = registered > 0 ? issued / registered * 100 : 0;
      precinctData.push({ key, onBallot, votes, validVotes, share, turnout });
    }

    let regionShare = 0;
    if (metric === 'strength') {
      const regionVotes = precinctData.filter(d => d.onBallot).reduce((s, d) => s + d.votes, 0);
      const regionValid = precinctData.filter(d => d.onBallot).reduce((s, d) => s + d.validVotes, 0);
      regionShare = regionValid > 0 ? regionVotes / regionValid * 100 : 0;
    }

    precinctData.forEach(d => {
      let value = null;
      if (metric === 'turnout') value = d.turnout;
      else if (!d.onBallot) value = null;
      else if (metric === 'votes') value = d.votes;
      else if (metric === 'share') value = d.share;
      else if (metric === 'strength') value = regionShare > 0 ? d.share / regionShare * 100 : 0;
      metricValues.set(d.key, { ...d, value, regionShare });
    });

    const numeric = [...metricValues.values()].map(d => d.value).filter(v => Number.isFinite(v));
    if (isPercentMetric()) {
      const min = numeric.length ? Math.floor(Math.min(...numeric)) : 0;
      const maxValue = numeric.length ? Math.max(...numeric) : 1;
      const max = Math.max(min + 1, Math.ceil(maxValue));
      percentDomain = { min, max };
      breaks = [];
    } else {
      breaks = quantileBreaks(numeric, quantileColors.length);
    }
    updateLegend(regionShare);
  }

  function quantileBreaks(values, n) {
    if (!values.length) return Array(n + 1).fill(0);
    const sorted = values.slice().sort((a, b) => a - b);
    const qs = [];
    for (let i = 0; i <= n; i++) {
      const p = i / n;
      const idx = (sorted.length - 1) * p;
      const lo = Math.floor(idx), hi = Math.ceil(idx);
      const val = lo === hi ? sorted[lo] : sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo);
      qs.push(val);
    }
    return qs;
  }

  function hexToRgb(hex) {
    const clean = hex.replace('#', '');
    return {
      r: parseInt(clean.slice(0, 2), 16),
      g: parseInt(clean.slice(2, 4), 16),
      b: parseInt(clean.slice(4, 6), 16)
    };
  }

  function mixColor(a, b, t) {
    const ca = hexToRgb(a), cb = hexToRgb(b);
    const c = ['r', 'g', 'b'].map(k => Math.round(ca[k] + (cb[k] - ca[k]) * Math.max(0, Math.min(1, t))));
    return `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
  }

  function percentColorFor(v) {
    const bucket = Math.floor(v);
    const span = Math.max(1, percentDomain.max - percentDomain.min);
    const t = (bucket - percentDomain.min) / span;
    return mixColor(percentLight, percentDark, t);
  }

  function colorFor(v) {
    if (v === null || v === undefined || !Number.isFinite(v)) return missingColor;
    if (isPercentMetric()) return percentColorFor(v);
    for (let i = 0; i < quantileColors.length; i++) {
      if (v <= breaks[i + 1] || i === quantileColors.length - 1) return quantileColors[i];
    }
    return quantileColors[quantileColors.length - 1];
  }

  function metricFormatter(v) {
    if (v === null || v === undefined || !Number.isFinite(v)) return 'bez dat';
    if (els.metric.value === 'votes') return fmtInt(v);
    if (els.metric.value === 'strength') return fmtStrength(v);
    return fmtPct(v);
  }

  function selectionLabel() {
    const mode = els.groupMode.value;
    if (mode === 'custom') {
      const selected = [...els.customGroups.selectedOptions].map(o => o.value);
      return selected.length ? selected.join(' + ') : 'Vlastní součet';
    }
    return els.group.value || '';
  }

  function appendLegendRow(color, text) {
    const row = document.createElement('div');
    row.className = 'legendRow';
    const sw = document.createElement('span');
    sw.className = 'legendSwatch';
    sw.style.background = color;
    const txt = document.createElement('span');
    txt.textContent = text;
    row.append(sw, txt);
    els.legend.appendChild(row);
  }

  function updateLegend(regionShare) {
    const label = els.metric.options[els.metric.selectedIndex]?.textContent || 'Ukazatel';
    els.legendTitle.textContent = label;
    els.legend.innerHTML = '';

    if (isPercentMetric()) {
      for (let p = percentDomain.min; p < percentDomain.max; p++) {
        appendLegendRow(percentColorFor(p + 0.01), `${p}–${p + 1} %`);
      }
    } else {
      const finiteBreaks = breaks.filter(v => Number.isFinite(v));
      const minBreak = finiteBreaks.length ? Math.min(...finiteBreaks) : 0;
      const maxBreak = finiteBreaks.length ? Math.max(...finiteBreaks) : 0;
      if (Math.abs(maxBreak - minBreak) < 1e-9) {
        appendLegendRow(quantileColors[Math.floor(quantileColors.length / 2)], metricFormatter(minBreak));
      } else {
        for (let i = 0; i < quantileColors.length; i++) {
          if (Math.abs(breaks[i + 1] - breaks[i]) < 1e-9) continue;
          appendLegendRow(quantileColors[i], `${metricFormatter(breaks[i])} – ${metricFormatter(breaks[i + 1])}`);
        }
      }
    }

    appendLegendRow(missingColor, 'Kandidátka zde není v datech / nekandiduje');

    if (els.metric.value === 'strength') {
      els.metricNote.textContent = `Index 100 = krajský výsledek vybrané kandidátky/skupiny (${fmtPct(regionShare)}).`;
    } else if (isPercentMetric()) {
      els.metricNote.textContent = 'Barvy jsou rozdělené po celých procentních bodech (1 p. b.) v rámci celého Libereckého kraje.';
    } else if (isMunicipal()) {
      els.metricNote.textContent = 'U komunálních voleb mapa standardně používá hlavní obecní/městské zastupitelstvo. Lokální kandidátky mohou kandidovat jen v části kraje.';
    } else {
      els.metricNote.textContent = 'Barevné intervaly jsou kvantily všech okrsků Libereckého kraje.';
    }
  }

  function layerStyle(feature) {
    const key = String(feature.properties?.precinct_key || '');
    const d = metricValues.get(key);
    const municipalityCode = String(feature.properties?.municipality_code || '');
    const selectedMunicipality = els.municipality.value;
    const focused = !selectedMunicipality || municipalityCode === selectedMunicipality;

    return {
      color: focused ? '#536273' : '#aeb7c1',
      weight: focused ? 0.8 : 0.45,
      opacity: focused ? 0.95 : 0.5,
      fillColor: focused ? colorFor(d?.value ?? null) : '#eef1f4',
      fillOpacity: focused ? 0.86 : 0.28,
      interactive: true
    };
  }

  function tooltipText(feature) {
    const p = feature.properties || {};
    const d = metricValues.get(String(p.precinct_key));
    const value = d ? metricFormatter(d.value) : 'bez dat';
    return `<strong>${escapeHtml(p.municipality_name || '')}</strong><br>okrsek ${escapeHtml(p.precinct || '')}<br>${escapeHtml(selectionLabel())}: ${escapeHtml(value)}`;
  }

  function escapeHtml(s) {
    return String(s ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  }

  function onEachFeature(feature, layer) {
    layer.bindTooltip(() => tooltipText(feature), { sticky: true, direction: 'auto' });

    layer.on('mouseover', () => {
      if (layer !== selectedLayer) {
        layer.setStyle({ weight: 2, color: '#1f2937', opacity: 1, fillOpacity: 0.96 });
      }
      if (layer.bringToFront) layer.bringToFront();
    });

    layer.on('mouseout', () => {
      if (layer !== selectedLayer && geoLayer) geoLayer.resetStyle(layer);
    });

    layer.on('click', () => {
      const props = feature.properties || {};
      const municipalityCode = String(props.municipality_code || '');

      // In the 2026 municipal view, clicking any precinct also selects its
      // municipality. This immediately narrows the party/list selector to the
      // candidates that actually stood there.
      if (isMunicipal() && municipalityCode && els.municipality.value !== municipalityCode) {
        els.municipality.value = municipalityCode;
        updateGroupControls();
        aggregateMetrics();
        refreshStylesOnly();
      }

      if (selectedLayer && geoLayer && selectedLayer !== layer) geoLayer.resetStyle(selectedLayer);
      selectedLayer = layer;
      layer.setStyle({ weight: 2.8, color: '#111827', opacity: 1, fillOpacity: 0.96 });
      if (layer.bringToFront) layer.bringToFront();
      showDetail(String(props.precinct_key || ''), props);
    });
  }

  function showDetail(key, props) {
    const rows = precinctIndex.get(key) || [];
    if (!rows.length) return;
    const base = rows[0];
    const selected = rows.filter(rowMatchesSelection);
    const votes = selected.reduce((s, r) => s + Number(r.votes || 0), 0);
    const valid = Number(base.valid_votes || 0);
    const share = valid > 0 ? votes / valid * 100 : 0;
    const turnout = Number(base.registered_voters || 0) > 0
      ? Number(base.issued_envelopes || 0) / Number(base.registered_voters || 0) * 100 : 0;

    els.detailEmpty.classList.add('hidden');
    els.detailContent.classList.remove('hidden');
    els.detailTitle.textContent = `${base.municipality_name || props.municipality_name || 'Obec'} · okrsek ${base.precinct || props.precinct || ''}`;
    els.detailStats.innerHTML = [
      ['Vybraná kandidátka/skupina', selectionLabel()],
      ['Hlasy', fmtInt(votes)],
      ['Podíl', selected.length ? fmtPct(share) : 'nekandiduje / bez dat'],
      ['Účast', fmtPct(turnout)]
    ].map(([k,v]) => `<div class="stat"><span class="k">${escapeHtml(k)}</span><span class="v">${escapeHtml(v)}</span></div>`).join('');

    const ranked = rows.slice().sort((a, b) => Number(b.votes || 0) - Number(a.votes || 0));
    els.detailRows.innerHTML = ranked.map(r => {
      const selectedRow = rowMatchesSelection(r) ? ' class="selectedRow"' : '';
      return `<tr${selectedRow}><td>${escapeHtml(r.list_name)}</td><td>${fmtInt(r.votes)}</td><td>${fmtPct(r.vote_share)}</td></tr>`;
    }).join('');
  }

  async function loadGeometry(eid) {
    if (geoCache.has(eid)) return geoCache.get(eid);
    const resp = await fetch(`precincts_${eid}.geojson`);
    if (!resp.ok) throw new Error(`Chybí data/precincts_${eid}.geojson`);
    const geo = await resp.json();
    geoCache.set(eid, geo);
    return geo;
  }

  function renderGeometry() {
    if (geoLayer) {
      map.removeLayer(geoLayer);
      geoLayer = null;
    }
    selectedLayer = null;

    // Geometry files are already filtered by build_data.py to the Liberec Region.
    geoLayer = L.geoJSON(currentGeo, {
      style: layerStyle,
      onEachFeature,
      renderer: L.svg({ padding: 0.3 })
    }).addTo(map);

    if (!geoLayer.getBounds().isValid()) return;
    fullRegionBounds = geoLayer.getBounds();
    map.setMaxBounds(fullRegionBounds.pad(0.12));
    focusCurrentSelection(false);
  }

  function focusCurrentSelection(animate = true) {
    if (!geoLayer || !fullRegionBounds) return;
    const selectedMunicipality = els.municipality.value;
    if (!selectedMunicipality) {
      map.fitBounds(fullRegionBounds, { padding: [18, 18], animate });
      return;
    }

    const bounds = L.latLngBounds([]);
    geoLayer.eachLayer(layer => {
      if (String(layer.feature?.properties?.municipality_code || '') === selectedMunicipality) {
        const b = layer.getBounds?.();
        if (b?.isValid()) bounds.extend(b);
      }
    });
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [32, 32], maxZoom: 14, animate });
  }

  function refreshStylesOnly() {
    if (!geoLayer) return;
    geoLayer.eachLayer(layer => {
      const feature = layer.feature;
      layer.setStyle(layerStyle(feature));
      if (layer.getTooltip()) layer.setTooltipContent(tooltipText(feature));
    });
    if (selectedLayer) selectedLayer.setStyle({ weight: 2.8, color: '#111827', opacity: 1, fillOpacity: 0.96 });
  }

  async function refreshElection() {
    currentElectionRows = rowsForElection();
    buildPrecinctIndex();
    updateGroupControls();
    updateMunicipalities();
    currentGeo = await loadGeometry(els.election.value);
    aggregateMetrics();
    renderGeometry();
    els.status.textContent = `${currentElectionRows.length.toLocaleString('cs-CZ')} řádků výsledků · ${currentGeo.features.length.toLocaleString('cs-CZ')} okrsků · pouze Liberecký kraj`;
    clearDetail();
  }

  function refreshMap({focus = false} = {}) {
    aggregateMetrics();
    refreshStylesOnly();
    if (focus) focusCurrentSelection(true);
    clearDetail();
  }

  function clearDetail() {
    if (selectedLayer && geoLayer) geoLayer.resetStyle(selectedLayer);
    els.detailContent.classList.add('hidden');
    els.detailEmpty.classList.remove('hidden');
    selectedLayer = null;
  }

  function bindEvents() {
    els.election.addEventListener('change', () => refreshElection());
    els.groupMode.addEventListener('change', () => { updateGroupControls(); refreshMap(); });
    els.group.addEventListener('change', () => refreshMap());
    els.customGroups.addEventListener('change', () => refreshMap());
    els.metric.addEventListener('change', () => refreshMap());
    els.municipality.addEventListener('change', () => {
      if (isMunicipal()) updateGroupControls();
      refreshMap({ focus: true });
    });
    els.resetView.addEventListener('click', () => {
      els.municipality.value = '';
      if (isMunicipal()) updateGroupControls();
      refreshMap({ focus: true });
    });
  }

  async function init() {
    try {
      if (!window.L) throw new Error('Nepodařilo se načíst Leaflet. Zkontroluj připojení k internetu.');

      // No world map / no external map tiles. The only visible geography is the
      // official precinct geometry of the Liberec Region.
      map = L.map('map', {
        preferCanvas: false,
        zoomControl: true,
        attributionControl: false,
        dragging: true,
        scrollWheelZoom: true,
        doubleClickZoom: true,
        boxZoom: true,
        keyboard: true,
        touchZoom: true,
        zoomSnap: 0.25,
        minZoom: 7,
        maxZoom: 16,
        maxBoundsViscosity: 1.0,
        worldCopyJump: false
      });
      map.setView([50.72, 15.15], 9);

      const [metaResp, resultsResp] = await Promise.all([
        fetch('metadata.json'),
        fetch('results.json')
      ]);
      if (!metaResp.ok || !resultsResp.ok) {
        throw new Error('Datové soubory ještě nejsou vytvořené. Spusť nejdřív: python build_data.py');
      }
      metadata = await metaResp.json();
      results = await resultsResp.json();

      metadata.elections.forEach(e => option(els.election, e.id, e.label));
      els.election.value = 'ps2025';
      bindEvents();
      await refreshElection();
      setTimeout(() => map.invalidateSize(), 0);
    } catch (err) {
      console.error(err);
      els.status.textContent = 'Data nejsou připravena';
      document.querySelector('.mapPanel').innerHTML = `<div class="errorBox"><strong>Atlas zatím nelze zobrazit.</strong><br>${escapeHtml(err.message)}<br><br>V kořenové složce projektu spusť <code>pip install -r requirements.txt</code>, potom <code>python build_data.py</code> a nakonec <code>python -m http.server 8000 -d public</code>.</div>`;
    }
  }

  init();
})();
