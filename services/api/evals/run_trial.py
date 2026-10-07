"""Run the real pipeline against Claude and score the results.

    cd services/api
    export ANTHROPIC_API_KEY=...            # or put it in .env
    uv run python evals/run_trial.py                     # the sample contracts, scored
    uv run python evals/run_trial.py --only commercial_lease --chat "Can we extend the lease?"
    uv run python evals/run_trial.py --file ~/contracts/real.pdf --chat "When must we give notice?"

For each contract: parse → split into clauses → Claude extraction → deadline calculation.
Sample contracts are scored against evals/expected.json. Outputs are saved under
evals/results/ (git-ignored). Prints token usage and an estimated cost.
"""

import argparse
import io
import json
import sys
import time
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.deadlines.engine import Calendar  # noqa: E402
from app.models import (  # noqa: E402
    Contract,
    DateRule,
    DayBasis,
    PaymentTerm,
    PeriodUnit,
    ReviewStatus,
)
from app.pipeline import extract as ext  # noqa: E402
from app.pipeline.compute import compute  # noqa: E402
from app.pipeline.parse import DOCX_MIME, parse, sniff_mime_type  # noqa: E402
from app.pipeline.segment import segment  # noqa: E402

HERE = Path(__file__).resolve().parent
AS_OF = date(2026, 10, 7)  # fixed, so results are comparable between runs
PRICE_PER_MTOK = {"input": 4.00, "output": 20.00}  # Claude Opus 5.5
GOVERNING_LAW_COUNTRY = {
    "germany": "DE",
    "england": "GB",
    "new york": "US",
    "turkey": "TR",
    "türkiye": "TR",
}


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------


def txt_to_docx(text: str) -> bytes:
    import docx

    document = docx.Document()
    for line in text.splitlines():
        if line.strip():
            document.add_paragraph(line.strip())
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


def load(path: Path) -> tuple[bytes, str]:
    if path.suffix == ".txt":
        return txt_to_docx(path.read_text()), DOCX_MIME
    data = path.read_bytes()
    return data, sniff_mime_type(data, path.name)


# ---------------------------------------------------------------------------
# Extraction → in-memory contract → deadlines
# ---------------------------------------------------------------------------


def to_contract(x: ext.ContractExtraction) -> Contract:
    c = Contract(id=uuid.uuid4(), title=x.title, counterparty_name=x.counterparty_name)
    c.effective_date = x.effective_date.value if x.effective_date else None
    c.end_date = x.end_date.value if x.end_date else None
    if x.initial_term:
        c.initial_term_amount = x.initial_term.value.amount
        c.initial_term_unit = PeriodUnit(x.initial_term.value.unit)
    c.auto_renews = x.auto_renews.value if x.auto_renews else None
    if x.renewal_term:
        c.renewal_term_amount = x.renewal_term.value.amount
        c.renewal_term_unit = PeriodUnit(x.renewal_term.value.unit)
    c.date_rules = [
        DateRule(
            id=uuid.uuid4(),
            rule_type=r.rule_type,
            label=r.label,
            anchor=r.anchor,
            fixed_date=r.fixed_date,
            offset_amount=r.offset.amount if r.offset else None,
            offset_unit=r.offset.unit if r.offset else None,
            offset_basis=r.offset_basis,
            direction=r.direction,
            delivery_amount=r.deemed_receipt_business_days or None,
            delivery_basis=DayBasis.BUSINESS,
            review_status=ReviewStatus.AI_SUGGESTED,
        )
        for r in x.date_rules
    ]
    c.payment_terms = [
        PaymentTerm(
            id=uuid.uuid4(),
            description=p.description,
            frequency=p.frequency,
            first_due_date=p.first_due_date,
            review_status=ReviewStatus.AI_SUGGESTED,
        )
        for p in x.payment_terms
    ]
    return c


def calendar_for(x: ext.ContractExtraction) -> Calendar:
    law = (x.governing_law.value if x.governing_law else "").lower()
    for name, code in GOVERNING_LAW_COUNTRY.items():
        if name in law:
            return Calendar(country=code)
    return Calendar()


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def norm_period(amount: int | None, unit: str | None) -> tuple[int, str]:
    if not amount or not unit:
        return (0, "days")
    if unit == "years":
        return (amount * 12, "months")
    if unit == "weeks":
        return (amount * 7, "days")
    return (amount, unit)


def as_list(v: Any) -> list[Any]:
    return (
        v
        if isinstance(v, list)
        and not (
            len(v) == 2 and isinstance(v[1], str) and v[1] in ("days", "weeks", "months", "years")
        )
        else [v]
    )


def rule_matches(exp: dict[str, Any], r: ext.ExtractedDateRule) -> bool:
    if r.rule_type not in as_list(exp["type"]):
        return False
    if "anchor" in exp:
        anchors = as_list(exp["anchor"])
        actual = f"fixed_date:{r.fixed_date}" if r.anchor == "fixed_date" else r.anchor
        if actual not in anchors:
            return False
    if "offset" in exp:
        got = norm_period(
            r.offset.amount if r.offset else None, r.offset.unit if r.offset else None
        )
        if got != norm_period(*exp["offset"]):
            return False
    # Direction only matters when there is an offset.
    has_offset = bool(r.offset and r.offset.amount)
    return not ("direction" in exp and has_offset and r.direction != exp["direction"])


def score(x: ext.ContractExtraction, expected: dict[str, Any]) -> tuple[int, int, list[str]]:
    lines: list[str] = []
    ok = total = 0

    def check(label: str, passed: bool, detail: str, required: bool = True) -> None:
        nonlocal ok, total
        if required:
            total += 1
            ok += passed
        mark = "✓" if passed else ("✗" if required else "·")
        lines.append(f"  {mark} {label}: {detail}")

    fields = expected.get("fields", {})
    actual: dict[str, Any] = {
        "effective_date": str(x.effective_date.value) if x.effective_date else None,
        "end_date": str(x.end_date.value) if x.end_date else None,
        "initial_term": norm_period(x.initial_term.value.amount, x.initial_term.value.unit)
        if x.initial_term
        else None,
        "renewal_term": norm_period(x.renewal_term.value.amount, x.renewal_term.value.unit)
        if x.renewal_term
        else None,
        "auto_renews": x.auto_renews.value if x.auto_renews else None,
        "governing_law": x.governing_law.value if x.governing_law else None,
        "currency": (x.currency or "").upper() or None,
    }
    for key, want in fields.items():
        if key.endswith("~"):
            name = key[:-1]
            got = actual.get(name) or ""
            check(name, want.lower() in got.lower(), f"expected ~{want!r}, got {got!r}")
        else:
            got = actual.get(key)
            want_n = norm_period(*want) if isinstance(want, list) else want
            check(key, got == want_n, f"expected {want_n!r}, got {got!r}")

    remaining = list(x.date_rules)
    for exp in expected.get("rules", []):
        required = exp.get("required", True)
        match = next((r for r in remaining if rule_matches(exp, r)), None)
        label = f"rule {exp['type']}"
        if match:
            remaining.remove(match)
            detail = (
                f"found “{match.label}” ({match.offset.amount if match.offset else 0} "
                f"{match.offset.unit if match.offset else 'days'} {match.direction} {match.anchor})"
            )
            check(label, True, detail, required)
            if "deemed_receipt" in exp:
                got = match.deemed_receipt_business_days
                check(
                    "  deemed receipt",
                    got == exp["deemed_receipt"],
                    f"expected {exp['deemed_receipt']}, got {got}",
                    required,
                )
        else:
            check(label, False, "not found", required)
    for r in remaining:
        lines.append(f"  + extra rule: {r.rule_type} “{r.label}”")

    pay_remaining = list(x.payment_terms)
    for exp in expected.get("payments", []):
        match = next((p for p in pay_remaining if p.frequency == exp["frequency"]), None)
        if not match:
            check(f"payment {exp['frequency']}", False, "not found")
            continue
        pay_remaining.remove(match)
        problems = []
        if "amount" in exp and (match.amount is None or abs(match.amount - exp["amount"]) > 0.01):
            problems.append(f"amount {match.amount} != {exp['amount']}")
        for key in ("first_due_date", "payment_days"):
            if key in exp:
                got = getattr(match, key)
                got = str(got) if got is not None and key == "first_due_date" else got
                if got != exp[key]:
                    problems.append(f"{key} {got} != {exp[key]}")
        check(
            f"payment {exp['frequency']}",
            not problems,
            "; ".join(problems) or f"“{match.description}”",
        )
    if not expected.get("payments") and x.payment_terms:
        check("no payments", False, f"found {len(x.payment_terms)}")
    for p in pay_remaining:
        lines.append(f"  + extra payment: {p.frequency} “{p.description}”")
    return ok, total, lines


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--only", help="run one sample contract by name")
    ap.add_argument("--file", type=Path, action="append", help="your own PDF/DOCX (repeatable)")
    ap.add_argument("--chat", help="also ask this question about each contract")
    ap.add_argument("--effort", default=None, help="extraction effort (default from settings)")
    args = ap.parse_args()

    settings = get_settings()
    if not settings.anthropic_api_key:
        sys.exit("ANTHROPIC_API_KEY is not set (environment or services/api/.env).")
    extractor = ext.ClaudeExtractor(
        settings.anthropic_api_key,
        settings.anthropic_model,
        args.effort or settings.extraction_effort,
    )
    expected_all = json.loads((HERE / "expected.json").read_text())

    if args.file:
        targets = [(p.stem, p) for p in args.file]
    else:
        targets = sorted((p.stem, p) for p in (HERE / "contracts").glob("*.txt"))
        if args.only:
            targets = [t for t in targets if t[0] == args.only]

    out_dir = HERE / "results" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    tokens = {"input": 0, "output": 0}
    scores: list[tuple[str, int, int]] = []

    for name, path in targets:
        print(f"\n=== {name} ===")
        data, mime = load(path)
        parsed = parse(data, mime)
        if parsed.text_source == "needs_ocr":
            print("Scanned PDF: transcribing with Claude…")
            from app.pipeline.parse import Page

            parsed.pages = [Page(p.page_number, p.text) for p in extractor.transcribe_pdf(data)]
        drafts = segment(parsed.pages)
        clauses = [(f"C{i}", d) for i, d in enumerate(drafts, start=1)]
        print(f"{len(clauses)} clauses; {sum(len(d.text) for _, d in clauses):,} characters")
        xml = ext.render_clauses(
            [(r, d.number, d.heading, d.page_start, d.text) for r, d in clauses]
        )

        started = time.monotonic()
        result = extractor.extract(
            xml, "Context: the user's organization is a law firm acting for one of the parties."
        )
        took = time.monotonic() - started
        tokens["input"] += result.input_tokens or 0
        tokens["output"] += result.output_tokens or 0
        x = result.extraction
        print(
            f"Extracted in {took:.0f}s "
            f"({result.input_tokens:,} in / {result.output_tokens:,} out tokens)"
        )
        print(f"Title: {x.title} · {x.contract_type} · counterparty: {x.counterparty_name}")
        print(f"Summary: {x.summary}")

        contract = to_contract(x)
        computed = compute(contract, AS_OF, calendar_for(x))
        print(f"Deadlines as of {AS_OF}:")
        for d in sorted(computed.deadlines, key=lambda d: d.due_date)[:12]:
            print(f"  {d.due_date}  {d.label}")
            for step in d.derivation:
                print(f"      {step}")
        for rule_id, error in computed.rule_errors.items():
            label = next(r.label for r in contract.date_rules if r.id == rule_id)
            print(f"  ! {label}: {error}")

        expected = expected_all.get(name)
        if expected and not args.file:
            ok, total, lines = score(x, expected)
            scores.append((name, ok, total))
            print(f"Score: {ok}/{total}")
            print("\n".join(lines))

        if args.chat:
            from app.chat import ClaudeChat, SourceDoc, resolve_citations

            source = SourceDoc(
                contract.id,
                x.title,
                None,
                [f"[{r}] {d.number or ''} {d.heading or ''}\n{d.text}".strip() for r, d in clauses],
                [r for r, _ in clauses],
                [contract.id for _ in clauses],
            )
            chat = ClaudeChat(
                settings.anthropic_api_key, settings.anthropic_model, settings.chat_effort
            )
            from app.chat import SYSTEM_PROMPT

            print(f"\nQ: {args.chat}\nA: ", end="", flush=True)
            final = None
            for item in chat.stream(
                SYSTEM_PROMPT,
                [
                    {
                        "role": "user",
                        "content": [source.to_param(), {"type": "text", "text": args.chat}],
                    }
                ],
            ):
                if isinstance(item, str):
                    print(item, end="", flush=True)
                else:
                    final = item
            print()
            if final:
                tokens["input"] += final.input_tokens or 0
                tokens["output"] += final.output_tokens or 0
                for b in final.blocks:
                    for cit in resolve_citations(b["citations"], [source], {contract.id: x.title}):
                        print(f"   [{', '.join(cit['clause_refs'])}] “{cit['cited_text'][:120]}”")

        (out_dir / f"{name}.json").write_text(
            json.dumps(
                {
                    "extraction": x.model_dump(mode="json"),
                    "deadlines": [
                        {"date": str(d.due_date), "label": d.label, "derivation": d.derivation}
                        for d in computed.deadlines
                    ],
                    "rule_errors": {str(k): v for k, v in computed.rule_errors.items()},
                },
                indent=2,
            )
        )

    cost = (
        tokens["input"] / 1e6 * PRICE_PER_MTOK["input"]
        + tokens["output"] / 1e6 * PRICE_PER_MTOK["output"]
    )
    print("\n=== Summary ===")
    for name, ok, total in scores:
        print(f"  {name:22s} {ok}/{total}")
    if scores:
        ok = sum(s[1] for s in scores)
        total = sum(s[2] for s in scores)
        print(f"  {'TOTAL':22s} {ok}/{total} ({ok / total:.0%})")
    print(f"Tokens: {tokens['input']:,} in / {tokens['output']:,} out ≈ ${cost:.2f}")
    print(f"Saved to {out_dir.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
