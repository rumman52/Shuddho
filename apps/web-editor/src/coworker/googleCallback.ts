import { CoworkerClient, WorkspaceError } from "./client";

const storageKey = "shuddho:google-connect";
// Capture/strip Google's code before Supabase's detectSessionInUrl can treat
// it as a Shuddho sign-in code. No code or token is persisted by this module.
const isGoogleCallbackRoute = typeof window !== "undefined" && window.location.pathname === "/oauth/google/callback";
const callback = isGoogleCallbackRoute ? new URLSearchParams(window.location.search) : null;
if (isGoogleCallbackRoute) window.history.replaceState(null, "", "/");
let completion: { account: string; promise: Promise<string | null> } | null = null;

export function hasPendingGoogleCallback(): boolean {
  return callback !== null && completion === null;
}

export function googleAuthorizationURL(value: string, state: string, origin: string): string {
  const url = new URL(value);
  const redirect = new URL(url.searchParams.get("redirect_uri") ?? "");
  if (url.origin !== "https://accounts.google.com" || url.pathname !== "/o/oauth2/v2/auth" || url.username || url.password ||
      url.hash || url.searchParams.get("state") !== state || !/^[A-Za-z0-9_-]{43}$/.test(state) ||
      redirect.origin !== origin || redirect.pathname !== "/oauth/google/callback" || redirect.search || redirect.hash) {
    throw new WorkspaceError("The Google connection redirect is not configured for this site.");
  }
  return url.href;
}

export async function beginGoogleConnection(client: CoworkerClient, account: string, capability: "email" | "calendar" | "drive") {
  const result = await client.connectGoogle(capability);
  const url = googleAuthorizationURL(result.authorization_url, result.state, window.location.origin);
  try { sessionStorage.setItem(storageKey, JSON.stringify({ state: result.state, account })); }
  catch { throw new WorkspaceError("Allow session storage in this tab to connect Google securely."); }
  window.location.assign(url);
}

export function finishGoogleCallback(client: CoworkerClient, account: string): Promise<string | null> {
  if (!callback) return Promise.resolve(null);
  if (completion) return completion.account === account ? completion.promise : Promise.resolve(null);
  const promise = (async () => {
    let saved;
    try { saved = JSON.parse(sessionStorage.getItem(storageKey) ?? "null"); sessionStorage.removeItem(storageKey); }
    catch { throw new WorkspaceError("Start the Google connection again in this tab."); }
    if (!saved || saved.account !== account || saved.state !== callback.get("state")) {
      throw new WorkspaceError("This connection belongs to another session. Start again from your workspace.");
    }
    if (callback.has("error") || !callback.get("code")) throw new WorkspaceError("Google connection was cancelled. You can connect again when ready.");
    const connection = await client.finishGoogle(callback.get("code")!, saved.state);
    callback.delete("code");
    return `${connection.email} is connected for ${connection.capability}.`;
  })();
  completion = { account, promise };
  return promise;
}
