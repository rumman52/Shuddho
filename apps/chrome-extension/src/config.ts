const API_BASE_URL_TOKEN = "__SHUDDHO_EXTENSION_API_BASE_URL__";
const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

export function getApiBaseUrl(): string {
  const configuredBaseUrl =
    API_BASE_URL_TOKEN === "__SHUDDHO_EXTENSION_API_BASE_URL__" ? DEFAULT_API_BASE_URL : API_BASE_URL_TOKEN;

  return configuredBaseUrl.replace(/\/+$/, "");
}
