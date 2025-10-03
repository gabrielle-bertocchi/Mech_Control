const CACHE_NAME = 'mechcontrol-cache-v1';
const urlsToCache = [
    '/', // Rota de login
    '/home',
    '/static/css/main.css', // Seu CSS principal
    '/static/icons/icon-192x192.png',
    // Adicione outros arquivos estáticos críticos, como fontes ou logos
];

// Instalação: Armazena em cache os recursos estáticos
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('Opened cache');
        return cache.addAll(urlsToCache);
      })
  );
});

// Fetch: Serve o conteúdo do cache, se disponível
self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        // Retorna recurso do cache se existir
        if (response) {
          return response;
        }
        // Caso contrário, busca na rede
        return fetch(event.request);
      })
  );
});

// Ativação: Limpa caches antigos
self.addEventListener('activate', event => {
  const cacheWhitelist = [CACHE_NAME];
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheWhitelist.indexOf(cacheName) === -1) {
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
});