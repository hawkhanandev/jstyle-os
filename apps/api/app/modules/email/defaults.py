"""First drafts of every client email. Jessica edits them in Settings; edits are new versions.

Variables available to every template: client_first_name, client_name, wedding_date,
venue, region_name, business_name, business_email, business_phone, venmo, zelle.
Some templates get more (quote, invoice, booking...).
"""

from __future__ import annotations

SIGNATURE = """
<p>Warmly,<br>Jessica<br>{{ business_name }}{% if business_phone %}<br>{{ business_phone }}{% endif %}</p>
"""

QUOTE_TABLE = """
<table style="border-collapse:collapse;min-width:320px">
{% for line in quote.lines %}
  <tr><td style="padding:4px 16px 4px 0">{{ line.description }}{% if line.quantity > 1 %} &times; {{ line.quantity }}{% endif %}</td>
      <td style="padding:4px 0;text-align:right">{{ line.amount }}</td></tr>
{% endfor %}
  <tr><td style="padding:8px 16px 4px 0;border-top:1px solid #ddd"><b>Total</b></td>
      <td style="padding:8px 0 4px;border-top:1px solid #ddd;text-align:right"><b>{{ quote.total }}</b></td></tr>
  <tr><td style="padding:4px 16px 4px 0">Deposit to book (non-refundable)</td><td style="text-align:right">{{ quote.deposit }}</td></tr>
  <tr><td style="padding:4px 16px 4px 0">Remaining balance</td><td style="text-align:right">{{ quote.balance }}</td></tr>
</table>
"""

DEFAULT_TEMPLATES: dict[str, tuple[str, str, str]] = {
    # key: (name, subject, body)
    "enquiry_ack": (
        "Enquiry acknowledgement",
        "Thank you for your enquiry, {{ client_first_name }}!",
        """<p>Hi {{ client_first_name }},</p>
<p>Thank you for reaching out about your wedding{% if wedding_date %} on {{ wedding_date }}{% endif %}{% if venue %} at {{ venue }}{% endif %}! I'm so happy you're considering us.</p>
<p>I'm reviewing your details now and will send you a personalised quote within two business days.</p>"""
        + SIGNATURE,
    ),
    "planner_ack": (
        "Planner enquiry acknowledgement",
        "Thank you, {{ client_first_name }}: your enquiry for {{ wedding_date }}",
        """<p>Hi {{ client_first_name }},</p>
<p>Thank you for thinking of us for your event on {{ wedding_date }}{% if venue %} at {{ venue }}{% endif %}. I'll review the details and come back to you shortly.</p>"""
        + SIGNATURE,
    ),
    "quote": (
        "Quotation",
        "Your hair and makeup quote for {{ wedding_date }}",
        """<p>Hi {{ client_first_name }},</p>
<p>Thank you for your patience! Here is your quote for {{ wedding_date }}{% if venue %} at {{ venue }}{% endif %}:</p>"""
        + QUOTE_TABLE
        + """<p>To book, simply reply to this email to accept. I'll then send your contract and deposit invoice. If you'd like to change anything, just reply and let me know.</p>"""
        + SIGNATURE,
    ),
    "quote_revision": (
        "Revised quotation",
        "Your updated quote for {{ wedding_date }}",
        """<p>Hi {{ client_first_name }},</p>
<p>Here is your updated quote:</p>"""
        + QUOTE_TABLE
        + """<p>Reply to accept, or let me know if anything else should change.</p>"""
        + SIGNATURE,
    ),
    "quote_follow_up": (
        "Quote follow-up",
        "Checking in about your wedding on {{ wedding_date }}",
        """<p>Hi {{ client_first_name }},</p>
<p>I wanted to check whether you had any questions about the quote I sent. I'd love to be part of your day!</p>"""
        + SIGNATURE,
    ),
    "contract_invoice": (
        "Contract and deposit invoice",
        "Your contract and deposit invoice",
        """<p>Hi {{ client_first_name }},</p>
<p>I'm thrilled you've chosen us! Attached are your contract and deposit invoice.</p>
<p>To secure your date, please sign and return the contract and pay the {{ deposit }} deposit by {{ deposit_due }} via Venmo ({{ venmo }}) or Zelle ({{ zelle }}).</p>"""
        + SIGNATURE,
    ),
    "booking_confirmed": (
        "Booking confirmation",
        "You're booked! {{ wedding_date }}",
        """<p>Hi {{ client_first_name }},</p>
<p>Your contract and deposit are received, and your date is officially booked. I can't wait!</p>"""
        + SIGNATURE,
    ),
    "prep_guide": (
        "Wedding preparation guide",
        "Your wedding preparation guide",
        """<p>Hi {{ client_first_name }},</p>
<p>Your wedding is almost here! Attached is your preparation guide with everything to do before the day.</p>"""
        + SIGNATURE,
    ),
    "trial_reminder": (
        "Trial reminder",
        "Reminder: your bridal trial on {{ trial_date }}",
        """<p>Hi {{ client_first_name }},</p>
<p>A quick reminder that your bridal trial is on {{ trial_date }}{% if trial_location %} at {{ trial_location }}{% endif %}. Please arrive with clean, dry hair and a bare face.</p>"""
        + SIGNATURE,
    ),
    "balance_reminder": (
        "Balance reminder",
        "Your remaining balance of {{ balance }}",
        """<p>Hi {{ client_first_name }},</p>
<p>A friendly reminder that your remaining balance of {{ balance }} is due before the wedding. You can pay via Venmo ({{ venmo }}) or Zelle ({{ zelle }}).</p>"""
        + SIGNATURE,
    ),
    "final_timeline": (
        "Final timeline",
        "Your final timeline for {{ wedding_date }}",
        """<p>Hi {{ client_first_name }},</p>
<p>Thank you, your balance is paid in full. Here is the final timeline for your wedding day.</p>"""
        + SIGNATURE,
    ),
    "thank_you_review": (
        "Thank you and review request",
        "Thank you, {{ client_first_name }}!",
        """<p>Hi {{ client_first_name }},</p>
<p>Thank you for letting us be part of your wedding day! If you have a moment, a review would mean the world to me.</p>"""
        + SIGNATURE,
    ),
}
