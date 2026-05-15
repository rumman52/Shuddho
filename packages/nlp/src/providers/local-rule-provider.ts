import type { Suggestion } from '@shuddho/shared';
import type { SuggestionContext, SuggestionProvider } from './types.js';

const escapeRegExp = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const makeId = (requestId: string, type: string, start: number, text: string) => `${requestId}:${type}:${start}:${text}`;

function literalSuggestions(text: string, requestId: string, original: string, suggested: string, type: Suggestion['type'], explanation: string): Suggestion[] {
  const results: Suggestion[] = [];
  const regex = new RegExp(`\\b${escapeRegExp(original)}\\b`, 'gi');
  let match: RegExpExecArray | null;
  while ((match = regex.exec(text)) !== null) {
    results.push({
      id: makeId(requestId, type, match.index, original),
      type,
      severity: type === 'spelling' ? 'high' : 'medium',
      originalText: match[0],
      suggestedText: suggested,
      explanation,
      startIndex: match.index,
      endIndex: match.index + match[0].length,
      confidence: 0.94,
      sourceProvider: 'LocalRuleProvider',
    });
  }
  return results;
}

export class LocalRuleProvider implements SuggestionProvider {
  readonly name = 'LocalRuleProvider';

  async check(text: string, context: SuggestionContext): Promise<Suggestion[]> {
    const requestId = context.requestId;
    const suggestions: Suggestion[] = [
      ...literalSuggestions(text, requestId, 'teh', 'the', 'spelling', 'Common transposition typo.'),
      ...literalSuggestions(text, requestId, 'recieve', 'receive', 'spelling', 'Use “receive” with i before e after c.'),
      ...literalSuggestions(text, requestId, 'I has', 'I have', 'grammar', 'Use “have” with the subject “I”.'),
      ...literalSuggestions(text, requestId, 'in order to', 'to', 'style', 'Prefer concise wording when the meaning is unchanged.'),
      ...literalSuggestions(text, requestId, 'due to the fact that', 'because', 'style', 'Replace wordy phrasing with a direct connector.'),
    ];

    const repeatedSpaces = / {2,}/g;
    let spaceMatch: RegExpExecArray | null;
    while ((spaceMatch = repeatedSpaces.exec(text)) !== null) {
      suggestions.push({
        id: makeId(requestId, 'style', spaceMatch.index, 'spaces'),
        type: 'style',
        severity: 'low',
        originalText: spaceMatch[0],
        suggestedText: ' ',
        explanation: 'Use a single space for consistent readability.',
        startIndex: spaceMatch.index,
        endIndex: spaceMatch.index + spaceMatch[0].length,
        confidence: 0.98,
        sourceProvider: this.name,
      });
    }

    const passive = /\\b(was|were|is|are|been|being)\\s+([a-z]+ed)\\b/gi;
    let passiveMatch: RegExpExecArray | null;
    while ((passiveMatch = passive.exec(text)) !== null) {
      suggestions.push({
        id: makeId(requestId, 'style', passiveMatch.index, 'passive'),
        type: 'style',
        severity: 'info',
        originalText: passiveMatch[0],
        suggestedText: passiveMatch[0],
        explanation: 'Consider active voice if the actor is known.',
        startIndex: passiveMatch.index,
        endIndex: passiveMatch.index + passiveMatch[0].length,
        confidence: 0.62,
        sourceProvider: this.name,
      });
    }

    const harshPhrases = [
      { phrase: 'you are wrong', replacement: 'I see it differently', note: 'Softening this phrase can make the tone more collaborative.' },
      { phrase: 'this is terrible', replacement: 'this needs improvement', note: 'A more constructive tone may help the reader act on the feedback.' },
      { phrase: 'obviously', replacement: 'clearly', note: 'This can sound dismissive; consider a neutral wording.' },
    ];
    for (const item of harshPhrases) {
      suggestions.push(...literalSuggestions(text, requestId, item.phrase, item.replacement, 'tone', item.note));
    }

    return suggestions.sort((a, b) => a.startIndex - b.startIndex || b.confidence - a.confidence);
  }
}
