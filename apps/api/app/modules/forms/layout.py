"""Editable layout for the public bride and planner forms.

Built-in fields keep their names (the server reads them by name), but their wording, order and,
where safe, visibility and whether they're required can be changed in Settings. Fields the
pricing or the pipeline depends on are locked visible. Custom questions can be added; their
answers are stored with the enquiry's notes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.modules.platform import settings
from app.modules.platform.audit import Actor

Kind = Literal["bride", "planner"]
FieldType = Literal["text", "email", "tel", "date", "number", "select", "textarea"]


@dataclass(frozen=True)
class Builtin:
    name: str
    type: FieldType
    label: str
    wide: bool = False
    # always: must be shown and filled in. pricing: shown always (drives the quote), may be blank.
    lock: Literal["always", "pricing", None] = None
    options: tuple[tuple[str, str], ...] = ()
    placeholder: str = ""


_CONTACT = (("email", "Email"), ("phone", "Phone call"), ("text", "Text"))
_REGION = (("", "Choose…"), ("HI", "Hawaii"), ("OR", "Oregon"))
_SERVICE = (
    ("full", "Hair and makeup"),
    ("hair_only", "Hair only"),
    ("makeup_only", "Makeup only"),
    ("none", "None for the bride"),
)
_YESNO = (("no", "No"), ("yes", "Yes"))

BUILTINS: dict[str, list[Builtin]] = {
    "bride": [
        Builtin("full_name", "text", "Full name", wide=True, lock="always"),
        Builtin("email", "email", "Email", lock="always"),
        Builtin("phone", "tel", "Phone"),
        Builtin("wedding_date", "date", "Wedding date", lock="always"),
        Builtin("preferred_contact", "select", "Preferred contact", options=_CONTACT),
        Builtin("region", "select", "Location", lock="pricing", options=_REGION),
        Builtin("venue_name", "text", "Venue name"),
        Builtin("venue_address", "text", "Venue address", wide=True),
        Builtin("bridal_service", "select", "Bridal service", lock="pricing", options=_SERVICE),
        Builtin("wedding_type", "text", "Wedding type", placeholder="e.g. beach ceremony"),
        Builtin("attendants_hair", "number", "Attendants needing hair", lock="pricing"),
        Builtin("attendants_makeup", "number", "Attendants needing makeup", lock="pricing"),
        Builtin("trial", "select", "Bridal trial", lock="pricing", options=_YESNO),
        Builtin(
            "travel_notes",
            "text",
            "Travel information",
            placeholder="Getting-ready location, timing",
        ),
        Builtin("notes", "textarea", "Anything else?", wide=True),
    ],
    "planner": [
        Builtin("company_name", "text", "Company name", lock="always"),
        Builtin("contact_name", "text", "Your name", lock="always"),
        Builtin("email", "email", "Email", lock="always"),
        Builtin("phone", "tel", "Phone"),
        Builtin("event_date", "date", "Event date", lock="always"),
        Builtin("client_name", "text", "Bride or client name"),
        Builtin("region", "select", "Location", lock="pricing", options=_REGION),
        Builtin("venue_name", "text", "Venue name"),
        Builtin("venue_address", "text", "Venue address", wide=True),
        Builtin("people_count", "number", "Number of people"),
        Builtin("stylists_needed", "number", "Stylists needed"),
        Builtin("services_needed", "textarea", "Services needed", wide=True),
        Builtin("notes", "textarea", "Additional event information", wide=True),
    ],
}

DEFAULT_TEXT = {
    "bride": {"title": "Bridal enquiry", "intro": "", "submit_label": "Send enquiry"},
    "planner": {"title": "Planner enquiry", "intro": "", "submit_label": "Send enquiry"},
}


class FieldOverride(BaseModel):
    label: str | None = Field(default=None, max_length=120)
    help: str | None = Field(default=None, max_length=300)
    placeholder: str | None = Field(default=None, max_length=120)
    hidden: bool = False
    required: bool = False


class CustomQuestion(BaseModel):
    id: str = Field(pattern=r"^c_[a-z0-9]{4,24}$")
    label: str = Field(min_length=1, max_length=200)
    type: Literal["text", "textarea", "select", "yesno", "number"] = "text"
    options: list[str] = Field(default_factory=list, max_length=20)
    required: bool = False
    help: str | None = Field(default=None, max_length=300)
    wide: bool = False

    @field_validator("options")
    @classmethod
    def _clean_options(cls, v: list[str]) -> list[str]:
        return [o.strip()[:100] for o in v if o.strip()]


class FormLayout(BaseModel):
    title: str = Field(max_length=120)
    intro: str = Field(default="", max_length=1000)
    submit_label: str = Field(default="Send enquiry", max_length=60)
    order: list[str] = Field(default_factory=list, max_length=60)
    fields: dict[str, FieldOverride] = Field(default_factory=dict)
    custom: list[CustomQuestion] = Field(default_factory=list, max_length=20)


def _key(kind: str) -> str:
    return f"form_layout_{kind}"


def default_layout(kind: Kind) -> FormLayout:
    t = DEFAULT_TEXT[kind]
    return FormLayout(
        title=t["title"],
        intro=t["intro"],
        submit_label=t["submit_label"],
        order=[b.name for b in BUILTINS[kind]],
    )


def get_layout(db: Session, kind: Kind) -> FormLayout:
    stored = settings.get(db, _key(kind))
    if not stored:
        return normalise(kind, default_layout(kind))
    return normalise(kind, FormLayout.model_validate(stored))


def normalise(kind: Kind, layout: FormLayout) -> FormLayout:
    """Drop unknown names, add any missing built-ins, and re-apply locks."""
    layout = layout.model_copy(deep=True)
    builtin = {b.name: b for b in BUILTINS[kind]}
    custom_ids = {c.id for c in layout.custom}
    if len(custom_ids) != len(layout.custom):
        raise ValueError("Two custom questions share an id.")
    seen: list[str] = []
    for name in layout.order:
        if (name in builtin or name in custom_ids) and name not in seen:
            seen.append(name)
    for name in [*builtin, *[c.id for c in layout.custom]]:
        if name not in seen:
            seen.append(name)
    layout.order = seen
    layout.fields = {k: v for k, v in layout.fields.items() if k in builtin}
    for name, b in builtin.items():
        o = layout.fields.setdefault(name, FieldOverride())
        if b.lock:
            o.hidden = False
        if b.lock == "always":
            o.required = True
        if o.hidden:
            o.required = False
    return layout


def save_layout(db: Session, kind: Kind, layout: FormLayout, actor: Actor) -> FormLayout:
    clean = normalise(kind, layout)
    settings.put(db, _key(kind), clean.model_dump(mode="json"), actor)
    return clean


def public_view(kind: Kind, layout: FormLayout) -> dict[str, Any]:
    """What the public form renders: every visible field, in order, with its final wording."""
    builtin = {b.name: b for b in BUILTINS[kind]}
    custom = {c.id: c for c in layout.custom}
    out: list[dict[str, Any]] = []
    for name in layout.order:
        if name in builtin:
            b = builtin[name]
            o = layout.fields.get(name, FieldOverride())
            if o.hidden:
                continue
            out.append(
                {
                    "name": name,
                    "custom": False,
                    "type": b.type,
                    "label": o.label or b.label,
                    "help": o.help or "",
                    "placeholder": o.placeholder if o.placeholder is not None else b.placeholder,
                    "required": o.required,
                    "wide": b.wide,
                    "options": [{"value": v, "label": lbl} for v, lbl in b.options],
                }
            )
        elif name in custom:
            c = custom[name]
            opts = (
                [{"value": "no", "label": "No"}, {"value": "yes", "label": "Yes"}]
                if c.type == "yesno"
                else [{"value": o, "label": o} for o in c.options]
            )
            out.append(
                {
                    "name": c.id,
                    "custom": True,
                    "type": "select" if c.type == "yesno" else c.type,
                    "label": c.label,
                    "help": c.help or "",
                    "placeholder": "",
                    "required": c.required,
                    "wide": c.wide or c.type == "textarea",
                    "options": opts,
                }
            )
    return {
        "title": layout.title,
        "intro": layout.intro,
        "submit_label": layout.submit_label,
        "fields": out,
    }


def editor_view(kind: Kind, layout: FormLayout) -> dict[str, Any]:
    return {
        "layout": layout.model_dump(mode="json"),
        "builtins": [
            {"name": b.name, "type": b.type, "label": b.label, "lock": b.lock, "wide": b.wide}
            for b in BUILTINS[kind]
        ],
        "defaults": DEFAULT_TEXT[kind],
    }


class MissingAnswers(Exception):
    def __init__(self, labels: list[str]) -> None:
        super().__init__(", ".join(labels))
        self.labels = labels


def _blank(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _invalid(c: CustomQuestion, text: str) -> bool:
    if c.type == "select":
        return bool(c.options) and text not in c.options
    if c.type == "number":
        return re.fullmatch(r"-?\d+(\.\d+)?", text) is None
    return False


def check_answers(
    kind: Kind, layout: FormLayout, values: dict[str, Any], custom: dict[str, Any]
) -> list[dict[str, str]]:
    """Enforce the layout's required fields and turn custom answers into label/value pairs."""
    builtin = {b.name: b for b in BUILTINS[kind]}
    missing: list[str] = []
    for name, o in layout.fields.items():
        if o.required and not o.hidden and _blank(values.get(name)):
            missing.append(o.label or builtin[name].label)
    answers: list[dict[str, str]] = []
    for c in layout.custom:
        v = custom.get(c.id)
        if _blank(v):
            if c.required:
                missing.append(c.label)
            continue
        text = str(v).strip()[:2000]
        if c.type == "yesno":
            text = "Yes" if text.lower() in ("yes", "true", "1") else "No"
        elif _invalid(c, text):
            continue
        answers.append({"label": c.label, "value": text})
    if missing:
        raise MissingAnswers(missing)
    return answers
