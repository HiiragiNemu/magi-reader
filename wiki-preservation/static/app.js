const app = document.querySelector('#app');
const UI_VERSION = 4;
const PAGE_SIZE = 48;

const portalCopy = {
  characters: ['魔法少女与人物', '角色、组织、关系、学校、城市与人物相关资料', '人物'],
  story: ['剧情与活动', '主线、支线、角色剧情、活动记录与章节资料', '剧情'],
  memoria: ['记忆结晶与道具', '记忆结晶、素材、道具、商店、装备与能力效果', '记忆'],
  doppel: ['Doppel、魔女与传言', 'Doppel、魔女、使魔、传言、魔女文字与设定考据', 'Doppel'],
  system: ['游戏与战斗系统', '战斗、属性、Disc、Magia、Connect、关卡与养成系统', '系统'],
  world: ['世界观与术语', '地点、概念、时间线、术语、团体与世界设定', '世界观'],
  media: ['动画、音乐与出版物', '动画、漫画、歌曲、广播、画集、宣传与衍生作品', '衍生'],
  technical: ['模板与技术档案', '模板、模块、分类、帮助、翻译规范与原站维护资料', '技术'],
};

const state = {
  manifest: null,
  dataVersion: '',
  archive: [],
  categories: [],
  portals: [],
  archiveById: new Map(),
  titleMap: new Map(),
  media: null,
  mediaMap: new Map(),
  jsonCache: new Map(),
  query: '',
  namespace: 'all',
  portal: 'all',
  category: 'all',
  page: 1,
  mediaQuery: '',
  mediaKind: 'image',
  mediaPage: 1,
  pendingScroll: 'top',
  prefs: readPreferences(),
};

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function attr(value) {
  return escapeHtml(value).replaceAll('`', '&#96;');
}

function normalize(value) {
  return String(value ?? '')
    .normalize('NFKC')
    .toLocaleLowerCase('zh-CN')
    .replace(/[\s\-_·・/（）()【】\[\]《》]+/g, ' ')
    .trim();
}

function matches(query, ...values) {
  const terms = normalize(query).split(' ').filter(Boolean);
  if (!terms.length) return true;
  const haystack = normalize(values.flat(Infinity).join(' '));
  return terms.every((term) => haystack.includes(term));
}

function formatBytes(value) {
  const number = Number(value || 0);
  if (number < 1024) return `${number} B`;
  if (number < 1024 ** 2) return `${(number / 1024).toFixed(1)} KiB`;
  if (number < 1024 ** 3) return `${(number / 1024 ** 2).toFixed(1)} MiB`;
  return `${(number / 1024 ** 3).toFixed(2)} GiB`;
}

function readPreferences() {
  const defaults = { theme: 'system', font: 1, width: 'comfortable' };
  try {
    const stored = JSON.parse(localStorage.getItem('magireco-reader-preferences') || '{}');
    return {
      theme: ['system', 'light', 'dark', 'eye', 'oled'].includes(stored.theme) ? stored.theme : defaults.theme,
      font: [0.9, 1, 1.12, 1.25].includes(Number(stored.font)) ? Number(stored.font) : defaults.font,
      width: ['narrow', 'comfortable', 'wide'].includes(stored.width) ? stored.width : defaults.width,
    };
  } catch {
    return defaults;
  }
}

function applyPreferences(save = false) {
  const root = document.documentElement;
  root.dataset.theme = state.prefs.theme;
  root.dataset.readerWidth = state.prefs.width;
  root.style.setProperty('--reader-scale', String(state.prefs.font));
  const themeColors = { light: '#f4f0ec', dark: '#181319', eye: '#eee8d8', oled: '#000000' };
  let color = themeColors[state.prefs.theme];
  if (!color) color = matchMedia('(prefers-color-scheme: dark)').matches ? themeColors.dark : themeColors.light;
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', color);
  if (save) localStorage.setItem('magireco-reader-preferences', JSON.stringify(state.prefs));
}

function route(path, { scroll = 'top' } = {}) {
  state.pendingScroll = scroll;
  const next = `#/${String(path).replace(/^\/+/, '')}`;
  if (location.hash === next) renderRoute();
  else location.hash = next;
}

function parseRoute() {
  const raw = location.hash.replace(/^#\/?/, '') || 'portal/all';
  const [section, ...rest] = raw.split('/');
  let id = rest.join('/');
  try { id = decodeURIComponent(id); } catch {}
  return { section, id };
}

function dataUrl(path, fresh = false) {
  const clean = String(path).replace(/^\/+/, '');
  const query = fresh ? `?fresh=${Date.now()}` : state.dataVersion ? `?v=${encodeURIComponent(state.dataVersion)}` : '';
  return `/data/${clean}${query}`;
}

async function loadJson(path, { fresh = false } = {}) {
  const key = `${path}:${fresh ? 'fresh' : state.dataVersion}`;
  if (!fresh && state.jsonCache.has(key)) return state.jsonCache.get(key);
  const response = await fetch(dataUrl(path, fresh), { cache: fresh ? 'no-store' : 'default' });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  const value = await response.json();
  if (!fresh) state.jsonCache.set(key, value);
  return value;
}

function setDocumentTitle(title) {
  document.title = title ? `${title} — 魔法纪录中文资料库` : '魔法纪录中文资料库';
}

function themeControls() {
  const themes = [
    ['system', '跟随系统'], ['light', '日间'], ['dark', '夜间'], ['eye', '护眼'], ['oled', '纯黑'],
  ];
  const fonts = [[0.9, '小'], [1, '标准'], [1.12, '大'], [1.25, '特大']];
  const widths = [['narrow', '紧凑'], ['comfortable', '舒适'], ['wide', '宽屏']];
  return `
    <details class="display-menu">
      <summary aria-label="外观和阅读设置">◐ <span>外观</span></summary>
      <div class="display-panel">
        <div class="display-panel-head"><strong>阅读外观</strong><small>设置保存在本机浏览器</small></div>
        <fieldset><legend>页面主题</legend><div class="segmented">${themes.map(([id, label]) => `<button type="button" data-theme="${id}" aria-pressed="${state.prefs.theme === id}">${label}</button>`).join('')}</div></fieldset>
        <fieldset><legend>文字大小</legend><div class="segmented">${fonts.map(([value, label]) => `<button type="button" data-font="${value}" aria-pressed="${state.prefs.font === value}">${label}</button>`).join('')}</div></fieldset>
        <fieldset><legend>正文宽度</legend><div class="segmented">${widths.map(([id, label]) => `<button type="button" data-width="${id}" aria-pressed="${state.prefs.width === id}">${label}</button>`).join('')}</div></fieldset>
      </div>
    </details>`;
}

function header(active = 'portal') {
  const links = [
    ['portal/all', '知识门户', 'portal'],
    ['portal/characters', '人物', 'characters'],
    ['portal/story', '剧情', 'story'],
    ['portal/memoria', '记忆结晶', 'memoria'],
    ['portal/doppel', 'Doppel', 'doppel'],
    ['media', '媒体', 'media'],
    ['about', '关于', 'about'],
  ];
  return `
    <header class="site-header">
      <div class="header-primary">
        <button class="brand" data-route="portal/all" type="button" aria-label="返回知识门户">
          <span class="brand-mark">✦</span>
          <span><strong>魔法纪录中文资料库</strong><small>STATIC PRESERVATION READER</small></span>
        </button>
        ${themeControls()}
      </div>
      <nav aria-label="主要栏目">${links.map(([path, label, id]) => `<button class="${active === id ? 'active' : ''}" data-route="${path}" type="button">${label}</button>`).join('')}</nav>
    </header>`;
}

function shell(content, active = 'portal') {
  app.innerHTML = `${header(active)}<main class="site-main">${content}</main>
    <footer class="site-footer"><span>只读静态资料库 · 可读页面与原始渲染HTML并存</span><button data-route="about">来源与保存说明</button></footer>
    <button class="to-top" type="button" data-scroll-top aria-label="返回页面顶部">↑</button>
    <dialog class="image-viewer" id="image-viewer"><button type="button" class="viewer-close" data-close-viewer aria-label="关闭图片">×</button><div class="viewer-stage"><img alt=""><p></p></div></dialog>`;
  applyPreferences();
}

function loading(label = '正在读取静态资料……') {
  shell(`<div class="state-panel"><div class="spinner"></div><strong>${escapeHtml(label)}</strong></div>`);
}

function errorPanel(error) {
  const message = error instanceof Error ? error.message : String(error);
  shell(`<div class="state-panel error"><strong>读取失败</strong><pre>${escapeHtml(message)}</pre><button data-route="portal/all">返回知识门户</button></div>`);
}

function articleSearchText(item) {
  return [item.title, item.namespaceLabel, item.preview, item.categories, item.headings?.map((value) => value.text), item.redirectTo].flat(Infinity).join(' ');
}

function activePortalRecord(id) {
  return state.portals.find((item) => item.id === id) || null;
}

function scheduleScroll(mode) {
  const requested = state.pendingScroll;
  state.pendingScroll = 'none';
  requestAnimationFrame(() => {
    if (requested === 'results' || mode === 'results') {
      document.querySelector('#portal-results')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } else if (requested === 'top') {
      scrollTo({ top: 0, behavior: 'smooth' });
    }
  });
}

function portalPage(forcedPortal = '') {
  const selectedPortal = forcedPortal || state.portal || 'all';
  state.portal = selectedPortal;
  const active = activePortalRecord(selectedPortal);
  const namespaces = [...new Map(state.archive.map((item) => [item.namespace, item.namespaceLabel])).entries()].sort((a, b) => a[0] - b[0]);
  const filtered = state.archive
    .filter((item) => selectedPortal === 'all' || item.portals?.includes(selectedPortal))
    .filter((item) => state.namespace === 'all' || String(item.namespace) === state.namespace)
    .filter((item) => state.category === 'all' || item.categories?.includes(state.category))
    .filter((item) => matches(state.query, articleSearchText(item)));
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  state.page = Math.min(Math.max(1, state.page), pages);
  const shown = filtered.slice((state.page - 1) * PAGE_SIZE, state.page * PAGE_SIZE);
  const counts = state.manifest.counts || {};
  const cards = [
    { id: 'all', title: '全部保存内容', count: state.archive.length, description: '浏览全部正文、Game、模板、模块、分类和项目资料', short: '全部' },
    ...state.portals.map((item) => ({ ...item, ...(portalCopy[item.id] ? { title: portalCopy[item.id][0], description: portalCopy[item.id][1], short: portalCopy[item.id][2] } : {}) })),
  ];
  const activeTitle = active?.title || (selectedPortal === 'all' ? '知识门户' : portalCopy[selectedPortal]?.[0]) || '知识门户';
  setDocumentTitle(activeTitle);
  shell(`
    <section class="portal-hero">
      <div><p class="eyebrow">MAGIA RECORD · PRESERVATION</p><h1>${escapeHtml(activeTitle)}</h1><p>把原 Wiki 的正文、章节、分类、重定向与媒体索引重组为无需账号和数据库的静态资料站。主题入口只负责筛选，不会删减底层内容。</p></div>
      <div class="coverage-grid">
        <div><strong>${Number(counts.pages || 0).toLocaleString('zh-CN')}</strong><span>归档页面</span></div>
        <div><strong>${Number(counts.categories || 0).toLocaleString('zh-CN')}</strong><span>分类</span></div>
        <div><strong>${Number(counts.media || 0).toLocaleString('zh-CN')}</strong><span>媒体记录</span></div>
        <div><strong>${formatBytes(counts.contentBytes)}</strong><span>正文数据</span></div>
      </div>
    </section>
    <section class="toolbar portal-toolbar">
      <label class="search-field"><span>⌕</span><input id="portal-search" type="search" value="${attr(state.query)}" placeholder="搜索标题、分类、章节或正文摘要" autocomplete="off"></label>
      <select id="namespace-filter"><option value="all">全部命名空间</option>${namespaces.map(([id, label]) => `<option value="${id}" ${state.namespace === String(id) ? 'selected' : ''}>${escapeHtml(label)}（${id}）</option>`).join('')}</select>
    </section>
    <section class="portal-cards" aria-label="主题入口">${cards.map((card) => `<button type="button" class="portal-card ${selectedPortal === card.id ? 'active' : ''}" data-portal="${attr(card.id)}" aria-pressed="${selectedPortal === card.id}"><span class="portal-card-top"><strong>${escapeHtml(card.title)}</strong><b aria-hidden="true">→</b></span><small>${escapeHtml(card.description || '')}</small><span>${Number(card.count || 0).toLocaleString('zh-CN')} 页</span></button>`).join('')}</section>
    <section class="category-strip category-scroller" aria-label="分类筛选"><button type="button" class="chip ${state.category === 'all' ? 'active' : ''}" data-category="all">全部分类</button>${state.categories.slice(0, 40).map((item) => `<button type="button" class="chip ${state.category === item.name ? 'active' : ''}" data-category="${attr(item.name)}">${escapeHtml(item.name)} · ${item.count}</button>`).join('')}</section>
    <section id="portal-results" class="results-section">
      <div class="section-heading"><div><p class="result-kicker">当前筛选</p><h2>${escapeHtml(activeTitle)}</h2></div><span>${filtered.length.toLocaleString('zh-CN')} 个匹配页面</span></div>
      ${shown.length ? `<div class="article-list">${shown.map((item) => `<button class="article-row" type="button" data-article="${attr(item.id)}"><span class="namespace-badge">${escapeHtml(item.namespaceLabel)}</span><span><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml([...(item.categories || []).slice(0, 3), ...(item.headings || []).slice(0, 2).map((value) => value.text), item.redirectTo ? `→ ${item.redirectTo}` : '', item.preview].filter(Boolean).join(' · '))}</small></span><span class="row-size">${formatBytes(item.textBytes)}</span><b aria-hidden="true">›</b></button>`).join('')}</div>` : '<div class="state-panel inline"><strong>没有符合当前条件的页面</strong><span>可清除分类或命名空间筛选后重试。</span></div>'}
      ${pages > 1 ? `<div class="pager"><button type="button" data-page="${state.page - 1}" ${state.page <= 1 ? 'disabled' : ''}>上一页</button><span>第 ${state.page} / ${pages} 页</span><button type="button" data-page="${state.page + 1}" ${state.page >= pages ? 'disabled' : ''}>下一页</button></div>` : ''}
    </section>
  `, selectedPortal === 'all' ? 'portal' : selectedPortal);
  scheduleScroll(selectedPortal !== 'all' && state.pendingScroll === 'results' ? 'results' : 'none');
}

async function ensureMedia() {
  if (state.media) return state.media;
  state.media = await loadJson('media-index.json');
  state.mediaMap = new Map();
  for (const item of state.media) {
    const names = new Set([item.name, String(item.name || '').replaceAll(' ', '_'), String(item.name || '').replaceAll('_', ' ')]);
    for (const name of names) state.mediaMap.set(normalize(name), item);
  }
  return state.media;
}

function articleFallback(record) {
  return `<pre class="raw-source"><code>${escapeHtml(record.rawHtml || record.text || '（空页面）')}</code></pre>`;
}

function enhanceArticle() {
  const body = document.querySelector('.wiki-document');
  if (!body) return;
  body.querySelectorAll('table').forEach((table) => {
    table.removeAttribute('width');
    if (table.parentElement?.classList.contains('table-viewport')) return;
    const wrapper = document.createElement('div');
    wrapper.className = 'table-viewport';
    table.parentNode?.insertBefore(wrapper, table);
    wrapper.appendChild(table);
  });
  body.querySelectorAll('img').forEach((image) => {
    image.removeAttribute('width');
    image.removeAttribute('height');
    image.removeAttribute('style');
    image.classList.add('reader-image');
    image.loading = 'lazy';
    image.decoding = 'async';
    image.tabIndex = 0;
    const classify = () => {
      if (image.naturalWidth <= 180 && image.naturalHeight <= 180) image.classList.add('reader-icon');
      if (image.closest('table')) image.classList.add('table-image');
    };
    if (image.complete) classify(); else image.addEventListener('load', classify, { once: true });
    image.addEventListener('error', () => image.classList.add('image-failed'), { once: true });
  });
  body.querySelectorAll('[width]').forEach((node) => node.removeAttribute('width'));
}

async function articlePage(id) {
  const item = state.archiveById.get(id);
  if (!item) {
    state.query = id.replace(/^\d+:/, '');
    state.portal = 'all';
    state.page = 1;
    route('portal/all', { scroll: 'results' });
    return;
  }
  loading(`正在载入 ${item.title}……`);
  const shard = await loadJson(`archive/${item.shard}.json`);
  const record = shard[id];
  if (!record) throw new Error(`正文分片中缺少记录：${id}`);
  setDocumentTitle(item.title);
  const outline = (item.headings || []).filter((entry) => entry.level <= 4 && entry.id);
  const tocOpen = !matchMedia('(max-width: 900px)').matches;
  const content = record.html || articleFallback(record);
  shell(`
    <article class="article-page">
      <div class="reading-bar"><button class="back-button" type="button" data-route="portal/${attr(state.portal || 'all')}">← 返回列表</button><span>${escapeHtml(item.namespaceLabel)}</span><button type="button" data-scroll-toc>目录</button></div>
      <header class="article-header">
        <p class="eyebrow">PRESERVED WIKI ARTICLE</p>
        <h1>${escapeHtml(item.title)}</h1>
        <div class="category-strip article-tags">${(item.categories || []).map((value) => `<button type="button" class="chip" data-category-jump="${attr(value)}">${escapeHtml(value)}</button>`).join('')}</div>
        <details class="technical-meta"><summary>页面信息与校验</summary><div><span>${escapeHtml(item.namespaceLabel)}</span><span>${formatBytes(item.textBytes)}</span><span>修订 ${escapeHtml(item.revision || '—')}</span><span>SHA-256 ${escapeHtml(item.sha256.slice(0, 20))}…</span>${item.redirectTo ? `<span>重定向至 ${escapeHtml(item.redirectTo)}</span>` : ''}</div></details>
      </header>
      <div class="article-actions"><a href="${attr(item.sourceUrl || `https://magireco.moe/wiki/${encodeURIComponent(item.title.replaceAll(' ', '_'))}`)}" target="_blank" rel="noreferrer">参考原 Wiki 页面</a><button type="button" id="copy-raw-html">复制原始HTML</button></div>
      <div class="rendered-layout">
        <div class="article-body"><div class="wiki-document">${content}</div></div>
        ${outline.length ? `<details class="article-toc" id="article-toc" ${tocOpen ? 'open' : ''}><summary>本页目录 <span>${outline.length}</span></summary><ol>${outline.map((entry) => `<li style="--toc-depth:${Math.max(0, entry.level - 2)}"><a href="#${attr(entry.id)}">${escapeHtml(entry.text)}</a></li>`).join('')}</ol></details>` : ''}
      </div>
      <details class="raw-details"><summary>查看完整原始渲染HTML（保真层）</summary><pre class="raw-source"><code>${escapeHtml(record.rawHtml || '（空页面）')}</code></pre></details>
    </article>
  `, 'article');
  enhanceArticle();
  document.querySelector('#copy-raw-html')?.addEventListener('click', async (event) => {
    try {
      await navigator.clipboard.writeText(record.rawHtml || '');
      event.currentTarget.textContent = '已复制';
      setTimeout(() => { event.currentTarget.textContent = '复制原始HTML'; }, 1400);
    } catch {
      event.currentTarget.textContent = '复制失败';
    }
  });
  scheduleScroll('top');
}

async function mediaPage() {
  loading('正在载入媒体索引……');
  const media = await ensureMedia();
  const filtered = media.filter((item) => (state.mediaKind === 'all' || item.mediaType === state.mediaKind) && matches(state.mediaQuery, item.name, item.mime, item.mediaType));
  const size = state.mediaKind === 'image' ? 48 : 80;
  const pages = Math.max(1, Math.ceil(filtered.length / size));
  state.mediaPage = Math.min(Math.max(1, state.mediaPage), pages);
  const shown = filtered.slice((state.mediaPage - 1) * size, state.mediaPage * size);
  setDocumentTitle('媒体档案');
  shell(`
    <section class="media-page"><p class="eyebrow">MEDIA ARCHIVE</p><div class="section-heading"><h1>媒体档案</h1><span>${filtered.length.toLocaleString('zh-CN')} 个文件</span></div><p class="section-copy">图片和音频按文件名、类型与来源建立索引。点击图片可全屏查看。</p>
    <div class="toolbar"><label class="search-field"><span>⌕</span><input id="media-search" type="search" value="${attr(state.mediaQuery)}" placeholder="搜索媒体文件名"></label><select id="media-kind"><option value="image" ${state.mediaKind === 'image' ? 'selected' : ''}>图片</option><option value="audio" ${state.mediaKind === 'audio' ? 'selected' : ''}>音频</option><option value="all" ${state.mediaKind === 'all' ? 'selected' : ''}>全部媒体</option></select></div>
    ${state.mediaKind === 'image' ? `<div class="media-grid">${shown.map((item) => `<article class="media-card">${item.url ? `<img class="reader-image" src="${attr(item.url)}" alt="${attr(item.name)}" loading="lazy" tabindex="0">` : '<div class="missing-media">无预览</div>'}<strong>${escapeHtml(item.name)}</strong><small>${[item.width && item.height ? `${item.width}×${item.height}` : '', formatBytes(item.size), item.mime].filter(Boolean).join(' · ')}</small><a href="${attr(item.url)}" target="_blank" rel="noreferrer">打开源文件</a></article>`).join('')}</div>` : `<div class="audio-list">${shown.map((item) => `<article><div><strong>${escapeHtml(item.name)}</strong><small>${formatBytes(item.size)} · ${escapeHtml(item.mime)}</small></div>${item.mediaType === 'audio' && item.url ? `<audio controls preload="none" src="${attr(item.url)}"></audio>` : `<a href="${attr(item.url)}" target="_blank" rel="noreferrer">打开</a>`}</article>`).join('')}</div>`}
    ${pages > 1 ? `<div class="pager"><button type="button" data-media-page="${state.mediaPage - 1}" ${state.mediaPage <= 1 ? 'disabled' : ''}>上一页</button><span>第 ${state.mediaPage} / ${pages} 页</span><button type="button" data-media-page="${state.mediaPage + 1}" ${state.mediaPage >= pages ? 'disabled' : ''}>下一页</button></div>` : ''}</section>
  `, 'media');
  scheduleScroll('top');
}

function aboutPage() {
  const source = state.manifest.source || {};
  const counts = state.manifest.counts || {};
  setDocumentTitle('关于数据');
  shell(`<article class="about-page"><p class="eyebrow">DATA & PROVENANCE</p><h1>关于数据与长期保存</h1><section><h2>保存方式</h2><p>本站从公开文章与分类链接图生成不可编辑的静态快照。构建后只需要普通静态文件托管，不依赖PHP、数据库、账号系统或原Wiki服务器程序。</p></section><section><h2>当前快照</h2><dl class="definition-grid"><div><dt>生成时间</dt><dd>${escapeHtml(state.manifest.generatedAt)}</dd></div><div><dt>来源</dt><dd>${escapeHtml(source.base || 'https://magireco.moe')}</dd></div><div><dt>页面</dt><dd>${Number(counts.pages || 0).toLocaleString('zh-CN')}</dd></div><div><dt>正文数据</dt><dd>${formatBytes(counts.contentBytes)}</dd></div><div><dt>图片记录</dt><dd>${Number(counts.images || 0).toLocaleString('zh-CN')}</dd></div><div><dt>抓取失败</dt><dd>${Number(counts.crawlFailures || 0).toLocaleString('zh-CN')}</dd></div></dl></section><section><h2>不衰减原则</h2><p>每个页面同时保存经过安全处理的可读HTML和完整原始渲染HTML。界面重排、移动端适配和主题切换不会删除底层正文。</p></section><section><h2>阅读设置</h2><p>右上角“外观”菜单提供跟随系统、日间、夜间、护眼和纯黑五种主题，以及四级字号和三档正文宽度。</p></section><section><h2>权利说明</h2><p>本站用于研究、保存、检索和兼容性开发。游戏文本、图像、音频、角色、商标及其他第三方内容的权利归各自权利人所有；Wiki编辑文本和译文的使用条件以原站声明为准。</p></section></article>`, 'about');
  scheduleScroll('top');
}

async function renderRoute() {
  try {
    const { section, id } = parseRoute();
    if (section === 'article') await articlePage(id);
    else if (section === 'media') await mediaPage();
    else if (section === 'about') aboutPage();
    else if (section === 'portal') portalPage(id || 'all');
    else if (portalCopy[section]) portalPage(section);
    else portalPage('all');
  } catch (error) {
    console.error(error);
    errorPanel(error);
  }
}

function openImageViewer(image) {
  if (!(image instanceof HTMLImageElement) || image.classList.contains('image-failed')) return;
  const dialog = document.querySelector('#image-viewer');
  const target = dialog?.querySelector('img');
  const caption = dialog?.querySelector('p');
  if (!dialog || !target || !caption) return;
  target.src = image.currentSrc || image.src;
  target.alt = image.alt || '';
  caption.textContent = image.alt || image.closest('figure')?.querySelector('figcaption')?.textContent || '';
  if (typeof dialog.showModal === 'function') dialog.showModal(); else dialog.setAttribute('open', '');
}

function bindEvents() {
  document.addEventListener('click', (event) => {
    const target = event.target instanceof Element ? event.target : null;
    if (!target) return;

    const tocLink = target.closest('.article-toc a[href^="#"]');
    if (tocLink) {
      event.preventDefault();
      const id = tocLink.getAttribute('href')?.slice(1);
      if (id) document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }
    const routeButton = target.closest('[data-route]');
    if (routeButton) { route(routeButton.dataset.route); return; }
    const articleButton = target.closest('[data-article]');
    if (articleButton) { route(`article/${encodeURIComponent(articleButton.dataset.article)}`); return; }
    const portalButton = target.closest('[data-portal]');
    if (portalButton) { state.page = 1; route(`portal/${portalButton.dataset.portal}`, { scroll: 'results' }); return; }
    const categoryButton = target.closest('[data-category]');
    if (categoryButton) { state.category = categoryButton.dataset.category; state.page = 1; state.pendingScroll = 'results'; portalPage(state.portal); return; }
    const categoryJump = target.closest('[data-category-jump]');
    if (categoryJump) { state.category = categoryJump.dataset.categoryJump; state.portal = 'all'; state.page = 1; route('portal/all', { scroll: 'results' }); return; }
    const pageButton = target.closest('[data-page]');
    if (pageButton && !pageButton.disabled) { state.page = Number(pageButton.dataset.page); state.pendingScroll = 'results'; portalPage(state.portal); return; }
    const mediaPageButton = target.closest('[data-media-page]');
    if (mediaPageButton && !mediaPageButton.disabled) { state.mediaPage = Number(mediaPageButton.dataset.mediaPage); mediaPage(); return; }
    const searchButton = target.closest('[data-search]');
    if (searchButton) { state.query = searchButton.dataset.search; state.portal = 'all'; state.page = 1; route('portal/all', { scroll: 'results' }); return; }
    const themeButton = target.closest('[data-theme]');
    if (themeButton) { state.prefs.theme = themeButton.dataset.theme; applyPreferences(true); renderRoute(); return; }
    const fontButton = target.closest('[data-font]');
    if (fontButton) { state.prefs.font = Number(fontButton.dataset.font); applyPreferences(true); renderRoute(); return; }
    const widthButton = target.closest('[data-width]');
    if (widthButton) { state.prefs.width = widthButton.dataset.width; applyPreferences(true); renderRoute(); return; }
    if (target.closest('[data-scroll-top]')) { scrollTo({ top: 0, behavior: 'smooth' }); return; }
    if (target.closest('[data-scroll-toc]')) { document.querySelector('#article-toc')?.scrollIntoView({ behavior: 'smooth', block: 'start' }); return; }
    if (target.closest('[data-close-viewer]')) { document.querySelector('#image-viewer')?.close?.(); return; }
    const image = target.closest('.reader-image, .wiki-document img');
    if (image) { openImageViewer(image); }
  });

  document.addEventListener('keydown', (event) => {
    if ((event.key === 'Enter' || event.key === ' ') && event.target instanceof HTMLImageElement && event.target.closest('.wiki-document, .media-grid')) {
      event.preventDefault();
      openImageViewer(event.target);
    }
  });

  document.addEventListener('input', (event) => {
    if (event.target.id === 'portal-search') {
      state.query = event.target.value;
      state.page = 1;
      clearTimeout(window.__portalTimer);
      window.__portalTimer = setTimeout(() => {
        state.pendingScroll = 'none';
        portalPage(state.portal);
        requestAnimationFrame(() => {
          const input = document.querySelector('#portal-search');
          input?.focus();
          input?.setSelectionRange?.(state.query.length, state.query.length);
        });
      }, 160);
    }
    if (event.target.id === 'media-search') {
      state.mediaQuery = event.target.value;
      state.mediaPage = 1;
      clearTimeout(window.__mediaTimer);
      window.__mediaTimer = setTimeout(mediaPage, 180);
    }
  });

  document.addEventListener('change', (event) => {
    if (event.target.id === 'namespace-filter') { state.namespace = event.target.value; state.page = 1; state.pendingScroll = 'results'; portalPage(state.portal); }
    if (event.target.id === 'media-kind') { state.mediaKind = event.target.value; state.mediaPage = 1; mediaPage(); }
  });

  addEventListener('hashchange', renderRoute);
  matchMedia('(prefers-color-scheme: dark)').addEventListener?.('change', () => { if (state.prefs.theme === 'system') applyPreferences(); });
}

async function boot() {
  try {
    applyPreferences();
    bindEvents();
    state.manifest = await loadJson('runtime-manifest.json', { fresh: true });
    state.dataVersion = state.manifest.generatedAt || String(state.manifest.schemaVersion || '3');
    state.jsonCache.clear();
    [state.archive, state.categories, state.portals] = await Promise.all([
      loadJson('archive-index.json'),
      loadJson('category-index.json'),
      loadJson('portal-index.json'),
    ]);
    for (const item of state.archive) {
      state.archiveById.set(item.id, item);
      const key = normalize(item.title);
      const current = state.titleMap.get(key);
      if (!current || (current.namespace !== 0 && item.namespace === 0)) state.titleMap.set(key, item);
    }
    if (!location.hash || location.hash === '#') history.replaceState(null, '', '#/portal/all');
    await renderRoute();
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register(`/sw.js?v=${UI_VERSION}`, { updateViaCache: 'none' }).then((registration) => registration.update()).catch((error) => console.warn('service worker', error));
    }
  } catch (error) {
    console.error(error);
    errorPanel(error);
  }
}

boot();
