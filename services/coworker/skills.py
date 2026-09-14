"""Versioned, server-owned work services. No model-generated routes or tools."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .errors import CoworkerError

SkillId = Literal["report_email", "email", "document", "career", "social", "meeting", "daily_plan", "personal_plan"]


@dataclass(frozen=True)
class WorkSkill:
    id: SkillId
    name: str
    description: str
    instruction: str
    guidance: str
    output: str
    filename: str

    @property
    def version(self):
        return "report_email_v1" if self.id == "report_email" else f"work_{self.id}_v1"

    def public(self):
        return {key: getattr(self, key) for key in ("id", "name", "description", "instruction", "output")}


SKILLS = {
    skill.id: skill for skill in [
        WorkSkill("report_email", "Report & email", "Turn your sources into a report and an email draft.",
                  "Turn these sources into a professional report and a short email sharing the key findings.",
                  "Create a professional report and an accompanying email draft.", "Report, email, DOCX, PDF", "report"),
        WorkSkill("email", "Email", "Draft replies, follow-ups, introductions, and professional emails.",
                  "Write a clear, professional email from these details. Keep the important facts and use an appropriate tone.",
                  "Create only the requested email with a subject and body. For replies use the supplied thread as context. "
                  "Do not invent recipients, commitments, attachments or prior correspondence. Never claim the email was sent.",
                  "Email draft, TXT, DOCX, PDF", "email-draft"),
        WorkSkill("document", "Official documents", "Prepare letters, proposals, applications, memos, and SOPs.",
                  "Prepare a professional document from these details. Use the structure and formality appropriate to my request.",
                  "Create the requested document type, such as a letter, application, proposal, memo, or SOP. "
                  "For letters use a suitable salutation and closing. Do not invent signatures, approvals, policies or legal authority. "
                  "Keep the document ready for editing; an empty summary is appropriate for a letter.",
                  "Editable document, DOCX, PDF, TXT", "document"),
        WorkSkill("career", "Career", "Build CVs, cover letters, bios, and interview preparation.",
                  "Create career material tailored to the role in my notes. Use only my actual experience, education, and skills.",
                  "Create the requested CV, resume, cover letter, bio, or interview preparation. "
                  "Use clear sections and concise bullets when useful. Never invent employment, dates, degrees, skills, "
                  "achievements, metrics or certifications. Preserve the candidate's facts and mark essential gaps. "
                  "Job descriptions describe requirements, not facts about the candidate. Do not promise hiring or ATS scores.",
                  "Career document, DOCX, PDF, TXT", "career-document"),
        WorkSkill("social", "Social content", "Create Facebook and LinkedIn posts, captions, and content plans.",
                  "Write social posts from these details for the platform and audience I describe. Keep the voice natural.",
                  "Create one to six ready-to-review posts for the requested platforms. "
                  "Include hashtags in each post only when appropriate or requested. Do not invent endorsements, "
                  "testimonials, audience numbers, offers or product claims. A post is a draft, never a publication. "
                  "Suggested timing is descriptive only; it does not schedule a post.",
                  "Post drafts, TXT, DOCX, PDF", "social-posts"),
        WorkSkill("meeting", "Meetings", "Prepare agendas, minutes, decisions, and follow-up actions.",
                  "Turn these notes into clear meeting minutes with decisions and follow-up actions. Leave unknown owners or deadlines blank.",
                  "Create an agenda or minutes as requested. Distinguish proposals from recorded decisions. "
                  "Only include a decision if the source says it was agreed. Separate existing action items from suggestions. "
                  "For an agenda, leave decisions and recorded actions empty unless the source supports them. "
                  "Never invent attendees, owners or deadlines; use null for unknown owners/deadlines.",
                  "Meeting notes and actions, DOCX, PDF, TXT", "meeting-notes"),
        WorkSkill("daily_plan", "Daily planner", "Organize priorities, routines, schedules, and checklists.",
                  "Create a realistic daily or weekly plan from my priorities and constraints. Show useful next steps and leave room for breaks.",
                  "Create a proposed plan from the user's priorities, availability and constraints. "
                  "Use descriptive time labels such as 'Morning' or 'Monday afternoon' if exact dates/times are absent. "
                  "Never infer a timezone or convert relative dates into invented calendar dates. "
                  "Separate user commitments from proposed tasks. No reminder or calendar event has been created.",
                  "Proposed plan and checklist, DOCX, PDF, TXT", "daily-plan"),
        WorkSkill("personal_plan", "Personal plans", "Organize events, household tasks, shopping, and travel ideas.",
                  "Create a practical personal plan from these details, preferences, and constraints. Include a clear checklist.",
                  "Create the requested household, event, shopping, or travel outline from the supplied facts. "
                  "Suggestions may be creative but must be marked as proposed. Do not invent live prices, opening hours, "
                  "availability, reservations or bookings. Put requests needing current information in missing_information. "
                  "Use descriptive time labels when dates/timezones are unknown. Nothing is booked, purchased or scheduled.",
                  "Personal plan and checklist, DOCX, PDF, TXT", "personal-plan"),
    ]
}


def skill_for_version(version: str) -> WorkSkill:
    for skill in SKILLS.values():
        if skill.version == version:
            return skill
    raise CoworkerError("workflow_version", "This task needs a newer coworker version. Please contact support.", 409)


def available_skills(work_services_enabled: bool):
    return [skill.public() for skill in SKILLS.values() if work_services_enabled or skill.id == "report_email"]
