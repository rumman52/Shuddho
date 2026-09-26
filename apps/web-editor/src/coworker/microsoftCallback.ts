import { CoworkerClient, WorkspaceError } from "./client";

const storageKey = "shuddho:microsoft-connect";
const isMicrosoftCallbackRoute =
  typeof window !== "undefined"
  && window.location.pathname === "/oauth/microsoft/callback";

const callback = isMicrosoftCallbackRoute
  ? new URLSearchParams(window.location.search)
  : null;

if (isMicrosoftCallbackRoute) {
  window.history.replaceState(null, "", "/");
}

let completion: {
  account: string;
  promise: Promise<string | null>;
} | null = null;

export function hasPendingMicrosoftCallback(): boolean {
  return callback !== null && completion === null;
}

export function microsoftAuthorizationURL(
  value: string,
  state: string,
  origin: string,
): string {
  const url = new URL(value);
  const redirect = new URL(
    url.searchParams.get("redirect_uri") ?? "",
  );
  const tenantPath = /^\/[A-Za-z0-9.-]{1,200}\/oauth2\/v2\.0\/authorize$/;
  if (
    url.protocol !== "https:"
    || url.hostname !== "login.microsoftonline.com"
    || !tenantPath.test(url.pathname)
    || url.username
    || url.password
    || url.hash
    || url.searchParams.get("state") !== state
    || !/^[A-Za-z0-9_-]{43}$/.test(state)
    || redirect.origin !== origin
    || redirect.pathname !== "/oauth/microsoft/callback"
    || redirect.search
    || redirect.hash
  ) {
    throw new WorkspaceError(
      "The Microsoft connection redirect is not configured for this site.",
    );
  }
  return url.href;
}

export async function beginMicrosoftConnection(
  client: CoworkerClient,
  account: string,
  capability: "email" | "calendar" | "email_read" | "calendar_read",
) {
  const result = await client.connectMicrosoft(capability);
  const url = microsoftAuthorizationURL(
    result.authorization_url,
    result.state,
    window.location.origin,
  );
  try {
    sessionStorage.setItem(
      storageKey,
      JSON.stringify({
        state: result.state,
        account,
      }),
    );
  } catch {
    throw new WorkspaceError(
      "Allow session storage in this tab to connect Microsoft securely.",
    );
  }
  window.location.assign(url);
}

export function finishMicrosoftCallback(
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
      saved = JSON.parse(
        sessionStorage.getItem(storageKey) ?? "null",
      );
      sessionStorage.removeItem(storageKey);
    } catch {
      throw new WorkspaceError(
        "Start the Microsoft connection again in this tab.",
      );
    }
    if (
      !saved
      || saved.account !== account
      || saved.state !== callback.get("state")
    ) {
      throw new WorkspaceError(
        "This Microsoft connection belongs to another session. "
        + "Start again from your workspace.",
      );
    }
    if (callback.has("error") || !callback.get("code")) {
      throw new WorkspaceError(
        "Microsoft connection was cancelled. "
        + "You can connect again when ready.",
      );
    }
    const connection = await client.finishMicrosoft(
      callback.get("code")!,
      saved.state,
    );
    callback.delete("code");
    return (
      connection.email
      + " is connected to Microsoft for "
      + connection.capability
      + "."
    );
  })();
  completion = { account, promise };
  return promise;
}
