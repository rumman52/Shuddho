from __future__ import annotations

import re

BANGLA_LETTER_PATTERN = re.compile(r"[\u0980-\u09FF]")
BANGLA_WORD_PATTERN = re.compile(r"[\u0980-\u09FF]+")
TOKEN_PATTERN = re.compile(r"[\u0980-\u09FFA-Za-z0-9]+|[^\s]")
PUNCTUATION_CHARS = ",.;:!?।"
PUNCTUATION_PATTERN = re.compile(rf"[{re.escape(PUNCTUATION_CHARS)}]")

COMMON_BANGLA_CONFUSIONS: dict[str, tuple[str, ...]] = {
    "া": ("া", "ো"),
    "ি": ("ি", "ী"),
    "ী": ("ী", "ি"),
    "ু": ("ু", "ূ"),
    "ূ": ("ূ", "ু"),
    "ে": ("ে", "ৈ"),
    "ো": ("ো", "ৌ", "া"),
    "ণ": ("ণ", "ন"),
    "ন": ("ন", "ণ"),
    "শ": ("শ", "ষ", "স"),
    "ষ": ("ষ", "শ", "স"),
    "স": ("স", "শ", "ষ"),
    "য": ("য", "য়"),
    "য়": ("য়", "য"),
    "ড়": ("ড়", "ড"),
    "ঢ়": ("ঢ়", "ঢ")
}

SAFE_EXACT_TYPOS: dict[str, str] = {
    "বংলা": "বাংলা",
    "ব্যকরণ": "ব্যাকরণ",
    "বানানভুল": "বানান ভুল",
    "এর পর": "এরপর",
    "যদি ও": "যদিও",
    "অবশ্যইই": "অবশ্যই"
}

