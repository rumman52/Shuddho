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
      "category": "correctness",
      "subtype": "safe_exact_typo",
      "original_text": "ব্যকরণ",
      "replacement_options": ["ব্যাকরণ"]
    },
    {
      "category": "grammar",
      "subtype": "repeated_word",
      "original_text": "বাংলা বাংলা",
      "replacement_options": ["বাংলা"]
    },
    {
      "category": "punctuation",
      "subtype": "duplicate_punctuation",
      "original_text": "।।",
      "replacement_options": ["।"]
    }
  ]
}
```

## Feedback request

```json
{
  "suggestion_id": "rule_xxx",
  "action": "dismissed",
  "text": "শুদ্ধ বাংলা ব্যকরণ আর বংলা বাংলা ভাষা সুন্দর।।"
}
```
