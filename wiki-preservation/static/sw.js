const VERSION = 'magireco-cn-reader-v4-ui-20260728';
const SHELL = `${VERSION}-shell`;
const DATA = `${VERSION}-data`;
const STATIC = `${VERSION}-static`;
const CORE = ['/', '/index.html', '/styles.css?v=4', '/app.js?v=4', '/manifest.webmanifest', '/icon.svg', '/data/runtime-manifest.json'];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(SHELL).then((cache) => cache.addAll(CORE)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key.startsWith('magireco-cn-reader-') && ![SHELL, DATA, STATIC].includes(key)).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

async function networkFirst(request) {
  const cache = await caches.open(SHELL);
  try {
    const response = await fetch(request);
    if (response.ok) cache.put(request, response.clone());
    return response;
  } catch {
    return (await cache.match(request)) || (await cache.match('/')) || Response.error();
  }
}

async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  const refresh = fetch(request).then((response) => {
    if (response.ok) cache.put(request, response.clone());
    return response;
  }).catch(() => null);
  return cached || (await refresh) || Response.error();
}

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET' || request.headers.has('range')) return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (request.mode === 'navigate') event.respondWith(networkFirst(request));
  else if (url.pathname.startsWith('/data/') && (url.pathname.endsWith('.json') || url.pathname.endsWith('.gz'))) event.respondWith(staleWhileRevalidate(request, DATA));
  else if (/\.(?:js|css|woff2?|png|jpe?g|gif|svg|webp|ico)$/i.test(url.pathname)) event.respondWith(staleWhileRevalidate(request, STATIC));
});
