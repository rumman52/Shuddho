import { createDefaultSettings, EXTENSION_SETTINGS_STORAGE_KEY } from "./config";
import type { ExtensionSettings } from "./types";

chrome.runtime.onInstalled.addListener(() => {
  void ensureSettings();
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  void handleMessage(message)
    .then((response) => sendResponse(response))
    .catch((error: unknown) => {
      sendResponse({ error: error instanceof Error ? error.message : "Unknown extension error" });
    });
  return true;
});

async function handleMessage(message: unknown): Promise<ExtensionSettings> {
  if (!message || typeof message !== "object" || !("type" in message)) {
    throw new Error("Unsupported background message");
  }

  const typedMessage = message as {
    type: string;
    patch?: Partial<ExtensionSettings>;
    hostname?: string;
    disabled?: boolean;
  };

  switch (typedMessage.type) {
    case "settings:get":
      return ensureSettings();
    case "settings:update":
      return saveSettings(typedMessage.patch ?? {});
    case "site:set_disabled":
      if (!typedMessage.hostname) {
        throw new Error("Missing hostname");
      }
      return toggleSite(typedMessage.hostname, Boolean(typedMessage.disabled));
    default:
      throw new Error(`Unsupported background message: ${typedMessage.type}`);
  }
}

async function ensureSettings(): Promise<ExtensionSettings> {
  const stored = await chrome.storage.local.get(EXTENSION_SETTINGS_STORAGE_KEY);
  const resolved = normalizeSettings(stored[EXTENSION_SETTINGS_STORAGE_KEY] as Partial<ExtensionSettings> | undefined);
  await chrome.storage.local.set({ [EXTENSION_SETTINGS_STORAGE_KEY]: resolved });
  return resolved;
}

async function saveSettings(patch: Partial<ExtensionSettings>): Promise<ExtensionSettings> {
  const current = await ensureSettings();
  const next = normalizeSettings({
    ...current,
    ...patch,
  });
  await chrome.storage.local.set({ [EXTENSION_SETTINGS_STORAGE_KEY]: next });
  return next;
}

async function toggleSite(hostname: string, disabled: boolean): Promise<ExtensionSettings> {
  const current = await ensureSettings();
  const normalizedHostname = hostname.trim().toLowerCase();
  const nextDisabledSites = disabled
    ? upsert(current.disabledSites, normalizedHostname)
    : current.disabledSites.filter((site) => site !== normalizedHostname);
  return saveSettings({ disabledSites: nextDisabledSites });
}

function normalizeSettings(value: Partial<ExtensionSettings> | undefined): ExtensionSettings {
  const defaults = createDefaultSettings();
  const backendBaseUrl = value?.backendBaseUrl?.trim() || defaults.backendBaseUrl;
  return {
    backendBaseUrl: backendBaseUrl.replace(/\/+$/, ""),
    writingGoal: value?.writingGoal ?? defaults.writingGoal,
    toneGoal: value?.toneGoal ?? defaults.toneGoal,
    suggestionDensity: value?.suggestionDensity ?? defaults.suggestionDensity,
    rewritesEnabled: value?.rewritesEnabled ?? defaults.rewritesEnabled,
    autoShowTone: value?.autoShowTone ?? defaults.autoShowTone,
    disabledSites: normalizeList(value?.disabledSites ?? defaults.disabledSites),
    currentUserId: value?.currentUserId?.trim() || defaults.currentUserId,
    localPersonalDictionaryMirror: normalizeList(value?.localPersonalDictionaryMirror ?? defaults.localPersonalDictionaryMirror),
    suppressedRuleKeys: normalizeList(value?.suppressedRuleKeys ?? defaults.suppressedRuleKeys),
  };
}

function normalizeList(values: string[]): string[] {
  const normalized: string[] = [];
  const seen = new Set<string>();
  for (const value of values) {
    const compact = value.trim().replace(/\s+/g, " ");
    if (!compact || seen.has(compact)) {
      continue;
    }
    seen.add(compact);
    normalized.push(compact);
  }
  return normalized;
}

function upsert(items: string[], value: string): string[] {
  if (!value || items.includes(value)) {
    return items;
  }
  return [...items, value];
}
