"""CA / tax services — catalog, landing pages, and appointment choices."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CaService:
    key: str
    label: str
    price_display: str
    category: str


CA_SERVICES: tuple[CaService, ...] = (
    CaService("itr1_filing", "ITR-1 filing", "₹800", "ITR filing"),
    CaService("itr2_filing", "ITR-2 filing", "₹1,000", "ITR filing"),
    CaService("itr3_filing", "ITR-3 filing", "₹2,000", "ITR filing"),
    CaService("itr4_filing", "ITR-4 filing", "₹1,500", "ITR filing"),
    CaService("gst_registration", "GST registration", "₹2,000", "GST"),
    CaService("gst_nil_filing", "GST filing — nil return", "from ₹500", "GST"),
    CaService(
        "gst_filing_under_50l",
        "GST filing — turnover under ₹50 lakh",
        "₹1,000",
        "GST",
    ),
    CaService(
        "gst_filing_over_50l",
        "GST filing — turnover above ₹50 lakh",
        "₹2,000",
        "GST",
    ),
    CaService("msme_udyam", "MSME Udyam registration", "₹1,000", "Business registration"),
)

CA_SERVICE_BY_KEY = {s.key: s for s in CA_SERVICES}

SERVICE_CHOICES = [(s.key, f"{s.label} ({s.price_display})") for s in CA_SERVICES]

ITR_FILING_SERVICES = tuple(s for s in CA_SERVICES if s.category == "ITR filing")

DOCUMENT_TYPE_TO_SERVICE = {
    "ITR1": "itr1_filing",
    "ITR2": "itr2_filing",
    "ITR3": "itr3_filing",
    "ITR4": "itr4_filing",
}


def services_by_category() -> dict[str, list[CaService]]:
    grouped: dict[str, list[CaService]] = {}
    for svc in CA_SERVICES:
        grouped.setdefault(svc.category, []).append(svc)
    return grouped


@dataclass(frozen=True)
class ServicePageContent:
    slug: str
    service_key: str
    page_title: str
    headline: str
    meta_description: str
    intro: str
    tagline: str
    eligible: tuple[str, ...]
    not_eligible: tuple[str, ...]
    process_steps: tuple[str, ...]
    documents: tuple[str, ...]
    faqs: tuple[tuple[str, str], ...]


SERVICE_PAGES: dict[str, ServicePageContent] = {
    "itr-1-filing": ServicePageContent(
        slug="itr-1-filing",
        service_key="itr1_filing",
        page_title="ITR-1 (Sahaj) Filing Service — From ₹800 | India",
        headline="ITR-1 (Sahaj) filing with CA support",
        meta_description=(
            "Expert ITR-1 filing for salaried individuals and pensioners. "
            "Form 16 review, e-filing, and acknowledgment — from ₹800."
        ),
        tagline="Salaried · one house property · income up to ₹50 lakh",
        intro=(
            "Ideal if your income is mostly from salary or pension, with at most one house property "
            "and no capital gains. We prepare, review, and e-file your return."
        ),
        eligible=(
            "Residents with total income up to ₹50 lakh",
            "Salary, pension, or one house property",
            "Other sources except lottery / gambling",
            "Agricultural income up to ₹5,000",
        ),
        not_eligible=(
            "Director of a company",
            "Unlisted equity share investments",
            "Capital gains or foreign income",
            "Business or professional income",
        ),
        process_steps=(
            "Book & share Form 16 and bank details",
            "CA verifies figures and deductions",
            "You approve the draft computation",
            "E-filing with acknowledgment delivered",
        ),
        documents=("Form 16", "Bank statements", "Home loan interest certificate (if any)", "Investment proofs u/s 80C"),
        faqs=(
            ("How long does ITR-1 filing take?", "Usually 1–2 business days after documents are complete."),
            ("Can I claim 80C deductions?", "Yes — share investment proofs and we include eligible deductions."),
        ),
    ),
    "itr-2-filing": ServicePageContent(
        slug="itr-2-filing",
        service_key="itr2_filing",
        page_title="ITR-2 Filing Service — Capital Gains & Multiple Properties | From ₹1,000",
        headline="ITR-2 filing for capital gains & complex income",
        meta_description=(
            "ITR-2 filing for capital gains, multiple properties, foreign income, and directors. "
            "CA-reviewed e-filing from ₹1,000."
        ),
        tagline="Capital gains · multiple properties · foreign income",
        intro=(
            "For individuals and HUFs without business income who need ITR-2 — capital gains, "
            "more than one house property, or foreign assets."
        ),
        eligible=(
            "Capital gains from shares, property, or mutual funds",
            "Income from more than one house property",
            "Foreign income or assets",
            "Directors or unlisted equity investments",
        ),
        not_eligible=(
            "Business or professional income (use ITR-3 or ITR-4)",
            "Partners in partnership firms",
            "Presumptive taxation u/s 44AD / 44ADA / 44AE",
        ),
        process_steps=(
            "Book & share capital-gains statements / property docs",
            "CA maps income heads and sets off losses",
            "Draft review with you before filing",
            "E-file + computation summary package",
        ),
        documents=(
            "Form 16 (if salaried)",
            "Capital gains statements (broker / property)",
            "Property purchase & sale documents",
            "Foreign income proofs (if applicable)",
        ),
        faqs=(
            ("I already have a JSON from the portal — can you help?", "Yes — upload on our homepage for a ₹20 PDF preview, then book filing here."),
            ("Do you handle crypto gains?", "Share your transaction summary — we assess scope during callback."),
        ),
    ),
    "itr-3-filing": ServicePageContent(
        slug="itr-3-filing",
        service_key="itr3_filing",
        page_title="ITR-3 Filing Service — Business & Professional Income | From ₹2,000",
        headline="ITR-3 filing for business & professionals",
        meta_description=(
            "ITR-3 filing for business owners, freelancers, and professionals. "
            "Books review, tax optimization, e-filing from ₹2,000."
        ),
        tagline="Business income · freelancing · partnership profits",
        intro=(
            "Full ITR-3 support when you have business or professional income with proper books, "
            "or complex combinations of salary plus business."
        ),
        eligible=(
            "Business owners with books of accounts",
            "Professionals — doctors, lawyers, consultants",
            "Freelancers with business income",
            "Partners in firms (where applicable)",
        ),
        not_eligible=(
            "Presumptive scheme eligible cases (consider ITR-4)",
            "Simple salary-only returns (ITR-1)",
        ),
        process_steps=(
            "Book & share P&L / balance sheet or books summary",
            "CA prepares computation and optimizes deductions",
            "Joint review before submission",
            "E-filing + documentation pack",
        ),
        documents=(
            "Profit & loss statement",
            "Balance sheet (if applicable)",
            "Bank statements",
            "GST returns (if registered)",
            "Form 16 (if also salaried)",
        ),
        faqs=(
            ("Is audit support included?", "Scope is confirmed on callback — audit support can be quoted separately."),
            ("What if I use presumptive taxation?", "You may qualify for ITR-4 instead — we'll guide you on the call."),
        ),
    ),
    "itr-4-filing": ServicePageContent(
        slug="itr-4-filing",
        service_key="itr4_filing",
        page_title="ITR-4 (Sugam) Filing — Presumptive Taxation | From ₹1,500",
        headline="ITR-4 (Sugam) — presumptive business income",
        meta_description=(
            "ITR-4 filing under sections 44AD, 44ADA, 44AE. "
            "Small business & professional presumptive returns from ₹1,500."
        ),
        tagline="Presumptive tax · turnover up to ₹2 Cr · professionals up to ₹50L",
        intro=(
            "Simplified filing for small businesses and professionals under presumptive taxation — "
            "no full audit trail required in most cases."
        ),
        eligible=(
            "Small business u/s 44AD (turnover up to ₹2 crore)",
            "Professionals u/s 44ADA (receipts up to ₹50 lakh)",
            "Transport business u/s 44AE (up to 10 vehicles)",
            "Also salary or one house property alongside",
        ),
        not_eligible=(
            "Capital gains income",
            "More than one house property",
            "Foreign income or assets",
            "Directors or unlisted equity shares",
        ),
        process_steps=(
            "Book & share turnover / receipts summary",
            "CA applies presumptive rates and checks eligibility",
            "You approve before e-filing",
            "Acknowledgment + computation delivered",
        ),
        documents=(
            "Turnover or gross receipts statement",
            "Bank statements",
            "Form 16 (if salaried)",
            "Vehicle RC (for 44AE transport)",
        ),
        faqs=(
            ("Can I switch from ITR-3 to ITR-4?", "Only if you meet presumptive eligibility — we'll confirm on review."),
            ("Is GST filing bundled?", "GST is separate — see our GST services page."),
        ),
    ),
    "gst-registration": ServicePageContent(
        slug="gst-registration",
        service_key="gst_registration",
        page_title="GST Registration Service — New GSTIN | ₹2,000",
        headline="GST registration for your business",
        meta_description=(
            "End-to-end GST registration — document prep, application filing, and GSTIN delivery. Flat ₹2,000."
        ),
        tagline="New GSTIN · proprietorship · partnership · company",
        intro=(
            "Starting a business or crossing the GST threshold? We handle documentation, "
            "portal filing, and follow-up until your GSTIN is issued."
        ),
        eligible=(
            "New businesses needing GSTIN",
            "Existing businesses crossing turnover threshold",
            "Voluntary registration",
            "E-commerce sellers",
        ),
        not_eligible=(),
        process_steps=(
            "Book & share PAN, address proof, bank details",
            "We prepare and file GST REG-01",
            "Track ARN and respond to queries",
            "GSTIN certificate delivered",
        ),
        documents=("PAN", "Aadhaar", "Address proof", "Bank account proof", "Business registration (if any)"),
        faqs=(
            ("How long does registration take?", "Typically 3–7 working days after documents are complete."),
            ("Do you also file returns?", "Yes — see our GST filing page for monthly/quarterly returns."),
        ),
    ),
    "gst-filing": ServicePageContent(
        slug="gst-filing",
        service_key="gst_nil_filing",
        page_title="GST Return Filing — Nil to High Turnover | From ₹500",
        headline="GST return filing (GSTR-1 / GSTR-3B)",
        meta_description=(
            "GST return filing for nil, small, and high-turnover businesses. "
            "From ₹500 per return. CA-reviewed submissions."
        ),
        tagline="Nil returns · turnover under ₹50L · above ₹50L",
        intro=(
            "Stay compliant with timely GSTR-1 and GSTR-3B filing. Pricing depends on turnover "
            "and transaction volume — pick the tier that fits on the booking form."
        ),
        eligible=(
            "Registered GST taxpayers",
            "Nil filers with no outward supplies",
            "Small business under ₹50 lakh turnover",
            "Higher turnover with regular sales",
        ),
        not_eligible=(),
        process_steps=(
            "Book & share sales/purchase data or Excel",
            "CA reconciles and prepares returns",
            "You approve before filing",
            "Filing acknowledgment shared",
        ),
        documents=("Sales register", "Purchase register", "Bank statements", "Previous GSTR filings"),
        faqs=(
            ("Which price applies to me?", "Nil from ₹500 · under ₹50L turnover ₹1,000 · above ₹50L ₹2,000 — select on the form."),
            ("Can you register me first?", "Yes — start with GST registration if you don't have a GSTIN yet."),
        ),
    ),
    "msme-udyam": ServicePageContent(
        slug="msme-udyam",
        service_key="msme_udyam",
        page_title="MSME Udyam Registration — Official Certificate | ₹1,000",
        headline="MSME Udyam registration",
        meta_description=(
            "MSME Udyam registration for micro, small, and medium enterprises. "
            "Official Udyam certificate — ₹1,000 all-inclusive."
        ),
        tagline="Micro · small · medium enterprise certificate",
        intro=(
            "Get your Udyam registration number for bank loans, tenders, and government schemes. "
            "We handle the full portal process."
        ),
        eligible=(
            "Manufacturing or service enterprises",
            "Proprietorships, partnerships, LLPs, companies",
            "New or existing businesses",
        ),
        not_eligible=(),
        process_steps=(
            "Book & share Aadhaar and business details",
            "We classify enterprise type and file on Udyam portal",
            "Certificate generated",
            "Udyam number + certificate emailed to you",
        ),
        documents=("Aadhaar of proprietor/partner", "PAN", "Business address", "Bank account details"),
        faqs=(
            ("Is Udyam mandatory?", "Not mandatory for all, but required for many schemes and tenders."),
            ("Can I register without GST?", "Yes — Udyam and GST are separate services."),
        ),
    ),
}

SERVICE_PAGE_SLUGS = tuple(SERVICE_PAGES.keys())

SERVICE_PAGE_SLUG_BY_KEY = {p.service_key: p.slug for p in SERVICE_PAGES.values()}


def service_page_for_key(service_key: str) -> ServicePageContent | None:
    for page in SERVICE_PAGES.values():
        if page.service_key == service_key:
            return page
    return None
