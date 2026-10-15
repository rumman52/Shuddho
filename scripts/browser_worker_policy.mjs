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
