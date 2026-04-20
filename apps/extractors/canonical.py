"""
Canonical field names stored in ExtractedField.field_name — single source of truth.
"""
from __future__ import annotations

# ReturnHeader
ASSESSEE_NAME = "assessee_name"
PAN = "pan"
ASSESSMENT_YEAR = "assessment_year"
ITR_TYPE = "itr_type"
FILING_DATE = "filing_date"
FINANCIAL_YEAR = "financial_year"
ORIGINAL_OR_REVISED = "original_or_revised"
FILING_SECTION = "filing_section"
STATUS = "status"
FILING_STATUS = "filing_status"
REGIME = "regime"
RESIDENTIAL_STATUS = "residential_status"

# PersonalDetails
FATHER_NAME = "father_name"
DATE_OF_BIRTH = "date_of_birth"
GENDER = "gender"
AADHAAR = "aadhaar"
EMAIL = "email"
MOBILE = "mobile"
ADDRESS = "address"

# IncomeComputation
INCOME_SALARY = "income_salary"
INCOME_BUSINESS_PROFESSION = "income_business_profession"
INCOME_HOUSE_PROPERTY = "income_house_property"
INCOME_OTHER_SOURCES = "income_other_sources"
TOTAL_HEAD_WISE_INCOME = "total_head_wise_income"
CURRENT_YEAR_LOSSES_ADJUSTMENT = "current_year_losses_adjustment"
BALANCE_AFTER_CYLA = "balance_after_cyla"
BROUGHT_FORWARD_LOSS_SETOFF = "brought_forward_loss_setoff"
GROSS_TOTAL_INCOME = "gross_total_income"
DEDUCTION_80C = "deduction_80c"
DEDUCTION_80D = "deduction_80d"
DEDUCTION_80TTA = "deduction_80tta"
DEDUCTION_80G = "deduction_80g"
TOTAL_DEDUCTIONS = "total_deductions"
TOTAL_INCOME = "total_income"
ROUNDED_TOTAL_INCOME = "rounded_total_income"
# Schedule OS / narrative (ITR-4)
OTHER_SOURCE_NATURE = "other_source_nature"
# Schedule OS line items (JSON / detailed export)
OS_INTEREST_SAVINGS = "os_interest_savings"
OS_INTEREST_TERM_DEPOSIT = "os_interest_term_deposit"
OS_INTEREST_REFUND = "os_interest_refund"
# ITR-3 Schedule BP (depreciation bridge lines on computation sheets)
BUSINESS_DEPRECIATION_BOOKS = "business_depreciation_books"
BUSINESS_DEPRECIATION_IT = "business_depreciation_it"
# Schedule BP — presumptive u/s 44AD (ITR-4)
BUSINESS_NAME = "business_name"
BUSINESS_CODE = "business_code"
BP_TURNOVER_44AD = "bp_turnover_44ad"
BP_RECEIPTS_OTHER_MODE_44AD = "bp_receipts_other_mode_44ad"
BP_PRESUMPTIVE_44AD = "bp_presumptive_44ad"
# ITR-1 salary schedule (utility / filed JSON)
SALARY_GROSS = "salary_gross"
SALARY_AS_PER_SECTION_17 = "salary_as_per_section_17"
NET_SALARY_UTILITY = "net_salary_utility"
ALLOWANCES_EXEMPT_US10_TOTAL = "allowances_exempt_us10_total"
STANDARD_DEDUCTION_US16IA = "standard_deduction_us16ia"
DEDUCTION_US16_TOTAL = "deduction_us16_total"
ENTERTAINMENT_ALLOWANCE_US16II = "entertainment_allowance_us16ii"
PROFESSIONAL_TAX_US16III = "professional_tax_us16iii"

# TaxComputation
TAX_NORMAL_RATES = "tax_normal_rates"
TAX_PAYABLE_ON_TOTAL_INCOME = "tax_payable_on_total_income"
CESS = "cess"
GROSS_TAX_LIABILITY = "gross_tax_liability"
NET_TAX_LIABILITY = "net_tax_liability"
ADVANCE_TAX = "advance_tax"
SELF_ASSESSMENT_TAX = "self_assessment_tax"
TDS_TOTAL = "tds_total"
TCS_TOTAL = "tcs_total"
TAXES_PAID_TOTAL = "taxes_paid_total"
REFUND_AMOUNT = "refund_amount"
REFUND_PRE_288B = "refund_pre_288b"
ROUNDED_REFUND_AMOUNT = "rounded_refund_amount"
DEMAND_AMOUNT = "demand_amount"
REBATE_87A = "rebate_87a"
TAX_RELIEF = "tax_relief"
INTEREST_234A = "interest_234a"
INTEREST_234B = "interest_234b"
INTEREST_234C = "interest_234c"
FEE_234F = "fee_234f"
TDS_FROM_SALARY = "tds_from_salary"
TDS_OTHER_THAN_SALARY = "tds_other_than_salary"
# Utility summary (ITR-1 tax computation block)
TOTAL_TAX_PLUS_INTEREST = "total_tax_plus_interest"

# ITR-1 filing / utility meta
FILING_DUE_DATE = "filing_due_date"
SEVENTH_PROVISO_139 = "seventh_proviso_139"
VERIFICATION_PLACE = "verification_place"
EMPLOYER_CATEGORY = "employer_category"

HEADER_FIELDS = [
    ASSESSEE_NAME,
    PAN,
    ASSESSMENT_YEAR,
    ITR_TYPE,
    FILING_DATE,
    FINANCIAL_YEAR,
    ORIGINAL_OR_REVISED,
    FILING_SECTION,
    STATUS,
    FILING_STATUS,
    REGIME,
    RESIDENTIAL_STATUS,
    FILING_DUE_DATE,
    SEVENTH_PROVISO_139,
]

PERSONAL_FIELDS = [
    FATHER_NAME,
    DATE_OF_BIRTH,
    GENDER,
    AADHAAR,
    EMAIL,
    MOBILE,
    ADDRESS,
    VERIFICATION_PLACE,
    EMPLOYER_CATEGORY,
]

INCOME_FIELDS = [
    INCOME_SALARY,
    INCOME_BUSINESS_PROFESSION,
    INCOME_HOUSE_PROPERTY,
    INCOME_OTHER_SOURCES,
    OTHER_SOURCE_NATURE,
    OS_INTEREST_SAVINGS,
    OS_INTEREST_TERM_DEPOSIT,
    OS_INTEREST_REFUND,
    BUSINESS_DEPRECIATION_BOOKS,
    BUSINESS_DEPRECIATION_IT,
    TOTAL_HEAD_WISE_INCOME,
    CURRENT_YEAR_LOSSES_ADJUSTMENT,
    BALANCE_AFTER_CYLA,
    BROUGHT_FORWARD_LOSS_SETOFF,
    GROSS_TOTAL_INCOME,
    DEDUCTION_80C,
    DEDUCTION_80D,
    DEDUCTION_80TTA,
    DEDUCTION_80G,
    TOTAL_DEDUCTIONS,
    TOTAL_INCOME,
    ROUNDED_TOTAL_INCOME,
    BUSINESS_NAME,
    BUSINESS_CODE,
    BP_TURNOVER_44AD,
    BP_RECEIPTS_OTHER_MODE_44AD,
    BP_PRESUMPTIVE_44AD,
    SALARY_GROSS,
    SALARY_AS_PER_SECTION_17,
    NET_SALARY_UTILITY,
    ALLOWANCES_EXEMPT_US10_TOTAL,
    STANDARD_DEDUCTION_US16IA,
    DEDUCTION_US16_TOTAL,
    ENTERTAINMENT_ALLOWANCE_US16II,
    PROFESSIONAL_TAX_US16III,
]

TAX_FIELDS = [
    TAX_NORMAL_RATES,
    TAX_PAYABLE_ON_TOTAL_INCOME,
    CESS,
    REBATE_87A,
    TAX_RELIEF,
    INTEREST_234A,
    INTEREST_234B,
    INTEREST_234C,
    FEE_234F,
    GROSS_TAX_LIABILITY,
    NET_TAX_LIABILITY,
    ADVANCE_TAX,
    SELF_ASSESSMENT_TAX,
    TDS_TOTAL,
    TDS_FROM_SALARY,
    TDS_OTHER_THAN_SALARY,
    TCS_TOTAL,
    TAXES_PAID_TOTAL,
    REFUND_AMOUNT,
    REFUND_PRE_288B,
    ROUNDED_REFUND_AMOUNT,
    DEMAND_AMOUNT,
    TOTAL_TAX_PLUS_INTEREST,
]

ALL_SCALAR_FIELDS = HEADER_FIELDS + PERSONAL_FIELDS + INCOME_FIELDS + TAX_FIELDS

CRITICAL_FOR_EXPORT = [
    ASSESSEE_NAME,
    PAN,
    ASSESSMENT_YEAR,
    GROSS_TOTAL_INCOME,
    TOTAL_INCOME,
    GROSS_TAX_LIABILITY,
    NET_TAX_LIABILITY,
]
