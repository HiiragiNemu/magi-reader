const doppelApp = document.querySelector('#app');
const DOPPEL_UI_VERSION = '5.3';
const doppelState = {
  catalog: null,
  manifest: null,
  query: '',
  credit: 'all',
  page: 1,
  rendering: false,
};

function dEscape(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function dAttr(value) {
  return dEscape(value).replaceAll('`', '&#96;');
}

function dNormalize(value) {
  return String(value ?? '')
    .normalize('NFKC')
    .toLocaleLowerCase('zh-CN')
    .replace(/[\s\-_·・/（）()【】\[\]《》]+/g, ' ')
    .trim();
}

function dMatches(query, ...values) {
  const terms = dNormalize(query).split(' ').filter(Boolean);
  if (!terms.length) return true;
  const haystack = dNormalize(values.flat(Infinity).join(' '));
  return terms.every((term) => haystack.includes(term));
}

async function dJson(path) {
  const response = await fetch(`/data/structured/${String(path).replace(/^\/+/, '')}?v=${DOPPEL_UI_VERSION}`, { cache: 'default' });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}

async function ensureDoppelData() {
  if (doppelState.catalog && doppelState.manifest) return;
  [doppelState.catalog, doppelState.manifest] = await Promise.all([
    dJson('doppel.json'),
    dJson('manifest.json'),
  ]);
}

function dThemeControls() {
  let preferences = {};
  try { preferences = JSON.parse(localStorage.getItem('magireco-reader-preferences') || '{}'); } catch {}
  const theme = ['system', 'light', 'dark', 'eye', 'oled'].includes(preferences.theme) ? preferences.theme : 'system';
  const font = [0.9, 1, 1.12, 1.25].includes(Number(preferences.font)) ? Number(preferences.font) : 1;
  const width = ['narrow', 'comfortable', 'wide'].includes(preferences.width) ? preferences.width : 'comfortable';
  const themes = [['system', '跟随系统'], ['light', '日间'], ['dark', '夜间'], ['eye', '护眼'], ['oled', '纯黑']];
  const fonts = [[0.9, '小'], [1, '标准'], [1.12, '大'], [1.25, '特大']];
  const widths = [['narrow', '紧凑'], ['comfortable', '舒适'], ['wide', '宽屏']];
  return `
    <details class="display-menu">
      <summary aria-label="外观和阅读设置">◐ <span>外观</span></summary>
      <div class="display-panel">
        <div class="display-panel-head"><strong>阅读外观</strong><small>设置保存在本机浏览器</small></div>
        <fieldset><legend>页面主题</legend><div class="segmented">${themes.map(([id, label]) => `<button type="button" data-structured-theme="${id}" aria-pressed="${theme === id}">${label}</button>`).join('')}</div></fieldset>
        <fieldset><legend>文字大小</legend><div class="segmented">${fonts.map(([value, label]) => `<button type="button" data-structured-font="${value}" aria-pressed="${font === value}">${label}</button>`).join('')}</div></fieldset>
        <fieldset><legend>正文宽度</legend><div class="segmented">${widths.map(([id, label]) => `<button type="button" data-structured-width="${id}" aria-pressed="${width === id}">${label}</button>`).join('')}</div></fieldset>
      </div>
    </details>`;
}

function dHeader() {
  const links = [
    ['portal/all', 'Wiki正文', 'wiki'],
    ['characters', '人物', 'characters'],
    ['voice', '语音', 'voice'],
    ['portal/story', '剧情', 'story'],
    ['portal/memoria', '记忆结晶', 'memoria'],
    ['doppel', 'Doppel', 'doppel'],
    ['media', '媒体', 'media'],
    ['about', '关于', 'about'],
  ];
  return `
    <header class="site-header structured-header">
      <div class="header-primary">
        <button class="brand" data-route="doppel" type="button" aria-label="返回Doppel图鉴">
          <span class="brand-mark">✦</span>
          <span><strong>魔法纪录中文资料库</strong><small>MAGIA RECORD DATABASE</small></span>
        </button>
        ${dThemeControls()}
      </div>
      <nav aria-label="主要栏目">${links.map(([path, label, id]) => `<button class="${id === 'doppel' ? 'active' : ''}" data-route="${path}" type="button">${label}</button>`).join('')}</nav>
    </header>`;
}

function dShell(content) {
  doppelApp.innerHTML = `${dHeader()}<main class="site-main structured-main doppel-main">${content}</main>
    <footer class="site-footer"><span>174条Doppel资料</span><button data-route="about">关于资料库</button></footer>
    <button class="to-top" type="button" data-scroll-top aria-label="返回页面顶部">↑</button>
    <dialog class="image-viewer" id="image-viewer"><button type="button" class="viewer-close" data-close-viewer aria-label="关闭图片">×</button><div class="viewer-stage"><img alt=""><p></p></div></dialog>`;
  document.documentElement.dataset.structuredView = 'doppel';
}

function dLoading(label = '正在载入Doppel图鉴……') {
  dShell(`<div class="state-panel"><div class="spinner"></div><strong>${dEscape(label)}</strong></div>`);
}

function dError(error) {
  dShell(`<div class="state-panel error"><strong>Doppel资料读取失败</strong><pre>${dEscape(error?.message || error)}</pre><button type="button" data-route="portal/all">转到Wiki正文</button></div>`);
}

function currentDoppelRoute() {
  const raw = location.hash.replace(/^#\/?/, '');
  const [section, ...rest] = raw.split('/');
  let id = rest.join('/');
  try { id = decodeURIComponent(id); } catch {}
  return { section, id };
}

function doppelRoute(path) {
  clearTimeout(window.__doppelSearchTimer);
  const next = `#/${String(path).replace(/^\/+/, '')}`;
  if (location.hash === next) {
    void renderDoppelRoute();
  } else {
    location.hash = next;
    queueMicrotask(() => void renderDoppelRoute());
  }
  scrollTo({ top: 0, behavior: 'smooth' });
}

function isDoppelRoute() {
  const { section } = currentDoppelRoute();
  return section === 'doppel';
}

function patchDoppelNavigation() {
  const old = doppelApp.querySelector('[data-route="portal/doppel"]');
  if (old) {
    if (old.dataset.route !== 'doppel') old.dataset.route = 'doppel';
    if (old.textContent !== 'Doppel') old.textContent = 'Doppel';
  }
  const nav = doppelApp.querySelector('.site-header nav');
  if (nav && !nav.querySelector('[data-route="doppel"]')) {
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.route = 'doppel';
    button.textContent = 'Doppel';
    const memoria = nav.querySelector('[data-route="portal/memoria"]');
    memoria?.after(button);
  }
}

function doppelCard(item) {
  return `<button type="button" class="doppel-card" data-doppel-id="${dAttr(item.id)}">
    <span class="doppel-card-image">${item.doppelImageUrl ? `<img src="${dAttr(item.doppelImageUrl)}" alt="${dAttr(item.character)}的Doppel" loading="lazy" decoding="async">` : '<span class="portrait-placeholder">◇</span>'}</span>
    <span class="doppel-card-copy">
      <small>${dEscape(item.character)}</small>
      <strong>${dEscape(item.name || item.epithetZh || '未命名Doppel')}</strong>
      <span>${[item.epithetZh, item.formZh ? `姿态 ${item.formZh}` : '', item.runes].filter(Boolean).map(dEscape).join(' · ')}</span>
    </span>
    <b aria-hidden="true">›</b>
  </button>`;
}

function doppelListPage() {
  const catalog = doppelState.catalog || [];
  const credits = [...new Set(catalog.map((item) => item.credit).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'zh-CN'));
  const filtered = catalog
    .filter((item) => doppelState.credit === 'all' || item.credit === doppelState.credit)
    .filter((item) => dMatches(doppelState.query, item.searchText, item.character, item.name));
  const size = 48;
  const pages = Math.max(1, Math.ceil(filtered.length / size));
  doppelState.page = Math.min(Math.max(1, doppelState.page), pages);
  const shown = filtered.slice((doppelState.page - 1) * size, doppelState.page * size);
  document.title = 'Doppel图鉴 — 魔法纪录中文资料库';
  dShell(`
    <section class="structured-hero doppel-hero">
      <div><p class="eyebrow">DOPPEL DATABASE</p><h1>Doppel图鉴</h1><p>浏览174条Doppel资料，包括关联角色、名称、魔女文字、感情称号、姿态、原案/监修与中日说明。</p></div>
      <div class="coverage-grid structured-stats">
        <div><strong>${Number(doppelState.manifest.doppel || catalog.length).toLocaleString('zh-CN')}</strong><span>Doppel条目</span></div>
        <div><strong>${Number(doppelState.manifest.doppelWithImage || 0).toLocaleString('zh-CN')}</strong><span>带图像</span></div>
        <div><strong>${Number(doppelState.manifest.doppelWithChineseDescription || 0).toLocaleString('zh-CN')}</strong><span>中文说明</span></div>
        <div><strong>${credits.length}</strong><span>原案/监修标记</span></div>
      </div>
    </section>
    <section class="toolbar doppel-toolbar">
      <label class="search-field"><span>⌕</span><input id="doppel-search" type="search" value="${dAttr(doppelState.query)}" placeholder="搜索角色、Doppel名称、感情、姿态、魔女文字或说明" autocomplete="off"></label>
      <select id="doppel-credit"><option value="all">全部原案/监修</option>${credits.map((value) => `<option value="${dAttr(value)}" ${doppelState.credit === value ? 'selected' : ''}>${dEscape(value)}</option>`).join('')}</select>
    </section>
    <section class="structured-result-head"><div><p class="result-kicker">Doppel资料</p><h2>Doppel列表</h2></div><span>${filtered.length.toLocaleString('zh-CN')}条</span></section>
    ${shown.length ? `<div class="doppel-grid">${shown.map(doppelCard).join('')}</div>` : '<div class="state-panel inline"><strong>没有匹配Doppel</strong></div>'}
    ${pages > 1 ? `<div class="pager"><button type="button" data-doppel-page="${doppelState.page - 1}" ${doppelState.page <= 1 ? 'disabled' : ''}>上一页</button><span>第 ${doppelState.page} / ${pages} 页</span><button type="button" data-doppel-page="${doppelState.page + 1}" ${doppelState.page >= pages ? 'disabled' : ''}>下一页</button></div>` : ''}
  `);
}

function findDoppel(id) {
  return (doppelState.catalog || []).find((item) => item.id === id) || null;
}

function descriptionBlock(title, value, lang = '') {
  if (!value) return '';
  return `<section class="doppel-description" ${lang ? `lang="${lang}"` : ''}><h2>${dEscape(title)}</h2><p>${dEscape(value).replaceAll('\n', '<br>')}</p></section>`;
}

function doppelDetailPage(item) {
  document.title = `${item.character}的Doppel — 魔法纪录中文资料库`;
  dShell(`
    <article class="structured-page doppel-detail">
      <div class="reading-bar"><button type="button" data-route="doppel">← 返回Doppel图鉴</button><button type="button" data-character-id="${dAttr(item.characterId)}">人物资料</button><span>${dEscape(item.name || 'Doppel')}</span></div>
      <header class="doppel-detail-head">
        <div class="doppel-detail-image">${item.doppelImageUrl ? `<img class="reader-image" src="${dAttr(item.doppelImageUrl)}" alt="${dAttr(item.character)}的Doppel" loading="eager">` : '<span class="portrait-placeholder">◇</span>'}${item.credit ? `<small>${dEscape(item.credit)}</small>` : ''}</div>
        <div><p class="eyebrow">DOPPEL PROFILE</p><h1>${dEscape(item.name || `${item.character}的Doppel`)}</h1><p class="doppel-owner">关联角色：<button type="button" data-character-id="${dAttr(item.characterId)}">${dEscape(item.character)}</button></p><div class="doppel-badges">${item.runes ? `<span>魔女文字 ${dEscape(item.runes)}</span>` : ''}${item.epithetZh ? `<span>${dEscape(item.epithetZh)}</span>` : ''}${item.formZh ? `<span>姿态 ${dEscape(item.formZh)}</span>` : ''}</div>${item.note ? `<p class="doppel-note">${dEscape(item.note)}</p>` : ''}</div>
      </header>
      <div class="character-actions"><button type="button" data-character-id="${dAttr(item.characterId)}">查看人物图鉴</button><button type="button" data-article="${dAttr(item.articleId)}">阅读完整Wiki正文</button><a href="${dAttr(item.sourceUrl)}" target="_blank" rel="noreferrer">原Wiki页面</a></div>
      <section class="doppel-facts"><div><span>中文感情称号</span><strong>${dEscape(item.epithetZh || '—')}</strong></div><div><span>中文姿态</span><strong>${dEscape(item.formZh || '—')}</strong></div><div lang="ja"><span>日文感情称号</span><strong>${dEscape(item.epithetJa || '—')}</strong></div><div lang="ja"><span>日文姿态</span><strong>${dEscape(item.formJa || '—')}</strong></div></section>
      ${descriptionBlock('中文说明', item.descriptionZh)}
      ${descriptionBlock('日文说明', item.descriptionJa, 'ja')}
      <section class="profile-section"><h2>来源与分类</h2><div class="category-strip">${(item.categories || []).map((value) => `<span class="chip">${dEscape(value)}</span>`).join('')}</div></section>
    </article>
  `);
}

async function renderDoppelRoute() {
  const route = currentDoppelRoute();
  if (route.section !== 'doppel') {
    delete document.documentElement.dataset.structuredView;
    patchDoppelNavigation();
    return;
  }
  if (doppelState.rendering) return;
  doppelState.rendering = true;
  try {
    dLoading();
    await ensureDoppelData();
    if (route.id) {
      const item = findDoppel(route.id);
      if (item) doppelDetailPage(item); else doppelRoute('doppel');
    } else {
      doppelListPage();
    }
  } catch (error) {
    console.error(error);
    dError(error);
  } finally {
    doppelState.rendering = false;
  }
}

document.addEventListener('click', (event) => {
  const target = event.target instanceof Element ? event.target : null;
  if (!target) return;
  const item = target.closest('[data-doppel-id]');
  if (item) {
    event.preventDefault();
    event.stopImmediatePropagation();
    doppelRoute(`doppel/${encodeURIComponent(item.dataset.doppelId)}`);
    return;
  }
  const page = target.closest('[data-doppel-page]');
  if (page && !page.disabled) {
    event.preventDefault();
    event.stopImmediatePropagation();
    doppelState.page = Number(page.dataset.doppelPage);
    doppelListPage();
    scrollTo({ top: 0, behavior: 'smooth' });
  }
}, true);

document.addEventListener('input', (event) => {
  if (!(event.target instanceof HTMLInputElement) || event.target.id !== 'doppel-search') return;
  doppelState.query = event.target.value;
  doppelState.page = 1;
  clearTimeout(window.__doppelSearchTimer);
  window.__doppelSearchTimer = setTimeout(() => {
    if (currentDoppelRoute().section === 'doppel' && !currentDoppelRoute().id) doppelListPage();
  }, 150);
});

document.addEventListener('change', (event) => {
  if (!(event.target instanceof HTMLSelectElement) || event.target.id !== 'doppel-credit') return;
  doppelState.credit = event.target.value;
  doppelState.page = 1;
  doppelListPage();
});

addEventListener('hashchange', () => setTimeout(() => void renderDoppelRoute(), 0));

const doppelObserver = new MutationObserver(() => {
  patchDoppelNavigation();
  if (isDoppelRoute() && !doppelApp.querySelector('.doppel-grid, .doppel-detail') && !doppelState.rendering) {
    queueMicrotask(() => void renderDoppelRoute());
  }
});
doppelObserver.observe(doppelApp, { childList: true, subtree: false });

patchDoppelNavigation();
setTimeout(() => void renderDoppelRoute(), 0);
