"""CA / tax services shown on the ITR landing page (appointment leads)."""
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


def services_by_category() -> dict[str, list[CaService]]:
    grouped: dict[str, list[CaService]] = {}
    for svc in CA_SERVICES:
        grouped.setdefault(svc.category, []).append(svc)
    return grouped
