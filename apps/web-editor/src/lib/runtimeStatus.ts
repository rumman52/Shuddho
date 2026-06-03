import type { AnalyzeResponse, AnalysisProfile, HealthDeepResponse, Suggestion } from "@shared/schemas/contracts";

export type BackendTransportState = "checking" | "online" | "offline" | "misconfigured";

export interface RuntimeDiagnostics {
  backendReachable: boolean;
  backendStatus: string;
  detectorLoaded: boolean;
  correctorLoaded: boolean;
  correctorReason: string | null;
  llmEnabled: boolean;
  llmConfigured: boolean;
  llmProvider: string | null;
  llmModel: string | null;
}

export interface RuntimeDescriptor {
  label: string;
  localOnly: boolean;
  degraded: boolean;
  warnings: string[];
  diagnostics: RuntimeDiagnostics;
}

const DEFAULT_RUNTIME_DIAGNOSTICS: RuntimeDiagnostics = {
  backendReachable: false,
  backendStatus: "unknown",
  detectorLoaded: false,
  correctorLoaded: false,
  correctorReason: null,
  llmEnabled: false,
  llmConfigured: false,
  llmProvider: null,
  llmModel: null,
};

function runtimeDiagnostics(
  health: HealthDeepResponse | null,
  transport: BackendTransportState,
): RuntimeDiagnostics {
  const llm = health?.llm;
  return {
    backendReachable: Boolean(health?.backend_reachable ?? (transport === "online" && health?.ok === true)),
    backendStatus: String(health?.status ?? (health?.ok === true ? "ok" : transport)),
    detectorLoaded: Boolean(health?.detector_loaded ?? health?.detector?.loaded ?? false),
    correctorLoaded: Boolean(health?.corrector_loaded ?? health?.corrector?.loaded ?? false),
    correctorReason: health?.corrector?.reason ?? null,
    llmEnabled: Boolean(llm?.enabled ?? false),
    llmConfigured: Boolean(llm?.configured ?? false),
    llmProvider: llm?.provider ?? null,
    llmModel: llm?.model ?? null,
  };
}

const BANGLA_LETTER_RE = /[\u0980-\u09ff]/u;

export function getRuntimeLabel(profile: AnalysisProfile): string {
  switch (profile) {
    case "full_local":
      return "Online contextual backend";
    case "backend_without_detector":
      return "Backend online but detector missing";
    case "backend_without_corrector":
      return "Backend online but corrector missing";
    case "backend_rules_and_spell_only":
      return "Backend online rules/spell only";
    case "frontend_local_fallback":
      return "Dev-only browser fallback";
    default:
      return "Backend online rules/spell only";
  }
}

export function describeRuntimeState(args: {
  analysis: AnalyzeResponse;
  transport: BackendTransportState;
  health: HealthDeepResponse | null;
  hardWarning?: string | null;
}): RuntimeDescriptor {
  const { analysis, transport, health, hardWarning } = args;
  const runtimeWarnings = Array.isArray(analysis.runtime_warnings) ? analysis.runtime_warnings : [];
  const localFallbackEnabled = runtimeWarnings.includes("frontend_local_fallback_enabled");

  if (transport === "misconfigured") {
    return {
      label: localFallbackEnabled ? "Dev-only browser fallback" : "Backend misconfigured - contextual correction disabled",
      localOnly: localFallbackEnabled,
      degraded: true,
      warnings: compactWarnings([
        hardWarning?.includes("VITE_API_BASE_URL")
          ? hardWarning
          : `${hardWarning ?? "Backend API URL is misconfigured."} Set VITE_API_BASE_URL to a public backend or gateway URL.`,
        analysis.backend_warning,
        ...runtimeWarnings,
      ]),
      diagnostics: { ...DEFAULT_RUNTIME_DIAGNOSTICS, backendStatus: "misconfigured" },
    };
  }

  if (transport === "offline") {
    return {
      label: localFallbackEnabled ? "Dev-only browser fallback" : "Backend offline, suggestions disabled",
      localOnly: localFallbackEnabled,
      degraded: true,
      warnings: compactWarnings([analysis.backend_warning, ...runtimeWarnings]),
      diagnostics: { ...DEFAULT_RUNTIME_DIAGNOSTICS, backendStatus: "offline" },
    };
  }

  if (transport === "checking") {
    return {
      label: "Checking backend connection",
      localOnly: false,
      degraded: false,
      warnings: compactWarnings(runtimeWarnings),
      diagnostics: { ...DEFAULT_RUNTIME_DIAGNOSTICS, backendStatus: "checking" },
    };
  }

  const profile = analysis.runtime_source || health?.analysis_profile || "backend_rules_and_spell_only";
  const diagnostics = runtimeDiagnostics(health, transport);
  const correctorDegraded = diagnostics.backendReachable && !diagnostics.correctorLoaded;
  return {
    label: correctorDegraded
      ? "Backend connected, but sentence-level corrector is degraded."
      : health?.backend_warning || analysis.backend_warning || getRuntimeLabel(profile),
    localOnly: profile === "frontend_local_fallback" && localFallbackEnabled,
    degraded: profile !== "full_local" || correctorDegraded,
    warnings: compactWarnings([
      correctorDegraded ? "sentence_level_corrector_unavailable" : null,
      health?.backend_warning,
      analysis.backend_warning,
      ...runtimeWarnings,
    ]),
    diagnostics,
  };
}

export function describeSuggestionSource(suggestion: Suggestion, analysis: AnalyzeResponse): string {
  const runtimeWarnings = Array.isArray(analysis.runtime_warnings) ? analysis.runtime_warnings : [];
  if (analysis.runtime_source === "frontend_local_fallback" && runtimeWarnings.includes("frontend_local_fallback_enabled")) {
    return "limited browser fallback";
  }
  return suggestion.source;
}

export function canAddSuggestionToDictionary(suggestion: Suggestion): boolean {
  const normalized = suggestion.original_text.trim();
  if (!normalized || normalized.length > 40) {
    return false;
  }
  if (normalized.includes("\n")) {
    return false;
  }
  if (!BANGLA_LETTER_RE.test(normalized)) {
    return false;
  }
  if (suggestion.category === "punctuation") {
    return false;
  }
  return suggestion.original_text.split(/\s+/u).length <= 3;
}

function compactWarnings(warnings: Array<string | null | undefined>): string[] {
  const seen = new Set<string>();
  const compact: string[] = [];
  for (const warning of warnings) {
    const value = warning?.trim();
    if (!value || seen.has(value)) {
      continue;
    }
    seen.add(value);
    compact.push(value);
  }
  return compact;
}
