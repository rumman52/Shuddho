import type { Suggestion } from '@shuddho/shared';

export interface SuggestionContext {
  requestId: string;
  locale: string;
  goals: string[];
}

export interface SuggestionProvider {
  readonly name: string;
  check(text: string, context: SuggestionContext): Promise<Suggestion[]>;
}

export interface RewriteProvider {
  readonly name: string;
  rewrite(text: string, instruction?: string): Promise<Suggestion[]>;
}
