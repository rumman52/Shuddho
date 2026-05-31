export const DEFAULT_REQUEST_TIMEOUT_MS = 8000;
export const HEALTH_REQUEST_TIMEOUT_MS = 3000;
export const GRAMMAR_CHECK_TIMEOUT_MS = 10000;
export const AI_REVIEW_TIMEOUT_MS = 50000;

export class FetchTimeoutError extends Error {
  readonly friendly = true;
  readonly timeoutMs: number;

  constructor(timeoutMs: number) {
    super("Request timed out. Please try again or check backend deployment.");
    this.name = "FetchTimeoutError";
    this.timeoutMs = timeoutMs;
  }
}

export async function fetchWithTimeout(
  url: string,
  options: RequestInit = {},
  timeoutMs = DEFAULT_REQUEST_TIMEOUT_MS,
): Promise<Response> {
  const timeoutController = new AbortController();
  const timeoutId = globalThis.setTimeout(
    () => timeoutController.abort(),
    timeoutMs,
  );
  const upstreamSignal = options.signal;

  if (upstreamSignal?.aborted) {
    globalThis.clearTimeout(timeoutId);
    throw new DOMException("The operation was aborted.", "AbortError");
  }

  const abortFromUpstream = () => timeoutController.abort();
  upstreamSignal?.addEventListener("abort", abortFromUpstream, { once: true });

  try {
    return await fetch(url, {
      ...options,
      signal: timeoutController.signal,
    });
  } catch (error) {
    if (timeoutController.signal.aborted && !upstreamSignal?.aborted) {
      throw new FetchTimeoutError(timeoutMs);
    }
    throw error;
  } finally {
    globalThis.clearTimeout(timeoutId);
    upstreamSignal?.removeEventListener("abort", abortFromUpstream);
  }
}
