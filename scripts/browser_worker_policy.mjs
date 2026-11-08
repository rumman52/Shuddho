import { isIP } from "node:net";

export function parseConnectAuthority(authority) {
  if (typeof authority !== "string" || authority.length > 512) {
    throw new Error("invalid_connect_authority");
  }
  const lastColon = authority.lastIndexOf(":");
  if (lastColon <= 0) throw new Error("invalid_connect_authority");
  const host = authority.slice(0, lastColon).trim().replace(/^\[|\]$/g, "").toLowerCase();
  const portText = authority.slice(lastColon + 1);
  const port = Number(portText);
  if (!host || !Number.isInteger(port) || port !== 443 || isIP(host)) {
    throw new Error("blocked_connect_authority");
  }
  return { host, port };
}

export function safeWorkerId(value) {
  if (!/^[A-Za-z0-9_.:-]{3,64}$/.test(value || "")) {
    throw new Error("invalid_worker_id");
  }
  return value;
}

export function normalizedBaseUrl(value) {
  const url = new URL(value);
  const loopbackHttp = url.protocol === "http:" && ["127.0.0.1", "localhost", "[::1]"].includes(url.hostname);
  if (
    (url.protocol !== "https:" && !loopbackHttp)
    || url.username
    || url.password
    || url.search
    || url.hash
  ) {
    throw new Error("invalid_worker_api_base_url");
  }
  return url.toString().replace(/\/$/, "");
}

// Chromium must not apply its implicit localhost/loopback proxy bypass. Its
// HTTP(S) request path is forced through the worker-owned loopback CONNECT
// proxy, which performs broker DNS authorization and pins the approved IP.
// This application-level policy does not replace host/container egress rules.
export function browserChromiumLaunchOptions(proxyUrl) {
  let proxy;
  try {
    proxy = new URL(proxyUrl);
  } catch {
    throw new Error("invalid_browser_proxy_url");
  }
  if (
    proxy.protocol !== "http:"
    || proxy.hostname !== "127.0.0.1"
    || !proxy.port
    || proxy.username
    || proxy.password
    || proxy.pathname !== "/"
    || proxy.search
    || proxy.hash
  ) {
    throw new Error("invalid_browser_proxy_url");
  }
  return {
    headless: true,
    proxy: {
      server: proxy.origin,
      // Chromium otherwise bypasses its proxy for localhost and loopback.
      bypass: "<-loopback>",
    },
    args: [
      "--disable-background-networking",
      "--disable-component-update",
      "--disable-default-apps",
      "--disable-extensions",
      "--disable-quic",
      "--disable-sync",
      "--dns-prefetch-disable",
      // Chromium never resolves page destinations directly. The worker proxy
      // resolves each CONNECT target and asks the broker to authorize the
      // complete answer set before dialing a pinned public address.
      // Permit only the numeric loopback address used by the local proxy;
      // all page destinations remain unresolved in Chromium itself.
      "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
      // Do not permit WebRTC to send UDP outside the configured proxy.
      "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
    ],
    env: { HOME: process.env.HOME || "/tmp" },
  };
}

// Agent read-only pages must not open realtime transports that can carry
// mutations outside the GET/HEAD request router. The WebSocket route is
// installed before the first page is created; browser APIs that could create
// direct peer or WebTransport connections are disabled in every document.
export const BROWSER_READ_ONLY_NETWORK_INIT_SCRIPT = `(() => {
  for (const name of ["RTCPeerConnection", "webkitRTCPeerConnection", "WebTransport"]) {
    try {
      Object.defineProperty(globalThis, name, {
        value: undefined,
        configurable: false,
        writable: false,
      });
    } catch {}
  }
})();`;

export async function installAgentReadOnlyBrowserGuards(context, state) {
  if (
    !context
    || typeof context.addInitScript !== "function"
    || typeof context.routeWebSocket !== "function"
    || !state
  ) {
    throw new Error("browser_read_only_guard_unavailable");
  }
  await context.addInitScript(BROWSER_READ_ONLY_NETWORK_INIT_SCRIPT);
  await context.routeWebSocket("**/*", async (webSocket) => {
    state.surfaceViolation = state.surfaceViolation || browserSurfaceViolation("websocket");
    await webSocket.close({ code: 1008, reason: "Read-only browser policy" });
  });
}

// A browser request must remain on the server-admitted HTTPS origin. This is
// a second guard in front of the CONNECT proxy, including for URLs Chromium
// might otherwise try to send directly (localhost, IP literals, or HTTP).
export function browserRequestTargetAllowed(rawUrl, allowedOrigin) {
  let url;
  let admitted;
  try {
    url = new URL(rawUrl);
    admitted = new URL(allowedOrigin);
  } catch {
    return false;
  }
  if (
    url.protocol !== "https:"
    || !url.hostname
    || url.username
    || url.password
    || (url.port && url.port !== "443")
    || admitted.protocol !== "https:"
    || url.origin !== admitted.origin
  ) {
    return false;
  }
  const hostname = url.hostname.toLowerCase().replace(/\.$/, "");
  const ipHost = hostname.startsWith("[") && hostname.endsWith("]")
    ? hostname.slice(1, -1)
    : hostname;
  if (isIP(ipHost) !== 0 || !hostname.includes(".")) return false;
  if (["localhost", "metadata", "metadata.google.internal"].includes(hostname)) return false;
  return ![".localhost", ".local", ".internal", ".home", ".lan"].some(
    (suffix) => hostname.endsWith(suffix),
  );
}


export function takeoverFieldPolicy(metadata) {
  const blockedTypes = new Set(["file", "hidden", "submit", "button", "image", "checkbox", "radio"]);
  if (
    !metadata
    || metadata.disabled
    || metadata.readOnly
    || !["input", "textarea"].includes(metadata.tag)
    || blockedTypes.has(metadata.type)
  ) {
    return "not_editable";
  }
  return "fillable";
}


export function formFieldPolicy(metadata) {
  const blockedTypes = new Set(["password", "file", "hidden", "submit", "button", "image", "checkbox", "radio"]);
  const sensitiveAutocomplete = new Set(["current-password", "new-password", "one-time-code", "cc-number", "cc-csc"]);
  if (
    !metadata
    || metadata.disabled
    || metadata.readOnly
    || !["input", "textarea"].includes(metadata.tag)
    || blockedTypes.has(metadata.type)
  ) {
    return "not_editable";
  }
  if (sensitiveAutocomplete.has(metadata.autocomplete)) {
    return "sensitive";
  }
  return "fillable";
}

export function browserSurfaceViolation(eventType) {
  if (eventType === "popup") return "browser_popup_blocked";
  if (eventType === "download") return "browser_download_blocked";
  if (eventType === "websocket") return "browser_websocket_blocked";
  return null;
}


export function browserRequestAllowed({ kind, method, preparingForm, humanInteractionArmed = false, navigationRequest, mainFrame, agentReadOnly = false }) {
  const verb = String(method || "").toUpperCase();
  if (kind === "idle") return false;
  if (agentReadOnly && !["GET", "HEAD"].includes(verb)) return false;
  if (kind === "prepare_form" && !["GET", "HEAD"].includes(verb)) return false;
  if (kind === "prepare_form" && preparingForm && navigationRequest && mainFrame) return false;
  if (kind === "takeover_frame" && !["GET", "HEAD"].includes(verb)) return false;
  if (kind === "takeover_interaction" && !humanInteractionArmed && !["GET", "HEAD"].includes(verb)) return false;
  return true;
}


// An autonomous read never imports cookies or persists an authenticated browsing context.
// Human-supervised commands retain their existing encrypted continuity contract.
// Hashes are computed over exactly the UTF-8 text returned to the broker,
// including when a visible page must be truncated at a codepoint boundary.
export function boundVisiblePageText(value, wasTruncated = false) {
  if (typeof value !== "string" || typeof wasTruncated !== "boolean" || value.includes("\0")) {
    throw new Error("browser_page_text_invalid");
  }
  const encoded = Buffer.from(value, "utf8");
  if (encoded.length <= 8192) return { text: value, truncated: wasTruncated };
  let end = 8192;
  while (end > 0 && (encoded[end] & 0xc0) === 0x80) end--;
  return { text: encoded.subarray(0, end).toString("utf8"), truncated: true };
}

// DNS/network-check is asynchronous. The worker may pause, cancel or switch
// commands while a CONNECT awaits server authorization. A matching command id
// alone is insufficient (a resumed command can reuse that id); the monotonic
// claim epoch and evidence identity must also still be current.
export function browserProxyClaimValid(state, claim) {
  return (
    typeof claim?.commandId === "string"
    && claim.commandId.length > 0
    && Number.isSafeInteger(claim.epoch)
    && claim.evidence !== null
    && claim.evidence !== undefined
    && state?.commandId === claim.commandId
    && state?.proxyClaimEpoch === claim.epoch
    && state?.evidence === claim.evidence
  );
}

export function browserWorkerMayReuseStorageState(command) {
  return command?.policy?.agent_read_only !== true;
}

export function browserContextOptions(storageState) {
  return {
    acceptDownloads: false,
    ignoreHTTPSErrors: false,
    serviceWorkers: "block",
    ...(storageState ? { storageState } : {}),
  };
}
