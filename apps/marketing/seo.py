"""SEO copy and search synonyms for Indian income-tax / ITR computation intent."""

# Meta keywords (comma-separated synonyms and long-tail variants)
SEO_META_KEYWORDS = (
    "ITR computation, income tax computation, computation summary, income computation "
    "summary, tax computation summary, computation of income, total income computation, "
    "ITR computation pdf, itr computation excel, itr computation ay, itr computation india, "
    "ITR summary, income computation sheet, CA computation sheet, computation sheet pdf, "
    "ITR-3 computation, ITR 3 computation, itr3 computation, filed ITR JSON, "
    "ITR acknowledgment JSON, income tax portal JSON, e filing json download, "
    "tax computation PDF India, ay computation, assessment year computation, "
    "Chapter VI-A, Chapter VIA deductions, Gross Total Income, taxable income computation, "
    "refund computation, tax liability computation, TDS computation, advance tax computation, "
    "professional income computation, business income computation, Form ITR-3 summary, "
    "सालाना आयकर गणना, आईटीआर संक्षेप, आयकर समरी, आय गणना, टैक्स समरी पीडीएफ"
)

SITE_TAGLINE = (
    "Turn filed ITR-3 JSON into a reviewed CA-style computation PDF — "
    "income tax computation summary built for assessment-year reporting."
)


def structured_data_json_ld(
    *,
    site_url: str,
    page_url: str,
    page_heading: str | None = None,
) -> str:
    """Organization + WebSite + WebPage + SoftwareApplication + FAQPage JSON-LD."""
    import json

    wp_name = (
        page_heading
        or "ITR computation summary — income tax computation PDF from ITR-3 JSON"
    )

    data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Organization",
                "@id": f"{site_url}/#organization",
                "name": "ITR Summary Generator",
                "url": site_url,
                "description": SITE_TAGLINE,
            },
            {
                "@type": "WebSite",
                "@id": f"{site_url}/#website",
                "name": "ITR Summary Generator",
                "url": site_url,
                "inLanguage": "en-IN",
                "description": SITE_TAGLINE,
                "publisher": {"@id": f"{site_url}/#organization"},
            },
            {
                "@type": "WebPage",
                "@id": page_url,
                "url": page_url,
                "name": wp_name,
                "description": SITE_TAGLINE,
                "inLanguage": "en-IN",
                "isPartOf": {"@id": f"{site_url}/#website"},
                "about": {
                    "@type": "Thing",
                    "name": (
                        "Income tax computation, ITR computation summary, "
                        "ITR-3 acknowledgment JSON"
                    ),
                },
            },
            {
                "@type": "SoftwareApplication",
                "name": "ITR Summary Generator",
                "applicationCategory": "FinanceApplication",
                "operatingSystem": "Web",
                "description": SITE_TAGLINE,
                "url": site_url,
                "keywords": (
                    "ITR computation, income tax computation summary, computation of income, "
                    "ITR-3 JSON import, CA computation PDF, assessment year India"
                ),
                "featureList": [
                    "Import filed ITR-3 JSON from the income-tax portal",
                    "Computation of income and tax liability summary sections",
                    "Chapter VI-A and head-wise income layout for CA review",
                    "Human review gate before exporting computation PDF",
                ],
                "offers": {
                    "@type": "Offer",
                    "price": "0",
                    "priceCurrency": "INR",
                },
                "publisher": {"@id": f"{site_url}/#organization"},
            },
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": "What is ITR computation?",
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": (
                                "ITR computation is the calculation of income under each head, "
                                "deductions, taxes, and refund or demand for an assessment year — "
                                "often summarized as a computation sheet for filing or CA review."
                            ),
                        },
                    },
                    {
                        "@type": "Question",
                        "name": "Does this replace a CA or the income-tax portal?",
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": (
                                "No. This tool imports your filed ITR-3 JSON and helps you generate "
                                "a human-reviewed summary PDF. Professional advice and official filing "
                                "remain your responsibility."
                            ),
                        },
                    },
                    {
                        "@type": "Question",
                        "name": "Which format is supported?",
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": (
                                "Filed ITR-3 JSON from the income-tax portal (acknowledgment / utility export). "
                                "PDF uploads are not used."
                            ),
                        },
                    },
                    {
                        "@type": "Question",
                        "name": "How long can I download the summary PDF?",
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": (
                                "Each generated PDF can be downloaded for a limited retention window "
                                "shown on the site (default 24 hours). Save a copy to your device before "
                                "the window ends; expired exports appear in your workspace without a file."
                            ),
                        },
                    },
                    {
                        "@type": "Question",
                        "name": "What is income tax computation summary?",
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": (
                                "It is a structured walkthrough of gross income, deductions, tax liability, "
                                "TDS, and refund or demand — useful for CA review and assessment-year records."
                            ),
                        },
                    },
                    {
                        "@type": "Question",
                        "name": (
                            "What is the difference between computation summary "
                            "and filed ITR JSON?"
                        ),
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": (
                                "Your filed return JSON is structured data exported from the income-tax portal. "
                                "This app reads that JSON and renders a readable computation-summary PDF layout "
                                "for review—not a substitute for filing or statutory forms."
                            ),
                        },
                    },
                    {
                        "@type": "Question",
                        "name": "Who uses an ITR computation PDF?",
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": (
                                "Professionals and filers preparing assessment-year paperwork, refunds, demands, "
                                "or internal review folders often keep a concise computation summary alongside "
                                "notices or bank documentation."
                            ),
                        },
                    },
                    {
                        "@type": "Question",
                        "name": (
                            "Is this the same as advance tax computation or "
                            "self-assessment tax?"
                        ),
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": (
                                "Computation summaries here reflect figures parsed from filed ITR-3 JSON "
                                "(including liability, TDS, relief, refund, demand). Separate advance-tax "
                                "calculators focus on installments before filing; compare against your audit "
                                "trail for any payment schedule."
                            ),
                        },
                    },
                ],
            },
        ],
    }
    return json.dumps(data, ensure_ascii=False)


def structured_data_pricing_json_ld(
    *,
    site_url: str,
    page_url: str,
    pro_inr: int,
    itr_home_url: str | None = None,
) -> str:
    """Product + Offer + FAQ for the pricing page."""
    import json

    home_nav = itr_home_url or site_url.rstrip("/") + "/"

    data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Organization",
                "@id": f"{site_url}/#organization",
                "name": "ITR Summary Generator",
                "url": site_url,
            },
            {
                "@type": "WebSite",
                "@id": f"{site_url}/#website",
                "url": site_url,
                "name": "ITR Summary Generator",
                "publisher": {"@id": f"{site_url}/#organization"},
            },
            {
                "@type": "WebPage",
                "@id": page_url,
                "url": page_url,
                "name": "Pricing — ITR Computation PDF Exports | India",
                "description": (
                    "Plans for unlimited or limited monthly income tax computation "
                    "summary PDF exports from filed ITR-3 JSON — Free vs Pro (India)."
                ),
                "inLanguage": "en-IN",
                "isPartOf": {"@id": f"{site_url}/#website"},
                "keywords": (
                    "ITR computation pricing, computation PDF export, income tax summary India"
                ),
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": 1,
                        "name": "ITR computation home",
                        "item": home_nav,
                    },
                    {
                        "@type": "ListItem",
                        "position": 2,
                        "name": "Pricing",
                        "item": page_url,
                    },
                ],
            },
            {
                "@type": "Product",
                "name": "ITR Summary Generator — Pro",
                "description": (
                    "Unlimited computation PDF exports while subscription is active; "
                    "same validation and review workflow as Free."
                ),
                "brand": {"@type": "Brand", "name": "ITR Summary Generator"},
                "offers": {
                    "@type": "Offer",
                    "priceCurrency": "INR",
                    "price": str(pro_inr),
                    "availability": "https://schema.org/InStock",
                    "url": page_url,
                },
            },
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": (
                            "Does Pro affect my income tax computation or refund amount?"
                        ),
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": (
                                "No. Pro only changes how often you may export computation PDF summaries "
                                "during your subscription period. Computation logic comes from your filed JSON."
                            ),
                        },
                    },
                    {
                        "@type": "Question",
                        "name": "What is the difference between Free and Pro?",
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": (
                                "Free includes ITR-3 JSON import and review with a limited number of "
                                "computation PDF exports per month. Pro removes that export cap for "
                                "heavy assessment-year workflows while your subscription is active."
                            ),
                        },
                    },
                    {
                        "@type": "Question",
                        "name": "How are payments processed?",
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": (
                                "When Razorpay is configured, upgrades use secure checkout. "
                                "See the billing page after logging in."
                            ),
                        },
                    },
                ],
            },
        ],
    }
    return json.dumps(data, ensure_ascii=False)
