import pytest

from app.modules.replies.classify import classify, latest_text
from app.modules.replies.models import Intent


@pytest.mark.parametrize(
    ("body", "intent"),
    [
        ("Hi Jessica! We'd love to book with you. How do we pay the deposit?", Intent.ACCEPT),
        ("Sounds perfect! Please send over the contract.", Intent.ACCEPT),
        ("Let's book it :)", Intent.ACCEPT),
        ("We accept the quote.", Intent.ACCEPT),
        ("Could we add one more bridesmaid for hair?", Intent.CHANGE_REQUEST),
        ("We'd love to book but can we also do makeup for my mom?", Intent.CHANGE_REQUEST),
        ("Hair only for the bridesmaids instead please", Intent.CHANGE_REQUEST),
        ("Thank you, but we decided to go with another artist.", Intent.DECLINE),
        ("Unfortunately it's out of our budget.", Intent.DECLINE),
        ("We found someone else, thanks anyway!", Intent.DECLINE),
        ("What time would you arrive on the day?", Intent.QUESTION),
        ("Thanks Jessica, talk soon.", Intent.OTHER),
    ],
)
def test_intents(body: str, intent: Intent) -> None:
    assert classify(body).intent == intent


def test_quoted_history_is_ignored() -> None:
    body = (
        "Thanks, what time would you arrive?\n\n"
        "On Fri, Nov 27, 2026 at 9:00 AM Jstyle <jessica@jstyle.example> wrote:\n"
        "> To accept, reply and we'll send the contract and deposit invoice.\n"
    )
    assert "accept" not in latest_text(body)
    assert classify(body).intent == Intent.QUESTION


def test_mixed_signals_lower_confidence() -> None:
    c = classify("We'd love to book! Could we add one more bridesmaid?")
    assert c.intent == Intent.CHANGE_REQUEST and c.confidence == "medium"
