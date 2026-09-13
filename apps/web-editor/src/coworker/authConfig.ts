/** Browser identity configuration accepts only publishable / legacy anon keys. */
export function publicAuthConfig(url: string | undefined, key: string | undefined): boolean {
  if (!url || !key || !url.startsWith("https://") || key.startsWith("sb_secret_")) return false;
  try {
    const endpoint = new URL(url);
    if (endpoint.username || endpoint.password || endpoint.search || endpoint.hash || endpoint.pathname !== "/") return false;
    if (key.startsWith("sb_publishable_")) return true;
    const payload = JSON.parse(atob(key.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    return payload.role === "anon";
  } catch { return false; }
}
