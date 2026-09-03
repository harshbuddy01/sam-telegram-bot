import re
import datetime
from typing import Optional, Dict, Any

def parse_validity_days(variant_name: Optional[str], fallback: int = 30) -> int:
    """Intelligently parses subscription duration in days from variant or product name."""
    if not variant_name:
        return fallback

    name_lower = variant_name.lower().strip()

    # Lifetime / Permanent
    if "lifetime" in name_lower or "permanent" in name_lower:
        return 36500

    # Explicit year matches
    if "1 year" in name_lower or "annual" in name_lower or "12 month" in name_lower:
        return 365
    if "2 year" in name_lower or "24 month" in name_lower:
        return 730

    # Regex for N years
    year_match = re.search(r"(\d+)\s*(?:years?|yrs?|y\b)", name_lower)
    if year_match:
        return int(year_match.group(1)) * 365

    # Explicit month checks
    if "6 month" in name_lower:
        return 180
    if "3 month" in name_lower or "quarterly" in name_lower:
        return 90
    if "2 month" in name_lower:
        return 60
    if "1 month" in name_lower or "monthly" in name_lower:
        return 30

    # Regex for N months
    month_match = re.search(r"(\d+)\s*(?:months?|mos?|m\b)", name_lower)
    if month_match:
        return int(month_match.group(1)) * 30

    # Regex for N weeks
    week_match = re.search(r"(\d+)\s*(?:weeks?|wks?|w\b)", name_lower)
    if week_match:
        return int(week_match.group(1)) * 7

    # Regex for N days
    day_match = re.search(r"(\d+)\s*(?:days?|d\b)", name_lower)
    if day_match:
        return int(day_match.group(1))

    return fallback


def calculate_order_expiry(order, now: Optional[datetime.datetime] = None) -> datetime.datetime:
    """Calculates order expiration datetime with 100% backward compatibility for existing records."""
    if getattr(order, "expires_at", None):
        return order.expires_at

    base_date = getattr(order, "fulfilled_at", None) or getattr(order, "created_at", None) or (now or datetime.datetime.utcnow())
    
    variant = getattr(order, "variant", None)
    if variant and getattr(variant, "validity_days", None):
        days = variant.validity_days
    elif variant and getattr(variant, "name", None):
        days = parse_validity_days(variant.name)
    else:
        days = 30

    return base_date + datetime.timedelta(days=days)


def get_order_validity_info(order, now: Optional[datetime.datetime] = None) -> Dict[str, Any]:
    """Returns detailed validity breakdown for order display & renewal logic."""
    if now is None:
        now = datetime.datetime.utcnow()

    expires_at = calculate_order_expiry(order, now=now)
    time_diff = expires_at - now
    total_seconds = time_diff.total_seconds()
    is_expired = total_seconds <= 0

    days_remaining = max(0, int(time_diff.days))
    hours_remaining = max(0, int(total_seconds // 3600))

    variant = getattr(order, "variant", None)
    duration_days = getattr(variant, "validity_days", None) or (parse_validity_days(getattr(variant, "name", "")) if variant else 30)

    expiry_formatted = expires_at.strftime("%d %b %Y, %H:%M UTC")
    expiry_short = expires_at.strftime("%d %b %Y")

    if is_expired:
        badge = "🔴"
        status_label = f"Expired on {expiry_short}"
        remaining_str = "Subscription Expired"
    elif days_remaining <= 5:
        badge = "🟡"
        if days_remaining == 0:
            status_label = f"Expires today ({hours_remaining}h left)"
            remaining_str = f"{hours_remaining} hours left"
        else:
            status_label = f"Expires in {days_remaining} day" + ("s" if days_remaining != 1 else "") + "!"
            remaining_str = f"{days_remaining} day" + ("s" if days_remaining != 1 else "") + " left"
    else:
        badge = "🟢"
        status_label = f"Active ({days_remaining} days left)"
        remaining_str = f"{days_remaining} days left"

    return {
        "expires_at": expires_at,
        "is_expired": is_expired,
        "days_remaining": days_remaining,
        "hours_remaining": hours_remaining,
        "duration_days": duration_days,
        "expiry_formatted": expiry_formatted,
        "expiry_short": expiry_short,
        "badge": badge,
        "status_label": status_label,
        "remaining_str": remaining_str
    }
