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
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
    throw new Error("invalid_worker_api_base_url");
  }
  return url.toString().replace(/\/$/, "");
}
