"""First-draft contract terms. Jessica replaces these in Settings before go-live."""

BRIDE_TERMS = """<p class="draft">DRAFT TERMS: to be reviewed and replaced by Jessica in Settings before use.</p>
<ol>
<li><strong>Reservation.</strong> The date is reserved only when this agreement is signed and the deposit is received. The deposit is non-refundable and is credited to the total.</li>
<li><strong>Balance.</strong> The balance is due by the date shown above. The final day-of timeline is sent once the balance is paid in full.</li>
<li><strong>Changes to services.</strong> Changes to the number of people or services should be requested in writing. Additions depend on availability and are priced at the current rates; the updated total is confirmed in writing.</li>
<li><strong>Timeline.</strong> The client provides an accurate getting-ready location, start time and headcount. Delays caused by late arrivals may shorten service time.</li>
<li><strong>Travel and parking.</strong> Travel fees are as shown above. Parking, ferry or toll costs at the venue are paid by the client.</li>
<li><strong>Trial.</strong> If a trial is included, it is scheduled by mutual agreement before the wedding.</li>
<li><strong>Cancellation by the client.</strong> Notice must be given in writing. The deposit is not refunded.</li>
<li><strong>Cancellation by us.</strong> If we cannot provide the services for reasons beyond our control, we will try to arrange a qualified replacement; otherwise all payments are refunded.</li>
<li><strong>Health.</strong> Please tell us about allergies or skin sensitivities before the wedding.</li>
<li><strong>Photos.</strong> We may share photos of our work unless the client asks us not to in writing.</li>
</ol>"""

PLANNER_TERMS = (
    BRIDE_TERMS.replace("The client provides", "The planner provides").replace(
        "paid by the client", "paid by the planner or client"
    )
    + "<p>When booked through a planner, the planner is our point of contact for timeline and headcount.</p>"
)
