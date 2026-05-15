import type { AnalyzeResponse, AnalysisProfile, HealthDeepResponse, Suggestion } from "@shared/schemas/contracts";

export type BackendTransportState = "checking" | "online" | "offline" | "misconfigured";

export interface RuntimeDescriptor {
  label: string;
  localOnly: boolean;
  degraded: boolean;
  warnings: string[];
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
  const localFallbackEnabled = analysis.runtime_warnings.includes("frontend_local_fallback_enabled");

  if (transport === "misconfigured") {
    return {
      label: localFallbackEnabled ? "Dev-only browser fallback" : "Backend misconfigured - contextual correction disabled",
      localOnly: localFallbackEnabled,
      degraded: true,
      warnings: compactWarnings([hardWarning, analysis.backend_warning, ...analysis.runtime_warnings]),
    };
  }

  if (transport === "offline") {
    return {
      label: localFallbackEnabled ? "Dev-only browser fallback" : "Backend offline, suggestions disabled",
      localOnly: localFallbackEnabled,
      degraded: true,
      warnings: compactWarnings([analysis.backend_warning, ...analysis.runtime_warnings]),
    };
  }

  if (transport === "checking") {
    return {
      label: "Checking backend connection",
      localOnly: false,
      degraded: false,
      warnings: compactWarnings(analysis.runtime_warnings),
    };
  }

  const profile = analysis.runtime_source || health?.analysis_profile || "backend_rules_and_spell_only";
  return {
    label: health?.backend_warning || analysis.backend_warning || getRuntimeLabel(profile),
    localOnly: profile === "frontend_local_fallback" && localFallbackEnabled,
    degraded: profile !== "full_local",
    warnings: compactWarnings([health?.backend_warning, analysis.backend_warning, ...analysis.runtime_warnings]),
  };
}

export function describeSuggestionSource(suggestion: Suggestion, analysis: AnalyzeResponse): string {
  if (analysis.runtime_source === "frontend_local_fallback" && analysis.runtime_warnings.includes("frontend_local_fallback_enabled")) {
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
