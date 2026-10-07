"""The real-Claude trial script (evals/run_trial.py), run with a stand-in extractor."""

import json
import sys
from datetime import date
from pathlib import Path

import pytest

from app.config import get_settings
from app.pipeline import extract as ext

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "evals"))
import run_trial  # noqa: E402

S = ext.Source(clause_refs=["C3"], quote="q", confidence=0.9)


def lease(correct: bool = True) -> ext.ContractExtraction:
    return ext.ContractExtraction(
        title="Lease of Commercial Premises",
        contract_type="Lease",
        summary="Five-year lease.",
        parties=[ext.Party(name="Harbourside Properties Limited", role="Landlord")],
        counterparty_name="Harbourside Properties Limited",
        effective_date=ext.SourcedDate(value=date(2023, 7, 1), source=S),
        end_date=ext.SourcedDate(value=date(2028, 6, 30), source=S),
        initial_term=ext.SourcedPeriod(
            value=ext.Period(amount=5, unit="years" if correct else "months"), source=S
        ),
        auto_renews=ext.SourcedBool(value=False, source=S),
        renewal_term=None,
        governing_law=ext.SourcedText(value="England and Wales", source=S),
        currency="GBP",
        contract_value=None,
        notice_details=None,
        date_rules=[
            ext.ExtractedDateRule(
                rule_type="option_exercise",
                label="Option to renew",
                anchor="fixed_date",
                fixed_date=date(2028, 6, 30),
                offset=ext.Period(amount=6, unit="months"),
                offset_basis="calendar",
                direction="before",
                deemed_receipt_business_days=2,
                source=S,
            ),
            ext.ExtractedDateRule(
                rule_type="price_review",
                label="Rent review",
                anchor="fixed_date",
                fixed_date=date(2026, 7, 1),
                offset=None,
                offset_basis="calendar",
                direction="before",
                deemed_receipt_business_days=None,
                source=S,
            ),
        ]
        + (
            [
                ext.ExtractedDateRule(
                    rule_type="insurance_expiry",
                    label="Insurance expires",
                    anchor="fixed_date",
                    fixed_date=date(2027, 1, 31),
                    offset=None,
                    offset_basis="calendar",
                    direction="before",
                    deemed_receipt_business_days=None,
                    source=S,
                )
            ]
            if correct
            else []
        ),
        payment_terms=[
            ext.ExtractedPaymentTerm(
                description="Quarterly rent",
                direction="payable",
                amount=30000,
                currency="GBP",
                frequency="quarterly",
                first_due_date=date(2023, 7, 1),
                payment_days=None,
                escalation=None,
                source=S,
            )
        ],
    )


def test_scoring() -> None:
    expected = json.loads((Path(run_trial.HERE) / "expected.json").read_text())["commercial_lease"]
    ok, total, lines = run_trial.score(lease(), expected)
    assert (ok, total) == (10, 10), lines
    ok, total, lines = run_trial.score(lease(correct=False), expected)
    assert total - ok == 2  # wrong term length, missing insurance rule
    assert any("✗ initial_term" in line for line in lines)
    assert any("✗ rule insurance_expiry: not found" in line for line in lines)


def test_script_end_to_end(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    class Stub:
        model = "stub"

        def __init__(self, *args: object) -> None:
            self.xml = ""

        def extract(self, xml: str, context: str) -> ext.ExtractionOutput:
            assert '<clause ref="C10" number="5" page=' not in xml  # DOCX has no pages
            assert "OPTION TO RENEW" in xml
            return ext.ExtractionOutput(
                extraction=lease(), model="stub", input_tokens=10_000, output_tokens=2_000
            )

    settings = get_settings().model_copy(update={"anthropic_api_key": "test"})
    monkeypatch.setattr(run_trial, "get_settings", lambda: settings)
    monkeypatch.setattr(run_trial.ext, "ClaudeExtractor", Stub)
    monkeypatch.setattr(run_trial, "HERE", tmp_path)
    (tmp_path / "contracts").mkdir()
    real = Path(__file__).resolve().parents[1] / "evals"
    (tmp_path / "contracts" / "commercial_lease.txt").write_text(
        (real / "contracts" / "commercial_lease.txt").read_text()
    )
    (tmp_path / "expected.json").write_text((real / "expected.json").read_text())
    monkeypatch.setattr(sys, "argv", ["run_trial.py"])

    run_trial.main()
    out = capsys.readouterr().out
    assert "Score: 10/10" in out
    # Option deadline: 6 months before 30 Jun 2028 = Thu 30 Dec 2027; deemed receipt 2
    # business days in England skips the 27/28 Dec bank holidays → Fri 24 Dec 2027.
    assert "2027-12-24  Option to renew" in out
    assert "TOTAL" in out and "10/10 (100%)" in out
    assert "≈ $0.08" in out
    saved = list((tmp_path / "results").glob("*/commercial_lease.json"))
    assert saved and json.loads(saved[0].read_text())["extraction"]["title"]
