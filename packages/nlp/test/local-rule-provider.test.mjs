import assert from 'node:assert/strict';
import { LocalRuleProvider } from '../dist/index.js';

const provider = new LocalRuleProvider();
const request = {
  requestId: 'req-test',
  documentId: 'doc-test',
  revision: 1,
  text: 'আমি  আমি বাংলা লিখি । বাংলা বাংলা ভাষা সুন্দর',
  language: 'bn',
  options: { includeGrammar: true, includeSpelling: true, includeStyle: true },
};
const response = await provider.check(request, 'req-test');
const suggestions = response.suggestions;

assert.equal(response.requestId, 'req-test');
assert.ok(suggestions.some((s) => s.ruleId === 'bn.spacing.repeated_spaces' && s.originalText === '  ' && s.suggestedText === ' '));
assert.ok(suggestions.some((s) => s.ruleId === 'bn.grammar.duplicate_word' && s.originalText === 'আমি  আমি' && s.suggestedText === 'আমি'));
assert.ok(suggestions.some((s) => s.ruleId === 'bn.grammar.duplicate_word' && s.originalText === 'বাংলা বাংলা' && s.suggestedText === 'বাংলা'));
assert.ok(suggestions.some((s) => s.ruleId === 'bn.punctuation.space_before_dari' && s.originalText === ' ।' && s.suggestedText === '।'));

const missingPunctuation = await provider.check({ ...request, text: 'আজ বাংলা ভাষা সুন্দর' }, 'req-missing-punctuation');
assert.ok(missingPunctuation.suggestions.some((s) => s.ruleId === 'bn.punctuation.missing_sentence_end' && s.span.startIndex === 'আজ বাংলা ভাষা সুন্দর'.length && s.suggestedText === '।'));

for (const suggestion of suggestions) {
  assert.equal(request.text.slice(suggestion.span.startIndex, suggestion.span.endIndex), suggestion.originalText);
  assert.ok(Array.isArray(suggestion.replacementOptions));
  assert.equal(suggestion.replacementOptions[0], suggestion.suggestedText);
}
console.log('LocalRuleProvider Bangla tests passed');
