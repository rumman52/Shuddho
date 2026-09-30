self.addEventListener("push", event => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch { data = {}; }
  const title = typeof data.title === "string" && data.title ? data.title : "Shuddho";
  const body = typeof data.body === "string" && data.body ? data.body : "You have a new Shuddho update.";
  let path = "/";
  if (typeof data.url === "string") {
    try {
      const target = new URL(data.url, self.location.origin);
      if (target.origin === self.location.origin) path = target.pathname + target.search + target.hash;
    } catch { path = "/"; }
  }
  event.waitUntil(self.registration.showNotification(title, {
    body,
    tag: typeof data.notification_id === "string" ? "shuddho-" + data.notification_id : "shuddho-update",
    renotify: false,
    data: { path },
  }));
});

self.addEventListener("notificationclick", event => {
  event.notification.close();
  const path = event.notification.data && typeof event.notification.data.path === "string"
    ? event.notification.data.path : "/";
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const client of windows) {
      if ("focus" in client) {
        if ("navigate" in client) await client.navigate(path);
        return client.focus();
      }
    }
    return self.clients.openWindow(path);
  })());
});
