from __future__ import annotations

from .services import get_request_cart_counts


def request_cart_summary(request) -> dict[str, int]:
    if not hasattr(request, "session"):
        return {
            "request_cart_line_count": 0,
            "request_cart_total_quantity": 0,
        }

    line_count, total_quantity = get_request_cart_counts(request.session)
    return {
        "request_cart_line_count": line_count,
        "request_cart_total_quantity": total_quantity,
    }
