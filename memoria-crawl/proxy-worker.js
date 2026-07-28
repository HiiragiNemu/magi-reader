const PROXY_TOKEN = '__PROXY_TOKEN__';
const ALLOWED_HOSTS = new Set(['magireco.moe', 'www.magireco.moe']);

function json(value, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store',
    },
  });
}

export default {
  async fetch(request) {
    const incoming = new URL(request.url);
    if (incoming.pathname === '/health') return json({ status: 'ok', scope: 'magireco-rendered-pages-only' });
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
    const upstream = await fetch(target.toString(), {
      method: 'GET',
      redirect: 'follow',
      headers: {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/138.0 Safari/537.36 MagirecoChinesePreservationReader/3.0',
        'accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
        'accept-language': 'zh-CN,zh;q=0.9,ja;q=0.7,en;q=0.4',
      },
      cf: {
        cacheTtl: 0,
        cacheEverything: false,
      },
    });

    const headers = new Headers();
    headers.set('content-type', upstream.headers.get('content-type') || 'application/octet-stream');
    headers.set('cache-control', 'no-store');
    headers.set('x-magireco-source-url', upstream.url || target.toString());
    headers.set('x-magireco-source-status', String(upstream.status));
    return new Response(upstream.body, { status: upstream.status, headers });
  },
};
