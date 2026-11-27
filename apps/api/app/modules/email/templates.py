from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import nh3
from jinja2 import StrictUndefined, TemplateError
from jinja2.sandbox import SandboxedEnvironment
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.modules.email.defaults import DEFAULT_TEMPLATES
from app.modules.email.models import EmailTemplate
from app.modules.platform.audit import Actor, write_audit

ENV = SandboxedEnvironment(autoescape=True, undefined=StrictUndefined)
TAG = re.compile(r"<[^>]+>")


class TemplateMissing(Exception):
    pass


class TemplateInvalid(Exception):
    pass


@dataclass(frozen=True)
class Rendered:
    subject: str
    html: str
    text: str
    template_key: str
    template_version: int


def html_to_text(html: str) -> str:
    text = re.sub(r"(?i)<br\s*/?>|</p>|</tr>", "\n", html)
    text = re.sub(r"(?i)</td>", "  ", text)
    text = TAG.sub("", text)
    text = re.sub(r"&times;", "x", text)
    text = re.sub(r"&amp;", "&", text)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(line.strip() for line in text.splitlines())).strip()


def render_strings(subject: str, body: str, context: dict[str, Any]) -> tuple[str, str]:
    try:
        subj = ENV.from_string(subject).render(**context)
        html = ENV.from_string(body).render(**context)
    except TemplateError as exc:
        raise TemplateInvalid(str(exc)) from exc
    # Subjects are plain text; autoescape may have escaped characters like '&'.
    subj = subj.replace("&amp;", "&").replace("&#39;", "'").replace("&quot;", '"')
    return " ".join(subj.split()), nh3.clean(html)


def active(db: Session, key: str) -> EmailTemplate:
    row = db.scalar(select(EmailTemplate).where(EmailTemplate.key == key, EmailTemplate.is_active))
    if row is None:
        raise TemplateMissing(key)
    return row


def render(db: Session, key: str, context: dict[str, Any]) -> Rendered:
    tpl = active(db, key)
    subject, html = render_strings(tpl.subject, tpl.body, context)
    return Rendered(subject, html, html_to_text(html), tpl.key, tpl.version)


def save_version(
    db: Session, actor: Actor, key: str, name: str, subject: str, body: str
) -> EmailTemplate:
    # Validate syntax before saving (rendering with real data happens at send time).
    try:
        ENV.parse(subject)
        ENV.parse(body)
    except TemplateError as exc:
        raise TemplateInvalid(str(exc)) from exc
    db.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"email_template:{key}"))))
    version = (
        db.scalar(select(func.max(EmailTemplate.version)).where(EmailTemplate.key == key)) or 0
    ) + 1
    db.execute(
        update(EmailTemplate)
        .where(EmailTemplate.key == key, EmailTemplate.is_active)
        .values(is_active=False)
    )
    row = EmailTemplate(
        key=key, version=version, name=name, subject=subject, body=body, is_active=True
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        actor,
        "email_template.save",
        entity_type="email_template",
        entity_id=row.id,
        after={"key": key, "version": version},
    )
    return row


def ensure_defaults(db: Session, actor: Actor) -> int:
    created = 0
    for key, (name, subject, body) in DEFAULT_TEMPLATES.items():
        if db.scalar(select(EmailTemplate.id).where(EmailTemplate.key == key)) is None:
            save_version(db, actor, key, name, subject, body)
            created += 1
    return created
