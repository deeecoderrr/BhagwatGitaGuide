"""Filed ITR JSON → canonical ExtractedField / BankDetail / TDSDetail rows."""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.db import transaction

from apps.documents.models import BankDetail, Document, ExtractedField, TDSDetail
from apps.extractors import canonical as C
from apps.extractors.utils import normalize as N
from apps.extractors.validators import issues_after_extraction
from apps.exports.tax_slabs import round_refund_288b, round_total_income_288a
from apps.extractors.india_state_codes import state_name_from_code

AMOUNT_FIELDS = set(C.INCOME_FIELDS + C.TAX_FIELDS)


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _dig(obj: Any, *keys: str, default: Any = None) -> Any:
    cur = obj
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur


def _fmt_num(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, Decimal):
        return str(v.quantize(Decimal("1")))
    if isinstance(v, float):
        return str(int(v)) if v == int(v) else str(v)
    if isinstance(v, int):
        return str(v)
    s = str(v).strip()
    return s


def _normalize_amount_field(field_name: str, raw_norm: str) -> str:
    if field_name not in AMOUNT_FIELDS:
        return raw_norm
    d = N.parse_indian_amount(raw_norm)
    if d is None:
        return raw_norm.strip()
    return N.normalize_decimal_string(d)


def _format_ay(assessment_year_field: str) -> str:
    """Form_ITR3 AssessmentYear is often '2025' → '2025-26'."""
    y = (assessment_year_field or "").strip()
    if len(y) == 4 and y.isdigit():
        yy = int(y)
        return f"{yy}-{str(yy + 1)[-2:]}"
    return y


def _format_fy_from_ay(ay: str) -> str:
    if "-" in ay and len(ay) >= 7:
        p = ay.split("-", 1)[0].strip()
        if len(p) == 4 and p.isdigit():
            yy = int(p)
            return f"{yy - 1}-{str(yy)[-2:]}"
    return ""


def _format_dob_iso(iso: str) -> str:
    raw = (iso or "").strip()
    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
        y, m, d = raw[:4], raw[5:7], raw[8:10]
        months = (
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        )
        mi = int(m) - 1
        if 0 <= mi < 12:
            return f"{int(d):02d}-{months[mi]}-{y}"
    return raw


def _compose_address(addr: dict[str, Any] | None) -> str:
    if not addr:
        return ""
    parts = [
        _fmt_num(addr.get("ResidenceNo")),
        _fmt_num(addr.get("ResidenceName")),
        _fmt_num(addr.get("RoadOrStreet")),
        _fmt_num(addr.get("LocalityOrArea")),
        _fmt_num(addr.get("CityOrTownOrDistrict")),
    ]
    pin = addr.get("PinCode")
    st_code = _fmt_num(addr.get("StateCode"))
    st_name = state_name_from_code(addr.get("StateCode"))
    line = ", ".join(p for p in parts if p and p != "None")
    tail = []
    if pin:
        if st_name:
            tail.append(f"{st_name}-{pin}")
        elif st_code:
            tail.append(f"{st_code}-{pin}")
        else:
            tail.append(str(pin))
    elif st_name:
        tail.append(st_name)
    elif st_code:
        tail.append(st_code)
    if tail:
        line = f"{line}, {' '.join(tail)}" if line else " ".join(tail)
    return line.strip()


def _return_file_sec_label(code: Any) -> str:
    try:
        c = int(code)
    except (TypeError, ValueError):
        return _fmt_num(code)
    mapping = {
        11: "139(1) — Original",
        12: "139(4) — Belated",
        13: "139(5) — Revised",
    }
    return mapping.get(c, f"Section code {c}")


def _return_file_sec_filing_status(code: Any) -> str:
    try:
        c = int(code)
    except (TypeError, ValueError):
        return ""
    mapping = {
        11: "Original Return",
        12: "Belated Return",
        13: "Revised Return",
    }
    return mapping.get(c, "")


def _status_individual(code: str) -> str:
    c = (code or "").strip().upper()
    if c == "I":
        return "Individual"
    if c == "H":
        return "HUF"
    return code or ""


def _residential_status(code: str) -> str:
    c = (code or "").strip().upper()
    if c == "RES":
        return "Resident"
    if c == "NRI":
        return "Non-resident"
    if c == "NOR":
        return "Not ordinarily resident"
    return code or ""


def _normalize_tds_section(sec: str) -> str:
    s = (sec or "").strip().upper()
    if len(s) == 3 and s.isalnum() and s.startswith("9"):
        return f"1{s}"
    return s


def _account_type_label(code: str) -> str:
    c = (code or "").strip().upper()
    if c == "SB":
        return "Savings"
    if c == "CA":
        return "Current"
    if c == "CC":
        return "Cash Credit"
    if c == "OD":
        return "Overdraft"
    return code or ""


def _gender_label(raw: Any) -> str:
    x = _fmt_num(raw).strip().upper()
    if x in ("F", "FEMALE", "2"):
        return "Female"
    if x in ("M", "MALE", "1"):
        return "Male"
    if x in ("O", "OTHER", "3"):
        return "Other"
    return ""


def _normalize_bank_refund_nomination(rows: list[dict[str, Any]]) -> None:
    """If JSON marks multiple accounts for refund, keep Yes on the last row only (CA-style)."""
    if len(rows) < 2:
        return
    yes_ix = [i for i, r in enumerate(rows) if r.get("nominate_for_refund") == "Yes"]
    if len(yes_ix) <= 1:
        return
    for i in yes_ix[:-1]:
        rows[i]["nominate_for_refund"] = "No"


def _itr3_salary_tds_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """One Schedule TDS1 / Form-16-style TDS-on-salary row (or same shape as Schedule TDS2)."""
    if not isinstance(row, dict):
        return None
    cr_box = row.get("TaxDeductCreditDtls")
    has_cr = isinstance(cr_box, dict)
    has_gross = row.get("GrossAmount") is not None
    if has_cr or has_gross:
        cr = cr_box if isinstance(cr_box, dict) else {}
        tan = _fmt_num(row.get("TANOfDeductor"))
        nm = _fmt_num(
            row.get("NameOfDeductor")
            or row.get("NameofDeductor")
            or row.get("EmployerOrCollecterName")
        )
        sec = _normalize_tds_section(_fmt_num(row.get("TDSSection")))
        ho = _fmt_num(row.get("HeadOfIncome")).strip()
        if not ho:
            ho = "Salary"
        return {
            "deductor_name": nm or tan,
            "tan_pan": tan,
            "section": sec,
            "amount_paid": row.get("GrossAmount"),
            "total_tax_deducted": cr.get("TaxDeductedOwnHands"),
            "amount_claimed_this_year": cr.get("TaxClaimedOwnHands"),
            "carry_forward": row.get("AmtCarriedFwd"),
            "head_of_income": ho,
        }
    deductor = row.get("EmployerOrDeductorOrCollectDetl") or {}
    tan = _fmt_num(deductor.get("TAN"))
    name = _fmt_num(deductor.get("EmployerOrDeductorOrCollecterName"))
    sec = _normalize_tds_section(_fmt_num(row.get("TDSSection")))
    ded_yr = _fmt_num(row.get("DeductedYr")).strip()
    sec_disp = f"{sec} ({ded_yr})" if ded_yr else sec
    return {
        "deductor_name": name or tan,
        "tan_pan": tan,
        "section": sec_disp,
        "amount_paid": row.get("AmtForTaxDeduct"),
        "total_tax_deducted": row.get("TotTDSOnAmtPaid"),
        "amount_claimed_this_year": row.get("ClaimOutOfTotTDSOnAmtPaid"),
        "carry_forward": row.get("AmtCarriedFwd"),
        "head_of_income": "Salary",
    }


def _collect_itr3_schedule_tds1_rows(itr3: dict[str, Any]) -> list[dict[str, Any]]:
    rows_out: list[dict[str, Any]] = []
    sch = itr3.get("ScheduleTDS1")
    if isinstance(sch, dict):
        for key in ("TDSSalaryDtls", "TDSSalary", "TDSalaryDtls", "TDSalary"):
            lst = sch.get(key)
            if isinstance(lst, list) and lst:
                for row in lst:
                    parsed = _itr3_salary_tds_row(row)
                    if parsed:
                        rows_out.append(parsed)
                break
    if not rows_out:
        ts = itr3.get("TDSonSalary")
        if isinstance(ts, dict):
            for key in ("TDSonSalary", "TDSSalaryDtls", "TDSalaryDtls"):
                lst = ts.get(key)
                if isinstance(lst, list) and lst:
                    for row in lst:
                        parsed = _itr3_salary_tds_row(row)
                        if parsed:
                            rows_out.append(parsed)
                    break
    return rows_out


def _itr3_tds_from_salary_total_str(itr3: dict[str, Any]) -> str:
    """Total TDS on salary from utility totals (Schedule TDS1 or legacy TDSonSalary)."""
    sch = itr3.get("ScheduleTDS1")
    if isinstance(sch, dict):
        for key in ("TotalTDSonSalary", "TotalTDSonSalaries", "TotalTDSSalary"):
            if sch.get(key) is not None:
                return _fmt_num(sch.get(key))
    ts = itr3.get("TDSonSalary")
    if isinstance(ts, dict) and ts.get("TotalTDSonSalary") is not None:
        return _fmt_num(ts.get("TotalTDSonSalary"))
    return ""


def _infer_regime_label(itr3: dict[str, Any], total_income: Decimal) -> str:
    tax_json = _dig(
        itr3,
        "PartB_TTI",
        "ComputationOfTaxLiability",
        "TaxPayableOnTI",
        "TaxAtNormalRatesOnAggrInc",
    )
    try:
        filed = Decimal(str(tax_json))
    except Exception:
        return "As per return (verify regime)"
    from apps.exports.tax_slabs import new_regime_tax_at_normal_rates

    computed = new_regime_tax_at_normal_rates(total_income)
    if abs(filed - computed) <= Decimal("2"):
        return "New Regime"
    return "As per return (verify regime)"


def _infer_regime_label_itr3(itr3: dict[str, Any], total_income: Decimal) -> str:
    """Prefer explicit utility flag on Part A; fall back to new-regime slab match."""
    fs = _dig(itr3, "PartA_GEN1", "FilingStatus") or {}
    opt = _fmt_num(fs.get("OptOutNewTaxRegime")).strip().upper()
    if opt == "N":
        return "New Regime"
    if opt == "Y":
        return "Old Regime"
    return _infer_regime_label(itr3, total_income)


def _infer_regime_label_itr1(itr1: dict[str, Any]) -> str:
    filing_status = _dig(itr1, "FilingStatus") or {}
    opt_out = _fmt_num(filing_status.get("OptOutNewTaxRegime")).strip().upper()
    if opt_out == "N":
        return "New Regime"
    if opt_out == "Y":
        return "Old Regime"
    return "As per return (verify regime)"


def _parse_itr1(
    itr1: dict[str, Any],
) -> tuple[dict[str, str], list[dict[str, Any]], list[dict[str, Any]]]:
    fields: dict[str, str] = {}

    form = _dig(itr1, "Form_ITR1") or {}
    ay_raw = _fmt_num(form.get("AssessmentYear"))
    ay = _format_ay(ay_raw)
    fields[C.ASSESSMENT_YEAR] = ay
    fields[C.FINANCIAL_YEAR] = _format_fy_from_ay(ay)
    fields[C.ITR_TYPE] = "ITR-1"

    pi = _dig(itr1, "PersonalInfo") or {}
    fn = _fmt_num(_dig(pi, "AssesseeName", "FirstName"))
    sn = _fmt_num(_dig(pi, "AssesseeName", "SurNameOrOrgName"))
    fields[C.ASSESSEE_NAME] = f"{fn} {sn}".strip()
    fields[C.PAN] = _fmt_num(pi.get("PAN")).upper()
    fields[C.DATE_OF_BIRTH] = _format_dob_iso(_fmt_num(pi.get("DOB")))
    fields[C.STATUS] = _status_individual(_fmt_num(pi.get("Status")))
    fields[C.AADHAAR] = _fmt_num(pi.get("AadhaarCardNo"))
    addr = pi.get("Address") if isinstance(pi.get("Address"), dict) else None
    fields[C.EMAIL] = _fmt_num(_dig(addr, "EmailAddress") if addr else None)
    fields[C.MOBILE] = _fmt_num(_dig(addr, "MobileNo") if addr else None)
    fields[C.ADDRESS] = _compose_address(addr)
    fields[C.GENDER] = _gender_label(pi.get("Gender"))
    fields[C.RESIDENTIAL_STATUS] = _residential_status(
        _fmt_num(pi.get("ResidentialStatus"))
    )
    fields[C.EMPLOYER_CATEGORY] = _fmt_num(pi.get("EmployerCategory"))

    fs = _dig(itr1, "FilingStatus") or {}
    fields[C.FILING_SECTION] = _return_file_sec_label(fs.get("ReturnFileSec"))
    fields[C.FILING_STATUS] = _return_file_sec_filing_status(fs.get("ReturnFileSec"))
    fields[C.ORIGINAL_OR_REVISED] = fields[C.FILING_STATUS] or fields[C.FILING_SECTION]
    fields[C.FILING_DUE_DATE] = _fmt_num(fs.get("ItrFilingDueDate"))
    fields[C.SEVENTH_PROVISO_139] = _fmt_num(fs.get("SeventhProvisio139"))

    ver = _dig(itr1, "Verification") or {}
    ver_decl = _dig(ver, "Declaration") or {}
    fields[C.FATHER_NAME] = _fmt_num(ver_decl.get("FatherName"))
    fields[C.FILING_DATE] = _fmt_num(ver.get("Date"))
    fields[C.VERIFICATION_PLACE] = _fmt_num(ver.get("Place"))

    income = _dig(itr1, "ITR1_IncomeDeductions") or {}
    fields[C.SALARY_GROSS] = _fmt_num(income.get("GrossSalary"))
    fields[C.SALARY_AS_PER_SECTION_17] = _fmt_num(income.get("Salary"))
    fields[C.NET_SALARY_UTILITY] = _fmt_num(income.get("NetSalary"))
    allw_ex = income.get("AllwncExemptUs10")
    if isinstance(allw_ex, dict):
        fields[C.ALLOWANCES_EXEMPT_US10_TOTAL] = _fmt_num(
            allw_ex.get("TotalAllwncExemptUs10")
        )
    fields[C.STANDARD_DEDUCTION_US16IA] = _fmt_num(income.get("DeductionUs16ia"))
    fields[C.DEDUCTION_US16_TOTAL] = _fmt_num(income.get("DeductionUs16"))
    fields[C.ENTERTAINMENT_ALLOWANCE_US16II] = _fmt_num(
        income.get("EntertainmentAlw16ii")
    )
    fields[C.PROFESSIONAL_TAX_US16III] = _fmt_num(income.get("ProfessionalTaxUs16iii"))

    fields[C.INCOME_SALARY] = _fmt_num(income.get("IncomeFromSal"))
    fields[C.INCOME_BUSINESS_PROFESSION] = "0"
    fields[C.INCOME_HOUSE_PROPERTY] = _fmt_num(income.get("TotalIncomeOfHP"))
    fields[C.INCOME_OTHER_SOURCES] = _fmt_num(income.get("IncomeOthSrc"))
    fields[C.GROSS_TOTAL_INCOME] = _fmt_num(income.get("GrossTotIncome"))
    fields[C.TOTAL_HEAD_WISE_INCOME] = _fmt_num(income.get("GrossTotIncome"))

    chap = _dig(income, "DeductUndChapVIA") or {}
    fields[C.TOTAL_DEDUCTIONS] = _fmt_num(chap.get("TotalChapVIADeductions"))
    fields[C.DEDUCTION_80C] = _fmt_num(chap.get("Section80C"))
    fields[C.DEDUCTION_80D] = _fmt_num(chap.get("Section80D"))
    fields[C.DEDUCTION_80TTA] = _fmt_num(chap.get("Section80TTA"))
    fields[C.DEDUCTION_80G] = _fmt_num(chap.get("Section80G"))

    total_income = income.get("TotalIncome")
    fields[C.TOTAL_INCOME] = _fmt_num(total_income)
    try:
        total_income_d = (
            Decimal(str(total_income)) if total_income is not None else Decimal("0")
        )
    except Exception:
        total_income_d = Decimal("0")
    fields[C.ROUNDED_TOTAL_INCOME] = _fmt_num(round_total_income_288a(total_income_d))
    fields[C.REGIME] = _infer_regime_label_itr1(itr1)

    # ITR-1 is typically filed without CYLA set-off rows; utility still expects GTI chain.
    fields[C.CURRENT_YEAR_LOSSES_ADJUSTMENT] = "0"
    fields[C.BALANCE_AFTER_CYLA] = fields[C.GROSS_TOTAL_INCOME]
    fields[C.BROUGHT_FORWARD_LOSS_SETOFF] = "0"

    others_rows = _dig(income, "OthersInc", "OthersIncDtlsOthSrc")
    if isinstance(others_rows, list):
        nature_parts: list[str] = []
        savings_interest = Decimal("0")
        term_and_other = Decimal("0")
        refund_interest = Decimal("0")
        for row in others_rows:
            if not isinstance(row, dict):
                continue
            desc_raw = _fmt_num(row.get("OthSrcNatureDesc"))
            desc_u = desc_raw.strip().upper()
            if desc_raw:
                extra = _fmt_num(row.get("OthSrcOthNatOfInc")).strip()
                if extra:
                    nature_parts.append(f"{desc_raw} ({extra})")
                else:
                    nature_parts.append(desc_raw)
            try:
                amt = Decimal(str(row.get("OthSrcOthAmount") or 0))
            except Exception:
                amt = Decimal("0")
            if desc_u == "SAV":
                savings_interest += amt
            elif desc_u == "TAX":
                refund_interest += amt
            else:
                term_and_other += amt
        fields[C.OTHER_SOURCE_NATURE] = ", ".join(nature_parts)
        fields[C.OS_INTEREST_SAVINGS] = _fmt_num(savings_interest)
        fields[C.OS_INTEREST_TERM_DEPOSIT] = _fmt_num(term_and_other)
        fields[C.OS_INTEREST_REFUND] = _fmt_num(refund_interest)

    tax_comp = _dig(itr1, "ITR1_TaxComputation") or {}
    fields[C.TAX_NORMAL_RATES] = _fmt_num(tax_comp.get("TotalTaxPayable"))
    fields[C.REBATE_87A] = _fmt_num(tax_comp.get("Rebate87A"))
    fields[C.TAX_PAYABLE_ON_TOTAL_INCOME] = _fmt_num(tax_comp.get("TaxPayableOnRebate"))
    fields[C.CESS] = _fmt_num(tax_comp.get("EducationCess"))
    fields[C.GROSS_TAX_LIABILITY] = _fmt_num(tax_comp.get("GrossTaxLiability"))
    fields[C.NET_TAX_LIABILITY] = _fmt_num(tax_comp.get("NetTaxLiability"))
    fields[C.TAX_RELIEF] = _fmt_num(tax_comp.get("Section89"))
    fields[C.INTEREST_234A] = _fmt_num(_dig(tax_comp, "IntrstPay", "IntrstPayUs234A"))
    fields[C.INTEREST_234B] = _fmt_num(_dig(tax_comp, "IntrstPay", "IntrstPayUs234B"))
    fields[C.INTEREST_234C] = _fmt_num(_dig(tax_comp, "IntrstPay", "IntrstPayUs234C"))
    fields[C.FEE_234F] = _fmt_num(_dig(tax_comp, "IntrstPay", "LateFilingFee234F"))
    fields[C.TOTAL_TAX_PLUS_INTEREST] = _fmt_num(tax_comp.get("TotTaxPlusIntrstPay"))

    paid = _dig(itr1, "TaxPaid", "TaxesPaid") or {}
    fields[C.ADVANCE_TAX] = _fmt_num(paid.get("AdvanceTax"))
    fields[C.SELF_ASSESSMENT_TAX] = _fmt_num(paid.get("SelfAssessmentTax"))
    fields[C.TDS_TOTAL] = _fmt_num(paid.get("TDS"))
    fields[C.TCS_TOTAL] = _fmt_num(paid.get("TCS"))
    fields[C.TAXES_PAID_TOTAL] = _fmt_num(paid.get("TotalTaxesPaid"))
    fields[C.TDS_OTHER_THAN_SALARY] = _fmt_num(
        _dig(itr1, "TDSonOthThanSals", "TotalTDSonOthThanSals")
    )
    fields[C.TDS_FROM_SALARY] = _fmt_num(
        _dig(itr1, "TDSonSalary", "TotalTDSonSalary")
    )

    demand_amount = _dig(itr1, "TaxPaid", "BalTaxPayable")
    fields[C.DEMAND_AMOUNT] = _fmt_num(demand_amount)
    ref_amt = _dig(itr1, "Refund", "RefundDue")
    try:
        ref_d = Decimal(str(ref_amt)) if ref_amt is not None else Decimal("0")
    except Exception:
        ref_d = Decimal("0")
    try:
        paid_d = Decimal(str(paid.get("TotalTaxesPaid") or 0))
        net_tax_d = Decimal(str(tax_comp.get("NetTaxLiability") or 0))
        pre_ref = max(paid_d - net_tax_d, Decimal("0"))
    except Exception:
        pre_ref = ref_d
    fields[C.REFUND_PRE_288B] = _fmt_num(pre_ref)
    fields[C.REFUND_AMOUNT] = _fmt_num(ref_amt)
    fields[C.ROUNDED_REFUND_AMOUNT] = _fmt_num(round_refund_288b(ref_d))

    bank_rows: list[dict[str, Any]] = []
    add_banks = _dig(itr1, "Refund", "BankAccountDtls", "AddtnlBankDetails")
    if isinstance(add_banks, list):
        for b in add_banks:
            if not isinstance(b, dict):
                continue
            ur = _fmt_num(b.get("UseForRefund")).lower()
            nom = "Yes" if ur in ("true", "1", "yes", "y") else "No"
            bank_rows.append(
                {
                    "bank_name": _fmt_num(b.get("BankName")),
                    "ifsc": _fmt_num(b.get("IFSCCode")),
                    "account_number": _fmt_num(b.get("BankAccountNo")),
                    "account_type": _account_type_label(_fmt_num(b.get("AccountType"))),
                    "nominate_for_refund": nom,
                }
            )
    _normalize_bank_refund_nomination(bank_rows)

    tds_rows: list[dict[str, Any]] = []
    tds_list = _dig(itr1, "TDSonOthThanSals", "TDSonOthThanSal")
    if isinstance(tds_list, list):
        for row in tds_list:
            if not isinstance(row, dict):
                continue
            deductor = row.get("EmployerOrDeductorOrCollectDetl") or {}
            tan = _fmt_num(deductor.get("TAN"))
            sec = _normalize_tds_section(_fmt_num(row.get("TDSSection")))
            ded_yr = _fmt_num(row.get("DeductedYr")).strip()
            sec_disp = f"{sec} ({ded_yr})" if ded_yr else sec
            tds_rows.append(
                {
                    "deductor_name": _fmt_num(
                        deductor.get("EmployerOrDeductorOrCollecterName")
                    ),
                    "tan_pan": tan,
                    "section": sec_disp,
                    "amount_paid": row.get("AmtForTaxDeduct"),
                    "total_tax_deducted": row.get("TotTDSOnAmtPaid"),
                    "amount_claimed_this_year": row.get("ClaimOutOfTotTDSOnAmtPaid"),
                    "carry_forward": None,
                    "head_of_income": _fmt_num(row.get("HeadOfIncome")),
                }
            )

    return fields, bank_rows, tds_rows


def _parse_itr4(
    itr4: dict[str, Any],
) -> tuple[dict[str, str], list[dict[str, Any]], list[dict[str, Any]]]:
    """Filed ITR-4 (Sugam): presumptive u/s 44AD/44ADA/44AE + optional salary/OS."""
    fields: dict[str, str] = {}

    form = _dig(itr4, "Form_ITR4") or {}
    ay_raw = _fmt_num(form.get("AssessmentYear"))
    ay = _format_ay(ay_raw)
    fields[C.ASSESSMENT_YEAR] = ay
    fields[C.FINANCIAL_YEAR] = _format_fy_from_ay(ay)
    fields[C.ITR_TYPE] = "ITR-4"

    pi = _dig(itr4, "PersonalInfo") or {}
    fn = _fmt_num(_dig(pi, "AssesseeName", "FirstName"))
    sn = _fmt_num(_dig(pi, "AssesseeName", "SurNameOrOrgName"))
    fields[C.ASSESSEE_NAME] = f"{fn} {sn}".strip()
    fields[C.PAN] = _fmt_num(pi.get("PAN")).upper()
    fields[C.DATE_OF_BIRTH] = _format_dob_iso(_fmt_num(pi.get("DOB")))
    fields[C.STATUS] = _status_individual(_fmt_num(pi.get("Status")))
    fields[C.AADHAAR] = _fmt_num(pi.get("AadhaarCardNo"))
    addr = pi.get("Address") if isinstance(pi.get("Address"), dict) else None
    fields[C.EMAIL] = _fmt_num(_dig(addr, "EmailAddress") if addr else None)
    fields[C.MOBILE] = _fmt_num(_dig(addr, "MobileNo") if addr else None)
    fields[C.ADDRESS] = _compose_address(addr)
    fields[C.GENDER] = _gender_label(pi.get("Gender"))
    fields[C.RESIDENTIAL_STATUS] = _residential_status(
        _fmt_num(pi.get("ResidentialStatus"))
    )
    fields[C.EMPLOYER_CATEGORY] = _fmt_num(pi.get("EmployerCategory"))

    fs = _dig(itr4, "FilingStatus") or {}
    fields[C.FILING_SECTION] = _return_file_sec_label(fs.get("ReturnFileSec"))
    fields[C.FILING_STATUS] = _return_file_sec_filing_status(fs.get("ReturnFileSec"))
    fields[C.ORIGINAL_OR_REVISED] = fields[C.FILING_STATUS] or fields[C.FILING_SECTION]
    fields[C.FILING_DUE_DATE] = _fmt_num(fs.get("ItrFilingDueDate"))
    fields[C.SEVENTH_PROVISO_139] = _fmt_num(fs.get("SeventhProvisio139"))

    ver = itr4.get("Verification")
    if not isinstance(ver, dict):
        ver = {}
    if not ver:
        inc_box = _dig(itr4, "IncomeDeductions") or {}
        vb = inc_box.get("Verification")
        if isinstance(vb, dict):
            ver = vb
    ver_decl = _dig(ver, "Declaration") or {}
    fields[C.FATHER_NAME] = _fmt_num(ver_decl.get("FatherName"))
    fields[C.FILING_DATE] = _fmt_num(ver.get("Date"))
    fields[C.VERIFICATION_PLACE] = _fmt_num(ver.get("Place"))

    income = _dig(itr4, "IncomeDeductions") or {}
    fields[C.SALARY_GROSS] = _fmt_num(income.get("GrossSalary"))
    fields[C.SALARY_AS_PER_SECTION_17] = _fmt_num(income.get("Salary"))
    fields[C.NET_SALARY_UTILITY] = _fmt_num(income.get("NetSalary"))
    allw_ex = income.get("AllwncExemptUs10")
    if isinstance(allw_ex, dict):
        fields[C.ALLOWANCES_EXEMPT_US10_TOTAL] = _fmt_num(
            allw_ex.get("TotalAllwncExemptUs10")
        )
    fields[C.STANDARD_DEDUCTION_US16IA] = _fmt_num(income.get("DeductionUs16ia"))
    fields[C.DEDUCTION_US16_TOTAL] = _fmt_num(income.get("DeductionUs16"))
    ent_amt = income.get("EntertainmentAlw16ii")
    if ent_amt is None:
        ent_amt = income.get("EntertainmntalwncUs16ii")
    fields[C.ENTERTAINMENT_ALLOWANCE_US16II] = _fmt_num(ent_amt)
    fields[C.PROFESSIONAL_TAX_US16III] = _fmt_num(income.get("ProfessionalTaxUs16iii"))

    fields[C.INCOME_SALARY] = _fmt_num(income.get("IncomeFromSal"))
    fields[C.INCOME_BUSINESS_PROFESSION] = _fmt_num(income.get("IncomeFromBusinessProf"))

    sch_bp = _dig(itr4, "ScheduleBP") or {}
    nab = sch_bp.get("NatOfBus44AD")
    if isinstance(nab, list) and nab:
        nb0 = nab[0]
        if isinstance(nb0, dict):
            fields[C.BUSINESS_NAME] = _fmt_num(nb0.get("NameOfBusiness"))
            fields[C.BUSINESS_CODE] = _fmt_num(nb0.get("CodeAD"))
    p44 = _dig(sch_bp, "PersumptiveInc44AD") or {}
    fields[C.BP_TURNOVER_44AD] = _fmt_num(p44.get("GrsTotalTrnOver"))
    fields[C.BP_RECEIPTS_OTHER_MODE_44AD] = _fmt_num(p44.get("GrsTrnOverAnyOthMode"))
    presumptive_total = p44.get("TotPersumptiveInc44AD")
    if presumptive_total is None:
        presumptive_total = p44.get("PersumptiveInc44AD8Per")
    fields[C.BP_PRESUMPTIVE_44AD] = _fmt_num(presumptive_total)

    fields[C.INCOME_HOUSE_PROPERTY] = _fmt_num(income.get("TotalIncomeOfHP"))
    fields[C.INCOME_OTHER_SOURCES] = _fmt_num(income.get("IncomeOthSrc"))
    fields[C.GROSS_TOTAL_INCOME] = _fmt_num(income.get("GrossTotIncome"))
    fields[C.TOTAL_HEAD_WISE_INCOME] = _fmt_num(income.get("GrossTotIncome"))

    chap = _dig(income, "DeductUndChapVIA") or {}
    fields[C.TOTAL_DEDUCTIONS] = _fmt_num(chap.get("TotalChapVIADeductions"))
    fields[C.DEDUCTION_80C] = _fmt_num(chap.get("Section80C"))
    fields[C.DEDUCTION_80D] = _fmt_num(chap.get("Section80D"))
    fields[C.DEDUCTION_80TTA] = _fmt_num(chap.get("Section80TTA"))
    fields[C.DEDUCTION_80G] = _fmt_num(chap.get("Section80G"))

    total_income = income.get("TotalIncome")
    fields[C.TOTAL_INCOME] = _fmt_num(total_income)
    try:
        total_income_d = (
            Decimal(str(total_income)) if total_income is not None else Decimal("0")
        )
    except Exception:
        total_income_d = Decimal("0")
    fields[C.ROUNDED_TOTAL_INCOME] = _fmt_num(round_total_income_288a(total_income_d))

    fields[C.REGIME] = _infer_regime_label_itr1(itr4)

    fields[C.CURRENT_YEAR_LOSSES_ADJUSTMENT] = "0"
    fields[C.BALANCE_AFTER_CYLA] = fields[C.GROSS_TOTAL_INCOME]
    fields[C.BROUGHT_FORWARD_LOSS_SETOFF] = "0"

    others_rows = _dig(income, "OthersInc", "OthersIncDtlsOthSrc")
    if isinstance(others_rows, list):
        nature_parts: list[str] = []
        savings_interest = Decimal("0")
        term_and_other = Decimal("0")
        refund_interest = Decimal("0")
        for row in others_rows:
            if not isinstance(row, dict):
                continue
            desc_raw = _fmt_num(row.get("OthSrcNatureDesc"))
            desc_u = desc_raw.strip().upper()
            if desc_raw:
                nature_parts.append(desc_raw)
            try:
                amt = Decimal(str(row.get("OthSrcOthAmount") or 0))
            except Exception:
                amt = Decimal("0")
            if desc_u == "SAV":
                savings_interest += amt
            elif desc_u == "TAX":
                refund_interest += amt
            elif desc_u == "IFD":
                term_and_other += amt
            else:
                term_and_other += amt
        fields[C.OTHER_SOURCE_NATURE] = ", ".join(nature_parts)
        fields[C.OS_INTEREST_SAVINGS] = _fmt_num(savings_interest)
        fields[C.OS_INTEREST_TERM_DEPOSIT] = _fmt_num(term_and_other)
        fields[C.OS_INTEREST_REFUND] = _fmt_num(refund_interest)

    tax_comp = _dig(itr4, "TaxComputation") or {}
    fields[C.TAX_NORMAL_RATES] = _fmt_num(tax_comp.get("TotalTaxPayable"))
    fields[C.REBATE_87A] = _fmt_num(tax_comp.get("Rebate87A"))
    fields[C.TAX_PAYABLE_ON_TOTAL_INCOME] = _fmt_num(tax_comp.get("TaxPayableOnRebate"))
    fields[C.CESS] = _fmt_num(tax_comp.get("EducationCess"))
    fields[C.GROSS_TAX_LIABILITY] = _fmt_num(tax_comp.get("GrossTaxLiability"))
    fields[C.NET_TAX_LIABILITY] = _fmt_num(tax_comp.get("NetTaxLiability"))
    fields[C.TAX_RELIEF] = _fmt_num(tax_comp.get("Section89"))
    fields[C.INTEREST_234A] = _fmt_num(_dig(tax_comp, "IntrstPay", "IntrstPayUs234A"))
    fields[C.INTEREST_234B] = _fmt_num(_dig(tax_comp, "IntrstPay", "IntrstPayUs234B"))
    fields[C.INTEREST_234C] = _fmt_num(_dig(tax_comp, "IntrstPay", "IntrstPayUs234C"))
    fields[C.FEE_234F] = _fmt_num(_dig(tax_comp, "IntrstPay", "LateFilingFee234F"))
    fields[C.TOTAL_TAX_PLUS_INTEREST] = _fmt_num(tax_comp.get("TotTaxPlusIntrstPay"))

    paid = _dig(itr4, "TaxPaid", "TaxesPaid") or {}
    fields[C.ADVANCE_TAX] = _fmt_num(paid.get("AdvanceTax"))
    fields[C.SELF_ASSESSMENT_TAX] = _fmt_num(paid.get("SelfAssessmentTax"))
    fields[C.TDS_TOTAL] = _fmt_num(paid.get("TDS"))
    fields[C.TCS_TOTAL] = _fmt_num(paid.get("TCS"))
    fields[C.TAXES_PAID_TOTAL] = _fmt_num(paid.get("TotalTaxesPaid"))
    fields[C.TDS_OTHER_THAN_SALARY] = _fmt_num(
        _dig(itr4, "TDSonOthThanSals", "TotalTDSonOthThanSals")
    )
    fields[C.TDS_FROM_SALARY] = _fmt_num(
        _dig(itr4, "TDSonSalaries", "TotalTDSonSalaries")
    )

    demand_amount = _dig(itr4, "TaxPaid", "BalTaxPayable")
    fields[C.DEMAND_AMOUNT] = _fmt_num(demand_amount)
    ref_amt = _dig(itr4, "Refund", "RefundDue")
    try:
        ref_d = Decimal(str(ref_amt)) if ref_amt is not None else Decimal("0")
    except Exception:
        ref_d = Decimal("0")
    try:
        paid_d = Decimal(str(paid.get("TotalTaxesPaid") or 0))
        net_tax_d = Decimal(str(tax_comp.get("NetTaxLiability") or 0))
        pre_ref = max(paid_d - net_tax_d, Decimal("0"))
    except Exception:
        pre_ref = ref_d
    fields[C.REFUND_PRE_288B] = _fmt_num(pre_ref)
    fields[C.REFUND_AMOUNT] = _fmt_num(ref_amt)
    fields[C.ROUNDED_REFUND_AMOUNT] = _fmt_num(round_refund_288b(ref_d))

    bank_rows: list[dict[str, Any]] = []
    add_banks = _dig(itr4, "Refund", "BankAccountDtls", "AddtnlBankDetails")
    if isinstance(add_banks, list):
        for b in add_banks:
            if not isinstance(b, dict):
                continue
            ur = _fmt_num(b.get("UseForRefund")).lower()
            nom = "Yes" if ur in ("true", "1", "yes", "y") else "No"
            bank_rows.append(
                {
                    "bank_name": _fmt_num(b.get("BankName")),
                    "ifsc": _fmt_num(b.get("IFSCCode")),
                    "account_number": _fmt_num(b.get("BankAccountNo")),
                    "account_type": _account_type_label(_fmt_num(b.get("AccountType"))),
                    "nominate_for_refund": nom,
                }
            )
    _normalize_bank_refund_nomination(bank_rows)

    tds_rows: list[dict[str, Any]] = []
    tds_list = _dig(itr4, "TDSonOthThanSals", "TDSonOthThanSal")
    if isinstance(tds_list, list):
        for row in tds_list:
            if not isinstance(row, dict):
                continue
            deductor = row.get("EmployerOrDeductorOrCollectDetl") or {}
            tan = _fmt_num(deductor.get("TAN"))
            sec = _normalize_tds_section(_fmt_num(row.get("TDSSection")))
            ded_yr = _fmt_num(row.get("DeductedYr")).strip()
            sec_disp = f"{sec} ({ded_yr})" if ded_yr else sec
            tds_rows.append(
                {
                    "deductor_name": _fmt_num(
                        deductor.get("EmployerOrDeductorOrCollecterName")
                    ),
                    "tan_pan": tan,
                    "section": sec_disp,
                    "amount_paid": row.get("AmtForTaxDeduct"),
                    "total_tax_deducted": row.get("TotTDSOnAmtPaid"),
                    "amount_claimed_this_year": row.get("ClaimOutOfTotTDSOnAmtPaid"),
                    "carry_forward": None,
                    "head_of_income": _fmt_num(row.get("HeadOfIncome")),
                }
            )

    return fields, bank_rows, tds_rows


def _parse_itr3(itr3: dict[str, Any]) -> tuple[dict[str, str], list[dict[str, Any]], list[dict[str, Any]]]:
    fields: dict[str, str] = {}

    form = _dig(itr3, "Form_ITR3") or {}
    ay_raw = _fmt_num(form.get("AssessmentYear"))
    ay = _format_ay(ay_raw)
    fields[C.ASSESSMENT_YEAR] = ay
    fields[C.FINANCIAL_YEAR] = _format_fy_from_ay(ay)
    fields[C.ITR_TYPE] = "ITR-3"

    pi = _dig(itr3, "PartA_GEN1", "PersonalInfo") or {}
    fn = _fmt_num(_dig(pi, "AssesseeName", "FirstName"))
    sn = _fmt_num(_dig(pi, "AssesseeName", "SurNameOrOrgName"))
    fields[C.ASSESSEE_NAME] = f"{fn} {sn}".strip()
    fields[C.PAN] = _fmt_num(pi.get("PAN")).upper()
    fields[C.DATE_OF_BIRTH] = _format_dob_iso(_fmt_num(pi.get("DOB")))
    fields[C.STATUS] = _status_individual(_fmt_num(pi.get("Status")))
    fields[C.AADHAAR] = _fmt_num(pi.get("AadhaarCardNo"))
    addr = pi.get("Address") if isinstance(pi.get("Address"), dict) else None
    fields[C.EMAIL] = _fmt_num(_dig(addr, "EmailAddress") if addr else None)
    mob = _dig(addr, "MobileNo") if addr else None
    fields[C.MOBILE] = _fmt_num(mob)
    fields[C.ADDRESS] = _compose_address(addr)
    fields[C.GENDER] = _gender_label(pi.get("Gender"))

    fs = _dig(itr3, "PartA_GEN1", "FilingStatus") or {}
    fields[C.RESIDENTIAL_STATUS] = _residential_status(_fmt_num(fs.get("ResidentialStatus")))
    fields[C.FILING_SECTION] = _return_file_sec_label(fs.get("ReturnFileSec"))
    fields[C.FILING_STATUS] = _return_file_sec_filing_status(fs.get("ReturnFileSec"))
    fields[C.FILING_DUE_DATE] = _fmt_num(fs.get("ItrFilingDueDate"))
    fields[C.SEVENTH_PROVISO_139] = _fmt_num(fs.get("SeventhProvisio139"))

    ver = _dig(itr3, "Verification", "Declaration") or {}
    fields[C.FATHER_NAME] = _fmt_num(ver.get("FatherName"))

    ver_main = itr3.get("Verification") if isinstance(itr3.get("Verification"), dict) else {}
    fields[C.FILING_DATE] = _fmt_num(ver_main.get("Date"))
    fields[C.VERIFICATION_PLACE] = _fmt_num(ver_main.get("Place"))
    fields[C.ORIGINAL_OR_REVISED] = fields[C.FILING_STATUS] or fields[C.FILING_SECTION]

    part_b = itr3.get("PartB-TI") or {}
    fields[C.INCOME_SALARY] = _fmt_num(part_b.get("Salaries"))
    fields[C.INCOME_HOUSE_PROPERTY] = _fmt_num(part_b.get("IncomeFromHP"))
    fields[C.INCOME_BUSINESS_PROFESSION] = _fmt_num(
        _dig(part_b, "ProfBusGain", "TotProfBusGain")
    )
    fields[C.INCOME_OTHER_SOURCES] = _fmt_num(_dig(part_b, "IncFromOS", "TotIncFromOS"))
    fields[C.TOTAL_HEAD_WISE_INCOME] = _fmt_num(part_b.get("TotalTI"))
    fields[C.CURRENT_YEAR_LOSSES_ADJUSTMENT] = _fmt_num(part_b.get("CurrentYearLoss"))
    fields[C.BALANCE_AFTER_CYLA] = _fmt_num(part_b.get("BalanceAfterSetoffLosses"))
    fields[C.BROUGHT_FORWARD_LOSS_SETOFF] = _fmt_num(part_b.get("BroughtFwdLossesSetoff"))
    fields[C.GROSS_TOTAL_INCOME] = _fmt_num(part_b.get("GrossTotalIncome"))
    ded = _dig(part_b, "DeductionsUndSchVIADtl") or {}
    fields[C.TOTAL_DEDUCTIONS] = _fmt_num(ded.get("TotDeductUndSchVIA"))
    ti = part_b.get("TotalIncome")
    fields[C.TOTAL_INCOME] = _fmt_num(ti)
    try:
        ti_d = Decimal(str(ti)) if ti is not None else Decimal("0")
    except Exception:
        ti_d = Decimal("0")
    fields[C.ROUNDED_TOTAL_INCOME] = _fmt_num(round_total_income_288a(ti_d))

    sch_os = _dig(itr3, "ScheduleOS", "IncOthThanOwnRaceHorse") or {}
    fields[C.OS_INTEREST_SAVINGS] = _fmt_num(sch_os.get("IntrstFrmSavingBank"))
    fields[C.OS_INTEREST_TERM_DEPOSIT] = _fmt_num(sch_os.get("IntrstFrmTermDeposit"))
    fields[C.OS_INTEREST_REFUND] = _fmt_num(sch_os.get("IntrstFrmIncmTaxRefund"))

    bp = _dig(itr3, "ITR3ScheduleBP", "BusinessIncOthThanSpec") or {}
    fields[C.BUSINESS_DEPRECIATION_BOOKS] = _fmt_num(bp.get("DepreciationDebPLCosAct"))
    dep_it = _dig(bp, "DepreciationAllowITAct32") or {}
    fields[C.BUSINESS_DEPRECIATION_IT] = _fmt_num(dep_it.get("TotDeprAllowITAct"))

    # Chapter VIA is not split per section in this JSON; 80TTA claim defaults to 0.
    fields[C.DEDUCTION_80TTA] = "0"

    tax_pay = _dig(itr3, "PartB_TTI", "ComputationOfTaxLiability", "TaxPayableOnTI") or {}
    fields[C.TAX_NORMAL_RATES] = _fmt_num(tax_pay.get("TaxAtNormalRatesOnAggrInc"))
    fields[C.REBATE_87A] = _fmt_num(tax_pay.get("Rebate87A"))
    fields[C.TAX_PAYABLE_ON_TOTAL_INCOME] = _fmt_num(tax_pay.get("TaxPayableOnTotInc"))

    fields[C.CESS] = _fmt_num(tax_pay.get("EducationCess"))
    fields[C.GROSS_TAX_LIABILITY] = _fmt_num(tax_pay.get("GrossTaxLiability"))

    net_tl = _dig(itr3, "PartB_TTI", "ComputationOfTaxLiability") or {}
    fields[C.NET_TAX_LIABILITY] = _fmt_num(net_tl.get("NetTaxLiability"))

    intr_pay = net_tl.get("IntrstPay")
    if isinstance(intr_pay, dict):
        fields[C.INTEREST_234A] = _fmt_num(intr_pay.get("IntrstPayUs234A"))
        fields[C.INTEREST_234B] = _fmt_num(intr_pay.get("IntrstPayUs234B"))
        fields[C.INTEREST_234C] = _fmt_num(intr_pay.get("IntrstPayUs234C"))
        fields[C.FEE_234F] = _fmt_num(intr_pay.get("LateFilingFee234F"))
    fields[C.TOTAL_TAX_PLUS_INTEREST] = _fmt_num(net_tl.get("AggregateTaxInterestLiability"))

    tpaid = _dig(itr3, "PartB_TTI", "TaxPaid", "TaxesPaid") or {}
    fields[C.ADVANCE_TAX] = _fmt_num(tpaid.get("AdvanceTax"))
    fields[C.SELF_ASSESSMENT_TAX] = _fmt_num(tpaid.get("SelfAssessmentTax"))
    fields[C.TCS_TOTAL] = _fmt_num(tpaid.get("TCS"))
    fields[C.TDS_TOTAL] = _fmt_num(tpaid.get("TDS"))
    fields[C.TAXES_PAID_TOTAL] = _fmt_num(tpaid.get("TotalTaxesPaid"))

    tax_paid_outer = _dig(itr3, "PartB_TTI", "TaxPaid") or {}
    fields[C.DEMAND_AMOUNT] = _fmt_num(tax_paid_outer.get("BalTaxPayable"))

    sch_tds2_root = itr3.get("ScheduleTDS2") if isinstance(itr3.get("ScheduleTDS2"), dict) else {}
    fields[C.TDS_OTHER_THAN_SALARY] = _fmt_num(sch_tds2_root.get("TotalTDSonOthThanSals"))

    salary_tds_rows = _collect_itr3_schedule_tds1_rows(itr3)
    sal_tot = _itr3_tds_from_salary_total_str(itr3)
    if not sal_tot.strip() and salary_tds_rows:
        tot_dec = Decimal("0")
        for r in salary_tds_rows:
            av = r.get("amount_claimed_this_year")
            if av is None:
                av = r.get("total_tax_deducted")
            if av is not None:
                try:
                    tot_dec += Decimal(str(av))
                except Exception:
                    pass
        sal_tot = _fmt_num(tot_dec)
    fields[C.TDS_FROM_SALARY] = sal_tot

    ref_amt = _dig(itr3, "PartB_TTI", "Refund", "RefundDue")
    try:
        ref_d = Decimal(str(ref_amt)) if ref_amt is not None else Decimal("0")
    except Exception:
        ref_d = Decimal("0")
    try:
        paid_d = Decimal(str(tpaid.get("TotalTaxesPaid") or 0))
        net_tax_d = Decimal(str(net_tl.get("NetTaxLiability") or 0))
        pre_ref = max(paid_d - net_tax_d, Decimal("0"))
    except Exception:
        pre_ref = ref_d
    fields[C.REFUND_PRE_288B] = _fmt_num(pre_ref)
    fields[C.REFUND_AMOUNT] = _fmt_num(ref_amt)
    fields[C.ROUNDED_REFUND_AMOUNT] = _fmt_num(round_refund_288b(ref_d))

    fields[C.REGIME] = _infer_regime_label_itr3(itr3, ti_d)

    bank_rows: list[dict[str, Any]] = []
    add_banks = _dig(itr3, "PartB_TTI", "Refund", "BankAccountDtls", "AddtnlBankDetails")
    if isinstance(add_banks, list):
        for b in add_banks:
            if not isinstance(b, dict):
                continue
            ur = _fmt_num(b.get("UseForRefund")).lower()
            nom = "Yes" if ur in ("true", "1", "yes", "y") else "No"
            bank_rows.append(
                {
                    "bank_name": _fmt_num(b.get("BankName")),
                    "ifsc": _fmt_num(b.get("IFSCCode")),
                    "account_number": _fmt_num(b.get("BankAccountNo")),
                    "account_type": _account_type_label(_fmt_num(b.get("AccountType"))),
                    "nominate_for_refund": nom,
                }
            )
    _normalize_bank_refund_nomination(bank_rows)

    tds_rows: list[dict[str, Any]] = []
    tds_rows.extend(salary_tds_rows)
    tds_list = _dig(itr3, "ScheduleTDS2", "TDSOthThanSalaryDtls")
    if isinstance(tds_list, list):
        for row in tds_list:
            if not isinstance(row, dict):
                continue
            nm = _fmt_num(
                row.get("NameOfDeductor")
                or row.get("NameofDeductor")
                or row.get("EmployerOrCollecterName")
            )
            tan = _fmt_num(row.get("TANOfDeductor"))
            sec = _normalize_tds_section(_fmt_num(row.get("TDSSection")))
            cr = row.get("TaxDeductCreditDtls") or {}
            ho = _fmt_num(row.get("HeadOfIncome")).strip()
            if not ho:
                ho = "Other sources"
            tds_rows.append(
                {
                    "deductor_name": nm or tan,
                    "tan_pan": tan,
                    "section": sec,
                    "amount_paid": row.get("GrossAmount"),
                    "total_tax_deducted": cr.get("TaxDeductedOwnHands"),
                    "amount_claimed_this_year": cr.get("TaxClaimedOwnHands"),
                    "carry_forward": row.get("AmtCarriedFwd"),
                    "head_of_income": ho,
                }
            )

    return fields, bank_rows, tds_rows


def detect_json_itr_type(data: dict[str, Any]) -> str | None:
    itr = data.get("ITR")
    if not isinstance(itr, dict):
        return None
    if "ITR3" in itr:
        return Document.TYPE_ITR3
    if "ITR1" in itr:
        return Document.TYPE_ITR1
    if "ITR4" in itr:
        return Document.TYPE_ITR4
    return None


def _parsed_to_db(
    document: Document,
    parsed_fields: dict[str, str],
    bank_rows: list[dict[str, Any]],
    tds_rows: list[dict[str, Any]],
    detected: str,
) -> None:
    document.extracted_fields.all().delete()
    document.bank_details.all().delete()
    document.tds_details.all().delete()

    field_map_for_validation: dict[str, str] = {}
    method = "json_itr"

    for key, norm in parsed_fields.items():
        norm = _normalize_amount_field(key, str(norm))
        field_map_for_validation[key] = norm
        ExtractedField.objects.create(
            document=document,
            field_name=key,
            raw_value=norm,
            normalized_value=norm,
            confidence_score=Decimal("1.0"),
            page_number=None,
            source_text="",
            source_bbox=None,
            extraction_method=method,
            requires_review=True,
            is_approved=False,
        )

    for i, row in enumerate(bank_rows):
        BankDetail.objects.create(
            document=document,
            sort_order=i,
            bank_name=row.get("bank_name") or "",
            ifsc=row.get("ifsc") or "",
            account_number=row.get("account_number") or "",
            account_type=row.get("account_type") or "",
            nominate_for_refund=row.get("nominate_for_refund") or "",
        )

    for i, row in enumerate(tds_rows):
        TDSDetail.objects.create(
            document=document,
            sort_order=i,
            deductor_name=row.get("deductor_name") or "",
            tan_pan=row.get("tan_pan") or "",
            section=row.get("section") or "",
            amount_paid=row.get("amount_paid"),
            total_tax_deducted=row.get("total_tax_deducted"),
            amount_claimed_this_year=row.get("amount_claimed_this_year"),
            carry_forward=row.get("carry_forward"),
            head_of_income=(row.get("head_of_income") or None),
        )

    document.status = Document.STATUS_REVIEW_REQUIRED
    document.error_message = ""
    document.review_completed = False
    document.save(
        update_fields=[
            "status",
            "error_message",
            "review_completed",
            "native_text_char_count",
            "used_ocr_fallback",
            "updated_at",
        ]
    )

    post_issues = issues_after_extraction(field_map_for_validation, detected)
    if any(i.code == "unknown_type" for i in post_issues):
        pass


@transaction.atomic
def process_json_document_file(document: Document) -> None:
    """Parse filed ITR JSON from uploaded_file; populate extraction rows."""
    path = Path(document.uploaded_file.path)
    document.status = Document.STATUS_CLASSIFYING
    document.save(update_fields=["status", "updated_at"])

    raw = path.read_bytes()
    document.file_hash = _file_sha256(path)
    document.native_text_char_count = len(raw.decode("utf-8", errors="replace"))
    document.used_ocr_fallback = False
    document.page_count = None

    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        document.status = Document.STATUS_FAILED
        document.error_message = f"Invalid JSON: {exc}"
        document.save(
            update_fields=[
                "status",
                "error_message",
                "file_hash",
                "native_text_char_count",
                "used_ocr_fallback",
                "page_count",
                "updated_at",
            ]
        )
        return

    detected = detect_json_itr_type(data)
    document.detected_type = detected or Document.TYPE_UNKNOWN

    if detected in (None, Document.TYPE_UNKNOWN):
        document.status = Document.STATUS_FAILED
        document.error_message = "Could not find ITR1, ITR3, or ITR4 under the JSON \"ITR\" key."
        document.save(
            update_fields=[
                "detected_type",
                "status",
                "error_message",
                "file_hash",
                "native_text_char_count",
                "used_ocr_fallback",
                "page_count",
                "updated_at",
            ]
        )
        return

    if detected not in (
        Document.TYPE_ITR1,
        Document.TYPE_ITR3,
        Document.TYPE_ITR4,
    ):
        document.status = Document.STATUS_FAILED
        document.error_message = (
            "JSON import is implemented for filed ITR-1, ITR-3, and ITR-4 JSON in "
            "this version. "
            f"Found: {detected}."
        )
        document.save(
            update_fields=[
                "detected_type",
                "status",
                "error_message",
                "file_hash",
                "native_text_char_count",
                "used_ocr_fallback",
                "page_count",
                "updated_at",
            ]
        )
        return

    itr_payload = (data.get("ITR") or {}).get(detected)
    if not isinstance(itr_payload, dict):
        document.status = Document.STATUS_FAILED
        document.error_message = f"Missing ITR.{detected} object."
        document.save(
            update_fields=[
                "detected_type",
                "status",
                "error_message",
                "file_hash",
                "native_text_char_count",
                "used_ocr_fallback",
                "page_count",
                "updated_at",
            ]
        )
        return

    try:
        if detected == Document.TYPE_ITR1:
            fields, bank_rows, tds_rows = _parse_itr1(itr_payload)
        elif detected == Document.TYPE_ITR4:
            fields, bank_rows, tds_rows = _parse_itr4(itr_payload)
        else:
            fields, bank_rows, tds_rows = _parse_itr3(itr_payload)
    except Exception as exc:
        document.status = Document.STATUS_FAILED
        document.error_message = f"JSON mapping failed: {exc}"
        document.save(
            update_fields=[
                "detected_type",
                "status",
                "error_message",
                "file_hash",
                "native_text_char_count",
                "used_ocr_fallback",
                "page_count",
                "updated_at",
            ]
        )
        return

    document.status = Document.STATUS_EXTRACTING
    document.save(
        update_fields=[
            "detected_type",
            "status",
            "file_hash",
            "native_text_char_count",
            "used_ocr_fallback",
            "page_count",
            "updated_at",
        ]
    )

    _parsed_to_db(document, fields, bank_rows, tds_rows, detected)
