"""Simulated service output for tests only; never used as production fallback."""
import json

from services.coworker.drafting import DraftResult
from services.coworker.schemas import parse_draft


def work_draft(skill_id, language="en", source_ids=None, missing=False):
    ids = list(source_ids or ["notes"])
    title, sentence, morning = {
        "en": ("Project update", "The team completed 12 reviews.", "Morning"),
        "bn": ("প্রকল্পের অগ্রগতি", "দলটি ১২টি পর্যালোচনা সম্পন্ন করেছে।", "সকাল"),
        "ar": ("تحديث المشروع", "أكمل الفريق 12 مراجعة.", "الصباح"),
    }[language]
    value = {"output_language": language, "missing_information": ["Please provide the missing recipient."] if missing else []}
    if skill_id == "email":
        value.update(email={"subject": title, "body": sentence}, source_ids=ids)
    elif skill_id in {"document", "career"}:
        value.update(document={"title": title, "summary": "", "sections": [
            {"heading": title, "paragraphs": [sentence], "bullets": [sentence], "source_ids": ids},
        ]})
    elif skill_id == "social":
        value.update(title=title, posts=[{"platform": platform, "label": title, "text": sentence,
                                        "suggested_timing": None, "source_ids": ids} for platform in ("facebook", "linkedin")])
    elif skill_id == "meeting":
        labels = {
            "en": ["Notes", "Decisions", "Actions", "Owner", "Deadline", "Recorded", "Suggested"],
            "bn": ["আলোচনা", "সিদ্ধান্ত", "করণীয়", "দায়িত্ব", "সময়সীমা", "নথিভুক্ত", "প্রস্তাবিত"],
            "ar": ["ملاحظات", "قرارات", "إجراءات", "المسؤول", "الموعد", "مسجل", "مقترح"],
        }[language]
        value.update(title=title, summary=sentence, labels=dict(zip(["notes", "decisions", "actions", "owner", "deadline", "recorded", "suggested"], labels)),
                     notes=[{"text": sentence, "source_ids": ids}], decisions=[],
                     actions=[{"text": sentence, "owner": None, "deadline": None, "basis": "suggested", "source_ids": ids}])
    else:
        labels = {
            "en": ["High priority", "Normal priority", "Low priority", "Provided", "Suggested"],
            "bn": ["উচ্চ অগ্রাধিকার", "সাধারণ অগ্রাধিকার", "কম অগ্রাধিকার", "প্রদত্ত", "প্রস্তাবিত"],
            "ar": ["أولوية عالية", "أولوية عادية", "أولوية منخفضة", "مقدم", "مقترح"],
        }[language]
        value.update(title=title, overview=sentence, labels=dict(zip(["high", "normal", "low", "provided", "suggested"], labels)),
                     items=[{"task": sentence, "when": morning, "priority": "high", "basis": "suggested", "source_ids": ids}])
    return parse_draft(skill_id, value)


class WorkModel:
    def __init__(self, missing=False):
        self.calls = 0
        self.missing = missing

    def messages(self, task, sources):
        return [{"role": "user", "content": json.dumps({"skill_id": task["skill_id"], "sources": sources})}]

    async def generate(self, messages, language, source_ids):
        self.calls += 1
        skill = json.loads(messages[-1]["content"])["skill_id"]
        return DraftResult(work_draft(skill, language, sorted(source_ids), self.missing), 220, 5)
