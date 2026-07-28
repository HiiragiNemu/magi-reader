(() => {
  const closeMenu = (except = null) => {
    document.querySelectorAll('.display-menu[open]').forEach((menu) => {
      if (menu === except) return;
      menu.open = false;
      menu.querySelector(':scope > summary')?.setAttribute('aria-expanded', 'false');
    });
  };

  document.addEventListener('click', (event) => {
    const target = event.target instanceof Element ? event.target : null;
    if (!target) return;
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
    if (event.key !== 'Escape') return;
    const open = document.querySelector('.display-menu[open]');
    if (!open) return;
    open.open = false;
    const summary = open.querySelector(':scope > summary');
    summary?.setAttribute('aria-expanded', 'false');
    summary?.focus();
  });
})();
