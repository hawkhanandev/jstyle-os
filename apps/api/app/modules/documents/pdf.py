"""HTML to PDF with WeasyPrint. Templates live next to this file and are code-owned;
the contract terms inside them come from Settings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

TEMPLATES = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(TEMPLATES),
    autoescape=select_autoescape(["html"]),
    undefined=StrictUndefined,
)


def render_html(template: str, context: dict[str, Any]) -> str:
    css = (TEMPLATES / "base.css").read_text()
    return _env.get_template(template).render(css=css, **context)


def html_to_pdf(html: str) -> bytes:
    from weasyprint import HTML  # type: ignore[import-untyped]  # heavy; only when needed

    pdf: bytes = HTML(string=html, base_url=str(TEMPLATES)).write_pdf()
    return pdf
