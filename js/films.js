// Optional enhancements: all content and links remain available without JavaScript.
(() => {
  const fold = text => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  const params = () => new URL(location.href).searchParams;
  const save = values => {
    const url = new URL(location.href);
    Object.entries(values).forEach(([key, value]) => value ? url.searchParams.set(key, value) : url.searchParams.delete(key));
    history.replaceState(history.state, '', url);
  };
  const restoreOnReturn = restore => {
    restore();
    window.addEventListener('pageshow', () => setTimeout(restore, 0));
    window.addEventListener('popstate', restore);
  };
  const catalogue = document.querySelector('#film-catalogue');
  if (catalogue) {
    document.querySelector('.film-filters').hidden = false;
    const search = document.querySelector('#film-search');
    const reviewed = document.querySelector('#reviewed-only');
    const count = document.querySelector('#filter-count');
    const rows = [...catalogue.querySelectorAll('tbody tr')];
    const index = rows.map(row => fold(row.textContent));
    function filter() {
      const query = fold(search.value.trim());
      let visible = 0;
      rows.forEach((row, i) => {
        row.hidden = !index[i].includes(query) || (reviewed.checked && row.dataset.reviewed !== 'true');
        if (!row.hidden) visible++;
      });
      document.querySelector('#recent-writing').hidden = !!query || reviewed.checked;
      count.textContent = `${visible} of ${rows.length} films`;
    }
    const update = () => { save({q: search.value, reviewed: reviewed.checked ? '1' : ''}); filter(); };
    search.addEventListener('input', update);
    reviewed.addEventListener('change', update);
    restoreOnReturn(() => { search.value = params().get('q') || ''; reviewed.checked = params().get('reviewed') === '1'; filter(); });
  }
  const directorSearch = document.querySelector('#director-search');
  if (directorSearch) {
    document.querySelector('#director-controls').hidden = false;
    const rows = [...document.querySelectorAll('.director-list li')];
    function filter() {
      rows.forEach(row => { row.hidden = !fold(row.textContent).includes(fold(directorSearch.value.trim())); });
      document.querySelector('#director-count').textContent = `${rows.filter(r => !r.hidden).length} of ${rows.length} directors`;
    }
    directorSearch.addEventListener('input', () => { save({q: directorSearch.value}); filter(); });
    restoreOnReturn(() => { directorSearch.value = params().get('q') || ''; filter(); });
  }
  const selection = document.querySelector('#filmography-filter');
  if (selection) {
    document.querySelector('#filmography-controls').hidden = false;
    const rows = [...document.querySelectorAll('#filmography tbody tr')];
    function filter() {
      rows.forEach(row => { row.hidden = selection.value === 'watched' ? row.dataset.status === 'unwatched' : selection.value === 'reviewed' && row.dataset.status !== 'reviewed'; });
      document.querySelector('#filmography-count').textContent = `${rows.filter(r => !r.hidden).length} of ${rows.length} films`;
    }
    selection.addEventListener('change', () => { save({view: selection.value === 'all' ? '' : selection.value}); filter(); });
    restoreOnReturn(() => { const value = params().get('view'); selection.value = ['watched', 'reviewed'].includes(value) ? value : 'all'; filter(); });
  }
})();
