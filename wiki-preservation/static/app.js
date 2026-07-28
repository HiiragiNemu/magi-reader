const app = document.querySelector('#app');

const PAGE_SIZE = 80;
const state = {
  manifest: null,
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
};

const portalCopy = {
  characters: ['魔法少女与人物', '角色、组织、关系、学校、城市与人物相关资料'],
  story: ['剧情与活动', '主线、支线、角色剧情、活动记录、章节与剧情格式'],
  memoria: ['记忆结晶与道具', '记忆结晶、素材、道具、商店、装备与能力效果'],
  doppel: ['Doppel、魔女与传言', 'Doppel、魔女、使魔、传言、魔女文字与设定考据'],
  system: ['游戏与战斗系统', '战斗、属性、Disc、Magia、Connect、关卡和养成系统'],
  world: ['世界观与术语', '地点、概念、时间线、术语、团体与世界设定'],
  media: ['动画、音乐与出版物', '动画、漫画、歌曲、广播、画集、宣传与衍生作品'],
  technical: ['模板与技术档案', '模板、模块、分类、帮助、翻译规范与原站维护资料'],
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

function route(path) {
  const next = `#/${String(path).replace(/^\/+/, '')}`;
  if (location.hash === next) renderRoute();
  else location.hash = next;
  scrollTo({ top: 0, behavior: 'smooth' });
}

function parseRoute() {
  const raw = location.hash.replace(/^#\/?/, '') || 'portal';
  const [section, ...rest] = raw.split('/');
  let id = rest.join('/');
  try { id = decodeURIComponent(id); } catch {}
  return { section, id };
}

async function loadJson(path) {
  if (state.jsonCache.has(path)) return state.jsonCache.get(path);
  const response = await fetch(`/data/${String(path).replace(/^\/+/, '')}`, { cache: 'force-cache' });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  const value = await response.json();
  state.jsonCache.set(path, value);
  return value;
}

function setDocumentTitle(title) {
  document.title = title ? `${title} — 魔法纪录中文资料库` : '魔法纪录中文资料库';
}

function header(active = 'portal') {
  const links = [
    ['portal', '知识门户'],
    ['characters', '人物'],
    ['story', '剧情'],
    ['memoria', '记忆结晶'],
    ['doppel', 'Doppel'],
    ['media', '媒体'],
    ['about', '关于'],
  ];
  return `
    <header class="site-header">
      <button class="brand" data-route="portal" type="button">
        <span class="brand-mark">✦</span>
        <span><strong>魔法纪录中文资料库</strong><small>STATIC PRESERVATION READER</small></span>
      </button>
      <nav>${links.map(([id, label]) => `<button class="${active === id ? 'active' : ''}" data-route="${id}" type="button">${label}</button>`).join('')}</nav>
    </header>`;
}

function shell(content, active = 'portal') {
  app.innerHTML = `${header(active)}<main class="site-main">${content}</main><footer class="site-footer"><span>只读静态资料库 · 页面与索引由 MediaWiki API 云端快照生成</span><button data-route="about">来源与保存说明</button></footer>`;
}

function loading(label = '正在读取静态资料……') {
  shell(`<div class="state-panel"><div class="spinner"></div><strong>${escapeHtml(label)}</strong></div>`);
}

function errorPanel(error) {
  const message = error instanceof Error ? error.message : String(error);
  shell(`<div class="state-panel error"><strong>读取失败</strong><pre>${escapeHtml(message)}</pre><button data-route="portal">返回知识门户</button></div>`);
}

function articleSearchText(item) {
  return [item.title, item.namespaceLabel, item.preview, item.categories, item.headings?.map((value) => value.text), item.redirectTo].flat(Infinity).join(' ');
}

function setPortal(id) {
  state.portal = id;
  state.page = 1;
  route('portal');
}

function portalPage(forcedPortal = '') {
  const selectedPortal = forcedPortal || state.portal;
  if (forcedPortal) state.portal = forcedPortal;
  const active = state.portals.find((item) => item.id === selectedPortal);
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
    { id: 'all', title: '全部保存内容', count: state.archive.length, description: '浏览全部正文、Game、模板、模块、分类和项目资料' },
    ...state.portals.map((item) => ({ ...item, ...(portalCopy[item.id] ? { title: portalCopy[item.id][0], description: portalCopy[item.id][1] } : {}) })),
  ];
  setDocumentTitle(active?.title || '知识门户');
  shell(`
    <section class="portal-hero">
      <div><p class="eyebrow">MAGIA RECORD · LONG-TERM PRESERVATION</p><h1>${escapeHtml(active?.title || '知识门户')}</h1><p>把原 Wiki 的正文、章节、分类、重定向与媒体索引重组为无需账号和数据库的静态资料站。可读页面与完整原始 wikitext 同时保留，界面改善不以删减信息为代价。</p></div>
      <div class="coverage-grid">
        <div><strong>${Number(counts.pages || 0).toLocaleString('zh-CN')}</strong><span>归档页面</span></div>
        <div><strong>${Number(counts.categories || 0).toLocaleString('zh-CN')}</strong><span>分类</span></div>
        <div><strong>${Number(counts.media || 0).toLocaleString('zh-CN')}</strong><span>媒体记录</span></div>
        <div><strong>${formatBytes(counts.contentBytes)}</strong><span>原始正文</span></div>
      </div>
    </section>
    <section class="toolbar">
      <label class="search-field"><span>⌕</span><input id="portal-search" type="search" value="${attr(state.query)}" placeholder="搜索标题、分类、章节、正文摘要或重定向目标"></label>
      <select id="namespace-filter"><option value="all">全部命名空间</option>${namespaces.map(([id, label]) => `<option value="${id}" ${state.namespace === String(id) ? 'selected' : ''}>${escapeHtml(label)}（${id}）</option>`).join('')}</select>
    </section>
    <section class="portal-cards">${cards.map((card) => `<button type="button" class="portal-card ${selectedPortal === card.id ? 'active' : ''}" data-portal="${attr(card.id)}"><strong>${escapeHtml(card.title)}</strong><small>${escapeHtml(card.description || '')}</small><span>${Number(card.count || 0).toLocaleString('zh-CN')} 页</span></button>`).join('')}</section>
    <section class="category-strip"><button type="button" class="chip ${state.category === 'all' ? 'active' : ''}" data-category="all">全部分类</button>${state.categories.slice(0, 36).map((item) => `<button type="button" class="chip ${state.category === item.name ? 'active' : ''}" data-category="${attr(item.name)}">${escapeHtml(item.name)} · ${item.count}</button>`).join('')}</section>
    <div class="section-heading"><h2>${escapeHtml(active?.title || '全部保存内容')}</h2><span>${filtered.length.toLocaleString('zh-CN')} 个匹配页面</span></div>
    ${shown.length ? `<div class="article-list">${shown.map((item) => `<button class="article-row" type="button" data-article="${attr(item.id)}"><span class="namespace-badge">${escapeHtml(item.namespaceLabel)}</span><span><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml([...(item.categories || []).slice(0, 4), ...(item.headings || []).slice(0, 2).map((value) => value.text), item.redirectTo ? `→ ${item.redirectTo}` : '', item.preview].filter(Boolean).join(' · '))}</small></span><span>${formatBytes(item.textBytes)}</span></button>`).join('')}</div>` : '<div class="state-panel"><strong>没有符合当前条件的页面</strong></div>'}
    ${pages > 1 ? `<div class="pager"><button type="button" data-page="${state.page - 1}" ${state.page <= 1 ? 'disabled' : ''}>上一页</button><span>第 ${state.page} / ${pages} 页</span><button type="button" data-page="${state.page + 1}" ${state.page >= pages ? 'disabled' : ''}>下一页</button></div>` : ''}
  `, forcedPortal || 'portal');
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

function mediaForName(name) {
  const bare = String(name || '').replace(/^(?:File|Image|文件|图像|圖像|档案|檔案)\s*:/i, '').trim();
  return state.mediaMap.get(normalize(bare)) || state.mediaMap.get(normalize(bare.replaceAll(' ', '_'))) || null;
}

function splitTop(value, delimiter = '|') {
  const parts = [];
  let buffer = '';
  let templates = 0;
  let links = 0;
  for (let i = 0; i < value.length; i += 1) {
    const pair = value.slice(i, i + 2);
    if (pair === '{{') { templates += 1; buffer += pair; i += 1; continue; }
    if (pair === '}}') { templates = Math.max(0, templates - 1); buffer += pair; i += 1; continue; }
    if (pair === '[[') { links += 1; buffer += pair; i += 1; continue; }
    if (pair === ']]') { links = Math.max(0, links - 1); buffer += pair; i += 1; continue; }
    if (value[i] === delimiter && templates === 0 && links === 0) { parts.push(buffer); buffer = ''; continue; }
    buffer += value[i];
  }
  parts.push(buffer);
  return parts;
}

function plain(value) {
  return String(value || '')
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\[\[(?:[^|\]]+\|)?([^\]]+)\]\]/g, '$1')
    .replace(/\{\{(?:[^{}|]+\|)?([^{}]*)\}\}/g, '$1')
    .replace(/'''|''/g, '')
    .replace(/<[^>]+>/g, '')
    .trim();
}

function internalTarget(target) {
  const clean = String(target || '').replace(/^:/, '').split('#')[0].replaceAll('_', ' ').trim();
  return state.titleMap.get(normalize(clean)) || null;
}

function renderTemplate(raw) {
  const parts = splitTop(raw.slice(2, -2)).map((value) => value.trim());
  const name = parts.shift() || '模板';
  const positional = parts.map((part) => part.includes('=') ? part.slice(part.indexOf('=') + 1).trim() : part).filter(Boolean);
  const last = positional.at(-1) || '';
  const lowered = normalize(name);
  if (['lang', '语言', 'zh cn', 'zh hans', 'zh hant', 'ja', 'nowrap', 'small'].includes(lowered)) return renderInline(last);
  if (['ruby', 'ruby ja', '注音'].includes(lowered) && positional.length >= 2) return `<ruby>${renderInline(positional[0])}<rp>（</rp><rt>${escapeHtml(plain(positional[1]))}</rt><rp>）</rp></ruby>`;
  if (['黑幕', 'spoiler', '剧透'].includes(lowered)) return `<span class="spoiler" title="剧透内容">${renderInline(last)}</span>`;
  return `<span class="template-inline" title="${attr(raw)}">模板：${escapeHtml(name)}${last && last.length < 160 ? ` · ${renderInline(last)}` : ''}</span>`;
}

function renderInline(value) {
  const source = String(value || '').replace(/<\/?(?:span|div|center|small|big|font|blockquote|poem|nowiki|onlyinclude|includeonly|noinclude|section)[^>]*>/gi, '');
  const token = /(\[\[[\s\S]*?\]\]|\{\{[\s\S]*?\}\}|\[(?:https?:\/\/)[^\]]+\]|'''[\s\S]*?'''|''[\s\S]*?''|<br\s*\/?>|<ref\b[^>]*>[\s\S]*?<\/ref>|<ref\b[^>]*\/>)/gi;
  let result = '';
  let cursor = 0;
  for (const match of source.matchAll(token)) {
    result += escapeHtml(source.slice(cursor, match.index));
    const raw = match[0];
    if (/^<br/i.test(raw)) result += '<br>';
    else if (/^<ref/i.test(raw)) result += `<sup class="reference" title="${attr(plain(raw))}">[注]</sup>`;
    else if (raw.startsWith('{{')) result += renderTemplate(raw);
    else if (raw.startsWith('[[')) {
      const parts = splitTop(raw.slice(2, -2)).map((item) => item.trim());
      const target = parts[0] || '';
      const label = parts.at(-1) || target;
      if (/^(?:File|Image|文件|图像|圖像|档案|檔案)\s*:/i.test(target)) {
        const item = mediaForName(target);
        result += item && item.mediaType === 'image' ? `<span class="inline-media"><img src="${attr(item.url)}" alt="${attr(plain(label))}" loading="lazy"><span>${escapeHtml(plain(label) || item.name)}</span></span>` : `<span class="template-inline">媒体：${escapeHtml(plain(label) || target)}</span>`;
      } else if (/^(?:Category|分类|分類)\s*:/i.test(target)) {
        result += `<span class="chip">${escapeHtml(plain(label))}</span>`;
      } else {
        const item = internalTarget(target);
        result += item ? `<button class="internal-link" type="button" data-article="${attr(item.id)}">${renderInline(label)}</button>` : `<button class="internal-link missing" type="button" data-search="${attr(target)}">${renderInline(label)}</button>`;
      }
    } else if (raw.startsWith('[http')) {
      const inner = raw.slice(1, -1).trim();
      const space = inner.search(/\s/);
      const href = space < 0 ? inner : inner.slice(0, space);
      const label = space < 0 ? inner : inner.slice(space).trim();
      result += `<a href="${attr(href)}" target="_blank" rel="noreferrer">${escapeHtml(label || href)}</a>`;
    } else if (raw.startsWith("'''")) result += `<strong>${renderInline(raw.slice(3, -3))}</strong>`;
    else if (raw.startsWith("''")) result += `<em>${renderInline(raw.slice(2, -2))}</em>`;
    cursor = match.index + raw.length;
  }
  result += escapeHtml(source.slice(cursor));
  return result;
}

function braceBalance(value) {
  return (String(value).match(/\{\{/g)?.length || 0) - (String(value).match(/\}\}/g)?.length || 0);
}

function renderTemplateBlock(raw) {
  const body = raw.trim().replace(/^\{\{/, '').replace(/\}\}\s*$/, '');
  const parts = splitTop(body);
  const name = plain(parts.shift() || '模板');
  const params = parts.map((part, index) => {
    const equals = part.indexOf('=');
    return { label: equals > 0 ? plain(part.slice(0, equals)) : String(index + 1), value: equals > 0 ? part.slice(equals + 1).trim() : part.trim() };
  }).filter((item) => item.value);
  return `<details class="template-block" ${/(?:信息|数据|角色|记忆|Doppel|魔女)/i.test(name) ? 'open' : ''}><summary>模板：${escapeHtml(name || '未命名')}<span>${params.length} 个参数</span></summary><dl>${params.map((item) => `<div><dt>${escapeHtml(item.label)}</dt><dd>${renderInline(item.value)}</dd></div>`).join('')}</dl></details>`;
}

function renderTable(lines, start) {
  const rows = [];
  let caption = '';
  let cells = [];
  let headerRow = false;
  let index = start + 1;
  const flush = () => { if (cells.length) rows.push({ header: headerRow, cells }); cells = []; headerRow = false; };
  for (; index < lines.length; index += 1) {
    const line = lines[index].trim();
    if (line.startsWith('|}')) { flush(); break; }
    if (line.startsWith('|+')) { caption = line.slice(2).trim(); continue; }
    if (line.startsWith('|-')) { flush(); continue; }
    if (line.startsWith('!')) { if (cells.length && !headerRow) flush(); headerRow = true; cells.push(...line.slice(1).split('!!')); continue; }
    if (line.startsWith('|')) { if (cells.length && headerRow) flush(); cells.push(...line.slice(1).split('||')); continue; }
    if (cells.length) cells[cells.length - 1] += `\n${line}`;
  }
  const cleanCell = (cell) => {
    const value = cell.trim();
    const pipe = value.indexOf('|');
    if (pipe > 0 && /(?:style|class|rowspan|colspan|align|width)\s*=/.test(value.slice(0, pipe))) return value.slice(pipe + 1).trim();
    return value;
  };
  return { next: Math.min(index + 1, lines.length), html: `<div class="table-scroll"><table class="wiki-table">${caption ? `<caption>${renderInline(caption)}</caption>` : ''}<tbody>${rows.map((row) => `<tr>${row.cells.map((cell) => row.header ? `<th>${renderInline(cleanCell(cell))}</th>` : `<td>${renderInline(cleanCell(cell))}</td>`).join('')}</tr>`).join('')}</tbody></table></div>` };
}

function renderWikitext(source) {
  const lines = String(source || '').replace(/\r\n?/g, '\n').replace(/<!--[\s\S]*?-->/g, '').replace(/__(?:TOC|NOTOC|NOEDITSECTION|FORCETOC)__/g, '').split('\n');
  const out = [];
  let paragraph = [];
  const flush = () => { const value = paragraph.join('\n').trim(); if (value) out.push(`<p class="article-paragraph">${renderInline(value)}</p>`); paragraph = []; };
  for (let index = 0; index < lines.length;) {
    const raw = lines[index];
    const line = raw.trim();
    if (!line) { flush(); index += 1; continue; }
    if (/^#(?:REDIRECT|重定向)/i.test(line)) { flush(); out.push(`<div class="redirect-notice">${renderInline(line)}</div>`); index += 1; continue; }
    if (line.startsWith('{|')) { flush(); const table = renderTable(lines, index); out.push(table.html); index = table.next; continue; }
    if (/^<gallery\b/i.test(line)) {
      flush(); const entries = []; index += 1;
      while (index < lines.length && !/<\/gallery>/i.test(lines[index])) { const [name, ...caption] = lines[index].split('|'); if (name.trim()) entries.push({ name: name.trim(), caption: caption.join('|').trim() }); index += 1; }
      out.push(`<div class="wiki-gallery">${entries.map((entry) => { const item = mediaForName(entry.name); return `<figure>${item?.url ? `<img src="${attr(item.url)}" alt="${attr(plain(entry.caption) || entry.name)}" loading="lazy">` : `<div class="missing-media">${escapeHtml(entry.name)}</div>`}<figcaption>${renderInline(entry.caption || entry.name)}</figcaption></figure>`; }).join('')}</div>`); index += 1; continue;
    }
    const heading = /^(={2,6})\s*(.*?)\s*\1$/.exec(line);
    if (heading) { flush(); const level = Math.min(6, heading[1].length); const id = `section-${index}-${plain(heading[2]).replace(/\s+/g, '-')}`; out.push(`<h${level} id="${attr(id)}" class="wiki-heading">${renderInline(heading[2])}</h${level}>`); index += 1; continue; }
    if (/^-{4,}$/.test(line)) { flush(); out.push('<hr>'); index += 1; continue; }
    const list = /^([*#;:]+)\s*(.*)$/.exec(raw);
    if (list) { flush(); const ordered = list[1].startsWith('#'); const items = []; const marker = ordered ? /^([#]+)\s*(.*)$/ : /^([*;:]+)\s*(.*)$/; while (index < lines.length) { const match = marker.exec(lines[index]); if (!match) break; items.push({ depth: match[1].length, value: match[2] }); index += 1; } out.push(`<${ordered ? 'ol' : 'ul'} class="wiki-list">${items.map((item) => `<li style="margin-inline-start:${Math.max(0, item.depth - 1) * 1.2}rem">${renderInline(item.value)}</li>`).join('')}</${ordered ? 'ol' : 'ul'}>`); continue; }
    if (/^\[\[(?:Category|分类|分類)\s*:/i.test(line)) { index += 1; continue; }
    if (line.startsWith('{{')) { let block = raw; let balance = braceBalance(raw); let next = index + 1; while (balance > 0 && next < lines.length) { block += `\n${lines[next]}`; balance += braceBalance(lines[next]); next += 1; } if (next > index + 1 || /^\{\{[^{}]+\}\}$/.test(line)) { flush(); out.push(renderTemplateBlock(block)); index = next; continue; } }
    if (/^\s/.test(raw)) { flush(); const pre = []; while (index < lines.length && /^\s/.test(lines[index]) && lines[index].trim()) { pre.push(lines[index].replace(/^ /, '')); index += 1; } out.push(`<pre class="raw-source"><code>${escapeHtml(pre.join('\n'))}</code></pre>`); continue; }
    paragraph.push(raw); index += 1;
  }
  flush();
  return out.join('');
}

async function articlePage(id) {
  const item = state.archiveById.get(id);
  if (!item) { state.query = id.replace(/^\d+:/, ''); state.portal = 'all'; state.page = 1; portalPage(); return; }
  loading(`正在载入 ${item.title}……`);
  await ensureMedia().catch(() => []);
  const shard = await loadJson(`archive/${item.shard}.json`);
  const record = shard[id];
  if (!record) throw new Error(`正文分片中缺少记录：${id}`);
  setDocumentTitle(item.title);
  const outline = (item.headings || []).filter((entry) => entry.level <= 4);
  shell(`
    <article class="article-page">
      <button class="back-button" type="button" data-route="portal">← 返回知识门户</button>
      <header class="article-header"><p class="eyebrow">PRESERVED WIKI ARTICLE</p><h1>${escapeHtml(item.title)}</h1><div class="article-meta"><span class="namespace-badge">${escapeHtml(item.namespaceLabel)}</span><span>${formatBytes(item.textBytes)}</span><span>修订 ${escapeHtml(item.revision || '—')}</span><span>SHA-256 ${escapeHtml(item.sha256.slice(0, 16))}…</span>${item.redirectTo ? `<span>重定向至 ${escapeHtml(item.redirectTo)}</span>` : ''}</div><div class="category-strip">${(item.categories || []).map((value) => `<button type="button" class="chip" data-category-jump="${attr(value)}">${escapeHtml(value)}</button>`).join('')}</div></header>
      <div class="article-actions"><button type="button" id="copy-wikitext">复制原始 wikitext</button><a href="https://magireco.moe/wiki/${encodeURIComponent(item.title.replaceAll(' ', '_'))}" target="_blank" rel="noreferrer">参考原 Wiki 页面</a></div>
      <div class="rendered-layout"><div class="article-body">${renderWikitext(record.wikitext)}</div>${outline.length > 1 ? `<nav class="toc"><strong>本页目录</strong><ol>${outline.map((entry, index) => `<li style="margin-inline-start:${Math.max(0, entry.level - 2)}rem"><a href="#section-${index}-${attr(plain(entry.text).replace(/\s+/g, '-'))}">${escapeHtml(entry.text)}</a></li>`).join('')}</ol></nav>` : ''}</div>
      <details class="raw-details"><summary>查看完整原始 wikitext（保真层）</summary><pre class="raw-source"><code>${escapeHtml(record.wikitext || '（空页面）')}</code></pre></details>
    </article>
  `, 'article');
  document.querySelector('#copy-wikitext')?.addEventListener('click', async (event) => { await navigator.clipboard.writeText(record.wikitext || ''); event.currentTarget.textContent = '已复制'; setTimeout(() => { event.currentTarget.textContent = '复制原始 wikitext'; }, 1600); });
}

async function mediaPage() {
  loading('正在载入媒体索引……');
  const media = await ensureMedia();
  const filtered = media.filter((item) => (state.mediaKind === 'all' || item.mediaType === state.mediaKind) && matches(state.mediaQuery, item.name, item.mime, item.mediaType));
  const size = state.mediaKind === 'image' ? 72 : 100;
  const pages = Math.max(1, Math.ceil(filtered.length / size));
  state.mediaPage = Math.min(Math.max(1, state.mediaPage), pages);
  const shown = filtered.slice((state.mediaPage - 1) * size, state.mediaPage * size);
  setDocumentTitle('媒体档案');
  shell(`
    <section><p class="eyebrow">MEDIA ARCHIVE</p><div class="section-heading"><h1>媒体档案</h1><span>${filtered.length.toLocaleString('zh-CN')} 个文件</span></div><p class="section-copy">保存文件名、尺寸、类型、哈希和原始下载地址。当前二进制仍从原站媒体地址读取，后续将迁移到独立对象存储。</p>
    <div class="toolbar"><label class="search-field"><span>⌕</span><input id="media-search" type="search" value="${attr(state.mediaQuery)}" placeholder="搜索图片或音频文件名"></label><select id="media-kind"><option value="image" ${state.mediaKind === 'image' ? 'selected' : ''}>图片</option><option value="audio" ${state.mediaKind === 'audio' ? 'selected' : ''}>音频</option><option value="all" ${state.mediaKind === 'all' ? 'selected' : ''}>全部媒体</option></select></div>
    ${state.mediaKind === 'image' ? `<div class="media-grid">${shown.map((item) => `<article class="media-card">${item.url ? `<img src="${attr(item.url)}" alt="${attr(item.name)}" loading="lazy">` : '<div class="missing-media">无预览</div>'}<strong>${escapeHtml(item.name)}</strong><small>${[item.width && item.height ? `${item.width}×${item.height}` : '', formatBytes(item.size), item.mime].filter(Boolean).join(' · ')}</small><a href="${attr(item.url)}" target="_blank" rel="noreferrer">打开源文件</a></article>`).join('')}</div>` : `<div class="audio-list">${shown.map((item) => `<article><div><strong>${escapeHtml(item.name)}</strong><small>${formatBytes(item.size)} · ${escapeHtml(item.mime)}</small></div>${item.mediaType === 'audio' && item.url ? `<audio controls preload="none" src="${attr(item.url)}"></audio>` : `<a href="${attr(item.url)}" target="_blank" rel="noreferrer">打开</a>`}</article>`).join('')}</div>`}
    ${pages > 1 ? `<div class="pager"><button type="button" data-media-page="${state.mediaPage - 1}" ${state.mediaPage <= 1 ? 'disabled' : ''}>上一页</button><span>第 ${state.mediaPage} / ${pages} 页</span><button type="button" data-media-page="${state.mediaPage + 1}" ${state.mediaPage >= pages ? 'disabled' : ''}>下一页</button></div>` : ''}</section>
  `, 'media');
}

function aboutPage() {
  const source = state.manifest.source || {};
  const counts = state.manifest.counts || {};
  setDocumentTitle('关于数据');
  shell(`<article class="about-page"><p class="eyebrow">DATA & PROVENANCE</p><h1>关于数据与长期保存</h1><section><h2>保存方式</h2><p>本网站在 GitHub Actions 中从魔法纪录中文 Wiki 的 MediaWiki API生成不可编辑的静态快照。构建后只需要普通静态文件托管，不依赖 PHP、数据库、账号系统或原 Wiki 的服务器程序。</p></section><section><h2>当前快照</h2><dl class="definition-grid"><div><dt>生成时间</dt><dd>${escapeHtml(state.manifest.generatedAt)}</dd></div><div><dt>API</dt><dd>${escapeHtml(source.api)}</dd></div><div><dt>页面</dt><dd>${Number(counts.pages || 0).toLocaleString('zh-CN')}</dd></div><div><dt>原始正文</dt><dd>${formatBytes(counts.contentBytes)}</dd></div><div><dt>图片</dt><dd>${Number(counts.images || 0).toLocaleString('zh-CN')}</dd></div><div><dt>音频</dt><dd>${Number(counts.audio || 0).toLocaleString('zh-CN')}</dd></div></dl></section><section><h2>不衰减原则</h2><p>可读渲染器不会替代原始正文。每个页面均保留完整 wikitext、修订号、时间、字节数和 SHA-256；尚未解释的复杂模板仍以模板参数块展示，并可在页面底部展开完整源代码。</p></section><section><h2>权利说明</h2><p>本站用于研究、保存、检索和兼容性开发。游戏文本、图像、音频、角色、商标及其他第三方内容的权利归各自权利人所有；Wiki 编辑文本和译文的使用条件以原站声明为准。</p></section></article>`, 'about');
}

async function renderRoute() {
  try {
    const { section, id } = parseRoute();
    if (section === 'article') await articlePage(id);
    else if (section === 'media') await mediaPage();
    else if (section === 'about') aboutPage();
    else if (portalCopy[section]) portalPage(section);
    else portalPage();
  } catch (error) {
    console.error(error);
    errorPanel(error);
  }
}

function bindEvents() {
  document.addEventListener('click', (event) => {
    const target = event.target instanceof Element ? event.target : null;
    if (!target) return;
    const routeButton = target.closest('[data-route]');
    if (routeButton) { route(routeButton.dataset.route); return; }
    const articleButton = target.closest('[data-article]');
    if (articleButton) { route(`article/${encodeURIComponent(articleButton.dataset.article)}`); return; }
    const portalButton = target.closest('[data-portal]');
    if (portalButton) { state.portal = portalButton.dataset.portal; state.page = 1; portalPage(); return; }
    const categoryButton = target.closest('[data-category]');
    if (categoryButton) { state.category = categoryButton.dataset.category; state.page = 1; portalPage(); return; }
    const categoryJump = target.closest('[data-category-jump]');
    if (categoryJump) { state.category = categoryJump.dataset.categoryJump; state.portal = 'all'; state.page = 1; route('portal'); return; }
    const pageButton = target.closest('[data-page]');
    if (pageButton && !pageButton.disabled) { state.page = Number(pageButton.dataset.page); portalPage(); scrollTo({ top: 0, behavior: 'smooth' }); return; }
    const mediaPageButton = target.closest('[data-media-page]');
    if (mediaPageButton && !mediaPageButton.disabled) { state.mediaPage = Number(mediaPageButton.dataset.mediaPage); mediaPage(); scrollTo({ top: 0, behavior: 'smooth' }); return; }
    const searchButton = target.closest('[data-search]');
    if (searchButton) { state.query = searchButton.dataset.search; state.portal = 'all'; state.page = 1; route('portal'); }
  });
  document.addEventListener('input', (event) => {
    if (event.target.id === 'portal-search') { state.query = event.target.value; state.page = 1; clearTimeout(window.__portalTimer); window.__portalTimer = setTimeout(portalPage, 120); }
    if (event.target.id === 'media-search') { state.mediaQuery = event.target.value; state.mediaPage = 1; clearTimeout(window.__mediaTimer); window.__mediaTimer = setTimeout(mediaPage, 150); }
  });
  document.addEventListener('change', (event) => {
    if (event.target.id === 'namespace-filter') { state.namespace = event.target.value; state.page = 1; portalPage(); }
    if (event.target.id === 'media-kind') { state.mediaKind = event.target.value; state.mediaPage = 1; mediaPage(); }
  });
  addEventListener('hashchange', renderRoute);
}

async function boot() {
  try {
    bindEvents();
    [state.manifest, state.archive, state.categories, state.portals] = await Promise.all([
      loadJson('runtime-manifest.json'),
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
    if (!location.hash || location.hash === '#') history.replaceState(null, '', '#/portal');
    await renderRoute();
    if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch((error) => console.warn('service worker', error));
  } catch (error) {
    console.error(error);
    errorPanel(error);
  }
}

boot();
