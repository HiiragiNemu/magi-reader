const PROXY_TOKEN = '__PROXY_TOKEN__';
const ALLOWED_HOSTS = new Set(['magireco.moe', 'www.magireco.moe']);
const HOME = 'https://magireco.moe/wiki/%E9%A6%96%E9%A1%B5';
const ORDINARY = 'https://magireco.moe/wiki/%E4%B8%83%E6%B5%B7%E5%85%AB%E5%8D%83%E4%BB%A3';
const USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/138.0 Safari/537.36 MagirecoChinesePreservationReader/3.0';

function json(value, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store',
    },
  });
}

function sourceHeaders({ cookie = '', referer = HOME } = {}) {
  const headers = new Headers({
    'user-agent': USER_AGENT,
    'accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
    'accept-language': 'zh-CN,zh;q=0.9,ja;q=0.7,en;q=0.4',
    'referer': referer,
    'cache-control': 'no-cache, no-store, max-age=0',
    'pragma': 'no-cache',
  });
  if (cookie) headers.set('cookie', cookie);
  return headers;
}

async function sourceFetch(url, options = {}) {
  return fetch(url, {
    method: 'GET',
    redirect: 'follow',
    headers: sourceHeaders(options),
    cf: {
      cacheTtl: 0,
      cacheEverything: false,
      cacheKey: `${url}${url.includes('?') ? '&' : '?'}_cf_bypass=${crypto.randomUUID()}`,
    },
  });
}

function cookieFrom(response) {
  let values = [];
  if (typeof response.headers.getSetCookie === 'function') {
    values = response.headers.getSetCookie();
  } else {
    const single = response.headers.get('set-cookie');
    if (single) values = [single];
  }
  return values
    .map((value) => value.split(';', 1)[0].trim())
    .filter(Boolean)
    .join('; ');
}

function uncached(url, label) {
  const value = new URL(url);
  value.searchParams.set('_preservation_warm', `${label}-${Date.now()}-${crypto.randomUUID()}`);
  return value.toString();
}

async function warmAndFetch(target) {
  const original = target.toString();
  if (original.startsWith(HOME)) return sourceFetch(uncached(HOME, 'home'));

  let last = null;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    const home = await sourceFetch(uncached(HOME, `home-${attempt}`));
    let cookie = cookieFrom(home);
    const ordinary = await sourceFetch(uncached(ORDINARY, `ordinary-${attempt}`), {
      cookie,
      referer: home.url || HOME,
    });
    const ordinaryCookie = cookieFrom(ordinary);
    if (ordinaryCookie) cookie = [cookie, ordinaryCookie].filter(Boolean).join('; ');

    last = await sourceFetch(original, {
      cookie,
      referer: ordinary.url || ORDINARY,
    });
    if (![403, 408, 425, 429, 500, 502, 503, 504, 522, 524].includes(last.status)) {
      return { response: last, homeStatus: home.status, ordinaryStatus: ordinary.status, cookieCount: cookie ? cookie.split(';').length : 0 };
    }
  }
  return { response: last, homeStatus: null, ordinaryStatus: null, cookieCount: 0 };
}

export default {
  async fetch(request) {
    const incoming = new URL(request.url);
    if (incoming.pathname === '/health') {
      return json({ status: 'ok', scope: 'magireco-rendered-pages-only', sessionWarmup: 'uncached-home-and-character' });
    }
    if (request.headers.get('x-magireco-proxy-token') !== PROXY_TOKEN) return json({ error: 'forbidden' }, 403);

    const value = incoming.searchParams.get('url');
    if (!value) return json({ error: 'missing url' }, 400);

    let target;
    try {
      target = new URL(value);
    } catch {
      return json({ error: 'invalid url' }, 400);
    }
    if (target.protocol !== 'https:' || !ALLOWED_HOSTS.has(target.hostname)) return json({ error: 'host not allowed' }, 403);
    if (!(target.pathname.startsWith('/wiki/') || target.pathname === '/index.php' || target.pathname === '/')) {
      return json({ error: 'path not allowed' }, 403);
    }

    target.hash = '';
    const result = await warmAndFetch(target);
    const upstream = result.response;
    const headers = new Headers();
    headers.set('content-type', upstream.headers.get('content-type') || 'application/octet-stream');
    headers.set('cache-control', 'no-store');
    headers.set('x-magireco-source-url', upstream.url || target.toString());
    headers.set('x-magireco-source-status', String(upstream.status));
    headers.set('x-magireco-home-status', String(result.homeStatus ?? 'unknown'));
    headers.set('x-magireco-ordinary-status', String(result.ordinaryStatus ?? 'unknown'));
    headers.set('x-magireco-cookie-count', String(result.cookieCount));
    headers.set('x-magireco-session-warmup', 'uncached-home-and-character');
    return new Response(upstream.body, { status: upstream.status, headers });
  },
};
