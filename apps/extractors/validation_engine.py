"""
Field-by-field computation validation against extracted ITR data.

Produces PASS / WARN / FAIL findings for CA-style review and PDF exception notes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Any

from apps.documents.models import BankDetail, Document, TDSDetail
from apps.extractors import canonical as C
from apps.extractors.utils import normalize as N


class Severity(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    INFO = "INFO"


@dataclass(frozen=True)
class ValidationFinding:
    field: str
    rule: str
    status: Severity
    message: str
    expected: str | None = None
    actual: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "rule": self.rule,
            "status": self.status.value,
            "message": self.message,
            "expected": self.expected,
            "actual": self.actual,
        }


def _d(fm: dict[str, str], key: str) -> Decimal | None:
    return N.parse_indian_amount(fm.get(key) or "")


def _pan_ok(pan: str) -> bool:
    return bool(re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]$", (pan or "").strip().upper()))


def round_total_income_288a(amount: Decimal) -> Decimal:
    """Round to nearest multiple of ₹10 (common return presentation; u/s 288A)."""
    q = Decimal("10")
    return (amount / q).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * q


def financial_year_from_ay(ay: str) -> str:
    """AY '2022-23' -> FY '2021-22'."""
    ay = (ay or "").strip()
    m = re.match(r"^(\d{4})\s*[-–]\s*(\d{2})$", ay)
    if not m:
        return ""
    y1 = int(m.group(1))
    y2 = int(m.group(2))
    if y2 != (y1 + 1) % 100:
        return ""
    fy_start = y1 - 1
    fy_end = (y1 % 100)
    return f"{fy_start}-{fy_end:02d}"


def run_computation_validation(
    field_map: dict[str, str],
    bank_rows: list[BankDetail],
    tds_rows: list[TDSDetail],
    detected_type: str,
) -> list[ValidationFinding]:
    """Run deterministic rules; does not require a second 'golden' ITR object."""
    out: list[ValidationFinding] = []
    fm = field_map

    def add(
        field: str,
        rule: str,
        status: Severity,
        message: str,
        expected: str | None = None,
        actual: str | None = None,
    ) -> None:
        out.append(
            ValidationFinding(
                field=field,
                rule=rule,
                status=status,
                message=message,
                expected=expected,
                actual=actual,
            )
        )

    # M1–M4 metadata
    name = (fm.get(C.ASSESSEE_NAME) or "").strip()
    add(
        C.ASSESSEE_NAME,
        "M1",
        Severity.PASS if name else Severity.FAIL,
        "Name of assessee must not be blank." if not name else "Name present.",
        "non-blank",
        name[:80] or None,
    )
    pan = (fm.get(C.PAN) or "").strip().upper()
    add(
        C.PAN,
        "M2",
        Severity.PASS if _pan_ok(pan) else Severity.WARN,
        "PAN must match format [AAAAA9999A]."
        if not _pan_ok(pan)
        else "PAN format valid.",
        "[A-Z]{5}[0-9]{4}[A-Z]",
        pan or None,
    )
    ay = (fm.get(C.ASSESSMENT_YEAR) or "").strip()
    add(
        C.ASSESSMENT_YEAR,
        "M3",
        Severity.PASS if ay else Severity.FAIL,
        "Assessment year should be present." if not ay else "Assessment year present.",
        "non-blank",
        ay or None,
    )
    itr = (fm.get(C.ITR_TYPE) or "").strip()
    add(
        C.ITR_TYPE,
        "M4",
        Severity.PASS if itr else Severity.FAIL,
        "ITR form type should be present." if not itr else "ITR type present.",
        "non-blank",
        itr or None,
    )
    fd = (fm.get(C.FILING_DATE) or "").strip()
    add(
        C.FILING_DATE,
        "M5",
        Severity.PASS if fd else Severity.WARN,
        "Filing date not extracted; add parser rule or enter manually in review."
        if not fd
        else "Filing date present.",
        "from ITR",
        fd or None,
    )
    regime = (fm.get(C.REGIME) or "").strip()
    add(
        C.REGIME,
        "M6",
        Severity.PASS if regime else Severity.WARN,
        "Tax regime (old/new) not extracted; verify Part A / regime selection."
        if not regime
        else "Tax regime present.",
        "non-blank",
        regime or None,
    )

    # I1 Gross total: ITR-1/4 use four heads; ITR-3 Part B-TI uses line 6 vs line 10 when extracted.
    b1 = _d(fm, C.INCOME_SALARY) or Decimal("0")
    b2 = _d(fm, C.INCOME_HOUSE_PROPERTY) or Decimal("0")
    b3 = _d(fm, C.INCOME_BUSINESS_PROFESSION) or Decimal("0")
    b4 = _d(fm, C.INCOME_OTHER_SOURCES) or Decimal("0")
    gti = _d(fm, C.GROSS_TOTAL_INCOME)
    sum_heads = b1 + b2 + b3 + b4
    head_wise_total = _d(fm, C.TOTAL_HEAD_WISE_INCOME)
    is_itr3 = detected_type == Document.TYPE_ITR3 or "ITR-3" in (fm.get(C.ITR_TYPE) or "")
    if gti is not None:
        if is_itr3 and head_wise_total is not None:
            ok = head_wise_total == gti
            add(
                C.GROSS_TOTAL_INCOME,
                "I1",
                Severity.PASS if ok else Severity.FAIL,
                "GTI (Part B-TI 10) should equal total head-wise income (line 6)."
                if not ok
                else "GTI matches Part B-TI line 6.",
                str(head_wise_total),
                str(gti),
            )
        else:
            ok = sum_heads == gti
            add(
                C.GROSS_TOTAL_INCOME,
                "I1",
                Severity.PASS if ok else Severity.FAIL,
                "GTI should equal salary + house + business + other sources."
                if not ok
                else "GTI matches head-wise sum.",
                str(sum_heads),
                str(gti),
            )
    else:
        add(
            C.GROSS_TOTAL_INCOME,
            "I1",
            Severity.WARN,
            "GTI missing; cannot verify I1.",
            str(head_wise_total if is_itr3 and head_wise_total is not None else sum_heads),
            None,
        )

    # I3 Total income vs GTI - deductions (allow ₹10 u/s 288A rounding)
    ded = _d(fm, C.TOTAL_DEDUCTIONS) or Decimal("0")
    ti = _d(fm, C.TOTAL_INCOME)
    if gti is not None and ti is not None:
        expected = gti - ded
        diff = abs(ti - expected)
        ok = diff <= Decimal("10")
        add(
            C.TOTAL_INCOME,
            "I3",
            Severity.PASS if ok else Severity.WARN,
            "Total income should equal GTI − Chapter VI-A (±₹10 for rounding)."
            if not ok
            else "Total income reconciles with GTI − deductions (within rounding).",
            str(expected),
            str(ti),
        )

    # I4 Rounded total income u/s 288A
    rti = _d(fm, C.ROUNDED_TOTAL_INCOME)
    if ti is not None and rti is not None:
        exp_r = round_total_income_288a(ti)
        ok_r = exp_r == rti
        add(
            C.ROUNDED_TOTAL_INCOME,
            "I4",
            Severity.PASS if ok_r else Severity.WARN,
            "Rounded total income should match TI rounded to nearest ₹10 u/s 288A."
            if not ok_r
            else "Rounded total income matches TI (nearest ₹10).",
            str(exp_r),
            str(rti),
        )

    # Refund vs demand (TAX8)
    ref = _d(fm, C.REFUND_AMOUNT) or Decimal("0")
    dem = _d(fm, C.DEMAND_AMOUNT) or Decimal("0")
    add(
        "refund_demand",
        "TAX8",
        Severity.PASS if not (ref > 0 and dem > 0) else Severity.FAIL,
        "Refund and demand should not both be positive."
        if ref > 0 and dem > 0
        else "Refund/demand mutually consistent.",
        "not both > 0",
        f"refund={ref}, demand={dem}",
    )

    # TAX6 / TAX7 — refund & demand vs taxes paid vs net liability (allow ₹2 for rounding / 288B)
    net_tax = _d(fm, C.NET_TAX_LIABILITY)
    if net_tax is None:
        net_tax = _d(fm, C.GROSS_TAX_LIABILITY) or Decimal("0")
    paid_total = _d(fm, C.TAXES_PAID_TOTAL) or Decimal("0")
    tol = Decimal("2")
    if ref > 0:
        expected_ref = max(Decimal("0"), paid_total - net_tax)
        rounded_r = _d(fm, C.ROUNDED_REFUND_AMOUNT)
        ok_ref = abs(ref - expected_ref) <= tol or (
            rounded_r is not None and abs(rounded_r - expected_ref) <= tol and ref == rounded_r
        )
        add(
            C.REFUND_AMOUNT,
            "TAX6",
            Severity.PASS if ok_ref else Severity.WARN,
            "Refund should reconcile with taxes paid minus net tax (±₹2 for rounding)."
            if not ok_ref
            else "Refund reconciles with paid vs liability (within rounding).",
            str(expected_ref),
            str(ref),
        )
    if dem > 0:
        expected_dem = max(Decimal("0"), net_tax - paid_total)
        ok_dem = abs(dem - expected_dem) <= tol
        add(
            C.DEMAND_AMOUNT,
            "TAX7",
            Severity.PASS if ok_dem else Severity.WARN,
            "Demand should reconcile with net tax minus taxes paid (±₹2)."
            if not ok_dem
            else "Demand reconciles with liability vs paid.",
            str(expected_dem),
            str(dem),
        )

    # TDS rows vs D15
    d15 = _d(fm, C.TDS_TOTAL)
    tds_claim_sum = Decimal("0")
    for t in tds_rows:
        c = t.amount_claimed_this_year or t.total_tax_deducted
        if c is not None:
            tds_claim_sum += c
    if d15 is not None and d15 > 0:
        if not tds_rows:
            add(
                "tds_schedule",
                "TDS2",
                Severity.FAIL,
                "Total TDS (D15) > 0 but no TDS line items extracted.",
                str(d15),
                "0 rows",
            )
        elif tds_claim_sum != d15:
            add(
                "tds_reconciliation",
                "TDS1",
                Severity.WARN,
                "Sum of TDS line claimed amounts should match Total TDS on income.",
                str(d15),
                str(tds_claim_sum),
            )
        else:
            add(
                "tds_schedule",
                "TDS1",
                Severity.PASS,
                "TDS line items present and sum matches Total TDS.",
                str(d15),
                str(tds_claim_sum),
            )
    elif d15 == Decimal("0") and not tds_rows:
        add("tds_schedule", "TDS2", Severity.PASS, "No TDS per return; no lines expected.", "0", "0 rows")

    # TDS row quality
    for i, row in enumerate(tds_rows):
        if not (row.tan_pan or "").strip():
            add(f"tds_row_{i}_tan", "TDS5", Severity.FAIL, "TDS row missing TAN/PAN.", "non-blank", None)
        if row.total_tax_deducted and row.amount_claimed_this_year:
            if row.amount_claimed_this_year > row.total_tax_deducted:
                add(
                    f"tds_row_{i}_claim",
                    "TDS3",
                    Severity.WARN,
                    "TDS claimed exceeds TDS deducted on a row.",
                    str(row.total_tax_deducted),
                    str(row.amount_claimed_this_year),
                )
        cl = row.amount_claimed_this_year or Decimal("0")
        if cl and cl > 0:
            if row.amount_paid is None or row.amount_paid <= 0:
                add(
                    f"tds_row_{i}_gross",
                    "TDS4",
                    Severity.WARN,
                    "TDS claimed > 0 but gross receipt / amount paid missing or zero.",
                    ">0",
                    str(row.amount_paid) if row.amount_paid is not None else None,
                )
            if not (row.head_of_income or "").strip():
                add(
                    f"tds_row_{i}_head",
                    "TDS4",
                    Severity.WARN,
                    "TDS claimed > 0 but head of income not extracted.",
                    "non-blank",
                    None,
                )

    # 44AD / turnover
    biz_inc = _d(fm, C.INCOME_BUSINESS_PROFESSION) or Decimal("0")
    dig = _d(fm, C.BP_TURNOVER_44AD)
    oth = _d(fm, C.BP_RECEIPTS_OTHER_MODE_44AD)
    biz_name = (fm.get(C.BUSINESS_NAME) or "").strip()
    if detected_type == Document.TYPE_ITR4 and biz_inc > 0:
        add(
            C.BUSINESS_NAME,
            "BIZ1",
            Severity.PASS if biz_name else Severity.FAIL,
            "Business name should be present when business income is offered."
            if not biz_name
            else "Business name present.",
            "non-blank",
            biz_name[:120] or None,
        )
    if detected_type == Document.TYPE_ITR4 and biz_inc > 0:
        if dig is None and oth is None:
            add(
                "44ad_turnover",
                "BIZ6",
                Severity.WARN,
                "Business income > 0 but digital/other turnover not extracted; CA review recommended.",
                "E1a/E1b",
                None,
            )
        elif (dig or Decimal("0")) + (oth or Decimal("0")) == 0 and biz_inc > 0:
            add(
                "44ad_turnover",
                "BIZ5",
                Severity.WARN,
                "Turnover fields are zero while business income is positive; verify extraction.",
                ">0",
                "0",
            )
        elif dig is not None and oth is not None:
            statutory_min = Decimal("0.06") * (dig or Decimal("0")) + Decimal("0.08") * (oth or Decimal("0"))
            if statutory_min > 0 and biz_inc + Decimal("0.01") < statutory_min:
                add(
                    "44ad_minimum",
                    "BIZ7",
                    Severity.FAIL,
                    "Income offered is below 6%/8% presumptive minimum on stated turnover (no relief context in data).",
                    f">= {statutory_min:.2f}",
                    str(biz_inc),
                )

    # Banks
    if not bank_rows:
        add("bank_accounts", "BANK1", Severity.WARN, "No bank accounts extracted; verify Schedule BA.", ">=1", "0")
    else:
        yes = sum(1 for b in bank_rows if (b.nominate_for_refund or "").lower() == "yes")
        add(
            "refund_bank",
            "BANK2",
            Severity.PASS if yes > 0 else Severity.WARN,
            "At least one account should be marked for refund (Yes) when refund expected."
            if yes == 0
            else "Refund nomination captured for at least one account.",
            ">=1 Yes",
            str(yes),
        )
        if yes > 1:
            add(
                "refund_bank_multi",
                "BANK3",
                Severity.INFO,
                "Multiple bank accounts marked for refund credit — preserve all in summary.",
                "1",
                str(yes),
            )
        for b in bank_rows:
            ifsc = (b.ifsc or "").replace(" ", "").upper()
            if ifsc and not re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", ifsc):
                add(
                    f"ifsc_{ifsc}",
                    "BANK4",
                    Severity.WARN,
                    f"IFSC format unusual: {ifsc}",
                    "[A-Z]{{4}}0[A-Z0-9]{{6}}",
                    ifsc,
                )

    # Other sources narrative
    os_amt = _d(fm, C.INCOME_OTHER_SOURCES) or Decimal("0")
    if os_amt > 0 and not (fm.get(C.OTHER_SOURCE_NATURE) or "").strip():
        add(
            C.OTHER_SOURCE_NATURE,
            "OS2",
            Severity.WARN,
            "Other sources > 0 but nature/description line not extracted.",
            "description",
            None,
        )

    return out


def findings_summary(findings: list[ValidationFinding]) -> dict[str, int]:
    counts = {s.value: 0 for s in Severity}
    for f in findings:
        counts[f.status.value] = counts.get(f.status.value, 0) + 1
    return counts
