// Escuta e exibe notificações mesmo com a página fechada
self.addEventListener('push', function(event) {
    let data = { title: "🚨 ALERTA - BioGlow", body: "Nova emergência registrada!" };

    if (event.data) {
        try {
            data = event.data.json();
        } catch (e) {
            data.body = event.data.text();
        }
    }

    const options = {
        body: data.body,
        icon: '/static/logotipo.png',
        badge: '/static/logotipo.png',
        vibrate: [200, 100, 200]
    };

    event.waitUntil(
        self.registration.showNotification(data.title, options)
    );
});