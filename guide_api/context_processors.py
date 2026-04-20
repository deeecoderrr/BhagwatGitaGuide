"""Template context shared across guide_api + main site templates."""

from __future__ import annotations


def itr_seo_links(request):
    """
    Cross-links when ITR Summary Generator is mounted (``ITR_ENABLED``).

    Templates: ``{% if itr_computation_path %}`` — empty when ITR is off.
    """
    from django.conf import settings

    if not getattr(settings, "ITR_ENABLED", False):
        return {
            "itr_computation_path": "",
            "itr_computation_absolute_url": "",
        }

    raw = getattr(settings, "ITR_URL_PREFIX", "/itr-computation")
    raw = raw or "/itr-computation"
    seg = raw.strip().strip("/")
    path = f"/{seg}/"
    try:
        abs_url = request.build_absolute_uri(path)
    except Exception:
        abs_url = ""

    return {
        "itr_computation_path": path,
        "itr_computation_absolute_url": abs_url,
    }
