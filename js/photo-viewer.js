// Enhance content photos; catalogue posters retain their navigation links.
(() => {
  if (typeof HTMLDialogElement === 'undefined' || !HTMLDialogElement.prototype.showModal) return;
  const photos = document.querySelectorAll('.post-body img, .cinema img:not(.film-thumbnail):not(.tmdb-logo)');
  if (!photos.length) return;

  const viewer = document.createElement('dialog');
  viewer.className = 'photo-viewer';
  viewer.setAttribute('aria-label', 'Full-screen photo');
  const close = document.createElement('button');
  close.type = 'button';
  close.className = 'photo-viewer-close';
  close.textContent = '×';
  close.setAttribute('aria-label', 'Close photo');
  const enlarged = document.createElement('img');
  enlarged.className = 'photo-viewer-image';
  viewer.append(close, enlarged);
  document.body.append(viewer);

  let opener;
  close.addEventListener('click', () => viewer.close());
  viewer.addEventListener('click', event => {
    if (event.target === viewer || event.target === enlarged) viewer.close();
  });
  // Native dialog handles Escape, modal focus containment and background inertness.
  viewer.addEventListener('close', () => {
    document.documentElement.classList.remove('photo-viewer-open');
    enlarged.removeAttribute('src');
    if (opener?.isConnected) opener.focus({ preventScroll: true });
  });

  photos.forEach(photo => {
    if (photo.closest('a, button')) return;
    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'photo-trigger';
    trigger.setAttribute('aria-haspopup', 'dialog');
    trigger.setAttribute('aria-label', photo.alt ? `Open full-screen photo: ${photo.alt}` : 'Open full-screen photo');
    photo.before(trigger);
    trigger.append(photo);
    trigger.addEventListener('click', () => {
      opener = trigger;
      enlarged.alt = photo.alt;
      enlarged.src = photo.currentSrc || photo.src;
      viewer.showModal();
      document.documentElement.classList.add('photo-viewer-open');
      close.focus({ preventScroll: true });
    });
  });
})();
