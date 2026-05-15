import type { CheckRequest, CheckResponse } from '@shuddho/shared';
export interface BanglaSuggestionProvider {
  readonly name: string;
  check(request: CheckRequest, requestId: string): Promise<CheckResponse>;
  rewrite?(text: string, options?: unknown): Promise<unknown>;
  tone?(text: string, options?: unknown): Promise<unknown>;
  ready?(): Promise<boolean>;
}
