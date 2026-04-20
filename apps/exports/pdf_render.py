"""PDF export: CA-grade computation layout (ReportLab)."""
from __future__ import annotations

from apps.exports.ca_computation_pdf import render_ca_computation_pdf


def render_computation_summary_pdf(context: dict) -> bytes:
    """Build the standardized computation PDF (numbered CA-style sections + validation notes)."""
    return render_ca_computation_pdf(context)
