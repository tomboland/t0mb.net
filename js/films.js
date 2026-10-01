// Optional enhancement: the full linked catalogue works without JavaScript.
const catalogue = document.querySelector('#film-catalogue');
if (catalogue) {
  const controls = document.querySelector('.film-filters');
  controls.hidden = false;
  const search = document.querySelector('#film-search');
  const reviewed = document.querySelector('#reviewed-only');
  const count = document.querySelector('#filter-count');
  const rows = [...catalogue.querySelectorAll('tbody tr')];
  const fold = text => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  const index = rows.map(row => fold(row.textContent));
  function filter() {
    const query = fold(search.value.trim());
    let visible = 0;
    rows.forEach((row, i) => {
      row.hidden = !index[i].includes(query) || (reviewed.checked && row.dataset.reviewed !== 'true');
      if (!row.hidden) visible++;
    });
    count.textContent = `${visible} of ${rows.length} films`;
  }
  search.addEventListener('input', filter);
  reviewed.addEventListener('change', filter);
  filter();
}
