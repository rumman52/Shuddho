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

export function browserRequestAllowed({ kind, method, preparingForm, navigationRequest, mainFrame }) {
  const verb = String(method || "").toUpperCase();
  if (kind === "prepare_form" && !["GET", "HEAD"].includes(verb)) return false;
  if (kind === "prepare_form" && preparingForm && navigationRequest && mainFrame) return false;
  return true;
}


export function browserContextOptions(storageState) {
  return {
    acceptDownloads: false,
    ignoreHTTPSErrors: false,
    serviceWorkers: "block",
    ...(storageState ? { storageState } : {}),
  };
}
