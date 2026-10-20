// Optional filtering; every release is available without JavaScript.
(() => {
  const table = document.querySelector('#collection-table');
  if (!table) return;
  const rows = [...table.querySelectorAll('tbody > tr')];
  const fold = s => s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  const search = document.querySelector('#collection-search');
  const format = document.querySelector('#collection-format');
  const label = document.querySelector('#collection-label');
  [...new Set(rows.map(r => r.dataset.label).filter(Boolean))].sort().forEach(name => label.add(new Option(name, name)));
  const index = rows.map(r => fold(r.textContent));
  function filter() {
    const query = fold(search.value.trim());
    rows.forEach((r, i) => { r.hidden = !index[i].includes(query) || (format.value && !r.dataset.format.split(', ').includes(format.value)) || (label.value && r.dataset.label !== label.value); });
    document.querySelector('#collection-count').textContent = `${rows.filter(r => !r.hidden).length} of ${rows.length} releases`;
  }
  function restore() {
    const p = new URL(location.href).searchParams;
    search.value = p.get('q') || ''; format.value = p.get('format') || ''; label.value = p.get('label') || ''; filter();
  }
  function update() {
    const u = new URL(location.href);
    Object.entries({q:search.value, format:format.value, label:label.value}).forEach(([k,v]) => v ? u.searchParams.set(k,v) : u.searchParams.delete(k));
    history.replaceState(history.state, '', u); filter();
  }
  search.addEventListener('input', update); format.addEventListener('change', update); label.addEventListener('change', update);
  window.addEventListener('popstate', restore); window.addEventListener('pageshow', restore);
  document.querySelector('#collection-controls').hidden = false; restore();
})();
