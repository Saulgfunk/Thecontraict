"""A ready-made example contract, so a new user can see the app with real-looking data.

Dates are relative to today: the contract started eleven months ago, so its notice
deadline falls in the next few weeks and shows up straight away.
"""

import io
from datetime import date
from decimal import Decimal

from app.contract_schemas import ContractCreate, DateRuleIn, PaymentTermIn
from app.models import DateAnchor, DateRuleType, PaymentDirection, PaymentFrequency, PeriodUnit

SAMPLE_TITLE = "Sample: Office cleaning agreement"
COUNTERPARTY = "Sparkle Cleaning Services Ltd"
NOTICE_DAYS = 14
MONTHLY_FEE = Decimal("1250.00")
CURRENCY_BY_COUNTRY = {"GB": "GBP", "US": "USD", "TR": "TRY", "CH": "CHF", "JP": "JPY"}


def _add_months(d: date, months: int) -> date:
    total = d.year * 12 + d.month - 1 + months
    return date(total // 12, total % 12 + 1, min(d.day, 28))


def sample_terms(today: date, country: str | None) -> ContractCreate:
    start = _add_months(today, -11)
    currency = CURRENCY_BY_COUNTRY.get((country or "").upper(), "EUR")
    return ContractCreate(
        title=SAMPLE_TITLE,
        counterparty_name=COUNTERPARTY,
        contract_type="Services",
        effective_date=start,
        initial_term_amount=12,
        initial_term_unit=PeriodUnit.MONTHS,
        auto_renews=True,
        renewal_term_amount=12,
        renewal_term_unit=PeriodUnit.MONTHS,
        governing_law="England and Wales",
        currency=currency,
        contract_value=MONTHLY_FEE * 12,
        notice_details="In writing, by email to contracts@sparkle-cleaning.example",
        date_rules=[
            DateRuleIn(
                rule_type=DateRuleType.NON_RENEWAL_NOTICE,
                label="Notice of non-renewal",
                anchor=DateAnchor.TERM_END,
                offset_amount=NOTICE_DAYS,
                offset_unit=PeriodUnit.DAYS,
            )
        ],
        payment_terms=[
            PaymentTermIn(
                description="Monthly cleaning fee",
                direction=PaymentDirection.PAYABLE,
                amount=MONTHLY_FEE,
                currency=currency,
                frequency=PaymentFrequency.MONTHLY,
                first_due_date=_add_months(start, 1),
                payment_days=30,
            )
        ],
    )


def sample_document(terms: ContractCreate) -> bytes:
    """The signed agreement the terms come from, as a Word file."""
    import docx

    start = terms.effective_date
    assert start is not None
    when = f"{start.day} {start:%B %Y}"
    lines = [
        "OFFICE CLEANING SERVICES AGREEMENT",
        f'This Agreement is made on {when} between {COUNTERPARTY} ("Contractor") and the '
        'Customer named in the order form ("Customer").',
        "1. SERVICES",
        "1.1 The Contractor shall clean the Customer's offices each working day in line with "
        "the specification in Schedule 1.",
        "2. TERM AND RENEWAL",
        f"2.1 This Agreement starts on {when} and continues for an initial term of 12 months.",
        "2.2 It then renews automatically for further periods of 12 months unless either party "
        f"gives the other at least {NOTICE_DAYS} days' written notice of non-renewal before the "
        "end of the then-current term.",
        "3. FEES AND PAYMENT",
        f"3.1 The Customer shall pay a monthly fee of {terms.currency} {MONTHLY_FEE}, invoiced "
        "monthly in arrears and payable within 30 days of the invoice date.",
        "4. NOTICES",
        "4.1 Notices under this Agreement must be in writing and sent by email to "
        "contracts@sparkle-cleaning.example (for the Contractor) or to the address in the "
        "order form (for the Customer).",
        "5. GOVERNING LAW",
        "5.1 This Agreement is governed by the laws of England and Wales.",
        "This is a sample agreement created by TheContrAIct to show how the app works.",
    ]
    document = docx.Document()
    for line in lines:
        document.add_paragraph(line)
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()
