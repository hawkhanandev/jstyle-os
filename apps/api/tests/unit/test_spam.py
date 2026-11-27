from datetime import date

from app.modules.forms import spam

TODAY = date(2026, 12, 1)


def score(**kw: object) -> spam.Verdict:
    base: dict[str, object] = dict(
        email="bride@example.com",
        phone="808-555-0101",
        wedding_date=date(2027, 6, 1),
        region_known=True,
        free_text=["Excited!"],
        today=TODAY,
        has_mail_server=True,
    )
    base.update(kw)
    return spam.score_content(**base)  # type: ignore[arg-type]


def test_clean_submission_scores_zero() -> None:
    assert score().score == 0


def test_disposable_email_is_held() -> None:
    v = score(email="x@mailinator.com")
    assert v.score >= spam.HOLD_THRESHOLD and "disposable_email" in v.reasons


def test_links_and_spam_words_add_up() -> None:
    v = score(free_text=["Best SEO and backlink deals http://a.example http://b.example"])
    assert v.score >= spam.HOLD_THRESHOLD


def test_dates_outside_window() -> None:
    assert "date_in_past" in score(wedding_date=date(2026, 1, 1)).reasons
    assert "date_over_3_years" in score(wedding_date=date(2031, 1, 1)).reasons


def test_form_token_roundtrip_and_forgery() -> None:
    token = spam.issue_form_token("s", now=1_000)
    assert spam.fill_seconds("s", token, now=1_010) == 10
    assert spam.fill_seconds("other", token, now=1_010) is None
    assert spam.fill_seconds("s", "123.bad", now=1_010) is None
    assert spam.fill_seconds("s", None) is None
