// Full reviews are present in the HTML and readable without JavaScript.
(() => {
  document.querySelectorAll('.embedded-review').forEach(review => {
    const body = review.querySelector('.embedded-review-body');
    const words = body.textContent.trim().split(/\s+/);
    if (words.length <= 220) return;

    const preview = document.createElement('p');
    preview.className = 'review-preview';
    preview.textContent = words.slice(0, 100).join(' ') + '…';
    const details = document.createElement('details');
    details.className = 'review-expansion';
    const summary = document.createElement('summary');
    summary.textContent = 'more…';
    details.append(summary);
    body.before(preview, details);
    details.append(body);
    details.addEventListener('toggle', () => {
      preview.hidden = details.open;
      summary.textContent = details.open ? 'less…' : 'more…';
    });
    // Follow in-review anchors without leaving their containing review collapsed.
    const revealAnchor = () => {
      if (!location.hash) return;
      let id;
      try { id = decodeURIComponent(location.hash.slice(1)); } catch { return; }
      const target = document.getElementById(id);
      if (target && body.contains(target)) {
        details.open = true;
        target.scrollIntoView();
      }
    };
    window.addEventListener('hashchange', revealAnchor);
    revealAnchor();
  });
})();
