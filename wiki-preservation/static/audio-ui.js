const audioState = {
  manifest: null,
  index: null,
  query: '',
  costume: 'all',
  page: 1,
  pageSize: 36,
  rendering: false,
  cache: new Map(),
};

const audioApp = document.querySelector('#app');

function audioEscape(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function audioAttr(value) {
  return audioEscape(value).replaceAll('`', '&#96;');
}

function audioNormalize(value) {
  return String(value ?? '')
    .normalize('NFKC')
    .toLocaleLowerCase('zh-CN')
    .replace(/[\s\-_·・/（）()【】\[\]《》]+/g, ' ')
    .trim();
}

function audioRoute() {
  const raw = location.hash.replace(/^#\/?/, '');
  if (raw === 'audio') return { active: true, id: '' };
  if (!raw.startsWith('audio/')) return { active: false, id: '' };
  let id = raw.slice('audio/'.length);
  try { id = decodeURIComponent(id); } catch {}
  return { active: true, id };
}

function setAudioRoute(id = '') {
  const next = id ? `#/audio/${encodeURIComponent(id)}` : '#/audio';
  if (location.hash === next) scheduleAudioRender();
  else location.hash = next;
  scrollTo({ top: 0, behavior: 'smooth' });
}

async function audioJson(path) {
  if (audioState.cache.has(path)) return audioState.cache.get(path);
  const response = await fetch(`/data/voice-audio/${path}`, { cache: 'force-cache' });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  const value = await response.json();
  audioState.cache.set(path, value);
  return value;
}

async function ensureAudioIndex() {
  if (audioState.index && audioState.manifest) return;
  [audioState.index, audioState.manifest] = await Promise.all([
    audioJson('character-index.json'),
    audioJson('manifest.json'),
  ]);
}

function ensureAudioNavigation() {
  const nav = document.querySelector('.site-header nav');
  if (!nav) return;
  let button = nav.querySelector('[data-audio-nav]');
  if (!button) {
    button = document.createElement('button');
    button.type = 'button';
    button.dataset.audioNav = 'true';
    button.textContent = '语音';
    button.title = '角色语音档案';
    nav.insertBefore(button, nav.querySelector('[data-route="media"]') || null);
  }
  const active = audioRoute().active;
  button.classList.toggle('active', active);
  if (active) {
    nav.querySelectorAll('button.active').forEach((item) => {
      if (item !== button) item.classList.remove('active');
    });
  }
}

function audioSourceMarkup(item) {
  const sources = Array.isArray(item.sources) ? item.sources : [];
  return sources
    .map((source) => `<source src="${audioAttr(source.url)}" type="${audioAttr(source.type || '')}" data-kind="${audioAttr(source.kind || '')}">`)
    .join('');
}

function sourceLabels(item) {
  return (item.sources || []).map((source) => {
    const labels = { github: 'GitHub', 'cn-cdn': '中文CDN', fandom: 'Fandom' };
    return labels[source.kind] || source.kind;
  }).join(' → ');
}

function attachAudioFallbacks(root) {
  root.querySelectorAll('audio[data-voice-player]').forEach((player) => {
    const sources = [...player.querySelectorAll('source')].map((source) => ({
      url: source.src,
      type: source.type,
      kind: source.dataset.kind || 'unknown',
    }));
    if (!sources.length) return;
    let index = 0;
    const status = player.closest('.voice-audio-card')?.querySelector('[data-source-status]');
    const load = (next) => {
      index = next;
      if (!sources[index]) {
        if (status) status.textContent = '没有可播放来源';
        return;
      }
      player.src = sources[index].url;
      if (status) status.textContent = `准备：${sources[index].kind}`;
      player.load();
    };
    player.replaceChildren();
    player.addEventListener('error', () => {
      if (index + 1 < sources.length) load(index + 1);
      else if (status) status.textContent = '所有来源均不可用';
    });
    player.addEventListener('loadedmetadata', () => {
      if (status) status.textContent = `当前来源：${sources[index].kind}`;
    });
    player.addEventListener('playing', () => {
      document.querySelectorAll('audio[data-voice-player]').forEach((other) => {
        if (other !== player && !other.paused) other.pause();
      });
    });
    load(0);
  });
}

function audioShell(content, selectedId = '') {
  const main = document.querySelector('.site-main');
  if (!main) return false;
  main.innerHTML = `<section class="voice-audio-page" data-audio-route="${audioAttr(selectedId || 'index')}">${content}</section>`;
  ensureAudioNavigation();
  attachAudioFallbacks(main);
  document.title = `${selectedId ? '角色语音' : '语音档案'} — 魔法纪录中文资料库`;
  return true;
}

function audioLoading(label) {
  return audioShell(`<div class="state-panel"><div class="spinner"></div><strong>${audioEscape(label)}</strong></div>`);
}

function audioError(error) {
  const message = error instanceof Error ? error.message : String(error);
  return audioShell(`<div class="state-panel error"><strong>语音档案读取失败</strong><pre>${audioEscape(message)}</pre><button type="button" data-audio-back>返回语音索引</button></div>`);
}

async function renderAudioIndex() {
  await ensureAudioIndex();
  const query = audioNormalize(audioState.query);
  const filtered = audioState.index.filter((item) => {
    const haystack = audioNormalize([item.name, item.charaId, item.costumes].flat().join(' '));
    return !query || query.split(' ').every((term) => haystack.includes(term));
  });
  const pages = Math.max(1, Math.ceil(filtered.length / audioState.pageSize));
  audioState.page = Math.min(Math.max(1, audioState.page), pages);
  const shown = filtered.slice((audioState.page - 1) * audioState.pageSize, audioState.page * audioState.pageSize);
  const m = audioState.manifest;
  audioShell(`
    <header class="voice-audio-hero">
      <p class="eyebrow">VOICE AUDIO ARCHIVE</p>
      <div class="section-heading"><div><h1>角色语音</h1><p>按角色、服装和槽位浏览。播放器依次尝试GitHub、中文Wiki CDN与Fandom音频。</p></div><span>${Number(m.voiceFiles || 0).toLocaleString('zh-CN')} 条</span></div>
      <div class="voice-audio-stats">
        <div><strong>${Number(m.characters || 0).toLocaleString('zh-CN')}</strong><span>角色ID</span></div>
        <div><strong>${Number(m.quotePagesProcessed || 0).toLocaleString('zh-CN')}</strong><span>语音页面</span></div>
        <div><strong>${Number(m.fandomUrls || 0).toLocaleString('zh-CN')}</strong><span>OGG回退</span></div>
      </div>
    </header>
    <div class="toolbar voice-audio-toolbar"><label class="search-field"><span>⌕</span><input id="audio-character-search" type="search" value="${audioAttr(audioState.query)}" placeholder="搜索角色名或角色ID" autocomplete="off"></label></div>
    <div class="voice-character-grid">
      ${shown.map((item) => `<button type="button" class="voice-character-card" data-audio-character="${audioAttr(item.charaId)}"><span><strong>${audioEscape(item.name)}</strong><small>ID ${audioEscape(item.charaId)} · ${item.costumes.length} 套服装</small></span><b>${Number(item.total).toLocaleString('zh-CN')}</b></button>`).join('')}
    </div>
    ${pages > 1 ? `<div class="pager"><button type="button" data-audio-page="${audioState.page - 1}" ${audioState.page <= 1 ? 'disabled' : ''}>上一页</button><span>第 ${audioState.page} / ${pages} 页</span><button type="button" data-audio-page="${audioState.page + 1}" ${audioState.page >= pages ? 'disabled' : ''}>下一页</button></div>` : ''}
    <p class="voice-source-note">GitHub主源要求媒体仓库可匿名读取；当前私有状态会自动切换到后续公共来源，不使用R2保存音频。</p>
  `);
}

async function renderAudioCharacter(charaId) {
  await ensureAudioIndex();
  const info = audioState.index.find((item) => item.charaId === charaId);
  if (!info) throw new Error(`找不到角色语音索引：${charaId}`);
  const records = await audioJson(`characters/${encodeURIComponent(charaId)}.json`);
  const costumes = [...new Set(records.map((item) => item.costumeId).filter(Boolean))].sort();
  if (audioState.costume !== 'all' && !costumes.includes(audioState.costume)) audioState.costume = 'all';
  const query = audioNormalize(audioState.query);
  const filtered = records.filter((item) => {
    if (audioState.costume !== 'all' && item.costumeId !== audioState.costume) return false;
    const haystack = audioNormalize([item.label, item.mp3Filename, item.slot, item.costumeId].join(' '));
    return !query || query.split(' ').every((term) => haystack.includes(term));
  });
  const pageSize = 40;
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  audioState.page = Math.min(Math.max(1, audioState.page), pages);
  const shown = filtered.slice((audioState.page - 1) * pageSize, audioState.page * pageSize);
  audioShell(`
    <button type="button" class="back-button" data-audio-back>← 返回角色语音</button>
    <header class="voice-audio-detail-head"><p class="eyebrow">CHARACTER VOICE</p><div class="section-heading"><div><h1>${audioEscape(info.name)}</h1><p>ID ${audioEscape(charaId)} · ${records.length.toLocaleString('zh-CN')} 条 · ${costumes.length} 套服装</p></div><span>${filtered.length.toLocaleString('zh-CN')} 条当前结果</span></div></header>
    <div class="toolbar voice-audio-toolbar detail"><label class="search-field"><span>⌕</span><input id="audio-line-search" type="search" value="${audioAttr(audioState.query)}" placeholder="搜索台词、槽位或文件名" autocomplete="off"></label><select id="audio-costume"><option value="all">全部服装</option>${costumes.map((value) => `<option value="${audioAttr(value)}" ${audioState.costume === value ? 'selected' : ''}>服装 ${audioEscape(value)}</option>`).join('')}</select></div>
    <div class="voice-audio-list">
      ${shown.map((item) => `<article class="voice-audio-card"><div class="voice-audio-copy"><div class="voice-audio-meta"><span>服装 ${audioEscape(item.costumeId || '—')}</span><span>槽位 ${audioEscape(item.slot || '—')}</span><code>${audioEscape(item.mp3Filename)}</code></div><p>${audioEscape(item.label || item.mp3Filename)}</p><small>${audioEscape(sourceLabels(item))}</small></div><div class="voice-player-wrap"><audio controls preload="none" data-voice-player aria-label="${audioAttr(item.label || item.mp3Filename)}">${audioSourceMarkup(item)}</audio><span data-source-status>等待播放</span></div></article>`).join('')}
    </div>
    ${pages > 1 ? `<div class="pager"><button type="button" data-audio-page="${audioState.page - 1}" ${audioState.page <= 1 ? 'disabled' : ''}>上一页</button><span>第 ${audioState.page} / ${pages} 页</span><button type="button" data-audio-page="${audioState.page + 1}" ${audioState.page >= pages ? 'disabled' : ''}>下一页</button></div>` : ''}
  `, charaId);
}

async function renderAudioRoute() {
  const route = audioRoute();
  if (!route.active || audioState.rendering) {
    ensureAudioNavigation();
    return;
  }
  const main = document.querySelector('.site-main');
  const current = main?.querySelector('.voice-audio-page')?.dataset.audioRoute || '';
  const expected = route.id || 'index';
  if (current === expected && main.querySelector('.voice-audio-list, .voice-character-grid')) {
    ensureAudioNavigation();
    return;
  }
  audioState.rendering = true;
  try {
    audioLoading(route.id ? '正在载入角色语音……' : '正在载入语音索引……');
    if (route.id) await renderAudioCharacter(route.id);
    else await renderAudioIndex();
  } catch (error) {
    console.error(error);
    audioError(error);
  } finally {
    audioState.rendering = false;
  }
}

let audioRenderQueued = false;
function scheduleAudioRender() {
  if (audioRenderQueued) return;
  audioRenderQueued = true;
  queueMicrotask(() => {
    audioRenderQueued = false;
    renderAudioRoute();
  });
}

document.addEventListener('click', (event) => {
  const target = event.target instanceof Element ? event.target : null;
  if (!target) return;
  if (target.closest('[data-audio-nav]')) { setAudioRoute(); return; }
  const character = target.closest('[data-audio-character]');
  if (character) { audioState.query = ''; audioState.costume = 'all'; audioState.page = 1; setAudioRoute(character.dataset.audioCharacter); return; }
  if (target.closest('[data-audio-back]')) { audioState.query = ''; audioState.costume = 'all'; audioState.page = 1; setAudioRoute(); return; }
  const page = target.closest('[data-audio-page]');
  if (page && !page.disabled) { audioState.page = Number(page.dataset.audioPage); renderAudioRoute(); return; }
}, true);

document.addEventListener('input', (event) => {
  if (!['audio-character-search', 'audio-line-search'].includes(event.target.id)) return;
  audioState.query = event.target.value;
  audioState.page = 1;
  clearTimeout(window.__voiceAudioTimer);
  window.__voiceAudioTimer = setTimeout(renderAudioRoute, 180);
});

document.addEventListener('change', (event) => {
  if (event.target.id !== 'audio-costume') return;
  audioState.costume = event.target.value;
  audioState.page = 1;
  renderAudioRoute();
});

addEventListener('hashchange', scheduleAudioRender);
new MutationObserver(scheduleAudioRender).observe(audioApp, { childList: true, subtree: true });
scheduleAudioRender();
