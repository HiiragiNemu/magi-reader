const structuredApp = document.querySelector('#app');
const STRUCTURED_UI_VERSION = '5.0';
const structuredState = {
  manifest: null,
  characters: null,
  voiceIndex: null,
  voiceCache: new Map(),
  characterQuery: '',
  characterKind: 'character',
  characterVoice: 'all',
  characterPage: 1,
  voiceQuery: '',
  voicePage: 1,
  lineQuery: '',
  lineCostume: 'all',
  lineGroup: 'all',
  linePage: 1,
  rendering: false,
};

function sEscape(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function sAttr(value) {
  return sEscape(value).replaceAll('`', '&#96;');
}

function sNormalize(value) {
  return String(value ?? '')
    .normalize('NFKC')
    .toLocaleLowerCase('zh-CN')
    .replace(/[\s\-_·・/（）()【】\[\]《》]+/g, ' ')
    .trim();
}

function sMatches(query, ...values) {
  const terms = sNormalize(query).split(' ').filter(Boolean);
  if (!terms.length) return true;
  const haystack = sNormalize(values.flat(Infinity).join(' '));
  return terms.every((term) => haystack.includes(term));
}

function structuredDataUrl(path) {
  return `/data/structured/${String(path).replace(/^\/+/, '')}?v=${STRUCTURED_UI_VERSION}`;
}

async function structuredJson(path) {
  const response = await fetch(structuredDataUrl(path), { cache: 'default' });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}

async function ensureStructuredCore() {
  if (structuredState.manifest && structuredState.characters && structuredState.voiceIndex) return;
  [structuredState.manifest, structuredState.characters, structuredState.voiceIndex] = await Promise.all([
    structuredJson('manifest.json'),
    structuredJson('characters.json'),
    structuredJson('voice-index.json'),
  ]);
}

async function loadVoiceFile(key) {
  if (structuredState.voiceCache.has(key)) return structuredState.voiceCache.get(key);
  const value = await structuredJson(`voice/${key}.json`);
  structuredState.voiceCache.set(key, value);
  return value;
}

function structuredThemeControls() {
  const preferences = (() => {
    try {
      return JSON.parse(localStorage.getItem('magireco-reader-preferences') || '{}');
    } catch {
      return {};
    }
  })();
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

function structuredHeader(active) {
  const links = [
    ['portal/all', 'Wiki正文', 'wiki'],
    ['characters', '人物', 'characters'],
    ['voice', '语音', 'voice'],
    ['portal/story', '剧情', 'story'],
    ['portal/memoria', '记忆结晶', 'memoria'],
    ['portal/doppel', 'Doppel', 'doppel'],
    ['media', '媒体', 'media'],
    ['about', '关于', 'about'],
  ];
  return `
    <header class="site-header structured-header">
      <div class="header-primary">
        <button class="brand" data-route="characters" type="button" aria-label="返回角色图鉴">
          <span class="brand-mark">✦</span>
          <span><strong>魔法纪录中文资料库</strong><small>STRUCTURED ARCHIVE & READER</small></span>
        </button>
        ${structuredThemeControls()}
      </div>
      <nav aria-label="主要栏目">${links.map(([path, label, id]) => `<button class="${active === id ? 'active' : ''}" data-route="${path}" type="button">${label}</button>`).join('')}</nav>
    </header>`;
}

function structuredShell(content, active) {
  structuredApp.innerHTML = `${structuredHeader(active)}<main class="site-main structured-main">${content}</main>
    <footer class="site-footer"><span>角色与语音来自原始人物页面的结构化提取 · Wiki正文独立保存</span><button data-route="about">来源与保存说明</button></footer>
    <button class="to-top" type="button" data-scroll-top aria-label="返回页面顶部">↑</button>
    <dialog class="image-viewer" id="image-viewer"><button type="button" class="viewer-close" data-close-viewer aria-label="关闭图片">×</button><div class="viewer-stage"><img alt=""><p></p></div></dialog>`;
  document.documentElement.dataset.structuredView = active;
}

function structuredLoading(label) {
  structuredShell(`<div class="state-panel"><div class="spinner"></div><strong>${sEscape(label)}</strong></div>`, 'characters');
}

function structuredError(error) {
  structuredShell(`<div class="state-panel error"><strong>结构化资料读取失败</strong><pre>${sEscape(error?.message || error)}</pre><button type="button" data-route="portal/all">转到Wiki正文</button></div>`, 'characters');
}

function routeStructured(path) {
  const next = `#/${String(path).replace(/^\/+/, '')}`;
  if (location.hash === next) void renderStructuredRoute();
  else location.hash = next;
  scrollTo({ top: 0, behavior: 'smooth' });
}

function currentStructuredRoute() {
  const raw = location.hash.replace(/^#\/?/, '');
  const [section, ...rest] = raw.split('/');
  let id = rest.join('/');
  try { id = decodeURIComponent(id); } catch {}
  return { section, id };
}

function isStructuredRoute() {
  const { section, id } = currentStructuredRoute();
  return section === 'characters' || section === 'character' || section === 'voice' || (section === 'portal' && id === 'characters');
}

function patchLegacyNavigation() {
  const wiki = structuredApp.querySelector('button[data-route="portal/all"]');
  if (wiki && wiki.closest('nav')) wiki.textContent = 'Wiki正文';
  const people = structuredApp.querySelector('button[data-route="portal/characters"]');
  if (people) {
    people.dataset.route = 'characters';
    people.textContent = '人物';
  }
  const nav = structuredApp.querySelector('.site-header nav');
  if (nav && !nav.querySelector('[data-route="voice"]')) {
    const voice = document.createElement('button');
    voice.type = 'button';
    voice.dataset.route = 'voice';
    voice.textContent = '语音';
    const character = nav.querySelector('[data-route="characters"]');
    character?.after(voice);
  }
}

function characterCard(item) {
  const voice = item.voiceCount ? `<span class="structured-badge voice">${item.voiceCount}条语音</span>` : '';
  const type = item.kind === 'organization' ? '<span class="structured-badge organization">组织</span>' : '';
  return `<button type="button" class="character-card" data-character-id="${sAttr(item.id)}">
    <span class="character-portrait">${item.imageUrl ? `<img src="${sAttr(item.imageUrl)}" alt="${sAttr(item.title)}" loading="lazy" decoding="async">` : '<span class="portrait-placeholder">✦</span>'}</span>
    <span class="character-card-copy">
      <span class="character-card-title"><strong>${sEscape(item.title)}</strong>${type}${voice}</span>
      ${item.nameJa ? `<small lang="ja">${sEscape(item.nameJa)}</small>` : ''}
      <span class="character-card-meta">${[item.voiceActor ? `声优 ${item.voiceActor}` : '', item.charaIds?.length ? `ID ${item.charaIds.join(' / ')}` : '', item.categories?.slice(0, 2).join(' · ')].filter(Boolean).map(sEscape).join(' · ')}</span>
    </span>
    <b aria-hidden="true">›</b>
  </button>`;
}

function characterListPage() {
  const all = structuredState.characters || [];
  const filtered = all
    .filter((item) => structuredState.characterKind === 'all' || item.kind === structuredState.characterKind)
    .filter((item) => structuredState.characterVoice === 'all' || (structuredState.characterVoice === 'with' ? item.voiceCount > 0 : item.voiceCount === 0))
    .filter((item) => sMatches(structuredState.characterQuery, item.searchText, item.title));
  const size = 48;
  const pages = Math.max(1, Math.ceil(filtered.length / size));
  structuredState.characterPage = Math.min(Math.max(1, structuredState.characterPage), pages);
  const shown = filtered.slice((structuredState.characterPage - 1) * size, structuredState.characterPage * size);
  const manifest = structuredState.manifest;
  document.title = '角色图鉴 — 魔法纪录中文资料库';
  structuredShell(`
    <section class="structured-hero">
      <div><p class="eyebrow">STRUCTURED CHARACTER ARCHIVE</p><h1>魔法少女与人物</h1><p>这里不是Wiki文章关键词筛选，而是从全部“人物信息”表直接生成的角色图鉴。活动、歌曲、目录页不会进入人物列表；组织可通过筛选单独查看。</p></div>
      <div class="coverage-grid structured-stats">
        <div><strong>${Number(manifest.characterPages).toLocaleString('zh-CN')}</strong><span>人物条目</span></div>
        <div><strong>${Number(manifest.organizations).toLocaleString('zh-CN')}</strong><span>组织条目</span></div>
        <div><strong>${Number(manifest.voiceCharacters).toLocaleString('zh-CN')}</strong><span>含语音人物</span></div>
        <div><strong>${Number(manifest.voiceWithAudio).toLocaleString('zh-CN')}</strong><span>可播放语音</span></div>
      </div>
    </section>
    <section class="toolbar structured-toolbar">
      <label class="search-field"><span>⌕</span><input id="character-search" type="search" value="${sAttr(structuredState.characterQuery)}" placeholder="搜索中文名、日文名、假名、罗马音、声优或人物资料" autocomplete="off"></label>
      <select id="character-kind"><option value="character" ${structuredState.characterKind === 'character' ? 'selected' : ''}>魔法少女与人物</option><option value="organization" ${structuredState.characterKind === 'organization' ? 'selected' : ''}>组织</option><option value="all" ${structuredState.characterKind === 'all' ? 'selected' : ''}>全部</option></select>
      <select id="character-voice"><option value="all" ${structuredState.characterVoice === 'all' ? 'selected' : ''}>全部语音状态</option><option value="with" ${structuredState.characterVoice === 'with' ? 'selected' : ''}>有语音</option><option value="without" ${structuredState.characterVoice === 'without' ? 'selected' : ''}>无语音</option></select>
    </section>
    <section class="structured-result-head"><div><p class="result-kicker">结构化图鉴</p><h2>${structuredState.characterKind === 'organization' ? '魔法少女组织' : '人物列表'}</h2></div><span>${filtered.length.toLocaleString('zh-CN')} 条</span></section>
    ${shown.length ? `<div class="character-grid">${shown.map(characterCard).join('')}</div>` : '<div class="state-panel inline"><strong>没有匹配人物</strong></div>'}
    ${pages > 1 ? `<div class="pager"><button type="button" data-character-page="${structuredState.characterPage - 1}" ${structuredState.characterPage <= 1 ? 'disabled' : ''}>上一页</button><span>第 ${structuredState.characterPage} / ${pages} 页</span><button type="button" data-character-page="${structuredState.characterPage + 1}" ${structuredState.characterPage >= pages ? 'disabled' : ''}>下一页</button></div>` : ''}
  `, 'characters');
}

function fieldRows(fields) {
  const preferred = ['日文名', '假名', '罗马音', '英文名', '别名', '其他译名', '声优', '人设', '初登场', '实装', '年龄', '身高', '愿望', '固有能力', '武器', '灵魂宝石位置', '出身地', '学校', '关系人', '备注'];
  const keys = [...preferred.filter((key) => fields[key]), ...Object.keys(fields).filter((key) => !preferred.includes(key))];
  return keys.map((key) => `<div><dt>${sEscape(key)}</dt><dd>${sEscape(fields[key]).replaceAll('\n', '<br>')}</dd></div>`).join('');
}

function findCharacter(id) {
  return (structuredState.characters || []).find((item) => item.id === id) || null;
}

function characterDetailPage(item) {
  document.title = `${item.title} — 角色图鉴`;
  structuredShell(`
    <article class="structured-page character-detail">
      <div class="reading-bar"><button type="button" data-route="characters">← 返回人物列表</button><span>${item.kind === 'organization' ? '组织资料' : '人物资料'}</span>${item.voiceKey ? `<button type="button" data-voice-id="${sAttr(item.id)}">角色语音</button>` : ''}</div>
      <header class="character-detail-head">
        <div class="character-detail-image">${item.imageUrl ? `<img class="reader-image" src="${sAttr(item.imageUrl)}" alt="${sAttr(item.title)}" loading="eager">` : '<span class="portrait-placeholder">✦</span>'}${item.imageCaption ? `<small>${sEscape(item.imageCaption)}</small>` : ''}</div>
        <div><p class="eyebrow">CHARACTER PROFILE</p><h1>${sEscape(item.title)}</h1>${item.nameJa ? `<p class="character-ja" lang="ja">${sEscape(item.nameJa)}</p>` : ''}<div class="profile-badges">${item.voiceActor ? `<span>声优 ${sEscape(item.voiceActor)}</span>` : ''}${item.designer ? `<span>人设 ${sEscape(item.designer)}</span>` : ''}${item.charaIds?.length ? `<span>角色ID ${sEscape(item.charaIds.join(' / '))}</span>` : ''}${item.voiceCount ? `<span>${item.voiceCount}条语音</span>` : ''}</div>${item.summary ? `<p class="character-summary">${sEscape(item.summary).replaceAll('\n\n', '</p><p class="character-summary">')}</p>` : ''}</div>
      </header>
      <div class="character-actions">${item.voiceKey ? `<button type="button" class="primary-action" data-voice-id="${sAttr(item.id)}">播放角色语音（${item.audioCount}）</button>` : ''}<button type="button" data-article="${sAttr(item.articleId)}">阅读完整Wiki正文</button><a href="${sAttr(item.sourceUrl)}" target="_blank" rel="noreferrer">原Wiki页面</a></div>
      <section class="profile-section"><h2>人物信息</h2><dl class="profile-fields">${fieldRows(item.fields || {})}</dl></section>
      <section class="profile-section"><h2>分类与关联</h2><div class="category-strip">${(item.categories || []).map((value) => `<span class="chip">${sEscape(value)}</span>`).join('')}</div></section>
    </article>
  `, 'characters');
}

function voiceIndexCard(item) {
  return `<button type="button" class="voice-character-card" data-voice-id="${sAttr(item.id)}">
    <span class="voice-character-image">${item.imageUrl ? `<img src="${sAttr(item.imageUrl)}" alt="${sAttr(item.title)}" loading="lazy">` : '<span class="portrait-placeholder">♪</span>'}</span>
    <span><strong>${sEscape(item.title)}</strong>${item.voiceActor ? `<small>声优 ${sEscape(item.voiceActor)}</small>` : ''}<span>${item.lineCount}条 · ${item.audioCount}条可播放 · ${item.costumes.length}套服装</span></span><b aria-hidden="true">›</b>
  </button>`;
}

function voiceIndexPage() {
  const filtered = (structuredState.voiceIndex || []).filter((item) => sMatches(structuredState.voiceQuery, item.searchText, item.title, item.costumes, item.groups));
  const size = 48;
  const pages = Math.max(1, Math.ceil(filtered.length / size));
  structuredState.voicePage = Math.min(Math.max(1, structuredState.voicePage), pages);
  const shown = filtered.slice((structuredState.voicePage - 1) * size, structuredState.voicePage * size);
  document.title = '角色语音 — 魔法纪录中文资料库';
  structuredShell(`
    <section class="structured-hero voice-hero"><div><p class="eyebrow">CHARACTER VOICE ARCHIVE</p><h1>角色语音</h1><p>从原Wiki语音组件的原始 <code>data-bind</code> 中恢复MP3地址，并保留中文译文、日文原文、服装、场景分类和语音槽位。播放器按需加载，不会在进入页面时批量下载音频。</p></div><div class="coverage-grid structured-stats"><div><strong>${structuredState.manifest.voiceCharacters}</strong><span>语音人物</span></div><div><strong>${structuredState.manifest.voiceLines.toLocaleString('zh-CN')}</strong><span>语音记录</span></div><div><strong>${structuredState.manifest.voiceWithAudio.toLocaleString('zh-CN')}</strong><span>可播放MP3</span></div><div><strong>${structuredState.manifest.voiceWithTranslation.toLocaleString('zh-CN')}</strong><span>有中文译文</span></div></div></section>
    <section class="toolbar"><label class="search-field"><span>⌕</span><input id="voice-character-search" type="search" value="${sAttr(structuredState.voiceQuery)}" placeholder="搜索人物、声优、服装或语音分类" autocomplete="off"></label></section>
    <section class="structured-result-head"><div><p class="result-kicker">可播放语音档案</p><h2>按人物浏览</h2></div><span>${filtered.length}人</span></section>
    <div class="voice-character-grid">${shown.map(voiceIndexCard).join('')}</div>
    ${pages > 1 ? `<div class="pager"><button type="button" data-voice-page="${structuredState.voicePage - 1}" ${structuredState.voicePage <= 1 ? 'disabled' : ''}>上一页</button><span>第 ${structuredState.voicePage} / ${pages} 页</span><button type="button" data-voice-page="${structuredState.voicePage + 1}" ${structuredState.voicePage >= pages ? 'disabled' : ''}>下一页</button></div>` : ''}
  `, 'voice');
}

async function voiceDetailPage(id) {
  const index = (structuredState.voiceIndex || []).find((item) => item.id === id);
  const character = findCharacter(id);
  if (!index) {
    routeStructured('voice');
    return;
  }
  structuredLoading(`正在载入 ${index.title} 的语音……`);
  const lines = await loadVoiceFile(index.voiceKey);
  const costumes = [...new Set(lines.map((item) => item.costumeLabel))];
  const groups = [...new Set(lines.map((item) => item.group))];
  const filtered = lines
    .filter((item) => structuredState.lineCostume === 'all' || item.costumeLabel === structuredState.lineCostume)
    .filter((item) => structuredState.lineGroup === 'all' || item.group === structuredState.lineGroup)
    .filter((item) => sMatches(structuredState.lineQuery, item.slotLabel, item.text, item.original, item.voiceId, item.group, item.costumeLabel));
  const size = 50;
  const pages = Math.max(1, Math.ceil(filtered.length / size));
  structuredState.linePage = Math.min(Math.max(1, structuredState.linePage), pages);
  const shown = filtered.slice((structuredState.linePage - 1) * size, structuredState.linePage * size);
  document.title = `${index.title}角色语音 — 魔法纪录中文资料库`;
  structuredShell(`
    <article class="structured-page voice-detail">
      <div class="reading-bar"><button type="button" data-route="voice">← 返回语音人物</button>${character ? `<button type="button" data-character-id="${sAttr(id)}">人物资料</button>` : ''}<span>${filtered.length}/${lines.length}条</span></div>
      <header class="voice-detail-head">${index.imageUrl ? `<img src="${sAttr(index.imageUrl)}" alt="${sAttr(index.title)}">` : ''}<div><p class="eyebrow">CHARACTER VOICE</p><h1>${sEscape(index.title)}</h1>${index.voiceActor ? `<p>声优 ${sEscape(index.voiceActor)}</p>` : ''}<div class="profile-badges"><span>${index.lineCount}条记录</span><span>${index.audioCount}条MP3</span><span>${index.translatedCount}条中文译文</span></div></div></header>
      <section class="toolbar voice-toolbar"><label class="search-field"><span>⌕</span><input id="voice-line-search" type="search" value="${sAttr(structuredState.lineQuery)}" placeholder="搜索台词、日文、槽位或语音ID" autocomplete="off"></label><select id="voice-costume"><option value="all">全部服装</option>${costumes.map((value) => `<option value="${sAttr(value)}" ${structuredState.lineCostume === value ? 'selected' : ''}>${sEscape(value)}</option>`).join('')}</select><select id="voice-group"><option value="all">全部分类</option>${groups.map((value) => `<option value="${sAttr(value)}" ${structuredState.lineGroup === value ? 'selected' : ''}>${sEscape(value)}</option>`).join('')}</select></section>
      <div class="voice-line-list">${shown.map((item) => `<article class="voice-line"><header><div><span>${sEscape(item.group)}</span><strong>${sEscape(item.slotLabel)}</strong><small>${sEscape(item.costumeLabel)}${item.voiceId ? ` · ${sEscape(item.voiceId)}` : ''}</small></div>${item.audioUrl ? `<audio controls preload="none" src="${sAttr(item.audioUrl)}">浏览器不支持音频播放</audio>` : '<span class="audio-missing">无音频</span>'}</header>${item.text ? `<p class="voice-translation">${sEscape(item.text)}</p>` : '<p class="voice-missing">中文译文待补充</p>'}${item.original ? `<details><summary>日文原文</summary><p lang="ja">${sEscape(item.original)}</p></details>` : ''}</article>`).join('')}</div>
      ${pages > 1 ? `<div class="pager"><button type="button" data-line-page="${structuredState.linePage - 1}" ${structuredState.linePage <= 1 ? 'disabled' : ''}>上一页</button><span>第 ${structuredState.linePage} / ${pages} 页</span><button type="button" data-line-page="${structuredState.linePage + 1}" ${structuredState.linePage >= pages ? 'disabled' : ''}>下一页</button></div>` : ''}
    </article>
  `, 'voice');
}

async function renderStructuredRoute() {
  const route = currentStructuredRoute();
  if (route.section === 'portal' && route.id === 'characters') {
    history.replaceState(null, '', '#/characters');
    return renderStructuredRoute();
  }
  if (!['characters', 'character', 'voice'].includes(route.section)) {
    delete document.documentElement.dataset.structuredView;
    patchLegacyNavigation();
    return;
  }
  if (structuredState.rendering) return;
  structuredState.rendering = true;
  try {
    structuredLoading('正在载入结构化人物与语音资料……');
    await ensureStructuredCore();
    if (route.section === 'characters') characterListPage();
    else if (route.section === 'character') {
      const item = findCharacter(route.id);
      if (item) characterDetailPage(item); else routeStructured('characters');
    } else if (route.section === 'voice' && route.id) await voiceDetailPage(route.id);
    else voiceIndexPage();
  } catch (error) {
    console.error(error);
    structuredError(error);
  } finally {
    structuredState.rendering = false;
  }
}

function saveStructuredPreference(key, value) {
  let preferences = {};
  try { preferences = JSON.parse(localStorage.getItem('magireco-reader-preferences') || '{}'); } catch {}
  preferences[key] = value;
  localStorage.setItem('magireco-reader-preferences', JSON.stringify(preferences));
  if (key === 'theme') document.documentElement.dataset.theme = value;
  if (key === 'font') document.documentElement.style.setProperty('--reader-scale', String(value));
  if (key === 'width') document.documentElement.dataset.readerWidth = value;
  structuredApp.querySelectorAll(`[data-structured-${key}]`).forEach((button) => button.setAttribute('aria-pressed', String(button.dataset[`structured${key[0].toUpperCase()}${key.slice(1)}`] === String(value))));
}

document.addEventListener('click', (event) => {
  const target = event.target instanceof Element ? event.target : null;
  if (!target) return;
  const character = target.closest('[data-character-id]');
  if (character) {
    event.preventDefault();
    event.stopImmediatePropagation();
    routeStructured(`character/${encodeURIComponent(character.dataset.characterId)}`);
    return;
  }
  const voice = target.closest('[data-voice-id]');
  if (voice) {
    event.preventDefault();
    event.stopImmediatePropagation();
    structuredState.linePage = 1;
    structuredState.lineQuery = '';
    structuredState.lineCostume = 'all';
    structuredState.lineGroup = 'all';
    routeStructured(`voice/${encodeURIComponent(voice.dataset.voiceId)}`);
    return;
  }
  const theme = target.closest('[data-structured-theme]');
  if (theme) { event.preventDefault(); event.stopImmediatePropagation(); saveStructuredPreference('theme', theme.dataset.structuredTheme); return; }
  const font = target.closest('[data-structured-font]');
  if (font) { event.preventDefault(); event.stopImmediatePropagation(); saveStructuredPreference('font', Number(font.dataset.structuredFont)); return; }
  const width = target.closest('[data-structured-width]');
  if (width) { event.preventDefault(); event.stopImmediatePropagation(); saveStructuredPreference('width', width.dataset.structuredWidth); return; }
  const characterPage = target.closest('[data-character-page]');
  if (characterPage && !characterPage.disabled) { event.preventDefault(); event.stopImmediatePropagation(); structuredState.characterPage = Number(characterPage.dataset.characterPage); characterListPage(); scrollTo({ top: 0, behavior: 'smooth' }); return; }
  const voicePage = target.closest('[data-voice-page]');
  if (voicePage && !voicePage.disabled) { event.preventDefault(); event.stopImmediatePropagation(); structuredState.voicePage = Number(voicePage.dataset.voicePage); voiceIndexPage(); scrollTo({ top: 0, behavior: 'smooth' }); return; }
  const linePage = target.closest('[data-line-page]');
  if (linePage && !linePage.disabled) { event.preventDefault(); event.stopImmediatePropagation(); structuredState.linePage = Number(linePage.dataset.linePage); void voiceDetailPage(currentStructuredRoute().id); scrollTo({ top: 0, behavior: 'smooth' }); }
}, true);

document.addEventListener('input', (event) => {
  if (!(event.target instanceof HTMLInputElement)) return;
  if (event.target.id === 'character-search') {
    structuredState.characterQuery = event.target.value;
    structuredState.characterPage = 1;
    clearTimeout(window.__structuredCharacterTimer);
    window.__structuredCharacterTimer = setTimeout(characterListPage, 150);
  } else if (event.target.id === 'voice-character-search') {
    structuredState.voiceQuery = event.target.value;
    structuredState.voicePage = 1;
    clearTimeout(window.__structuredVoiceTimer);
    window.__structuredVoiceTimer = setTimeout(voiceIndexPage, 150);
  } else if (event.target.id === 'voice-line-search') {
    structuredState.lineQuery = event.target.value;
    structuredState.linePage = 1;
    clearTimeout(window.__structuredLineTimer);
    window.__structuredLineTimer = setTimeout(() => void voiceDetailPage(currentStructuredRoute().id), 180);
  }
});

document.addEventListener('change', (event) => {
  if (!(event.target instanceof HTMLSelectElement)) return;
  if (event.target.id === 'character-kind') { structuredState.characterKind = event.target.value; structuredState.characterPage = 1; characterListPage(); }
  if (event.target.id === 'character-voice') { structuredState.characterVoice = event.target.value; structuredState.characterPage = 1; characterListPage(); }
  if (event.target.id === 'voice-costume') { structuredState.lineCostume = event.target.value; structuredState.linePage = 1; void voiceDetailPage(currentStructuredRoute().id); }
  if (event.target.id === 'voice-group') { structuredState.lineGroup = event.target.value; structuredState.linePage = 1; void voiceDetailPage(currentStructuredRoute().id); }
});

document.addEventListener('play', (event) => {
  if (!(event.target instanceof HTMLAudioElement) || !event.target.closest('.voice-line-list')) return;
  document.querySelectorAll('.voice-line-list audio').forEach((audio) => { if (audio !== event.target) audio.pause(); });
}, true);

addEventListener('hashchange', () => setTimeout(() => void renderStructuredRoute(), 0));

const structuredObserver = new MutationObserver(() => {
  patchLegacyNavigation();
  if (isStructuredRoute() && !structuredApp.querySelector('.structured-page, .character-grid, .voice-character-grid') && !structuredState.rendering) {
    queueMicrotask(() => void renderStructuredRoute());
  }
});
structuredObserver.observe(structuredApp, { childList: true, subtree: true });

patchLegacyNavigation();
setTimeout(() => void renderStructuredRoute(), 0);
