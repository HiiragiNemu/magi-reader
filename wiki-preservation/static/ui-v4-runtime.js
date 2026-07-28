(() => {
  const RUNTIME_REVISION = '4.4-all-structured-reader-images';
  document.documentElement.dataset.uiRuntime = RUNTIME_REVISION;

  const closeMenu = (except = null) => {
    document.querySelectorAll('.display-menu[open]').forEach((menu) => {
      if (menu === except) return;
      menu.open = false;
      menu.querySelector(':scope > summary')?.setAttribute('aria-expanded', 'false');
    });
  };

  const openImage = (image) => {
    if (!(image instanceof HTMLImageElement) || image.classList.contains('image-failed')) return false;
    const dialog = document.querySelector('#image-viewer');
    const target = dialog?.querySelector('img');
    const caption = dialog?.querySelector('p');
    if (!dialog || !target || !caption) return false;
    target.src = image.currentSrc || image.src;
    target.alt = image.alt || '';
    caption.textContent = image.alt || image.closest('figure')?.querySelector('figcaption')?.textContent || '';
    if (typeof dialog.showModal === 'function') dialog.showModal();
    else dialog.setAttribute('open', '');
    return true;
  };

  document.addEventListener('click', (event) => {
    const target = event.target instanceof Element ? event.target : null;
    if (!target) return;

    const image = target.closest('.wiki-document img, .reader-image');
    if (image && openImage(image)) {
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }

    const summary = target.closest('.display-menu > summary');
    if (summary) {
      event.preventDefault();
      event.stopImmediatePropagation();
      const menu = summary.parentElement;
      const next = !menu.open;
      closeMenu(menu);
      menu.open = next;
      summary.setAttribute('aria-expanded', String(next));
      if (next) requestAnimationFrame(() => menu.querySelector('.display-panel button[aria-pressed="true"]')?.focus({ preventScroll: true }));
      return;
    }
    if (!target.closest('.display-menu')) closeMenu();
  }, true);

  document.addEventListener('keydown', (event) => {
    const target = event.target instanceof Element ? event.target : null;
    if ((event.key === 'Enter' || event.key === ' ') && target?.matches('.wiki-document img, .reader-image')) {
      if (openImage(target)) {
        event.preventDefault();
        event.stopImmediatePropagation();
        return;
      }
    }
    if (event.key !== 'Escape') return;
    const viewer = document.querySelector('#image-viewer[open]');
    if (viewer) {
      viewer.close?.();
      return;
    }
    const open = document.querySelector('.display-menu[open]');
    if (!open) return;
    open.open = false;
    const summary = open.querySelector(':scope > summary');
    summary?.setAttribute('aria-expanded', 'false');
    summary?.focus();
  }, true);
})();
