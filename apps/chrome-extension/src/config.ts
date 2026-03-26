const API_BASE_URL = "__SHUDDHO_EXTENSION_API_BASE_URL__";

export function getApiBaseUrl(): string {
  return API_BASE_URL.replace(/\/+$/, "");
}
