import type { HealthDeepResponse } from "@shared/schemas/contracts";

import { getExtensionSettings, getHostnameFromUrl, setSiteDisabled, updateExtensionSettings } from "./config";
import type { ExtensionSettings } from "./types";

const DETECTOR_UNAVAILABLE_COPY = "Detector unavailable";
const CORRECTOR_UNAVAILABLE_COPY = "Sentence-level corrector is not loaded. Shuddho is running rules + spelling only.";
const BACKEND_UNREACHABLE_COPY = "Backend offline. Only limited local checks are available.";

const statusElement = document.getElementById("status");
const siteHostnameElement = document.getElementById("site-hostname");
const toggleSiteButton = document.getElementById("toggle-site") as HTMLButtonElement | null;
const backendUrlInput = document.getElementById("backend-url") as HTMLInputElement | null;
const userIdInput = document.getElementById("user-id") as HTMLInputElement | null;
const writingGoalSelect = document.getElementById("writing-goal") as HTMLSelectElement | null;
const toneGoalSelect = document.getElementById("tone-goal") as HTMLSelectElement | null;
const suggestionDensitySelect = document.getElementById("suggestion-density") as HTMLSelectElement | null;
const rewritesEnabledInput = document.getElementById("rewrites-enabled") as HTMLInputElement | null;
const autoShowToneInput = document.getElementById("auto-show-tone") as HTMLInputElement | null;
const dictionaryTextarea = document.getElementById("dictionary") as HTMLTextAreaElement | null;
const saveButton = document.getElementById("save-settings") as HTMLButtonElement | null;

let settings: ExtensionSettings | null = null;
let currentHostname: string | null = null;

void initializePopup();

async function initializePopup(): Promise<void> {
  settings = await getExtensionSettings();
  currentHostname = await resolveCurrentHostname();
  renderSettings();
  await refreshBackendStatus();
}

async function refreshBackendStatus(): Promise<void> {
  if (!settings || !statusElement) {
    return;
  }

  try {
    const response = await fetch(`${settings.backendBaseUrl}/health/deep`);
    if (!response.ok) {
      throw new Error(String(response.status));
    }
    const health = (await response.json()) as HealthDeepResponse;
    const issues: string[] = [];
    if (!health.detector.loaded) {
      issues.push(DETECTOR_UNAVAILABLE_COPY);
    }
    if (!health.corrector.loaded) {
      issues.push(CORRECTOR_UNAVAILABLE_COPY);
    }
    statusElement.textContent = health.backend_warning || (issues.length ? `${health.analysis_profile} (${issues.join(", ")})` : `${health.analysis_profile}`);
  } catch {
    statusElement.textContent = `${BACKEND_UNREACHABLE_COPY} at ${settings.backendBaseUrl}`;
  }
}

function renderSettings(): void {
  if (!settings) {
    return;
  }

  if (backendUrlInput) {
    backendUrlInput.value = settings.backendBaseUrl;
  }
  if (userIdInput) {
    userIdInput.value = settings.currentUserId;
  }
  if (writingGoalSelect) {
    writingGoalSelect.value = settings.writingGoal;
  }
  if (toneGoalSelect) {
    toneGoalSelect.value = settings.toneGoal;
  }
  if (suggestionDensitySelect) {
    suggestionDensitySelect.value = settings.suggestionDensity;
  }
  if (rewritesEnabledInput) {
    rewritesEnabledInput.checked = settings.rewritesEnabled;
  }
  if (autoShowToneInput) {
    autoShowToneInput.checked = settings.autoShowTone;
  }
  if (dictionaryTextarea) {
    dictionaryTextarea.value = settings.localPersonalDictionaryMirror.join("\n");
  }
  if (siteHostnameElement) {
    siteHostnameElement.textContent = currentHostname ?? "Unavailable";
  }
  if (toggleSiteButton) {
    const disabled = Boolean(currentHostname && settings.disabledSites.includes(currentHostname));
    toggleSiteButton.textContent = disabled ? "Enable site" : "Disable site";
  }
}

saveButton?.addEventListener("click", async () => {
  if (!backendUrlInput || !userIdInput || !writingGoalSelect || !toneGoalSelect || !suggestionDensitySelect || !rewritesEnabledInput || !autoShowToneInput || !dictionaryTextarea) {
    return;
  }

  settings = await updateExtensionSettings({
    backendBaseUrl: backendUrlInput.value.trim(),
    currentUserId: userIdInput.value.trim(),
    writingGoal: writingGoalSelect.value as ExtensionSettings["writingGoal"],
    toneGoal: toneGoalSelect.value as ExtensionSettings["toneGoal"],
    suggestionDensity: suggestionDensitySelect.value as ExtensionSettings["suggestionDensity"],
    rewritesEnabled: rewritesEnabledInput.checked,
    autoShowTone: autoShowToneInput.checked,
    localPersonalDictionaryMirror: normalizeDictionary(dictionaryTextarea.value),
  });
  renderSettings();
  await refreshBackendStatus();
});

toggleSiteButton?.addEventListener("click", async () => {
  if (!currentHostname || !settings) {
    return;
  }
  const disabled = !settings.disabledSites.includes(currentHostname);
  settings = await setSiteDisabled(currentHostname, disabled);
  renderSettings();
});

async function resolveCurrentHostname(): Promise<string | null> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return getHostnameFromUrl(tab?.url);
}

function normalizeDictionary(value: string): string[] {
  const entries = value
    .split(/\r?\n/g)
    .map((entry) => entry.trim())
    .filter(Boolean);
  return [...new Set(entries)];
}
