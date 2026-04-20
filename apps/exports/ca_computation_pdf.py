"""
CA-style income tax computation PDF — premium ReportLab layout (print-ready, no system PDF deps).

Design: navy hero band, structured key–value sheets, zebra data tables, validation chips.
"""
from __future__ import annotations

from decimal import Decimal
from io import BytesIO

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from apps.exports.formatting import (
    format_inr,
    format_inr_pair,
    format_inr_tax_zero,
    mask_account_number,
)
from apps.extractors import canonical as C
from apps.extractors.utils import normalize as N
from apps.extractors.validation_engine import ValidationFinding, Severity, financial_year_from_ay

# Design tokens (professional / India income-tax document aesthetic)
C_PRIMARY = HexColor("#0c4a6e")
C_PRIMARY_LIGHT = HexColor("#e0f2fe")
C_TEXT = HexColor("#0f172a")
C_MUTED = HexColor("#64748b")
C_BORDER = HexColor("#e2e8f0")
C_ROW_ALT = HexColor("#f8fafc")
C_FAIL_BG = HexColor("#fef2f2")
C_FAIL_TX = HexColor("#991b1b")
C_WARN_BG = HexColor("#fffbeb")
C_WARN_TX = HexColor("#b45309")
C_PASS_BG = HexColor("#ecfdf5")
C_PASS_TX = HexColor("#047857")
C_TABLE_HEAD = HexColor("#1e3a5f")


def _styles() -> dict:
    base = getSampleStyleSheet()
    hero_title = ParagraphStyle(
        "HeroTitle",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=20,
        textColor=colors.white,
        alignment=TA_CENTER,
        leading=24,
        spaceAfter=4,
    )
    hero_sub = ParagraphStyle(
        "HeroSub",
        parent=base["Normal"],
        fontSize=9.5,
        textColor=HexColor("#bae6fd"),
        alignment=TA_CENTER,
        leading=12,
        spaceAfter=0,
    )
    disclaimer = ParagraphStyle(
        "Disclaimer",
        parent=base["Normal"],
        fontSize=8,
        textColor=C_MUTED,
        alignment=TA_CENTER,
        leading=11,
        spaceAfter=14,
    )
    sec = ParagraphStyle(
        "SecTitle",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11.5,
        textColor=C_PRIMARY,
        spaceBefore=16,
        spaceAfter=8,
        borderPadding=0,
        leftIndent=0,
    )
    kv_label = ParagraphStyle(
        "KVLabel",
        parent=base["Normal"],
        fontSize=8.5,
        textColor=C_MUTED,
        leading=11,
    )
    kv_val = ParagraphStyle(
        "KVVal",
        parent=base["Normal"],
        fontSize=10,
        textColor=C_TEXT,
        alignment=TA_RIGHT,
        leading=12,
        fontName="Helvetica-Bold",
    )
    body = ParagraphStyle("Body", parent=base["Normal"], fontSize=9, leading=12, textColor=C_TEXT)
    small = ParagraphStyle("Small", parent=base["Normal"], fontSize=8, leading=10.5, textColor=C_MUTED)
    th = ParagraphStyle("Th", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=8.5, textColor=colors.white)
    td = ParagraphStyle("Td", parent=base["Normal"], fontSize=8.5, leading=11, textColor=C_TEXT)
    td_r = ParagraphStyle("TdR", parent=td, alignment=TA_RIGHT)
    note = ParagraphStyle(
        "Note",
        parent=base["Normal"],
        fontSize=8.5,
        leading=12,
        textColor=C_MUTED,
        leftIndent=6,
        borderPadding=(6, 6, 6, 6),
        backColor=C_PRIMARY_LIGHT,
    )
    return {
        "hero_title": hero_title,
        "hero_sub": hero_sub,
        "disclaimer": disclaimer,
        "sec": sec,
        "kv_label": kv_label,
        "kv_val": kv_val,
        "body": body,
        "small": small,
        "th": th,
        "td": td,
        "td_r": td_r,
        "note": note,
    }


def _forty_four_ad_schedule(f: dict) -> tuple[list[tuple[str, str]], str]:
    """44AD working lines: 6%/8% minima vs income offered (Schedule BP)."""
    dig = N.parse_indian_amount(f.get(C.BP_TURNOVER_44AD) or "")
    oth = N.parse_indian_amount(f.get(C.BP_RECEIPTS_OTHER_MODE_44AD) or "")
    dig = dig if dig is not None else Decimal("0")
    oth = oth if oth is not None else Decimal("0")
    min_d = Decimal("0.06") * dig
    min_o = Decimal("0.08") * oth
    min_total = min_d + min_o
    offered = N.parse_indian_amount(f.get(C.INCOME_BUSINESS_PROFESSION) or "")
    if offered is None:
        offered = N.parse_indian_amount(f.get(C.BP_PRESUMPTIVE_44AD) or "")
    if offered is None:
        offered = Decimal("0")
    accepted = offered
    rows: list[tuple[str, str]] = [
        ("Deemed profit at 6% on digital / prescribed electronic turnover (E1a)", format_inr_tax_zero(min_d)),
        ("Deemed profit at 8% on other-mode turnover (E1b)", format_inr_tax_zero(min_o)),
        ("Minimum deemed profit (sum of 6% + 8% components)", format_inr(min_total)),
        ("Profit / income actually offered (business head)", format_inr(offered)),
        ("Income assessed under business head (accepted)", format_inr(accepted)),
    ]
    if dig == 0 and oth == 0 and offered == 0:
        note = "Turnover not populated — presumptive minimum not computed here."
    elif offered > min_total:
        note = "Profit offered exceeds the presumptive minimum computed on stated turnover; accepted as filed."
    elif offered == min_total:
        note = "Profit offered equals the presumptive minimum on stated turnover; accepted as filed."
    else:
        note = (
            "Offered profit is below the computed 6%/8% minimum on extracted turnover — "
            "verify Schedule BP, eligible receipts, and other statutory disclosures."
        )
    return rows, note


def _esc(s: str) -> str:
    return (
        str(s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _hero_band(ay: str, fy: str, st: dict) -> Table:
    sub = f"Assessment Year {ay or '—'} · Financial Year {fy or '—'}"
    inner = Table(
        [
            [Paragraph("Income Tax Computation", st["hero_title"])],
            [Paragraph(_esc(sub), st["hero_sub"])],
        ],
        colWidths=[174 * mm],
    )
    inner.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 14),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
            ]
        )
    )
    outer = Table([[inner]], colWidths=[180 * mm])
    outer.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), C_PRIMARY),
                ("BOX", (0, 0), (-1, -1), 0, C_PRIMARY),
                ("ROUNDEDCORNERS", [10, 10, 10, 10]),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return outer


def _kv_sheet(rows: list[tuple[str, str]], st: dict, label_w: float = 82 * mm) -> Table:
    data = []
    for lab, val in rows:
        data.append(
            [
                Paragraph(_esc(lab), st["kv_label"]),
                Paragraph(_esc(str(val)), st["kv_val"]),
            ]
        )
    t = Table(data, colWidths=[label_w, 180 * mm - label_w - 24 * mm])
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("LINEABOVE", (0, 0), (-1, 0), 0.8, C_BORDER),
                ("LINEBELOW", (0, -1), (-1, -1), 0.8, C_BORDER),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, C_ROW_ALT]),
                ("BOX", (0, 0), (-1, -1), 0.6, C_BORDER),
            ]
        )
    )
    return t


def _section_title(text: str, st: dict) -> Table:
    """Left-accent bar + title."""
    p = Paragraph(f"<b>{_esc(text)}</b>", st["sec"])
    tbl = Table([[p]], colWidths=[180 * mm])
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), HexColor("#f1f5f9")),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("LEFTPADDING", (0, 0), (0, 0), 0),
                ("LINEBEFORE", (0, 0), (0, -1), 4, C_PRIMARY),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return tbl


def _annex_table(
    headers: list[str],
    data_rows: list[list[str]],
    widths: list[float],
    st: dict,
    *,
    right_align_from: int | None = None,
) -> Table:
    h = [Paragraph(f"<b>{_esc(x)}</b>", st["th"]) for x in headers]
    body = []
    ra = right_align_from if right_align_from is not None else max(0, len(headers) - 3)
    for row in data_rows:
        pr = []
        for i, cell in enumerate(row):
            p = st["td_r"] if i >= ra else st["td"]
            pr.append(Paragraph(_esc(str(cell)), p))
        body.append(pr)
    tbl = Table([h] + body, colWidths=widths, repeatRows=1)
    n = len(body)
    zebra = []
    for i in range(n):
        zebra.append(C_ROW_ALT if i % 2 else colors.white)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), C_TABLE_HEAD),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.25, C_BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]
            + [
                ("BACKGROUND", (0, i + 1), (-1, i + 1), zebra[i])
                for i in range(n)
            ]
        )
    )
    return tbl


def _finding_row(vf: ValidationFinding, st: dict) -> Table:
    status = vf.status
    if status == Severity.FAIL:
        bg, fg = C_FAIL_BG, C_FAIL_TX
    elif status == Severity.WARN:
        bg, fg = C_WARN_BG, C_WARN_TX
    elif status == Severity.PASS:
        bg, fg = C_PASS_BG, C_PASS_TX
    else:
        bg, fg = C_ROW_ALT, C_MUTED
    chip = ParagraphStyle(
        "Chip",
        parent=st["small"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        textColor=fg,
        alignment=TA_CENTER,
    )
    chip_cell = Paragraph(f"{status.value}", chip)
    detail = _esc(vf.message)
    if vf.expected or vf.actual:
        detail += f" <font size=7 color='#64748b'>(exp: {_esc(vf.expected or '—')}, act: {_esc(vf.actual or '—')})</font>"
    text_p = Paragraph(
        f"<b>{_esc(vf.rule)}</b> · {_esc(vf.field)} · {detail}",
        ParagraphStyle("FV", parent=st["small"], textColor=C_TEXT, alignment=TA_LEFT, leading=11),
    )
    tbl = Table([[chip_cell, text_p]], colWidths=[22 * mm, 156 * mm])
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("BOX", (0, 0), (-1, -1), 0.4, C_BORDER),
            ]
        )
    )
    return tbl


def _footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setStrokeColor(C_BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(12 * mm, 11 * mm, A4[0] - 12 * mm, 11 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(C_MUTED)
    canvas.drawCentredString(A4[0] / 2, 7 * mm, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


def render_ca_computation_pdf(context: dict) -> bytes:
    f = context.get("fields") or {}
    st = _styles()
    story: list = []
    findings: list[ValidationFinding] = list(context.get("validation_findings") or [])

    ay = (f.get(C.ASSESSMENT_YEAR) or "").strip()
    fy = (f.get(C.FINANCIAL_YEAR) or "").strip() or financial_year_from_ay(ay)

    story.append(_hero_band(ay, fy, st))
    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            "Figures reproduced from extracted filed ITR data — not legal advice. Verify against the original return.",
            st["disclaimer"],
        )
    )

    # 1. Assessee
    story.append(_section_title("1. Assessee and return metadata", st))
    story.append(Spacer(1, 4))
    story.append(
        _kv_sheet(
            [
                ("Name", f.get(C.ASSESSEE_NAME) or "—"),
                ("PAN", f.get(C.PAN) or "—"),
                ("ITR form", f.get(C.ITR_TYPE) or "—"),
                ("Assessment year", ay or "—"),
                ("Financial year", fy or "—"),
                ("Residential status", f.get(C.RESIDENTIAL_STATUS) or "—"),
                ("Tax regime", f.get(C.REGIME) or "—"),
                ("Filing date (e-filed)", f.get(C.FILING_DATE) or "Not extracted"),
                ("Original / Revised", f.get(C.ORIGINAL_OR_REVISED) or "Not extracted"),
                ("Section filed under", f.get(C.FILING_SECTION) or "Not extracted"),
            ],
            st,
        )
    )

    # 2. Synopsis
    story.append(_section_title("2. Return synopsis", st))
    story.append(Spacer(1, 4))
    refund_marked = sum(
        1
        for b in context.get("bank_rows") or []
        if (b.nominate_for_refund or "").lower() == "yes"
    )
    reg_raw = (f.get(C.REGIME) or "").strip()
    rl = reg_raw.lower()
    if not reg_raw:
        new_reg = "—"
    elif "new" in rl:
        new_reg = "Opted (new regime)"
    elif "old" in rl:
        new_reg = "Not opted (old regime)"
    else:
        new_reg = reg_raw
    story.append(
        _kv_sheet(
            [
                ("Returned total income", format_inr(f.get(C.TOTAL_INCOME))),
                ("Gross tax liability", format_inr_tax_zero(f.get(C.GROSS_TAX_LIABILITY))),
                ("Net tax liability", format_inr_tax_zero(f.get(C.NET_TAX_LIABILITY))),
                ("Taxes paid (total)", format_inr_tax_zero(f.get(C.TAXES_PAID_TOTAL))),
                ("Refund / Demand", format_inr_pair(f.get(C.REFUND_AMOUNT), f.get(C.DEMAND_AMOUNT))),
                ("Nature of business (if extracted)", f.get(C.BUSINESS_NAME) or "—"),
                ("Business code / activity", f.get(C.BUSINESS_CODE) or "—"),
                ("Presumptive basis (44AD fields)", "See §4"),
                ("New tax regime (if stated)", new_reg),
                ("Refund bank a/c marked “Yes” (count)", str(refund_marked)),
            ],
            st,
        )
    )

    # 3. Income ladder
    story.append(_section_title("3. Computation of total income", st))
    story.append(Spacer(1, 4))
    story.append(
        _kv_sheet(
            [
                ("Income from Salary", format_inr(f.get(C.INCOME_SALARY))),
                ("Income from House Property", format_inr(f.get(C.INCOME_HOUSE_PROPERTY))),
                ("Profits and gains of business or profession", format_inr(f.get(C.INCOME_BUSINESS_PROFESSION))),
                ("Income from Other Sources", format_inr(f.get(C.INCOME_OTHER_SOURCES))),
                ("Gross Total Income", format_inr(f.get(C.GROSS_TOTAL_INCOME))),
                ("Less: Deductions under Chapter VI-A", format_inr_tax_zero(f.get(C.TOTAL_DEDUCTIONS))),
                ("Total Income", format_inr(f.get(C.TOTAL_INCOME))),
                ("Rounded Total Income u/s 288A", format_inr(f.get(C.ROUNDED_TOTAL_INCOME) or f.get(C.TOTAL_INCOME))),
            ],
            st,
        )
    )

    # 4. 44AD
    story.append(_section_title("4. Business — presumptive income (Schedule BP / 44AD)", st))
    story.append(Spacer(1, 4))
    ad_rows, ad_note = _forty_four_ad_schedule(f)
    story.append(
        _kv_sheet(
            [
                ("Business name", f.get(C.BUSINESS_NAME) or "—"),
                ("Business code / description", f.get(C.BUSINESS_CODE) or "—"),
                (
                    "Digital / prescribed electronic turnover (E1a)",
                    format_inr(f.get(C.BP_TURNOVER_44AD)),
                ),
                ("Non-digital / other-mode turnover (E1b)", format_inr(f.get(C.BP_RECEIPTS_OTHER_MODE_44AD))),
            ]
            + ad_rows,
            st,
        )
    )
    story.append(Spacer(1, 6))
    story.append(
        Table(
            [[Paragraph(f"<b>Working note (44AD).</b> {_esc(ad_note)}", st["note"])]],
            colWidths=[180 * mm],
        )
    )

    # 5. Other sources
    story.append(_section_title("5. Other sources (detail)", st))
    story.append(Spacer(1, 4))
    os_amt = N.parse_indian_amount(f.get(C.INCOME_OTHER_SOURCES) or "") or Decimal("0")
    offered_os = "Yes" if os_amt > 0 else "—"
    story.append(
        _kv_sheet(
            [
                ("Nature / description", f.get(C.OTHER_SOURCE_NATURE) or "—"),
                ("Amount", format_inr(f.get(C.INCOME_OTHER_SOURCES))),
                ("Linked TDS (total TDS on income)", format_inr(f.get(C.TDS_TOTAL))),
                ("Offered in this year of income (return)", offered_os),
            ],
            st,
        )
    )

    # 6. VI-A
    story.append(_section_title("6. Deductions under Chapter VI-A", st))
    story.append(Spacer(1, 4))
    story.append(
        _kv_sheet(
            [
                ("80C", format_inr_tax_zero(f.get(C.DEDUCTION_80C))),
                ("80D", format_inr_tax_zero(f.get(C.DEDUCTION_80D))),
                ("80G", format_inr_tax_zero(f.get(C.DEDUCTION_80G))),
                ("80TTA / 80TTB", format_inr_tax_zero(f.get(C.DEDUCTION_80TTA))),
                ("Other Chapter VI-A (if any)", "0"),
                ("Total Chapter VI-A", format_inr_tax_zero(f.get(C.TOTAL_DEDUCTIONS))),
            ],
            st,
        )
    )

    # 7. Tax
    story.append(_section_title("7. Tax computation", st))
    story.append(Spacer(1, 4))
    story.append(
        _kv_sheet(
            [
                ("Tax on total income", format_inr_tax_zero(f.get(C.TAX_PAYABLE_ON_TOTAL_INCOME))),
                ("Less: Rebate u/s 87A", format_inr_tax_zero(f.get(C.REBATE_87A))),
                ("Tax after rebate", format_inr_tax_zero(f.get(C.TAX_NORMAL_RATES))),
                ("Add: Health and Education Cess", format_inr_tax_zero(f.get(C.CESS))),
                ("Gross tax liability", format_inr_tax_zero(f.get(C.GROSS_TAX_LIABILITY))),
                ("Relief (where applicable)", format_inr_tax_zero(f.get(C.TAX_RELIEF))),
                ("Add: Interest u/s 234A", format_inr_tax_zero(f.get(C.INTEREST_234A))),
                ("Add: Interest u/s 234B", format_inr_tax_zero(f.get(C.INTEREST_234B))),
                ("Add: Interest u/s 234C", format_inr_tax_zero(f.get(C.INTEREST_234C))),
                ("Add: Fee u/s 234F", format_inr_tax_zero(f.get(C.FEE_234F))),
                ("Net tax payable / total tax liability", format_inr_tax_zero(f.get(C.NET_TAX_LIABILITY))),
            ],
            st,
        )
    )

    # 8. Taxes paid
    story.append(_section_title("8. Taxes paid and reconciliation", st))
    story.append(Spacer(1, 4))
    story.append(
        _kv_sheet(
            [
                ("Advance tax", format_inr_tax_zero(f.get(C.ADVANCE_TAX))),
                ("Self-assessment tax", format_inr_tax_zero(f.get(C.SELF_ASSESSMENT_TAX))),
                ("TDS on salary (if split)", format_inr_tax_zero(f.get(C.TDS_FROM_SALARY))),
                ("TDS on income other than salary", format_inr_tax_zero(f.get(C.TDS_OTHER_THAN_SALARY) or f.get(C.TDS_TOTAL))),
                ("TCS", format_inr_tax_zero(f.get(C.TCS_TOTAL))),
                ("Total taxes paid (D17)", format_inr_tax_zero(f.get(C.TAXES_PAID_TOTAL))),
            ],
            st,
        )
    )

    # 9. Refund
    story.append(_section_title("9. Refund / demand", st))
    story.append(Spacer(1, 4))
    story.append(
        _kv_sheet(
            [
                ("Refund due", format_inr(f.get(C.REFUND_AMOUNT))),
                ("Tax demand payable", format_inr_tax_zero(f.get(C.DEMAND_AMOUNT))),
            ],
            st,
        )
    )

    # 10. TDS
    story.append(_section_title("10. TDS schedule (line items)", st))
    story.append(Spacer(1, 4))
    tds_list = list(context.get("tds_rows") or [])
    if tds_list:
        tdata = []
        for t in tds_list:
            cl = t.amount_claimed_this_year or t.total_tax_deducted
            tdata.append(
                [
                    t.deductor_name or "—",
                    t.tan_pan or "—",
                    (t.head_of_income or t.section or "—"),
                    format_inr(t.amount_paid),
                    format_inr(t.total_tax_deducted),
                    format_inr(cl),
                    format_inr(t.carry_forward) if t.carry_forward is not None else "0",
                ]
            )
        story.append(
            _annex_table(
                [
                    "Deductor",
                    "TAN/PAN",
                    "Head / §",
                    "Gross",
                    "TDS deducted",
                    "TDS claimed",
                    "Carry fwd",
                ],
                tdata,
                [32, 22, 34, 24, 24, 24, 22],
                st,
                right_align_from=3,
            )
        )
    else:
        story.append(Paragraph(_esc("No TDS rows extracted — see validation notes."), st["body"]))

    # 11. Banks
    story.append(_section_title("11. Bank accounts (refund credit)", st))
    story.append(Spacer(1, 4))
    banks = list(context.get("bank_rows") or [])
    if banks:
        bdata = []
        for b in banks:
            bdata.append(
                [
                    b.bank_name or "—",
                    b.ifsc or "—",
                    mask_account_number(b.account_number),
                    b.account_type or "—",
                    (b.nominate_for_refund or "—"),
                ]
            )
        story.append(
            _annex_table(
                ["Bank", "IFSC", "Account (masked)", "Type", "Refund eligible"],
                bdata,
                [42, 26, 36, 28, 40],
                st,
            )
        )
    else:
        story.append(Paragraph(_esc("No bank rows extracted."), st["body"]))

    # 12. Validation
    story.append(_section_title("12. Extraction and validation notes", st))
    story.append(Spacer(1, 4))
    story.append(
        Paragraph(
            _esc(
                "Review (K): Data imported from the filed ITR (JSON); figures reproduced as imported. "
                "No independent legal or tax opinion. Automated rules below do not replace professional judgement."
            ),
            st["small"],
        )
    )
    story.append(Spacer(1, 6))
    if not findings:
        story.append(Paragraph("No automated validation results (empty).", st["body"]))
    else:
        for vf in findings:
            story.append(_finding_row(vf, st))
            story.append(Spacer(1, 4))

    story.append(Spacer(1, 6))
    gen = context.get("generated_at")
    gen_s = (
        timezone.localtime(gen).strftime("%d %b %Y, %H:%M")
        if gen is not None
        else ""
    )
    conf = context.get("extraction_confidence_avg")
    conf_bit = ""
    if conf is not None:
        try:
            conf_bit = f" · Mean field confidence: {float(conf):.2f}"
        except (TypeError, ValueError):
            conf_bit = ""
    story.append(
        Paragraph(
            _esc(f"Generated {gen_s} · ITR Summary Generator · Indian rupee grouping.{conf_bit}"),
            st["small"],
        )
    )

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
