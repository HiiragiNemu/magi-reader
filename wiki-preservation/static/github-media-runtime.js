(() => {
  const RUNTIME_VERSION = '1.0';
  const CONFIG_URL = '/media-origin.json';
  const state = {
    config: null,
    githubReadable: false,
    initialized: false,
    processed: new WeakSet(),
  };

  function encodedPathSegments(pathname) {
    return String(pathname || '').split('/').filter(Boolean);
  }

  function sourceObjectPath(value) {
    let url;
    try {
      url = new URL(value, location.href);
    } catch {
      return null;
    }
    const host = url.hostname.toLowerCase();
    if (!['cdn.mfjl.wiki', 'magireco.moe', 'www.magireco.moe'].includes(host)) return null;
    const segments = encodedPathSegments(url.pathname);
    if (!segments.length) return null;

    const thumb = segments.indexOf('thumb');
    if (thumb >= 0 && segments.length >= thumb + 4) {
      const first = segments[thumb + 1];
      const second = segments[thumb + 2];
      const filename = segments[thumb + 3];
      if (/^[0-9a-f]$/i.test(first) && /^[0-9a-f]{2}$/i.test(second)) {
        return `${first}/${second}/${filename}`;
      }
    }

    const images = segments.indexOf('images');
    const offset = images >= 0 ? images + 1 : 0;
    if (
      segments.length >= offset + 3 &&
      /^[0-9a-f]$/i.test(segments[offset]) &&
      /^[0-9a-f]{2}$/i.test(segments[offset + 1])
    ) {
      return segments.slice(offset, offset + 3).join('/');
    }
    return null;
  }

  function githubRawBase(config) {
    const github = config?.github || {};
    if (github.publicBase) return String(github.publicBase).replace(/\/$/, '');
    const owner = encodeURIComponent(github.owner || '');
    const repository = encodeURIComponent(github.repository || '');
    const branch = encodeURIComponent(github.branch || 'main');
    const root = String(github.root || '').replace(/^\/+|\/+$/g, '');
    if (!owner || !repository) return '';
    return `https://raw.githubusercontent.com/${owner}/${repository}/${branch}${root ? `/${root}` : ''}`;
  }

  function githubCandidate(value) {
    if (!state.config) return null;
    const objectPath = sourceObjectPath(value);
    const base = githubRawBase(state.config);
    return objectPath && base ? `${base}/${objectPath}` : null;
  }

  function sourceAttribute(element) {
    if (element instanceof HTMLImageElement || element instanceof HTMLAudioElement || element instanceof HTMLSourceElement || element instanceof HTMLVideoElement) {
      return 'src';
    }
    return null;
  }

  function applyElement(element) {
    if (!(element instanceof Element) || state.processed.has(element)) return;
    const attribute = sourceAttribute(element);
    if (!attribute) return;
    const original = element.getAttribute(attribute);
    if (!original || /raw\.githubusercontent\.com/i.test(original)) return;
    const github = githubCandidate(original);
    if (!github) return;

    state.processed.add(element);
    element.dataset.sourceFallback = original;
    element.dataset.githubSource = github;

    if (!state.githubReadable) return;
    const fallback = () => {
      if (element.getAttribute(attribute) === github) {
        element.setAttribute(attribute, original);
        element.dataset.mediaOrigin = 'source-fallback';
      }
    };
    element.addEventListener('error', fallback, { once: true });
    element.setAttribute(attribute, github);
    element.dataset.mediaOrigin = 'github';
  }

  function applyLink(anchor) {
    if (!(anchor instanceof HTMLAnchorElement) || state.processed.has(anchor)) return;
    const original = anchor.getAttribute('href');
    if (!original) return;
    const github = githubCandidate(original);
    if (!github) return;
    state.processed.add(anchor);
    anchor.dataset.sourceFallback = original;
    anchor.dataset.githubSource = github;
    if (state.githubReadable) {
      anchor.href = github;
      anchor.dataset.mediaOrigin = 'github';
    }
  }

  function applyTree(root = document) {
    if (root instanceof HTMLImageElement || root instanceof HTMLAudioElement || root instanceof HTMLSourceElement || root instanceof HTMLVideoElement) applyElement(root);
    if (root instanceof HTMLAnchorElement) applyLink(root);
    if (!(root instanceof Document || root instanceof DocumentFragment || root instanceof Element)) return;
    root.querySelectorAll('img[src],audio[src],video[src],source[src]').forEach(applyElement);
    root.querySelectorAll('a[href]').forEach(applyLink);
    updateStatusBadge();
  }

  function statusText() {
    const github = state.config?.github || {};
    const repository = [github.owner, github.repository].filter(Boolean).join('/');
    if (state.githubReadable) return `媒体原件：GitHub · ${repository}@${github.branch || 'main'}`;
    return `媒体原件已保存于GitHub${repository ? `（${repository}）` : ''}；公共读取层未开放时临时使用历史源地址。`;
  }

  function updateStatusBadge() {
    const targets = [
      document.querySelector('.media-page .section-copy'),
      document.querySelector('.about-page section'),
    ].filter(Boolean);
    for (const target of targets) {
      let badge = target.querySelector('.media-origin-status');
      if (!badge) {
        badge = document.createElement('span');
        badge.className = 'media-origin-status';
        target.appendChild(badge);
      }
      badge.textContent = statusText();
      badge.dataset.available = String(state.githubReadable);
    }
  }

  function installStyle() {
    if (document.querySelector('#github-media-runtime-style')) return;
    const style = document.createElement('style');
    style.id = 'github-media-runtime-style';
    style.textContent = `
      .media-origin-status{display:block;margin-top:.75rem;padding:.55rem .75rem;border:1px solid var(--line);border-radius:.65rem;color:var(--muted);font-size:.76rem;line-height:1.55;background:color-mix(in srgb,var(--paper-2) 88%,transparent)}
      .media-origin-status[data-available="true"]{border-color:color-mix(in srgb,var(--plum) 38%,var(--line));color:var(--plum)}
    `;
    document.head.appendChild(style);
  }

  async function probeGithub(config) {
    const github = config?.github || {};
    const owner = encodeURIComponent(github.owner || '');
    const repository = encodeURIComponent(github.repository || '');
    const branch = encodeURIComponent(github.branch || 'main');
    const probePath = String(github.probePath || 'README.md').replace(/^\/+/, '').split('/').map(encodeURIComponent).join('/');
    if (!owner || !repository) return false;
    const url = github.probeUrl || `https://raw.githubusercontent.com/${owner}/${repository}/${branch}/${probePath}`;
    try {
      const response = await fetch(url, { method: 'HEAD', mode: 'cors', cache: 'no-store' });
      return response.ok;
    } catch {
      return false;
    }
  }

  async function initialize() {
    installStyle();
    try {
      const response = await fetch(`${CONFIG_URL}?v=${RUNTIME_VERSION}`, { cache: 'no-store' });
      if (!response.ok) throw new Error(`media origin config HTTP ${response.status}`);
      state.config = await response.json();
      state.githubReadable = await probeGithub(state.config);
    } catch (error) {
      console.warn('[media-origin] initialization failed', error);
      state.config = { strategy: 'source-fallback', sourceFallback: true, r2Storage: false };
      state.githubReadable = false;
    }
    state.initialized = true;
    document.documentElement.dataset.mediaStorage = state.githubReadable ? 'github' : 'github-private-source-fallback';
    applyTree(document);
    window.dispatchEvent(new CustomEvent('magireco-media-origin-ready', { detail: status() }));
  }

  function status() {
    return {
      runtimeVersion: RUNTIME_VERSION,
      initialized: state.initialized,
      githubReadable: state.githubReadable,
      storage: 'github',
      r2Storage: false,
      config: state.config,
    };
  }

  const observer = new MutationObserver((records) => {
    if (!state.initialized) return;
    for (const record of records) {
      for (const node of record.addedNodes) applyTree(node);
    }
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });

  window.MagirecoMediaOrigin = {
    status,
    candidate: githubCandidate,
    refresh: async () => {
      state.processed = new WeakSet();
      await initialize();
      return status();
    },
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize, { once: true });
  else void initialize();
})();
