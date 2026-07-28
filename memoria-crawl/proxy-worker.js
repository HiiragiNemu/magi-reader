const PROXY_TOKEN = '__PROXY_TOKEN__';
const ALLOWED_HOSTS = new Set(['magireco.moe', 'www.magireco.moe']);
const USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/138.0 Safari/537.36 MagirecoChinesePreservationReader/3.0';
const RETRYABLE = new Set([408, 425, 429, 500, 502, 503, 504, 522, 524]);

function json(value, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store',
    },
  });
}

function allowed(target) {
  if (target.protocol !== 'https:' || !ALLOWED_HOSTS.has(target.hostname)) return false;
  const decoded = decodeURIComponent(target.pathname);
  return decoded.startsWith('/wiki/记忆结晶/') || decoded === '/wiki/记忆结晶' || decoded === '/wiki/首页';
}

async function sourceFetch(target) {
  let last = null;
  for (let attempt = 1; attempt <= 5; attempt += 1) {
    last = await fetch(target.toString(), {
      method: 'GET',
      redirect: 'follow',
      headers: {
        'user-agent': USER_AGENT,
        'accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
        'accept-language': 'zh-CN,zh;q=0.9,ja;q=0.7,en;q=0.4',
        'referer': 'https://magireco.moe/wiki/记忆结晶',
      },
      cf: {
        cacheTtl: 0,
        cacheEverything: false,
      },
    });
    if (!RETRYABLE.has(last.status)) break;
    if (attempt < 5) await new Promise((resolve) => setTimeout(resolve, 1500 * attempt));
  }
  return last;
}

export default {
  async fetch(request) {
    const incoming = new URL(request.url);
    if (incoming.pathname === '/health') {
      return json({ status: 'ok', scope: 'ordinary-memoria-articles-only', retries: 5, backoff: '1.5s-linear' });
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
    if (!allowed(target)) return json({ error: 'target not allow-listed' }, 403);

    target.hash = '';
    const upstream = await sourceFetch(target);
    const headers = new Headers();
    headers.set('content-type', upstream.headers.get('content-type') || 'application/octet-stream');
    headers.set('cache-control', 'no-store');
    headers.set('x-magireco-source-url', upstream.url || target.toString());
    headers.set('x-magireco-source-status', String(upstream.status));
    headers.set('x-magireco-proxy-scope', 'ordinary-memoria-articles-only');
    return new Response(upstream.body, { status: upstream.status, headers });
  },
};
