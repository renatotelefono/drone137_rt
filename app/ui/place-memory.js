const $ = id => document.getElementById(id);
let selected = '', selectedVisit = '', rendered = '';
let placeOptions = '', visitOptions = '';
const text = (tag, value) => {
  const element = document.createElement(tag);
  element.textContent = value;
  return element;
};
const option = (label, value) => {
  const element = text('option', label);
  element.value = value;
  return element;
};
function draw(map) {
  const canvas = $('place-map'), ctx = canvas.getContext('2d');
  ctx.fillStyle = '#14262e';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  if (!map?.cells?.length) {
    ctx.fillStyle = '#b9cccf';
    ctx.fillText('No mapped observations in this visit', 20, 30);
    return;
  }
  const cells = map.cells, xs = cells.map(c => c[0]), ys = cells.map(c => c[1]);
  const lo = [Math.min(...xs) - 2, Math.min(...ys) - 2];
  const hi = [Math.max(...xs) + 3, Math.max(...ys) + 3];
  const scale = Math.min(canvas.width / (hi[0] - lo[0]), canvas.height / (hi[1] - lo[1]));
  for (const [x, y, value] of cells) {
    ctx.fillStyle = value > .5 ? '#e7b16c' : value < -.3 ? '#83d1ad' : '#52636b';
    ctx.fillRect((x - lo[0]) * scale, canvas.height - (y - lo[1] + 1) * scale, scale, scale);
  }
  const zero = map.extent_m / map.resolution_m;
  ctx.fillStyle = '#fff';
  ctx.beginPath();
  ctx.arc((zero - lo[0]) * scale, canvas.height - (zero - lo[1]) * scale, 4, 0, 2 * Math.PI);
  ctx.fill();
  ctx.fillText('Launch origin', Math.max(10, (zero - lo[0]) * scale + 10), Math.max(20, canvas.height - (zero - lo[1]) * scale));
  ctx.fillText(`Grid: ${map.resolution_m} m per cell`, 12, 20);
}
async function refresh() {
  try {
    const listing = await fetch('/api/places');
    if (!listing.ok) throw Error('Place memory unavailable');
    const list = await listing.json();
    const newPlaceOptions = JSON.stringify(list.places.map(p => [p.id, p.name]));
    if (newPlaceOptions !== placeOptions) {
      $('places').replaceChildren(...list.places.map(p => option(p.name, p.id)));
      placeOptions = newPlaceOptions;
      if (selected) $('places').value = selected;
    }
    selected = $('places').value;
    if (!selected) {
      $('status').textContent = 'No places recorded yet.';
      return;
    }
    const response = await fetch('/api/places/' + encodeURIComponent(selected) + (selectedVisit ? '?visit=' + encodeURIComponent(selectedVisit) : ''));
    if (!response.ok) throw Error('Cannot load place');
    const place = await response.json();
    $('name').textContent = place.name;
    $('scope').textContent = place.reuse_policy;
    const newVisitOptions = JSON.stringify(place.visits.map(v => [v.id, v.state]));
    if (newVisitOptions !== visitOptions) {
      $('visit-picker').replaceChildren(option('Latest visit (updates automatically)', ''), ...place.visits.slice().reverse().map(v =>
        option(new Date(v.started * 1000).toLocaleString() + ' · ' + v.state, v.id)));
      visitOptions = newVisitOptions;
      $('visit-picker').value = selectedVisit;
    }
    const visit = place.visits.find(v => v.id === selectedVisit) || place.visits.at(-1);
    $('status').textContent = `Saved locally · ${place.visits.length} visits`;
    const evaluation = visit?.summary?.evaluation;
    const assessment = evaluation ? (evaluation.accepted ? 'Simulation test passed; hardware unqualified' : 'Simulation test NOT PASSED') : 'Map is unqualified';
    $('visit-state').textContent = visit ? `${visit.state} · ${visit.observations.length} saved images · ${assessment}` : 'No visit selected';
    const fingerprint = JSON.stringify([visit?.id, visit?.state, visit?.map?.revision, visit?.observations.length, evaluation?.accepted]);
    if (fingerprint === rendered) return;
    rendered = fingerprint;
    draw(visit?.map);
    $('visits').replaceChildren();
    if (!visit) return;
    if (visit.summary.error) $('visits').append(text('p', visit.summary.error));
    const journal = document.createElement('div');
    journal.className = 'observation-grid';
    for (const observation of visit.observations.slice().reverse()) {
      if (!observation.observation) continue;
      const card = document.createElement('article'), image = document.createElement('img');
      image.src = `/api/places/${encodeURIComponent(selected)}/visits/${visit.id}/images/${observation.sequence}`;
      image.alt = `Recorded onboard observation ${observation.sequence}`;
      image.loading = 'lazy';
      card.append(image, text('small', `Model observation ${observation.sequence}`), text('p', observation.observation));
      journal.append(card);
    }
    $('visits').append(journal);
  } catch (error) {
    $('status').textContent = String(error);
  }
}
$('places').addEventListener('change', () => {
  selected = $('places').value;
  selectedVisit = rendered = visitOptions = '';
  $('answer').textContent = '';
  refresh();
});
$('visit-picker').addEventListener('change', () => {
  selectedVisit = $('visit-picker').value;
  rendered = '';
  refresh();
});
$('ask').addEventListener('click', async () => {
  if (!selected) return;
  const requestedPlace = selected;
  $('ask').disabled = true;
  $('answer').textContent = 'Reading saved observations…';
  try {
    const response = await fetch('/api/places/' + encodeURIComponent(requestedPlace) + '/ask', {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-Drone137-Control': 'local'},
      body: JSON.stringify({question: $('question').value || 'What did we observe here?'})
    });
    const answer = await response.json();
    if (selected !== requestedPlace) return;
    if (!response.ok) throw Error(answer.error || 'Model unavailable');
    $('answer').textContent = answer.answer;
    for (const source of answer.evidence || []) {
      const link = text('a', ` ${source.evidence_id}: visit ${source.visit.slice(0, 8)}, observation ${source.sequence}`);
      link.href = `/api/places/${encodeURIComponent(requestedPlace)}/visits/${source.visit}/images/${source.sequence}`;
      link.target = '_blank';
      link.rel = 'noopener';
      $('answer').append(link);
    }
  } catch (error) {
    $('answer').textContent = String(error);
  } finally {
    $('ask').disabled = false;
  }
});
refresh();
setInterval(refresh, 5000);
