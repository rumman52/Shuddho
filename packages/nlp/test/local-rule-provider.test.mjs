import assert from 'node:assert/strict';
import { LocalRuleProvider } from '../dist/index.js';
const suggestions = await new LocalRuleProvider().check('I has teh report  in order to show you are wrong.', { requestId: 'req-test', locale: 'en-US', goals: ['grammar', 'spelling', 'style', 'tone'] });
assert.ok(suggestions.some((s) => s.originalText.toLowerCase() === 'teh' && s.suggestedText === 'the'));
assert.ok(suggestions.some((s) => s.originalText === 'I has' && s.suggestedText === 'I have'));
assert.ok(suggestions.some((s) => s.originalText === '  ' && s.suggestedText === ' '));
assert.ok(suggestions.some((s) => s.type === 'tone'));
console.log('LocalRuleProvider tests passed');
