"""Validation rules: block export on hard failures; warnings for review."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from apps.documents.models import Document
from apps.extractors import canonical as C
from apps.extractors.utils.normalize import parse_indian_amount


class Severity(str, Enum):
    BLOCK = "block"
    WARN = "warn"


@dataclass
class ValidationIssue:
    code: str
    message: str
    severity: Severity


_PAN_PATTERN = __import__("re").compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")


def _d(val: str | None) -> Decimal | None:
    if val is None or str(val).strip() == "":
        return None
    return parse_indian_amount(str(val))


def coerce_refund_demand_field_map(field_map: dict[str, str]) -> dict[str, str]:
    """
    If refund and demand are both positive but arithmetic matches a refund-only return
    (taxes paid ≥ net tax and refund ≈ paid − net), treat demand as 0 for export/validation.

    This fixes stale review rows where a loose PDF regex captured a spurious demand while
    Part B-TTI line 11 is actually 0.
    """
    out = dict(field_map)
    ref = _d(out.get(C.REFUND_AMOUNT)) or Decimal("0")
    dem = _d(out.get(C.DEMAND_AMOUNT)) or Decimal("0")
    if ref <= 0 or dem <= 0:
        return out
    paid = _d(out.get(C.TAXES_PAID_TOTAL)) or Decimal("0")
    net = _d(out.get(C.NET_TAX_LIABILITY))
    if net is None:
        net = _d(out.get(C.GROSS_TAX_LIABILITY)) or Decimal("0")
    expected_ref = max(Decimal("0"), paid - net)
    tol = Decimal("15")
    if paid >= net and abs(ref - expected_ref) <= tol:
        out[C.DEMAND_AMOUNT] = "0"
    return out


def validate_document_for_export(
    document: Document,
    field_map: dict[str, str],
    detected_type: str,
) -> list[ValidationIssue]:
    """Run all rules. BLOCK issues prevent PDF export."""
    issues: list[ValidationIssue] = []

    if not document.review_completed:
        issues.append(
            ValidationIssue(
                "review_incomplete",
                "Mark review as complete (approve) before export.",
                Severity.BLOCK,
            )
        )

    if detected_type == Document.TYPE_UNKNOWN:
        issues.append(
            ValidationIssue(
                "unknown_type",
                "Document type could not be determined as ITR-1, ITR-3, or ITR-4.",
                Severity.BLOCK,
            )
        )

    pan = field_map.get(C.PAN, "").strip().upper()
    if not pan:
        issues.append(
            ValidationIssue("pan_missing", "PAN is required.", Severity.BLOCK)
        )
    elif not _PAN_PATTERN.match(pan):
        issues.append(
            ValidationIssue("pan_invalid", "PAN format looks invalid.", Severity.BLOCK)
        )

    name = (field_map.get(C.ASSESSEE_NAME) or "").strip()
    if not name:
        issues.append(
            ValidationIssue(
                "name_missing", "Name of assessee is required.", Severity.BLOCK
            )
        )

    ay = (field_map.get(C.ASSESSMENT_YEAR) or "").strip()
    if not ay:
        issues.append(
            ValidationIssue(
                "ay_missing", "Assessment year is required.", Severity.BLOCK
            )
        )

    gti = _d(field_map.get(C.GROSS_TOTAL_INCOME))
    ti = _d(field_map.get(C.TOTAL_INCOME))
    if gti is None:
        issues.append(
            ValidationIssue(
                "gti_missing", "Gross Total Income is required.", Severity.BLOCK
            )
        )
    if ti is None:
        issues.append(
            ValidationIssue(
                "ti_missing", "Total Income is required.", Severity.BLOCK
            )
        )

    gtl = _d(field_map.get(C.GROSS_TAX_LIABILITY))
    ntl = _d(field_map.get(C.NET_TAX_LIABILITY))
    if gtl is None and ntl is None:
        issues.append(
            ValidationIssue(
                "tax_liability_missing",
                "Gross or Net Tax Liability is required.",
                Severity.BLOCK,
            )
        )

    ref = _d(field_map.get(C.REFUND_AMOUNT))
    dem = _d(field_map.get(C.DEMAND_AMOUNT))
    if ref is not None and dem is not None and ref > 0 and dem > 0:
        issues.append(
            ValidationIssue(
                "refund_and_demand",
                "Refund and demand should not both be positive (clear one to zero if this is a refund-only return).",
                Severity.BLOCK,
            )
        )

    # Total Income is rounded u/s 288A and can exceed (GTI − deductions) by up to ₹10;
    # do not treat a small gap as an error.
    ded = _d(field_map.get(C.TOTAL_DEDUCTIONS))
    if ded is None:
        ded = Decimal("0")
    if gti is not None and ti is not None:
        ceiling = gti - ded + Decimal("10")
        if ti > ceiling:
            issues.append(
                ValidationIssue(
                    "ti_inconsistent",
                    "Total Income is much higher than Gross Total Income minus deductions (check values).",
                    Severity.BLOCK,
                )
            )

    biz = _d(field_map.get(C.INCOME_BUSINESS_PROFESSION))
    if detected_type == Document.TYPE_ITR1 and biz is not None and biz > 0:
        issues.append(
            ValidationIssue(
                "itr1_business",
                "ITR-1 normally has no business income; verify form type or set to zero.",
                Severity.WARN,
            )
        )

    if detected_type == Document.TYPE_ITR4:
        if biz is None or biz == 0:
            if not (field_map.get(C.INCOME_SALARY) or "").strip():
                issues.append(
                    ValidationIssue(
                        "itr4_income_heads",
                        "ITR-4: confirm business/salary income heads — values may be incomplete.",
                        Severity.WARN,
                    )
                )

    tds = _d(field_map.get(C.TDS_TOTAL))
    # Annexure reconciliation: soft warning only
    if tds is not None and tds > 0:
        issues.append(
            ValidationIssue(
                "tds_check",
                "Verify TDS annexure rows sum against Total TDS if annexure was extracted.",
                Severity.WARN,
            )
        )

    return issues


def blocking_issues(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    return [i for i in issues if i.severity == Severity.BLOCK]


def issues_after_extraction(
    field_map: dict[str, str],
    detected_type: str,
) -> list[ValidationIssue]:
    """Validation without review gate — used after extraction."""
    issues: list[ValidationIssue] = []
    if detected_type == Document.TYPE_UNKNOWN:
        issues.append(
            ValidationIssue(
                "unknown_type",
                "Could not classify as ITR-1, ITR-3, or ITR-4.",
                Severity.BLOCK,
            )
        )
    pan = field_map.get(C.PAN, "").strip()
    if not pan:
        issues.append(ValidationIssue("pan_missing", "PAN not extracted.", Severity.WARN))
    if not (field_map.get(C.GROSS_TOTAL_INCOME) or "").strip():
        issues.append(
            ValidationIssue("gti_missing", "Gross Total Income not extracted.", Severity.WARN)
        )
    return issues
