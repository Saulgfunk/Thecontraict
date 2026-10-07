"""AI extraction of contract terms with Claude.

The model reads clauses we have labelled with refs (C1, C2, ...) and returns a strict
JSON structure (structured outputs) in which every value cites the refs it came from.
Dates are *not* calculated here: the model returns rules ("90 days before the end of
the term") and ``app.pipeline.compute`` turns them into dates.
"""

import base64
from datetime import date
from functools import lru_cache
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.config import get_settings

PROMPT_VERSION = "2026-10-07.1"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Source(Strict):
    clause_refs: list[str] = Field(
        description="Refs of the clauses this value comes from, e.g. ['C7']. Empty if inferred."
    )
    quote: str = Field(description="Short verbatim quote (max ~40 words) supporting the value.")
    confidence: float = Field(description="0.0–1.0: how certain the value is correct.")


class Period(Strict):
    amount: int
    unit: Literal["days", "weeks", "months", "years"]


class SourcedDate(Strict):
    value: date
    source: Source


class SourcedPeriod(Strict):
    value: Period
    source: Source


class SourcedBool(Strict):
    value: bool
    source: Source


class SourcedText(Strict):
    value: str
    source: Source


class SourcedNumber(Strict):
    value: float
    source: Source


class Party(Strict):
    name: str
    role: str = Field(description="Role in the contract, e.g. 'Supplier', 'Customer', 'Landlord'.")


class ExtractedDateRule(Strict):
    rule_type: Literal[
        "non_renewal_notice",
        "termination_notice",
        "option_exercise",
        "price_review",
        "warranty_end",
        "insurance_expiry",
        "guarantee_expiry",
        "lock_in_end",
        "other",
    ]
    label: str = Field(description="Short human label, e.g. 'Notice of non-renewal'.")
    anchor: Literal["fixed_date", "effective_date", "term_start", "term_end"] = Field(
        description="The date the offset is measured from. term_end/term_start refer to the "
        "current (initial or renewal) term."
    )
    fixed_date: date | None = Field(description="Required when anchor is fixed_date.")
    offset: Period | None = Field(description="Null when the deadline is the anchor date itself.")
    offset_basis: Literal["calendar", "business"] = Field(
        description="'business' only if the contract says business/working days."
    )
    direction: Literal["before", "after"]
    deemed_receipt_business_days: int | None = Field(
        description="If notices are only deemed received N business days after sending, N."
    )
    source: Source


class ExtractedPaymentTerm(Strict):
    description: str = Field(description="e.g. 'Monthly service fee', 'Annual licence fee'.")
    direction: Literal["receivable", "payable", "unknown"] = Field(
        description="From the user's side, if their party is known; otherwise 'unknown'."
    )
    amount: float | None
    currency: str | None = Field(description="ISO 4217 code, e.g. 'EUR'.")
    frequency: Literal["one_off", "monthly", "quarterly", "semi_annual", "annual", "other"]
    first_due_date: date | None = Field(
        description="First invoice/payment date if stated or directly derivable; else null."
    )
    payment_days: int | None = Field(description="Payment term in days, e.g. 30 for 'net 30'.")
    escalation: str | None = Field(description="Price increase/indexation mechanism, if any.")
    source: Source


class ContractExtraction(Strict):
    title: str = Field(description="Contract title, e.g. 'Master Services Agreement'.")
    contract_type: str = Field(description="Category, e.g. 'Services', 'Lease', 'NDA', 'SaaS'.")
    summary: str = Field(description="2–4 plain-English sentences: who, what, how long, money.")
    parties: list[Party]
    counterparty_name: str | None = Field(
        description="The party on the other side from the user's organization, if identifiable."
    )
    effective_date: SourcedDate | None
    end_date: SourcedDate | None = Field(
        description="Only an explicitly stated expiry date. Do not calculate one."
    )
    initial_term: SourcedPeriod | None
    auto_renews: SourcedBool | None
    renewal_term: SourcedPeriod | None
    governing_law: SourcedText | None
    currency: str | None
    contract_value: SourcedNumber | None = Field(
        description="Total or annual contract value if stated."
    )
    notice_details: SourcedText | None = Field(
        description="How and where formal notices must be given (method, address, recipient)."
    )
    date_rules: list[ExtractedDateRule]
    payment_terms: list[ExtractedPaymentTerm]


class OcrPage(Strict):
    page_number: int
    text: str


class OcrResult(Strict):
    pages: list[OcrPage]


SYSTEM_PROMPT = """\
You are a meticulous contract analyst. You extract key dates, notice periods and \
payment terms from contracts so a legal team can be alerted before deadlines.

Rules:
- Use only what the contract says. If something is not stated, return null or an \
empty list. Never guess a date.
- Every value must cite the clause refs (the `ref` attribute, e.g. "C7") it comes \
from, with a short verbatim quote.
- Do not calculate deadlines. Express them as rules: an anchor (fixed date, effective \
date, start or end of the current term), an offset and a direction. Example: "either \
party may terminate by giving at least three months' written notice before the end of \
the then-current term" → rule_type non_renewal_notice, anchor term_end, offset 3 \
months, direction before.
- A term "commencing on X and continuing for 24 months" is an initial_term of 24 \
months with effective_date X. "Thereafter renews automatically for successive 12-month \
periods" means auto_renews true and renewal_term 12 months.
- Use offset_basis "business" only when the contract says business or working days.
- Include option windows (extension, purchase), price reviews/indexation dates, \
warranty, insurance, guarantee and lock-in end dates when present.
- Payment terms: list each distinct recurring or one-off payment obligation.
- Confidence reflects how unambiguous the wording is, not how important the item is.
"""


def render_clauses(clauses: list[tuple[str, str | None, str | None, int | None, str]]) -> str:
    """clauses: (ref, number, heading, page, text)."""
    parts = []
    for ref, number, heading, page, text in clauses:
        attrs = f'ref="{ref}"'
        if number:
            attrs += f' number="{number}"'
        if page:
            attrs += f' page="{page}"'
        title = f"{heading}\n" if heading else ""
        parts.append(f"<clause {attrs}>\n{title}{text}\n</clause>")
    return "<contract>\n" + "\n".join(parts) + "\n</contract>"


class ExtractionOutput(BaseModel):
    extraction: ContractExtraction
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class Extractor(Protocol):
    model: str

    def extract(self, contract_xml: str, context: str) -> ExtractionOutput: ...
    def transcribe_pdf(self, pdf: bytes) -> list[OcrPage]: ...


class ExtractionError(RuntimeError):
    pass


class ClaudeExtractor:
    def __init__(self, api_key: str, model: str, effort: str) -> None:
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.effort = effort

    def _parse[T: BaseModel](self, output: type[T], system: str, content: list) -> tuple[T, object]:
        # Streaming avoids HTTP timeouts on long documents. Server-side fallbacks re-run the
        # request on a recommended model if a safety classifier declines it.
        with self.client.beta.messages.stream(
            model=self.model,
            max_tokens=64000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            output_config={"effort": self.effort},  # type: ignore[arg-type]
            output_format=output,
            messages=[{"role": "user", "content": content}],
        ) as stream:
            message = stream.get_final_message()
        if message.stop_reason == "refusal":
            raise ExtractionError("The AI model declined to process this document")
        if message.stop_reason == "max_tokens":
            raise ExtractionError("The document is too long to analyse in one pass")
        parsed = message.parsed_output
        if parsed is None:
            raise ExtractionError("The AI response could not be parsed")
        return parsed, message.usage

    def extract(self, contract_xml: str, context: str) -> ExtractionOutput:
        extraction, usage = self._parse(
            ContractExtraction,
            SYSTEM_PROMPT,
            [
                {"type": "text", "text": contract_xml},
                {"type": "text", "text": context},
            ],
        )
        return ExtractionOutput(
            extraction=extraction,
            model=self.model,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
        )

    def transcribe_pdf(self, pdf: bytes) -> list[OcrPage]:
        result, _ = self._parse(
            OcrResult,
            "You transcribe scanned documents exactly, preserving clause numbering, headings "
            "and line breaks. Do not summarise or omit anything.",
            [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": base64.b64encode(pdf).decode(),
                    },
                },
                {"type": "text", "text": "Transcribe every page of this document."},
            ],
        )
        return result.pages


@lru_cache
def get_extractor() -> Extractor:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise ExtractionError("AI analysis is not configured (ANTHROPIC_API_KEY is not set)")
    return ClaudeExtractor(
        settings.anthropic_api_key, settings.anthropic_model, settings.extraction_effort
    )
