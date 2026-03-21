# API Examples

## Analyze request

```json
{
  "text": "শুদ্ধ বাংলা ব্যকরণ আর বংলা বাংলা ভাষা সুন্দর।।",
  "personal_dictionary": []
}
```

## Analyze response

```json
{
  "text": "শুদ্ধ বাংলা ব্যকরণ আর বংলা বাংলা ভাষা সুন্দর।।",
  "normalized_text": "শুদ্ধ বাংলা ব্যকরণ আর বংলা বাংলা ভাষা সুন্দর।।",
  "suggestions": [
    {
      "id": "s_1711059000000_1",
      "rule_id": "SPELL_001",
      "category": "spelling",
      "subtype": "safe_exact_typo",
      "span_start": 12,
      "span_end": 19,
      "original_text": "ব্যকরণ",
      "replacement_options": ["ব্যাকরণ"],
      "confidence": 0.98,
      "severity": "medium",
      "explanation_bn": "এখানে 'ব্যকরণ' এর বদলে 'ব্যাকরণ' লেখা উচিত।",
      "explanation_en": "Replace 'ব্যকরণ' with 'ব্যাকরণ' here.",
      "source": "rule"
    },
    {
      "id": "s_1711059000000_2",
      "rule_id": "SPELL_001",
      "category": "spelling",
      "subtype": "safe_exact_typo",
      "span_start": 23,
      "span_end": 27,
      "original_text": "বংলা",
      "replacement_options": ["বাংলা"],
      "confidence": 0.98,
      "severity": "medium",
      "explanation_bn": "এখানে 'বংলা' এর বদলে 'বাংলা' লেখা উচিত।",
      "explanation_en": "Replace 'বংলা' with 'বাংলা' here.",
      "source": "rule"
    },
    {
      "id": "s_1711059000000_3",
      "rule_id": "REP_001",
      "category": "grammar",
      "subtype": "repeated_word",
      "span_start": 23,
      "span_end": 34,
      "original_text": "বংলা বাংলা",
      "replacement_options": ["বাংলা"],
      "confidence": 0.7,
      "severity": "medium",
      "explanation_bn": "একই শব্দ 'বাংলা' পরপর দুইবার এসেছে।",
      "explanation_en": "The word 'বাংলা' appears twice in a row.",
      "source": "rule"
    },
    {
      "id": "s_1711059000000_4",
      "rule_id": "PUNC_001",
      "category": "punctuation",
      "subtype": "duplicate_punctuation",
      "span_start": 48,
      "span_end": 50,
      "original_text": "।।",
      "replacement_options": ["।"],
      "confidence": 0.99,
      "severity": "low",
      "explanation_bn": "এখানে '।।' এর বদলে '।' ব্যবহার করুন।",
      "explanation_en": "Replace '।।' with '।' here.",
      "source": "rule"
    }
  ]
}
```

## Feedback request

```json
{
  "suggestion_id": "s_1711059000000_1",
  "action": "dismissed",
  "text": "শুদ্ধ বাংলা ব্যকরণ আর বংলা বাংলা ভাষা সুন্দর।।"
}
```
