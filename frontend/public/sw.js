/* 极简 Service Worker：只缓存带内容哈希的静态资源（不可变），API 与 HTML 一律走网络。
   这样「添加到主屏幕」在安卓上可用，又不会把升级后的新版本缓存成旧版。 */
const CACHE = 'ss-static-v1';

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/')) return;
  // 带内容哈希的构建产物才进缓存（文件名一变就是新条目，永不过期问题不存在）
  const immutable =
    /^\/assets\/.+\.[0-9a-f]{8}\./.test(url.pathname) ||
    /^\/(icon-192|icon-512|apple-touch-icon|favicon-32)\.png$/.test(url.pathname) ||
    /^\/manifest\.webmanifest$/.test(url.pathname);
  if (!immutable) return;

  event.respondWith(
    caches.open(CACHE).then(async (cache) => {
      const hit = await cache.match(req);
      if (hit) return hit;
      const resp = await fetch(req);
      if (resp && resp.ok) cache.put(req, resp.clone());
      return resp;
    }),
  );
});
