from __future__ import annotations

import re


BANGLA_LETTER_PATTERN = re.compile(r"[\u0980-\u09FF]")
BANGLA_WORD_PATTERN = re.compile(r"[\u0980-\u09FF]+")
TOKEN_PATTERN = re.compile(r"[\u0980-\u09FFA-Za-z0-9]+|[^\s]")
PUNCTUATION_CHARS = ",.;:!?।"
PUNCTUATION_PATTERN = re.compile(rf"[{re.escape(PUNCTUATION_CHARS)}]")
SENTENCE_TERMINATORS = frozenset({"।", "!", "?"})

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
    "ঢ়": ("ঢ়", "ঢ"),
}

SAFE_EXACT_TYPOS: dict[str, str] = {
    "বংলা": "বাংলা",
    "ব্যকরন": "ব্যাকরণ",
    "ব্যকরণ": "ব্যাকরণ",
    "ব্যাবহার": "ব্যবহার",
    "কিন্ত": "কিন্তু",
    "বানানভুল": "বানান ভুল",
    "এর পর": "এরপর",
    "যদি ও": "যদিও",
    "অবশ্যইই": "অবশ্যই",
}

CURATED_VARIANT_CORRECTIONS: dict[str, str] = {
    "নিয়ে": "নিয়ে",
    "নিয়েই": "নিয়েই",
    "হয়": "হয়",
    "হয়নি": "হয়নি",
    "হয়েছে": "হয়েছে",
    "দেয়": "দেয়",
}

REDUPLICATION_WHITELIST = frozenset(
    {
        "ধীরে ধীরে",
        "আস্তে আস্তে",
        "রোজ রোজ",
        "দিন দিন",
        "বার বার",
        "ঘরে ঘরে",
        "মাঝে মাঝে",
        "মনে মনে",
        "পথে পথে",
        "দলে দলে",
        "এক এক",
    }
)

POLITE_PRONOUNS = frozenset({"আপনি", "তিনি", "আপনারা", "তাঁরা"})
CASUAL_PRONOUNS = frozenset({"তুমি", "তোমরা"})
FIRST_PERSON_PRONOUNS = frozenset({"আমি", "আমরা"})
THIRD_PERSON_PRONOUNS = frozenset({"সে", "ও", "এ", "তারা", "ওরা", "এরা"})

POLITE_IMPERATIVE_MAP: dict[str, str] = {
    "যাও": "যান",
    "দাও": "দিন",
    "নাও": "নিন",
    "করো": "করুন",
    "খাও": "খান",
    "বলো": "বলুন",
    "দেখো": "দেখুন",
    "শোনো": "শুনুন",
}

HONORIFIC_VERB_MAP: dict[str, str] = {
    **POLITE_IMPERATIVE_MAP,
    "যায়": "যান",
    "খায়": "খান",
    "করে": "করুন",
}

CASUAL_VERB_MAP: dict[str, str] = {
    "যায়": "যাও",
    "খায়": "খাও",
    "করে": "করো",
    "দেয়": "দাও",
    "নেয়": "নাও",
    "আসে": "আসো",
    "থাকে": "থাকো",
    "যান": "যাও",
    "খান": "খাও",
    "করুন": "করো",
}

FIRST_PERSON_VERB_MAP: dict[str, str] = {
    "যায়": "যাই",
    "খায়": "খাই",
    "দেয়": "দিই",
    "নেয়": "নিই",
    "করে": "করি",
    "আসে": "আসি",
    "থাকে": "থাকি",
    "যাবে": "যাব",
    "খাবে": "খাব",
    "করবে": "করব",
    "হবে": "হব",
}

THIRD_PERSON_VERB_MAP: dict[str, str] = {
    "যাই": "যায়",
    "খাই": "খায়",
    "করি": "করে",
    "দিই": "দেয়",
    "নিই": "নেয়",
    "আসি": "আসে",
    "থাকি": "থাকে",
}

COMMON_POSTPOSITIONS = (
    "পর্যন্ত",
    "থেকে",
    "মধ্যে",
    "জন্য",
    "দিকে",
    "সাথে",
    "আগে",
    "সহ",
    "পর",
)

POSTPOSITION_EXCEPTIONS = frozenset({"একদিকে", "অন্যদিকে", "এদিকে", "ওদিকে", "সেদিকে"})
GENITIVE_MARKERS = frozenset({"এর", "র"})
COORDINATORS = frozenset({"এবং"})
COMMON_UNITS = frozenset({"কেজি", "কিমি", "মিটার", "ঘণ্টা", "টাকা", "জন"})

LATIN_TO_BANGLA_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")
BANGLA_TO_LATIN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

CODE_MIX_REPLACEMENTS: dict[str, str] = {
    "tomorrow": "আগামীকাল",
    "today": "আজ",
}

OPENING_DELIMITERS: dict[str, str] = {
    "(": ")",
    "[": "]",
    "{": "}",
    "“": "”",
    "‘": "’",
}

CLOSING_DELIMITERS = {closing: opening for opening, closing in OPENING_DELIMITERS.items()}
