const memoriaApp = document.querySelector('#app');
const MEMORIA_UI_VERSION = new URL(import.meta.url).searchParams.get('v') || 'dev';
const MEMORIA_PAGE_SIZE = 48;
const memoriaState = {
  index: null,
  manifest: null,
  detailCache: new Map(),
  query: '',
  rarity: 'all',
  type: 'all',
  source: 'all',
  completion: 'all',
  page: 1,
  rendering: false,
};

function mEscape(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function mAttr(value) {
  return mEscape(value).replaceAll('`', '&#96;');
}

function mNormalize(value) {
  return String(value ?? '')
    .normalize('NFKC')
    .toLocaleLowerCase('zh-CN')
    .replace(/[\s\-_·・/（）()【】\[\]《》]+/g, ' ')
    .trim();
}

function mMatches(query, ...values) {
  const terms = mNormalize(query).split(' ').filter(Boolean);
  if (!terms.length) return true;
  const haystack = mNormalize(values.flat(Infinity).join(' '));
  return terms.every((term) => haystack.includes(term));
}

async function mJson(path) {
  const response = await fetch(`/data/structured/${String(path).replace(/^\/+/, '')}?v=${encodeURIComponent(MEMORIA_UI_VERSION)}`, {
    cache: 'default',
  });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}

async function ensureMemoriaIndex() {
  if (memoriaState.index && memoriaState.manifest) return;
  [memoriaState.index, memoriaState.manifest] = await Promise.all([
    mJson('memoria-index.json'),
    mJson('memoria-manifest.json'),
  ]);
}

async function loadMemoriaDetail(indexItem) {
  if (memoriaState.detailCache.has(indexItem.id)) return memoriaState.detailCache.get(indexItem.id);
  const shard = await mJson(`memoria/${indexItem.shard}.json`);
  const detail = shard[indexItem.id];
  if (!detail) throw new Error(`记忆结晶分片缺少记录：${indexItem.id}`);
  memoriaState.detailCache.set(indexItem.id, detail);
  return detail;
}

function mThemeControls() {
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

function mHeader() {
  const links = [
    ['portal/all', 'Wiki正文', 'wiki'],
    ['characters', '人物', 'characters'],
    ['voice', '语音', 'voice'],
    ['portal/story', '剧情', 'story'],
    ['memoria', '记忆结晶', 'memoria'],
    ['doppel', 'Doppel', 'doppel'],
    ['media', '媒体', 'media'],
    ['about', '关于', 'about'],
  ];
  return `
    <header class="site-header structured-header memoria-header">
      <div class="header-primary">
        <button class="brand" data-route="memoria" type="button" aria-label="返回记忆结晶图鉴">
          <span class="brand-mark">✦</span>
          <span><strong>魔法纪录中文资料库</strong><small>MAGIA RECORD DATABASE</small></span>
        </button>
        ${mThemeControls()}
      </div>
      <nav aria-label="主要栏目">${links.map(([path, label, id]) => `<button class="${id === 'memoria' ? 'active' : ''}" data-route="${path}" type="button">${label}</button>`).join('')}</nav>
    </header>`;
}

function mShell(content) {
  memoriaApp.innerHTML = `${mHeader()}<main class="site-main structured-main memoria-main">${content}</main>
    <footer class="site-footer"><span>记忆结晶资料</span><button data-route="about">关于资料库</button></footer>
    <button class="to-top" type="button" data-scroll-top aria-label="返回页面顶部">↑</button>
    <dialog class="image-viewer" id="image-viewer"><button type="button" class="viewer-close" data-close-viewer aria-label="关闭图片">×</button><div class="viewer-stage"><img alt=""><p></p></div></dialog>`;
  document.documentElement.dataset.structuredView = 'memoria';
}

function mLoading(label = '正在载入记忆结晶图鉴……') {
  mShell(`<div class="state-panel"><div class="spinner"></div><strong>${mEscape(label)}</strong></div>`);
}

function mError(error) {
  mShell(`<div class="state-panel error"><strong>资料读取失败</strong><pre>${mEscape(error?.message || error)}</pre><button type="button" data-route="portal/all">转到Wiki正文</button></div>`);
}

function currentMemoriaRoute() {
  const raw = location.hash.replace(/^#\/?/, '');
  const [section, ...rest] = raw.split('/');
  let id = rest.join('/');
  try { id = decodeURIComponent(id); } catch {}
  return { section, id };
}

function memoriaRoute(path) {
  clearTimeout(window.__memoriaSearchTimer);
  const next = `#/${String(path).replace(/^\/+/, '')}`;
  if (location.hash === next) {
    void renderMemoriaRoute();
  } else {
    location.hash = next;
    queueMicrotask(() => void renderMemoriaRoute());
  }
  scrollTo({ top: 0, behavior: 'smooth' });
}

function isMemoriaRoute() {
  return currentMemoriaRoute().section === 'memoria';
}

function patchMemoriaNavigation() {
  memoriaApp.querySelectorAll('[data-route="portal/memoria"]').forEach((button) => {
    if (button.dataset.route !== 'memoria') button.dataset.route = 'memoria';
    if (button.textContent !== '记忆结晶') button.textContent = '记忆结晶';
  });
  const nav = memoriaApp.querySelector('.site-header nav');
  if (nav && !nav.querySelector('[data-route="memoria"]')) {
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.route = 'memoria';
    button.textContent = '记忆结晶';
    const doppel = nav.querySelector('[data-route="doppel"], [data-route="portal/doppel"]');
    if (doppel) doppel.before(button); else nav.append(button);
  }
}

function memoriaCard(item) {
  const status = item.complete ? '<span class="memoria-status complete">资料完整</span>' : '<span class="memoria-status partial">资料待补</span>';
  const stars = item.rarity ? `${'★'.repeat(Number(item.rarity))}` : '稀有度待补';
  return `<button type="button" class="memoria-card ${item.complete ? '' : 'is-partial'}" data-memoria-id="${mAttr(item.id)}">
    <span class="memoria-card-image">${item.imageUrl ? `<img src="${mAttr(item.imageUrl)}" alt="${mAttr(item.nameZh || item.nameJa)}" loading="lazy" decoding="async">` : '<span class="portrait-placeholder">◇</span>'}</span>
    <span class="memoria-card-copy">
      <span class="memoria-card-meta"><small>${item.number != null ? `No. ${mEscape(item.number)}` : '编号待补'}</small><small>${mEscape(stars)}</small></span>
      <strong>${mEscape(item.nameZh || item.nameJa)}</strong>
      ${item.nameZh && item.nameJa && item.nameZh !== item.nameJa ? `<span lang="ja">${mEscape(item.nameJa)}</span>` : ''}
      <span>${[item.type, item.artist, item.equipLimit && item.equipLimit !== '所有人' ? `限 ${item.equipLimit}` : ''].filter(Boolean).map(mEscape).join(' · ')}</span>
      ${status}
    </span>
    <b aria-hidden="true">›</b>
  </button>`;
}

function memoriaListPage() {
  const catalog = memoriaState.index || [];
  const manifest = memoriaState.manifest || {};
  const types = manifest.types || [...new Set(catalog.map((item) => item.type).filter(Boolean))];
  const sources = manifest.sourceTabs || [...new Set(catalog.flatMap((item) => item.sourceTabs || []))];
  const filtered = catalog
    .filter((item) => memoriaState.rarity === 'all' || String(item.rarity) === memoriaState.rarity)
    .filter((item) => memoriaState.type === 'all' || item.type === memoriaState.type)
    .filter((item) => memoriaState.source === 'all' || item.sourceTabs?.includes(memoriaState.source))
    .filter((item) => memoriaState.completion === 'all' || (memoriaState.completion === 'complete' ? item.complete : !item.complete))
    .filter((item) => mMatches(memoriaState.query, item.searchText, item.nameZh, item.nameJa, item.number));
  const pages = Math.max(1, Math.ceil(filtered.length / MEMORIA_PAGE_SIZE));
  memoriaState.page = Math.min(Math.max(1, memoriaState.page), pages);
  const shown = filtered.slice((memoriaState.page - 1) * MEMORIA_PAGE_SIZE, memoriaState.page * MEMORIA_PAGE_SIZE);
  document.title = '记忆结晶图鉴 — 魔法纪录中文资料库';
  mShell(`
    <section class="structured-hero memoria-hero">
      <div><p class="eyebrow">MEMORIA DATABASE</p><h1>记忆结晶图鉴</h1><p>按名称、编号、稀有度、类型、效果、画师与实装来源浏览记忆结晶。</p></div>
      <div class="coverage-grid structured-stats">
        <div><strong>${Number(manifest.records || catalog.length).toLocaleString('zh-CN')}</strong><span>目录条目</span></div>
        <div><strong>${Number(manifest.uniqueNumbers || 0).toLocaleString('zh-CN')}</strong><span>有效编号</span></div>
        <div><strong>${Number(manifest.complete || 0).toLocaleString('zh-CN')}</strong><span>完整资料</span></div>
        <div><strong>${Number(manifest.partial || 0).toLocaleString('zh-CN')}</strong><span>待补记录</span></div>
      </div>
    </section>
    <section class="toolbar memoria-toolbar">
      <label class="search-field"><span>⌕</span><input id="memoria-search" type="search" value="${mAttr(memoriaState.query)}" placeholder="搜索名称、编号、画师、效果、装备限制或简介" autocomplete="off"></label>
      <select id="memoria-rarity"><option value="all">全部稀有度</option>${[1, 2, 3, 4].map((value) => `<option value="${value}" ${memoriaState.rarity === String(value) ? 'selected' : ''}>${value}★</option>`).join('')}</select>
      <select id="memoria-type"><option value="all">全部类型</option>${types.map((value) => `<option value="${mAttr(value)}" ${memoriaState.type === value ? 'selected' : ''}>${mEscape(value)}</option>`).join('')}</select>
      <select id="memoria-source"><option value="all">全部实装来源</option>${sources.map((value) => `<option value="${mAttr(value)}" ${memoriaState.source === value ? 'selected' : ''}>${mEscape(value)}</option>`).join('')}</select>
      <select id="memoria-completion"><option value="all">全部完整度</option><option value="complete" ${memoriaState.completion === 'complete' ? 'selected' : ''}>资料完整</option><option value="partial" ${memoriaState.completion === 'partial' ? 'selected' : ''}>资料待补</option></select>
    </section>
    <section class="structured-result-head"><div><p class="result-kicker">结构化图鉴</p><h2>记忆结晶列表</h2></div><span>${filtered.length.toLocaleString('zh-CN')}条</span></section>
    ${shown.length ? `<div class="memoria-grid">${shown.map(memoriaCard).join('')}</div>` : '<div class="state-panel inline"><strong>没有匹配记忆结晶</strong></div>'}
    ${pages > 1 ? `<div class="pager"><button type="button" data-memoria-page="${memoriaState.page - 1}" ${memoriaState.page <= 1 ? 'disabled' : ''}>上一页</button><span>第 ${memoriaState.page} / ${pages} 页</span><button type="button" data-memoria-page="${memoriaState.page + 1}" ${memoriaState.page >= pages ? 'disabled' : ''}>下一页</button></div>` : ''}
  `);
}

function statCell(label, minimum, maximum) {
  const value = minimum == null || maximum == null ? '—' : `${Number(minimum).toLocaleString('zh-CN')} → ${Number(maximum).toLocaleString('zh-CN')}`;
  return `<div><span>${mEscape(label)}</span><strong>${mEscape(value)}</strong></div>`;
}

function textBlock(title, value, className = '') {
  if (!value) return '';
  return `<section class="memoria-text ${className}"><h2>${mEscape(title)}</h2><p>${mEscape(value).replaceAll('\n', '<br>')}</p></section>`;
}

function effectBlock(item) {
  if (!item.effect && !item.effectMax && !item.effectDetail && !item.effectDetailMax) return '';
  return `<section class="memoria-effect-panel"><h2>能力效果</h2>
    <div class="memoria-effect-grid">
      <article><span>初始</span><strong>${mEscape(item.skillName || '—')}</strong><p>${mEscape(item.effect || '—').replaceAll('\n', '<br>')}</p>${item.effectDetail ? `<small>${mEscape(item.effectDetail).replaceAll('\n', '<br>')}</small>` : ''}${item.cooldown != null ? `<b>${mEscape(item.cooldown)}回合冷却</b>` : ''}</article>
      <article><span>满破</span><strong>${mEscape(item.skillNameMax || item.skillName || '—')}</strong><p>${mEscape(item.effectMax || item.effect || '—').replaceAll('\n', '<br>')}</p>${item.effectDetailMax ? `<small>${mEscape(item.effectDetailMax).replaceAll('\n', '<br>')}</small>` : ''}${item.cooldownMax != null ? `<b>${mEscape(item.cooldownMax)}回合冷却</b>` : ''}</article>
    </div>
  </section>`;
}

function memoriaDetailPage(item) {
  document.title = `${item.nameZh || item.nameJa} — 魔法纪录中文资料库`;
  const stars = item.rarity ? `${'★'.repeat(Number(item.rarity))}` : '稀有度待补';
  const localArticle = item.articleId ? `<button type="button" data-memoria-article="${mAttr(item.articleId)}">阅读本地Wiki正文</button>` : '';
  const sourceLink = item.articleUrl ? `<a href="${mAttr(item.articleUrl)}" target="_blank" rel="noreferrer">原Wiki页面</a>` : '';
  mShell(`
    <article class="structured-page memoria-detail">
      <div class="reading-bar"><button type="button" data-route="memoria">← 返回记忆结晶图鉴</button><span>${item.number != null ? `No. ${mEscape(item.number)}` : '编号待补'}</span></div>
      <header class="memoria-detail-head">
        <div class="memoria-detail-image">${item.imageUrl ? `<img class="reader-image" src="${mAttr(item.imageUrl)}" alt="${mAttr(item.nameZh || item.nameJa)}" loading="eager">` : '<span class="portrait-placeholder">◇</span>'}</div>
        <div><p class="eyebrow">MEMORIA PROFILE</p><h1>${mEscape(item.nameZh || item.nameJa)}</h1>${item.nameZh && item.nameJa && item.nameZh !== item.nameJa ? `<p lang="ja" class="memoria-japanese-title">${mEscape(item.nameJa)}</p>` : ''}<div class="memoria-badges"><span>${mEscape(stars)}</span>${item.type ? `<span>${mEscape(item.type)}</span>` : ''}${item.complete ? '<span class="complete">资料完整</span>' : '<span class="partial">资料待补</span>'}</div>
        <dl class="memoria-summary"><div><dt>画师</dt><dd>${mEscape(item.artist || '—')}</dd></div><div><dt>装备限制</dt><dd>${mEscape(item.equipLimit || '所有人/待确认')}</dd></div><div><dt>获取方式</dt><dd>${mEscape(item.obtain || '—')}</dd></div><div><dt>数据修订</dt><dd>${mEscape(item.revision || '—')}</dd></div></dl></div>
      </header>
      <div class="character-actions">${localArticle}${sourceLink}</div>
      ${item.complete ? '' : `<section class="memoria-partial-notice"><strong>该记录尚未完整解析</strong><p>${mEscape(item.articleError || `源页面状态：${item.articleStatus ?? '未知'}`)}</p></section>`}
      <section class="memoria-stats">${statCell('HP', item.hpMin, item.hpMax)}${statCell('ATK', item.atkMin, item.atkMax)}${statCell('DEF', item.defMin, item.defMax)}<div><span>等级</span><strong>${item.levelMin == null || item.levelMax == null ? '—' : `${mEscape(item.levelMin)} → ${mEscape(item.levelMax)}`}</strong></div></section>
      ${effectBlock(item)}
      ${textBlock('中文简介', item.descZh)}
      ${textBlock('日文简介', item.descJa, 'japanese')}
      ${item.notes ? textBlock('数据说明', item.notes, 'notes') : ''}
      <section class="profile-section"><h2>来源信息</h2><div class="category-strip">${(item.sourceTabs || []).map((value) => `<span class="chip">${mEscape(value)}</span>`).join('')}${item.rawTableSha256 ? `<span class="chip">表格 SHA-256 ${mEscape(item.rawTableSha256.slice(0, 16))}…</span>` : ''}</div></section>
    </article>
  `);
}

function findMemoriaIndex(id) {
  return (memoriaState.index || []).find((item) => item.id === id) || null;
}

async function renderMemoriaRoute() {
  const route = currentMemoriaRoute();
  if (route.section !== 'memoria') {
    clearTimeout(window.__memoriaSearchTimer);
    delete document.documentElement.dataset.structuredView;
    patchMemoriaNavigation();
    return;
  }
  if (route.id) clearTimeout(window.__memoriaSearchTimer);
  if (memoriaState.rendering) return;
  memoriaState.rendering = true;
  const expectedHash = location.hash;
  try {
    mLoading(route.id ? '正在载入记忆结晶详情……' : '正在载入记忆结晶图鉴……');
    await ensureMemoriaIndex();
    if (location.hash !== expectedHash) return;
    if (route.id) {
      const indexItem = findMemoriaIndex(route.id);
      if (!indexItem) {
        memoriaRoute('memoria');
        return;
      }
      const detail = await loadMemoriaDetail(indexItem);
      if (location.hash !== expectedHash) return;
      memoriaDetailPage(detail);
    } else {
      memoriaListPage();
    }
  } catch (error) {
    console.error(error);
    if (location.hash === expectedHash) mError(error);
  } finally {
    memoriaState.rendering = false;
  }
}

document.addEventListener('click', (event) => {
  const target = event.target instanceof Element ? event.target : null;
  if (!target) return;
  const legacyPortal = target.closest('[data-portal="memoria"]');
  if (legacyPortal) {
    event.preventDefault();
    event.stopImmediatePropagation();
    memoriaRoute('memoria');
    return;
  }
  const item = target.closest('[data-memoria-id]');
  if (item) {
    event.preventDefault();
    event.stopImmediatePropagation();
    memoriaRoute(`memoria/${encodeURIComponent(item.dataset.memoriaId)}`);
    return;
  }
  const page = target.closest('[data-memoria-page]');
  if (page && !page.disabled) {
    event.preventDefault();
    event.stopImmediatePropagation();
    memoriaState.page = Number(page.dataset.memoriaPage);
    memoriaListPage();
    scrollTo({ top: 0, behavior: 'smooth' });
    return;
  }
  const article = target.closest('[data-memoria-article]');
  if (article) {
    event.preventDefault();
    event.stopImmediatePropagation();
    location.hash = `#/article/${encodeURIComponent(article.dataset.memoriaArticle)}`;
  }
}, true);

document.addEventListener('input', (event) => {
  if (!(event.target instanceof HTMLInputElement) || event.target.id !== 'memoria-search') return;
  memoriaState.query = event.target.value;
  memoriaState.page = 1;
  clearTimeout(window.__memoriaSearchTimer);
  window.__memoriaSearchTimer = setTimeout(() => {
    const route = currentMemoriaRoute();
    if (route.section === 'memoria' && !route.id) memoriaListPage();
  }, 160);
});

document.addEventListener('change', (event) => {
  if (!(event.target instanceof HTMLSelectElement)) return;
  const values = {
    'memoria-rarity': 'rarity',
    'memoria-type': 'type',
    'memoria-source': 'source',
    'memoria-completion': 'completion',
  };
  const key = values[event.target.id];
  if (!key) return;
  memoriaState[key] = event.target.value;
  memoriaState.page = 1;
  memoriaListPage();
});

addEventListener('hashchange', () => setTimeout(() => void renderMemoriaRoute(), 0));

const memoriaObserver = new MutationObserver(() => {
  patchMemoriaNavigation();
  if (isMemoriaRoute() && !memoriaApp.querySelector('.memoria-grid, .memoria-detail') && !memoriaState.rendering) {
    queueMicrotask(() => void renderMemoriaRoute());
  }
});
memoriaObserver.observe(memoriaApp, { childList: true, subtree: false });

patchMemoriaNavigation();
setTimeout(() => void renderMemoriaRoute(), 0);
