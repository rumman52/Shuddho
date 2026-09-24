import { CoworkerClient, WorkspaceError } from "./client";

const storageKey = "shuddho:linkedin-connect";
const isLinkedInCallbackRoute =
  typeof window !== "undefined"
  && window.location.pathname === "/oauth/linkedin/callback";

const callback = isLinkedInCallbackRoute
  ? new URLSearchParams(window.location.search)
  : null;

if (isLinkedInCallbackRoute) {
  window.history.replaceState(null, "", "/");
}

let completion: {
  account: string;
  promise: Promise<string | null>;
} | null = null;

export function hasPendingLinkedInCallback(): boolean {
  return callback !== null && completion === null;
}

export function linkedInAuthorizationURL(
  value: string,
  state: string,
  origin: string,
): string {
  const url = new URL(value);
  const redirect = new URL(url.searchParams.get("redirect_uri") ?? "");
  if (
    url.protocol !== "https:"
    || url.hostname !== "www.linkedin.com"
    || url.pathname !== "/oauth/v2/authorization"
    || url.username
    || url.password
    || url.hash
    || url.searchParams.get("state") !== state
    || !/^[A-Za-z0-9_-]{43}$/.test(state)
    || redirect.origin !== origin
    || redirect.pathname !== "/oauth/linkedin/callback"
    || redirect.search
    || redirect.hash
  ) {
    throw new WorkspaceError(
      "The LinkedIn connection redirect is not configured for this site.",
    );
  }
  return url.href;
}

export async function beginLinkedInConnection(
  client: CoworkerClient,
  account: string,
) {
  const result = await client.connectLinkedIn();
  const url = linkedInAuthorizationURL(
    result.authorization_url,
    result.state,
    window.location.origin,
  );
  try {
    sessionStorage.setItem(
      storageKey,
      JSON.stringify({ state: result.state, account }),
    );
  } catch {
    throw new WorkspaceError(
      "Allow session storage in this tab to connect LinkedIn securely.",
    );
  }
  window.location.assign(url);
}

export function finishLinkedInCallback(
  client: CoworkerClient,
  account: string,
): Promise<string | null> {
  if (!callback) return Promise.resolve(null);
  if (completion) {
    return completion.account === account
      ? completion.promise
      : Promise.resolve(null);
  }
  const promise = (async () => {
    let saved;
    try {
      saved = JSON.parse(sessionStorage.getItem(storageKey) ?? "null");
      sessionStorage.removeItem(storageKey);
    } catch {
      throw new WorkspaceError(
        "Start the LinkedIn connection again in this tab.",
      );
    }
    if (
      !saved
      || saved.account !== account
      || saved.state !== callback.get("state")
    ) {
      throw new WorkspaceError(
        "This LinkedIn connection belongs to another session. "
        + "Start again from your workspace.",
      );
    }
    if (callback.has("error") || !callback.get("code")) {
      throw new WorkspaceError(
        "LinkedIn connection was cancelled. You can connect again when ready.",
      );
    }
    await client.finishLinkedIn(
      callback.get("code")!,
      saved.state,
    );
    callback.delete("code");
    return "Your LinkedIn member account is connected for approved publishing.";
  })();
  completion = { account, promise };
  return promise;
}
