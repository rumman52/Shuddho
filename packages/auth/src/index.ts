import { createClient, type SupabaseClient } from "@supabase/supabase-js";

/** Accept only a public Supabase publishable key or a legacy anon JWT. */
export function publicAuthConfig(url: string | undefined, key: string | undefined): boolean {
  if (!url || !key || !url.startsWith("https://") || key.startsWith("sb_secret_")) return false;
  try {
    const endpoint = new URL(url);
    if (endpoint.username || endpoint.password || endpoint.search || endpoint.hash || endpoint.pathname !== "/") return false;
    if (key.startsWith("sb_publishable_")) return true;
    const payload = JSON.parse(atob(key.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    return payload.role === "anon";
  } catch {
    return false;
  }
}

const clients = new Map<string, SupabaseClient>();

/**
 * One browser client per public project/key pair. Keep Supabase's default
 * storage key so existing Coworker sessions remain available to both apps
 * when they are served from the same origin.
 */
export function getRukhAuthClient(url: string | undefined, key: string | undefined): SupabaseClient | null {
  if (!publicAuthConfig(url, key)) return null;
  const cacheKey = `${url}\u0000${key}`;
  const existing = clients.get(cacheKey);
  if (existing) return existing;
  const client = createClient(url!, key!, {
    auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
  });
  clients.set(cacheKey, client);
  return client;
}
