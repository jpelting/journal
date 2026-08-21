self.addEventListener('install', function (event) {
    self.skipWaiting();
});

self.addEventListener('activate', function (event) {
    event.waitUntil(self.clients.claim());
});

// No offline caching - just here so the browser considers the app installable.
self.addEventListener('fetch', function () {});

self.addEventListener('push', function (event) {
    var data = {};
    try {
        data = event.data ? event.data.json() : {};
    } catch (e) {
        data = {};
    }
    var title = data.title || 'The Wax Tablet';
    var body = data.body || '';
    event.waitUntil(
        self.registration.showNotification(title, {
            body: body,
            icon: '/static/entries/icons/icon-192.png',
            badge: '/static/entries/icons/icon-192.png',
        })
    );
});

self.addEventListener('notificationclick', function (event) {
    event.notification.close();
    event.waitUntil(self.clients.openWindow('/'));
});
