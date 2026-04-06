import re


def parse_time_minutes(time_str):
    """Parse delivery time strings into minutes.

    Handles: '15 min', '15-20 min', '15–20 min', '15 - 20 min'
    Returns the midpoint for ranges, or None if unparseable.
    """
    if not time_str or time_str == "Unknown":
        return None
    range_match = re.search(r'(\d+)\s*[-–]\s*(\d+)\s*min', time_str)
    if range_match:
        return (int(range_match.group(1)) + int(range_match.group(2))) // 2
    single_match = re.search(r'(\d+)\s*min', time_str)
    if single_match:
        return int(single_match.group(1))
    return None


def parse_fee_dollars(fee_str):
    """Parse delivery fee strings into a dollar float.

    Handles: '$2.99 delivery fee', 'free delivery', '$0 delivery', '$0.00'
    Returns 0.0 for free, None if unparseable.
    """
    if not fee_str or fee_str == "Unknown":
        return None
    if re.search(r'\bfree\b|\$0\b', fee_str, re.IGNORECASE):
        return 0.0
    dollar_match = re.search(r'\$([\d]+(?:\.[\d]+)?)', fee_str)
    if dollar_match:
        return float(dollar_match.group(1))
    return None


def _normalize(value, lo, hi, invert=True):
    """Scale value to 0–100; invert=True means lower value → higher score."""
    if value is None or lo is None or hi is None:
        return None
    if hi == lo:
        return 100.0
    score = (value - lo) / (hi - lo) * 100
    return round(100 - score if invert else score, 1)


# Maps app name → membership name that waives its fee
_MEMBERSHIP_MAP = {
    "DoorDash": "dashpass",
    "Grubhub": "grubhub_plus",
    "Uber Eats": "uber_one",
}


def rank_results(results, memberships=None, promos=None):
    """Enrich scraper results with parsed fields, rankings, and a recommendation score.

    Args:
        results: list of dicts from scrapers, each with keys:
                 app, available, delivery_time, delivery_fee (or error)
        memberships: set/list of active membership keys, e.g. {'dashpass', 'uber_one'}
        promos: dict mapping app name → discount amount in dollars,
                e.g. {'DoorDash': 5.0, 'Uber Eats': 3.0}

    Returns:
        (enriched_results, recommendation)
        - enriched_results: original dicts + time_minutes, fee_dollars,
          rank_cheapest, rank_fastest, recommendation_score,
          membership_discount, promo_applied
        - recommendation: app name with the highest score, or None
    """
    memberships = set(memberships or [])
    promos = promos or {}

    for r in results:
        if r.get("available"):
            r["time_minutes"] = parse_time_minutes(r.get("delivery_time"))
            r["fee_dollars"] = parse_fee_dollars(r.get("delivery_fee"))

            # Apply membership fee waiver first
            membership_key = _MEMBERSHIP_MAP.get(r["app"])
            if membership_key and membership_key in memberships and r["fee_dollars"] != 0.0:
                r["fee_dollars"] = 0.0
                r["delivery_fee"] = "$0.00 delivery fee"
                r["membership_discount"] = True
            else:
                r["membership_discount"] = False

            # Apply per-app promo discount on top (floor at $0)
            promo = promos.get(r["app"])
            if promo and promo > 0 and r["fee_dollars"] is not None:
                original = r["fee_dollars"]
                r["fee_dollars"] = max(0.0, round(original - promo, 2))
                r["promo_applied"] = promo
            else:
                r["promo_applied"] = None
        else:
            r["time_minutes"] = None
            r["fee_dollars"] = None
            r["membership_discount"] = False
            r["promo_applied"] = None

    available = [r for r in results if r.get("available")]

    # Rank by cheapest fee (None sorts last)
    by_fee = sorted(available, key=lambda r: (r["fee_dollars"] is None, r["fee_dollars"] or 0))
    for i, r in enumerate(by_fee):
        r["rank_cheapest"] = i + 1

    # Rank by fastest delivery (None sorts last)
    by_time = sorted(available, key=lambda r: (r["time_minutes"] is None, r["time_minutes"] or 0))
    for i, r in enumerate(by_time):
        r["rank_fastest"] = i + 1

    for r in results:
        if not r.get("available"):
            r["rank_cheapest"] = None
            r["rank_fastest"] = None

    # Compute recommendation score (0–100, higher = better)
    # Weighted 60% fee, 40% time — fee matters more for most users
    fees = [r["fee_dollars"] for r in available if r["fee_dollars"] is not None]
    times = [r["time_minutes"] for r in available if r["time_minutes"] is not None]

    fee_min, fee_max = (min(fees), max(fees)) if fees else (None, None)
    time_min, time_max = (min(times), max(times)) if times else (None, None)

    for r in available:
        fee_score = _normalize(r["fee_dollars"], fee_min, fee_max)
        time_score = _normalize(r["time_minutes"], time_min, time_max)

        if fee_score is not None and time_score is not None:
            r["recommendation_score"] = round(0.6 * fee_score + 0.4 * time_score, 1)
        elif fee_score is not None:
            r["recommendation_score"] = round(fee_score, 1)
        elif time_score is not None:
            r["recommendation_score"] = round(time_score, 1)
        else:
            r["recommendation_score"] = None

    for r in results:
        if not r.get("available"):
            r["recommendation_score"] = None

    scored = [r for r in available if r.get("recommendation_score") is not None]
    recommendation = max(scored, key=lambda r: r["recommendation_score"])["app"] if scored else None

    return results, recommendation
