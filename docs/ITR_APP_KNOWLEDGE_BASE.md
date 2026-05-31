# ITR Summary Generator — Complete Knowledge Base

**Purpose:** Comprehensive reference for AI agents and developers working on the ITR computation summary feature. Read this before making changes to any `apps/*` code, ITR templates, or billing logic.

**Last updated:** 2026-05-31

---

## 1. Product Overview

### What It Does
The ITR Summary Generator is an **optional bundled Django app** within the BhagwatGitaGuide project that converts filed Income Tax Return (ITR) JSON files from the Indian income-tax portal into professional CA-style computation summary PDFs.

### Target Users
- Tax professionals (CAs, tax consultants)
- Individual taxpayers who need computation summaries for assessment workflows
- Businesses requiring standardized ITR documentation

### Supported ITR Types
| Type | Full Name | Use Case |
|------|-----------|----------|
| **ITR-1** (Sahaj) | Simplified return | Salaried individuals with income ≤₹50L |
| **ITR-3** | Business/Profession | Individuals with business/profession income |
| **ITR-4** (Sugam) | Presumptive taxation | Small business (44AD/44ADA/44AE) |

---

## 2. Architecture

### Toggle & Isolation
```
ITR_ENABLED=true   → ITR app active, mounted at ITR_URL_PREFIX
ITR_ENABLED=false  → Pure Bhagavad Gita deploy, no ITR routes/apps
```

### Shared vs Separate Components

| Component | Shared with Gita | Separate for ITR |
|-----------|------------------|------------------|
| Django `User` model | ✅ | — |
| Database | ✅ | — |
| Admin site | ✅ | — |
| SECRET_KEY | ✅ | — |
| Billing/Plans | — | ✅ `apps.billing`, `apps.accounts.UserProfile` |
| Templates | — | ✅ `templates/` (ITR-specific) |
| Static files | — | ✅ `static_itr/` |
| URL namespace | — | ✅ `/itr-computation/` |

### File Structure
```
BhagwatGitaGuide/
├── apps/                          # ITR-specific Django apps
│   ├── accounts/                  # UserProfile (ITR credits/plans)
│   │   ├── models.py             # UserProfile, QuotaSettings
│   │   ├── services.py           # can_export_pdf(), record_export()
│   │   ├── adapter.py            # ItrAccountAdapter for allauth
│   │   └── context_processors.py # google_oauth, account_profile
│   ├── billing/                   # Razorpay payments
│   │   ├── models.py             # RazorpayOrder, GuestOrder
│   │   ├── views.py              # checkout, verify, webhook
│   │   └── urls.py               # /billing/* routes
│   ├── documents/                 # File upload & lifecycle
│   │   ├── models.py             # Document, ExtractedField, BankDetail, TDSDetail
│   │   ├── views.py              # upload, list, detail, reprocess
│   │   ├── access.py             # document_for_request() auth helper
│   │   ├── session_docs.py       # Anonymous document tracking
│   │   └── urls.py               # /documents/* routes
│   ├── extractors/                # JSON parsing engine
│   │   ├── json_pipeline.py      # _parse_itr1(), _parse_itr3(), _parse_itr4()
│   │   ├── pipeline.py           # process_document_file() entry point
│   │   ├── queue.py              # schedule_document_processing() (sync/async)
│   │   ├── canonical.py          # Canonical field name constants
│   │   ├── validators.py         # Field validation rules
│   │   └── validation_engine.py  # Computation cross-checks
│   ├── exports/                   # PDF generation
│   │   ├── models.py             # ExportedSummary
│   │   ├── views.py              # export_pdf(), download_export()
│   │   ├── weasy_render.py       # WeasyPrint HTML→PDF
│   │   ├── tax_slabs.py          # New regime slab calculations
│   │   ├── retention.py          # purge_expired_exports()
│   │   └── urls.py               # /exports/* routes
│   ├── marketing/                 # Landing pages
│   │   ├── views.py              # home(), pricing()
│   │   ├── seo.py                # Structured data, meta tags
│   │   └── urls.py               # Root ITR routes
│   ├── reviews/                   # Human verification UI
│   │   ├── views.py              # review_document()
│   │   ├── models.py             # ReviewAction (audit trail)
│   │   └── field_labels.py       # Human-readable field names
│   ├── comments/                  # Public comments on pages
│   ├── analytics/                 # Audience tracking middleware
│   └── core/                      # Shared utilities
├── config/
│   ├── settings_itr.py           # register_itr_settings() — ITR config
│   └── urls_itr.py               # ITR URL patterns
├── templates/
│   ├── marketing/                # home.html, pricing.html
│   ├── documents/                # list.html, detail.html, upload.html
│   ├── reviews/                  # review.html
│   ├── exports/                  # ca_computation_weasy.html, export_confirm.html
│   ├── billing/                  # checkout_bundle.html
│   └── account/                  # allauth overrides
└── static_itr/                   # ITR-specific CSS, samples
```

---

## 3. Complete User Flow

### Flow Diagram
```
┌──────────────────────────────────────────────────────────────────────────┐
│                           USER JOURNEY                                    │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  1. LANDING PAGE                                                         │
│     /itr-computation/                                                    │
│     └── marketing/views.py::home()                                       │
│         • SEO-optimized landing                                          │
│         • Beta mode: try without account                                 │
│         • Google OAuth button (if configured)                            │
│                        ↓                                                 │
│  2. AUTHENTICATION                                                       │
│     /accounts/signup/ or /accounts/login/                                │
│     └── django-allauth                                                   │
│         • Email/password                                                 │
│         • Google OAuth (optional)                                        │
│                        ↓                                                 │
│  3. WORKSPACE                                                            │
│     /itr-computation/documents/                                          │
│     └── documents/views.py::document_list()                              │
│         • All user documents                                             │
│         • Plan status bar                                                │
│         • Upload CTA                                                     │
│                        ↓                                                 │
│  4. UPLOAD JSON                                                          │
│     /itr-computation/documents/upload/                                   │
│     └── documents/views.py::document_upload()                            │
│         • Accept .json file                                              │
│         • Create Document(status=UPLOADED)                               │
│         • Trigger extraction                                             │
│                        ↓                                                 │
│  5. EXTRACTION PIPELINE                                                  │
│     └── extractors/queue.py::schedule_document_processing()              │
│         ├── SYNC (default): Direct processing                            │
│         └── ASYNC: django-rq background job                              │
│                                                                          │
│     └── extractors/json_pipeline.py::process_json_document_file()        │
│         • Detect ITR type (ITR-1/3/4)                                    │
│         • Parse JSON → ExtractedField rows                               │
│         • Create BankDetail, TDSDetail rows                              │
│         • Run validation                                                 │
│         • Set status=REVIEW_REQUIRED                                     │
│                        ↓                                                 │
│  6. DOCUMENT DETAIL                                                      │
│     /itr-computation/documents/<pk>/                                     │
│     └── documents/views.py::document_detail()                            │
│         • Status display                                                 │
│         • HTMX polling (if processing)                                   │
│         • Review / Export links                                          │
│                        ↓                                                 │
│  7. HUMAN REVIEW                                                         │
│     /itr-computation/reviews/<pk>/                                       │
│     └── reviews/views.py::review_document()                              │
│         • Grouped field display                                          │
│         • Editable inputs                                                │
│         • Save / Approve actions                                         │
│         • Creates ReviewAction audit trail                               │
│         • Approve → status=APPROVED                                      │
│                        ↓                                                 │
│  8. PAYMENT (if no credits)                                              │
│     /itr-computation/billing/checkout/<bundle>/                          │
│     └── billing/views.py::checkout_bundle()                              │
│         • PAYG (₹50/1 export)                                            │
│         • Essentials (₹1,000/40 exports/year)                            │
│         • Professional (₹2,000/100 exports/year)                         │
│         • Razorpay inline checkout                                       │
│         • Signature verification                                         │
│         • Grant credits                                                  │
│                        ↓                                                 │
│  9. PDF EXPORT                                                           │
│     /itr-computation/exports/<pk>/pdf/                                   │
│     └── exports/views.py::export_pdf()                                   │
│         • Validate document ready                                        │
│         • Check credits/plan                                             │
│         • Generate PDF (WeasyPrint)                                      │
│         • Create ExportedSummary                                         │
│         • Deduct credit                                                  │
│         • Cleanup input file                                             │
│                        ↓                                                 │
│  10. DOWNLOAD                                                            │
│      /itr-computation/exports/<pk>/exports/<id>/download/                │
│      └── exports/views.py::download_export()                             │
│          • Serve PDF (24h retention)                                     │
│          • After expiry: "Expired" badge                                 │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Data Models

### apps/documents/models.py

#### Document
```python
class Document(models.Model):
    # Lifecycle statuses
    STATUS_UPLOADED = "uploaded"
    STATUS_QUEUED = "queued"           # Waiting for async worker
    STATUS_CLASSIFYING = "classifying" # Detecting ITR type
    STATUS_EXTRACTING = "extracting"   # Parsing fields
    STATUS_REVIEW_REQUIRED = "review_required"
    STATUS_APPROVED = "approved"       # Ready for export
    STATUS_EXPORTED = "exported"       # PDF generated
    STATUS_FAILED = "failed"

    # ITR types
    TYPE_ITR1 = "ITR1"
    TYPE_ITR3 = "ITR3"
    TYPE_ITR4 = "ITR4"
    TYPE_UNKNOWN = "UNKNOWN"

    user = ForeignKey(User)           # Owner (nullable for beta/guest)
    uploaded_file = FileField()        # Original JSON
    original_filename = CharField()
    file_hash = CharField()            # SHA256 for dedup
    detected_type = CharField()        # ITR1/ITR3/ITR4
    status = CharField()
    error_message = TextField()
    review_completed = BooleanField()
    created_at = DateTimeField()
    updated_at = DateTimeField()
```

#### ExtractedField
```python
class ExtractedField(models.Model):
    document = ForeignKey(Document)
    field_name = CharField()          # Canonical name (see canonical.py)
    raw_value = TextField()           # Original from JSON
    normalized_value = TextField()    # Cleaned/formatted
    confidence_score = DecimalField() # 0-100 extraction confidence
    requires_review = BooleanField()
    is_approved = BooleanField()

    # Unique constraint: one field per document
    class Meta:
        constraints = [UniqueConstraint(fields=["document", "field_name"])]
```

#### BankDetail
```python
class BankDetail(models.Model):
    document = ForeignKey(Document)
    sort_order = PositiveSmallIntegerField()
    bank_name = CharField()
    ifsc = CharField()
    account_number = CharField()
    account_type = CharField()       # Savings/Current/CC/OD
    nominate_for_refund = CharField() # Yes/No
```

#### TDSDetail
```python
class TDSDetail(models.Model):
    document = ForeignKey(Document)
    deductor_name = CharField()
    tan_pan = CharField()
    section = CharField()            # 192/194A/etc.
    amount_paid = DecimalField()
    total_tax_deducted = DecimalField()
    amount_claimed_this_year = DecimalField()
    head_of_income = CharField()     # Salary/Other
```

### apps/accounts/models.py

#### UserProfile
```python
class UserProfile(models.Model):
    user = OneToOneField(User, related_name="itr_profile")

    # Credit wallet (never expires)
    itr_export_credits = PositiveIntegerField(default=0)

    # Annual plan
    itr_plan = CharField()           # "" / "essentials" / "professional"
    itr_plan_until = DateTimeField() # Expiry timestamp
    itr_annual_exports_used = PositiveIntegerField(default=0)

    # Annual limits
    ANNUAL_EXPORT_LIMITS = {
        "essentials": 40,
        "professional": 100,
    }
```

### apps/billing/models.py

#### RazorpayOrder
```python
class RazorpayOrder(models.Model):
    user = ForeignKey(User)
    razorpay_order_id = CharField()
    amount_paise = PositiveIntegerField()
    bundle_key = CharField()         # payg/essentials/professional
    credits_granted = PositiveIntegerField()
    status = CharField()             # created/paid/failed
    razorpay_payment_id = CharField()
    raw_payload = JSONField()
```

#### GuestOrder
```python
class GuestOrder(models.Model):
    guest_name = CharField()
    guest_email = EmailField()
    razorpay_order_id = CharField()
    amount_paise = PositiveIntegerField(default=5000)  # ₹50
    status = CharField()
    credits_granted = PositiveIntegerField(default=1)
    export_used = BooleanField(default=False)
```

### apps/exports/models.py

#### ExportedSummary
```python
class ExportedSummary(models.Model):
    document = ForeignKey(Document, related_name="exports")
    pdf_file = FileField(upload_to="itr_exports/")
    created_at = DateTimeField()
    expires_at = DateTimeField()     # Retention window end
    pdf_purged_at = DateTimeField()  # When file was deleted

    def can_download(self) -> bool:
        return self.pdf_purged_at is None and timezone.now() < self.expires_at
```

---

## 5. Canonical Field Names

All extracted fields use canonical names defined in `apps/extractors/canonical.py`:

### Header Fields
```python
ASSESSEE_NAME = "assessee_name"
PAN = "pan"
ASSESSMENT_YEAR = "assessment_year"
ITR_TYPE = "itr_type"
FILING_DATE = "filing_date"
FINANCIAL_YEAR = "financial_year"
ORIGINAL_OR_REVISED = "original_or_revised"
REGIME = "regime"                    # New Regime / Old Regime
RESIDENTIAL_STATUS = "residential_status"
```

### Personal Fields
```python
FATHER_NAME = "father_name"
DATE_OF_BIRTH = "date_of_birth"
GENDER = "gender"
AADHAAR = "aadhaar"
EMAIL = "email"
MOBILE = "mobile"
ADDRESS = "address"
```

### Income Fields
```python
INCOME_SALARY = "income_salary"
INCOME_BUSINESS_PROFESSION = "income_business_profession"
INCOME_HOUSE_PROPERTY = "income_house_property"
INCOME_OTHER_SOURCES = "income_other_sources"
GROSS_TOTAL_INCOME = "gross_total_income"
TOTAL_DEDUCTIONS = "total_deductions"
TOTAL_INCOME = "total_income"
ROUNDED_TOTAL_INCOME = "rounded_total_income"

# ITR-4 Schedule BP (44AD)
BP_TURNOVER_44AD = "bp_turnover_44ad"
BP_PRESUMPTIVE_44AD = "bp_presumptive_44ad"
```

### Tax Fields
```python
TAX_NORMAL_RATES = "tax_normal_rates"
REBATE_87A = "rebate_87a"
CESS = "cess"
GROSS_TAX_LIABILITY = "gross_tax_liability"
NET_TAX_LIABILITY = "net_tax_liability"
TDS_TOTAL = "tds_total"
ADVANCE_TAX = "advance_tax"
TAXES_PAID_TOTAL = "taxes_paid_total"
REFUND_AMOUNT = "refund_amount"
DEMAND_AMOUNT = "demand_amount"
```

---

## 6. URL Routes

### Main URL Configuration (config/urls.py)
```python
if ITR_ENABLED:
    urlpatterns += [
        path("accounts/", include("allauth.urls")),  # Auth
        path(f"{ITR_URL_PREFIX}/", include("config.urls_itr")),
    ]
```

### ITR Routes (config/urls_itr.py)
```python
urlpatterns = [
    path("billing/", include("apps.billing.urls")),
    path("documents/", include("apps.documents.urls")),
    path("reviews/", include("apps.reviews.urls")),
    path("exports/", include("apps.exports.urls")),
    path("comments/", include("apps.comments.urls")),
    path("", include("apps.marketing.urls")),  # Landing pages
]
```

### Route Summary
| Route | View | Purpose |
|-------|------|---------|
| `/itr-computation/` | marketing:home | Landing page |
| `/itr-computation/pricing/` | marketing:pricing | Pricing page |
| `/itr-computation/documents/` | documents:list | Workspace |
| `/itr-computation/documents/upload/` | documents:upload | Upload JSON |
| `/itr-computation/documents/<pk>/` | documents:detail | Document detail |
| `/itr-computation/documents/<pk>/status/` | documents:status | HTMX status poll |
| `/itr-computation/documents/<pk>/reprocess/` | documents:reprocess | Re-import |
| `/itr-computation/documents/beta-try/` | documents:beta_try | Anonymous upload |
| `/itr-computation/reviews/<pk>/` | reviews:review | Field review |
| `/itr-computation/exports/<pk>/pdf/` | exports:create | Generate PDF |
| `/itr-computation/exports/<pk>/exports/<id>/download/` | exports:download | Download PDF |
| `/itr-computation/billing/checkout/<bundle>/` | billing:checkout_bundle | Checkout page |
| `/itr-computation/billing/checkout/<bundle>/init/` | billing:checkout_bundle_init | Create order (AJAX) |
| `/itr-computation/billing/success/` | billing:payment_success | Verify payment |
| `/itr-computation/billing/webhook/razorpay/` | billing:razorpay_webhook | Webhook |
| `/itr-computation/billing/guest-checkout/` | billing:guest_checkout | Guest payment |
| `/accounts/login/` | allauth | Login |
| `/accounts/signup/` | allauth | Registration |
| `/accounts/google/login/` | allauth | Google OAuth |

---

## 7. Environment Variables

### Core ITR Settings
```bash
# Enable/disable ITR app
ITR_ENABLED=true                           # default: true

# URL prefix for ITR routes
ITR_URL_PREFIX=/itr-computation            # default: /itr-computation

# Contact email shown on ITR pages
ITR_CONTACT_EMAIL=support@example.com
```

### Pricing (in paise)
```bash
ITR_PAYG_AMOUNT_PAISE=5000                 # ₹50 for 1 export
ITR_ESSENTIALS_AMOUNT_PAISE=100000         # ₹1,000 for 40/year
ITR_PROFESSIONAL_AMOUNT_PAISE=200000       # ₹2,000 for 100/year
```

### Razorpay
```bash
RAZORPAY_KEY_ID=rzp_test_...
RAZORPAY_KEY_SECRET=...
ITR_RAZORPAY_WEBHOOK_SECRET=...            # Webhook signature verification
```

### Retention & Cleanup
```bash
ITR_OUTPUT_RETENTION_HOURS=24              # PDF download window
ITR_DELETE_INPUT_AFTER_EXPORT=true         # Remove JSON after PDF generated
```

### Processing Mode
```bash
ITR_ASYNC_EXTRACTION=false                 # true: django-rq background jobs
```

### Beta / Anonymous Mode
```bash
ITR_BETA_RELEASE=true                      # Enable try-without-account
ITR_ANONYMOUS_MAX_DOCS_PER_SESSION=8       # Max anonymous uploads per session
```

### PDF Customization
```bash
COMPUTATION_PDF_FIRM_NAME="Your Firm Name" # Header on PDF
COMPUTATION_PDF_REPORT_DATE=               # Override report date
COMPUTATION_PDF_FOOTER_BRAND=              # Footer branding
```

### Google OAuth (django-allauth)
```bash
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
# Redirect URI: https://<host>/accounts/google/login/callback/
```

### Email Verification
```bash
ACCOUNT_EMAIL_VERIFICATION=none            # none/optional/mandatory
```

---

## 8. Payment & Billing System

### Credit Bundles
```python
ITR_BUNDLES = {
    "payg": {
        "key": "payg",
        "label": "Pay-as-you-go",
        "credits": 1,
        "amount_paise": 5000,           # ₹50
        "description": "One PDF export",
    },
    "essentials": {
        "key": "essentials",
        "label": "Essentials",
        "credits": 40,
        "annual": True,
        "amount_paise": 100000,         # ₹1,000
        "description": "40 PDF exports per year",
        "badge": "Popular",
    },
    "professional": {
        "key": "professional",
        "label": "Professional",
        "credits": 100,
        "annual": True,
        "amount_paise": 200000,         # ₹2,000
        "description": "100 PDF exports per year",
        "badge": "Best value",
    },
}
```

### Credit Consumption Priority
```python
# In apps/accounts/services.py::can_export_pdf()
def can_export_pdf(profile: UserProfile) -> tuple[bool, str]:
    # 1. Check annual plan first
    if active_annual_plan and remaining_annual_exports > 0:
        return True, ""

    # 2. Check PAYG credits
    if profile.itr_export_credits > 0:
        return True, ""

    # 3. No credits available
    return False, "Purchase a plan to generate PDF exports."
```

### Payment Flow
```
1. User clicks "Buy Essentials"
2. → GET /billing/checkout/essentials/
3. → Page loads with Razorpay script
4. User clicks "Pay" → AJAX POST /billing/checkout/essentials/init/
5. → Server creates RazorpayOrder, returns order_id
6. → Client opens Razorpay modal
7. User completes payment in Razorpay
8. → Razorpay returns signature to client
9. → Client POST /billing/success/ with order_id, payment_id, signature
10. → Server verifies signature with Razorpay
11. → Grant credits to UserProfile
12. → Redirect to workspace with success message

Webhook (backup):
- POST /billing/webhook/razorpay/
- Verifies X-Razorpay-Signature header
- Handles payment.captured event
- Idempotent: skips if already processed
```

### Guest Payment
```
1. Anonymous user at export paywall
2. → GET /billing/guest-checkout/
3. → Enter name, email
4. → AJAX POST /billing/guest-checkout/init/
5. → Creates GuestOrder, returns order_id
6. → Razorpay payment
7. → POST /billing/guest-success/
8. → Sets session credit + signed URL token
9. → Redirect back to document with guest_token
10. → Token allows one export (24h validity)
```

---

## 9. JSON Parsing Logic

### Detection & Dispatch
```python
# apps/extractors/json_pipeline.py::process_json_document_file()
def process_json_document_file(document: Document):
    data = json.load(document.uploaded_file)

    # Type detection
    if "Form_ITR1" in data or "ITR1" in data:
        detected_type = Document.TYPE_ITR1
        fields, banks, tds = _parse_itr1(data)
    elif "Form_ITR3" in data or "ITR3" in data:
        detected_type = Document.TYPE_ITR3
        fields, banks, tds = _parse_itr3(data)
    elif "Form_ITR4" in data or "ITR4" in data:
        detected_type = Document.TYPE_ITR4
        fields, banks, tds = _parse_itr4(data)
    else:
        raise ValueError("Unknown ITR type")

    # Save extracted data
    document.detected_type = detected_type
    _save_extracted_fields(document, fields)
    _save_bank_details(document, banks)
    _save_tds_details(document, tds)

    # Run validation
    issues = issues_after_extraction(document, fields)
    if blocking_issues(issues):
        document.status = Document.STATUS_FAILED
    else:
        document.status = Document.STATUS_REVIEW_REQUIRED
```

### ITR-1 Parsing (Sahaj)
Key JSON paths:
```python
# Header
form = data["Form_ITR1"]
ay = form["AssessmentYear"]  # "2025" → "2025-26"

# Personal
personal_info = data["PersonalInfo"]
name = f"{personal_info['AssesseeName']['FirstName']} {personal_info['AssesseeName']['SurNameOrOrgName']}"
pan = personal_info["PAN"]
address = personal_info["Address"]

# Income
income = data["ITR1_IncomeDeductions"]
salary = income["IncomeFromSal"]
house_property = income["TotalIncomeOfHP"]
other_sources = income["IncomeOthSrc"]
gross_total = income["GrossTotIncome"]
deductions = income["DeductUndChapVIA"]["TotalChapVIADeductions"]
total_income = income["TotalIncome"]

# Tax
tax = data["ITR1_TaxComputation"]
tax_payable = tax["TotalTaxPayable"]
rebate = tax["Rebate87A"]
cess = tax["EducationCess"]
net_tax = tax["NetTaxLiability"]

# Refund/Demand
taxes_paid = data["TaxPaid"]["TaxesPaid"]["TotalTaxesPaid"]
refund = data["Refund"]["RefundDue"]
demand = data["TaxPaid"]["BalTaxPayable"]

# Banks
banks = data["Refund"]["BankAccountDtls"]["AddtnlBankDetails"]

# TDS
tds = data["TDSonOthThanSals"]["TDSonOthThanSal"]
```

### ITR-4 Parsing (Sugam - 44AD)
Key additions:
```python
# Schedule BP (presumptive business)
bp = data["ScheduleBP"]
turnover = bp["NatOfBus44AD"][0]["GrsTrnOverAnyOthMode"]
presumptive = bp["NatOfBus44AD"][0]["PresumpIncUs44AD"]
business_name = bp["NatOfBus44AD"][0]["NameOfBusiness"]
```

### ITR-3 Parsing (Business)
Key additions:
```python
# Business income
part_b = data["PartB_TI"]
business_income = part_b["ProfBusGain"]["TotProfBusGain"]

# Depreciation
depreciation_books = data["ScheduleDEP"]["TotDepnAsTotIncBooks"]
depreciation_it = data["ScheduleDEP"]["TotDepnAsTotIncIT"]

# TDS on salary (Schedule TDS1)
tds_salary = data["ScheduleTDS1"]["TDSSalaryDtls"]
```

### Normalization Helpers
```python
def _format_ay(ay: str) -> str:
    """'2025' → '2025-26'"""

def _format_dob_iso(iso: str) -> str:
    """'1990-05-15' → '15-May-1990'"""

def _compose_address(addr: dict) -> str:
    """Combine address fields into single line"""

def _account_type_label(code: str) -> str:
    """'SB' → 'Savings', 'CA' → 'Current'"""

def _normalize_tds_section(sec: str) -> str:
    """'92A' → '192A'"""
```

---

## 10. PDF Generation

### WeasyPrint Pipeline
```python
# apps/exports/weasy_render.py

def render_computation_weasy_pdf(context: dict) -> bytes:
    # 1. Augment context with display data
    ctx = augment_weasy_context(context)

    # 2. Render HTML template
    html = render_to_string("exports/ca_computation_weasy.html", ctx)

    # 3. Convert to PDF
    buf = BytesIO()
    HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf(buf)
    return buf.getvalue()

def augment_weasy_context(base: dict) -> dict:
    # Add slab breakdown for display
    ctx["slab_rows"] = new_regime_slab_rows_for_display(total_income)

    # Add firm header
    ctx["computation_firm_name"] = settings.COMPUTATION_PDF_FIRM_NAME

    # Add footer date
    ctx["footer_report_date"] = _footer_report_date_line(fields)

    # Pick primary bank (nominated for refund)
    ctx["primary_bank"] = _pick_primary_bank(banks)

    return ctx
```

### Tax Slab Calculation (New Regime A.Y. 2025-26)
```python
# apps/exports/tax_slabs.py

_SLAB_META = (
    (Decimal("300000"), Decimal("0"), "0"),      # 0-3L: Nil
    (Decimal("400000"), Decimal("0.05"), "5"),   # 3-7L: 5%
    (Decimal("300000"), Decimal("0.10"), "10"),  # 7-10L: 10%
    (Decimal("300000"), Decimal("0.15"), "15"),  # 10-13L: 15%
    (Decimal("300000"), Decimal("0.20"), "20"),  # 13-16L: 20%
    (Decimal("300000"), Decimal("0.25"), "25"),  # 16-19L: 25%
    # Above 19L: 30%
)

def new_regime_tax_at_normal_rates(total_income: Decimal) -> Decimal:
    """Calculate tax before cess and rebate."""

def round_total_income_288a(value: Decimal) -> Decimal:
    """Round to nearest ₹10 (Section 288A style)."""

def round_refund_288b(value: Decimal) -> Decimal:
    """Round refund to nearest ₹10 (Section 288B style)."""
```

### PDF Template Structure
```html
<!-- templates/exports/ca_computation_weasy.html -->
<html>
<head>
    <style>
        /* CA-style beige sections, professional typography */
    </style>
</head>
<body>
    <!-- Header: Firm name, report date -->
    <!-- Section 1: Assessee details (PAN, name, AY) -->
    <!-- Section 2: Income computation (head-wise breakdown) -->
    <!-- Section 3: Tax computation (slabs, cess, rebate) -->
    <!-- Section 4: Tax paid / Refund / Demand -->
    <!-- Section 5: Bank details -->
    <!-- Footer: Generated timestamp -->
</body>
</html>
```

### OS Dependencies (WeasyPrint)
WeasyPrint requires native libraries. The Dockerfile installs:
```dockerfile
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libcairo2 \
    libffi-dev \
    shared-mime-info \
    fonts-liberation
```

---

## 11. Retention & Cleanup

### PDF Retention
```python
# apps/exports/retention.py

def purge_expired_exports(now=None):
    """Remove PDF files past retention window."""
    qs = ExportedSummary.objects.filter(
        expires_at__lte=now,
        pdf_purged_at__isnull=True
    )
    for exp in qs:
        exp.pdf_file.delete(save=False)  # Delete blob
        exp.pdf_purged_at = now          # Mark purged
        exp.save()
```

### Input Cleanup
```python
def delete_document_upload_after_export(document):
    """Remove uploaded JSON after successful export."""
    if settings.ITR_DELETE_INPUT_AFTER_EXPORT:
        document.uploaded_file.delete(save=False)
        document.uploaded_file = None
        document.save()
```

### Management Command
```bash
# Cron job for retention cleanup
python manage.py purge_itr_retention
```

---

## 12. Security Considerations

### Authentication
- All document/export routes require `@login_required` (except beta mode)
- Documents are user-scoped: `document_for_request()` checks ownership
- Guest mode uses session-based tracking + signed URL tokens

### Payment Security
- Razorpay signature verification on all payment callbacks
- Webhook signature verification via `X-Razorpay-Signature`
- Idempotent payment processing (checks if already paid)
- CSRF protection on all form submissions

### Data Retention
- Uploaded JSON can contain PII (PAN, Aadhaar, address)
- Default: Delete input after export
- PDF expires after 24 hours
- User can re-upload if needed

### File Upload
- Only `.json` files accepted
- Max file size enforced (Django setting)
- File hash computed for deduplication
- Files stored in `media/itr_uploads/`

---

## 13. Testing

### Run Tests
```bash
# From project root
python manage.py test apps.documents apps.extractors apps.exports apps.billing

# Or with Makefile
make test
```

### Key Test Files
- `apps/documents/tests.py` - Upload, status transitions
- `apps/extractors/tests/` - JSON parsing for each ITR type
- `apps/exports/tests/` - PDF generation, retention
- `apps/billing/tests.py` - Payment flows (mock Razorpay)

---

## 14. Common Operations

### Add Support for New ITR Type
1. Add type constant to `apps/documents/models.py::Document.TYPE_*`
2. Create parser in `apps/extractors/json_pipeline.py::_parse_itr_X()`
3. Update `process_json_document_file()` detection logic
4. Add any new canonical fields to `apps/extractors/canonical.py`
5. Update field labels in `apps/reviews/field_labels.py`
6. Add test cases

### Modify PDF Layout
1. Edit `templates/exports/ca_computation_weasy.html`
2. Update `apps/exports/weasy_render.py::augment_weasy_context()` if new data needed
3. Test locally with sample documents

### Change Pricing
1. Update `.env` variables (`ITR_*_AMOUNT_PAISE`)
2. Or modify `apps/billing/views.py::ITR_BUNDLES` defaults
3. Redeploy

### Debug Extraction Issues
```python
# In Django shell
from apps.documents.models import Document
from apps.extractors.json_pipeline import process_json_document_file

doc = Document.objects.get(pk=123)
process_json_document_file(doc)  # Re-run extraction

# Check extracted fields
for f in doc.extracted_fields.all():
    print(f"{f.field_name}: {f.normalized_value}")
```

---

## 15. Troubleshooting

### "WeasyPrint not available"
- OS libraries missing (Pango, Cairo, GLib)
- Solution: Check Dockerfile or install via apt/brew

### "Unknown ITR type"
- JSON structure not recognized
- Check for `Form_ITR1`, `Form_ITR3`, `Form_ITR4` keys
- May be unfiled/draft JSON (not supported)

### Payment not reflecting
1. Check `RazorpayOrder` status in admin
2. Verify webhook received (`/billing/webhook/razorpay/`)
3. Check server logs for verification errors
4. Manual credit: Update `UserProfile.itr_export_credits`

### PDF generation fails
1. Check document status is `APPROVED`
2. Check blocking validation issues
3. Check WeasyPrint installation
4. Check template syntax errors

---

*This document should be read by AI agents before making changes to ITR-related code. Update this file when adding new features or changing architecture.*
