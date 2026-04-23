import type { AnalyzeMode } from "./types";
import type { ExtensionSettings } from "./types";

const API_BASE_URL_TOKEN = "__SHUDDHO_EXTENSION_API_BASE_URL__";
const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";
export const EXTENSION_SETTINGS_STORAGE_KEY = "shuddho-extension-settings";

export function getDefaultApiBaseUrl(): string {
  const configuredBaseUrl =
    API_BASE_URL_TOKEN === "__SHUDDHO_EXTENSION_API_BASE_URL__" ? DEFAULT_API_BASE_URL : API_BASE_URL_TOKEN;
  return configuredBaseUrl.replace(/\/+$/, "");
}

export function createDefaultSettings(): ExtensionSettings {
  return {
    backendBaseUrl: getDefaultApiBaseUrl(),
    writingGoal: "general",
    toneGoal: "neutral",
    suggestionDensity: "balanced",
    rewritesEnabled: true,
    autoShowTone: true,
    disabledSites: [],
    currentUserId: createLocalUserId(),
    localPersonalDictionaryMirror: [],
    suppressedRuleKeys: [],
  };
}

export function modeFromWritingGoal(goal: ExtensionSettings["writingGoal"]): AnalyzeMode {
  if (goal === "formal" || goal === "academic" || goal === "business") {
    return "formal";
  }
  return "standard";
}

export function getHostnameFromUrl(url: string | undefined): string | null {
  if (!url) {
    return null;
  }
  try {
    return new URL(url).hostname.toLowerCase();
  } catch {
    return null;
  }
}

export async function getExtensionSettings(): Promise<ExtensionSettings> {
  return sendRuntimeMessage<ExtensionSettings>({ type: "settings:get" });
}

export async function updateExtensionSettings(patch: Partial<ExtensionSettings>): Promise<ExtensionSettings> {
  return sendRuntimeMessage<ExtensionSettings>({ type: "settings:update", patch });
}

export async function setSiteDisabled(hostname: string, disabled: boolean): Promise<ExtensionSettings> {
  return sendRuntimeMessage<ExtensionSettings>({
    type: "site:set_disabled",
    hostname,
    disabled,
  });
}

function createLocalUserId(): string {
  return `extension-${Date.now().toString(36)}`;
}

function sendRuntimeMessage<TResponse>(message: unknown): Promise<TResponse> {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(message, (response: TResponse | { error?: string } | undefined) => {
      const runtimeError = chrome.runtime.lastError;
      if (runtimeError) {
        reject(new Error(runtimeError.message));
        return;
      }
      if (response && typeof response === "object" && "error" in response && response.error) {
        reject(new Error(response.error));
        return;
      }
      resolve(response as TResponse);
    });
  });
}
