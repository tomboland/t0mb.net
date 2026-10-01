// Keep the server-rendered selection when JavaScript is unavailable.
(() => {
  const pool = document.querySelector('#featured-review-pool');
  const target = document.querySelector('#home-reviews .review-list');
  if (!pool || !target) return;

  const entries = [...pool.content.querySelectorAll('.review-entry')];
  if (entries.length <= 3) return;

  // Fisher–Yates gives each featured review an equal chance, without duplicates.
  for (let i = entries.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [entries[i], entries[j]] = [entries[j], entries[i]];
  }
  target.replaceChildren(...entries.slice(0, 3));
})();
