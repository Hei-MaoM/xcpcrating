"""Identity normalization: names, organizations, coach detection, player keys.

The rating model treats individual competitors as the unit of identity.
Two competitors are considered the same player when their normalized
``(clean_name, clean_org)`` pair matches. Coaches / advisors are excluded
entirely from the player population.
"""

import re
import unicodedata

# Coach / advisor markers. Applied to the *raw* member name (parenthesised
# or not) and used to drop the member from the team entirely.
_COACH_RE = re.compile(r"(教练|教練|领队|領隊|coach|advisor)", re.IGNORECASE)

# Member roles that mark a non-contestant. Newer datasets carry an explicit
# ``role`` field on each member (e.g. {"name": ..., "role": "coach"}) instead
# of tagging the name; matched case-insensitively against the same markers.
_COACH_ROLES = {"coach", "advisor", "manager", "mentor", "教练", "教練", "领队", "領隊"}

# Parenthetical segments to strip from identity names: both CJK full-width
# brackets （...） and ASCII (...), including the brackets themselves.
_PAREN_RE = re.compile(r"（[^（）]*）|\([^()]*\)")

# i18n preference order when a field is an internationalization dict.
_I18N_ORDER = ("fallback", "zh-CN", "en")


def resolve_i18n(value) -> str:
    """Resolve a possibly-i18n field to a single string.

    Accepts a plain string or an i18n dict. For dicts the preference order
    is fallback, then zh-CN, then en, then any remaining value. Returns an
    empty string for None / empty input.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in _I18N_ORDER:
            picked = value.get(key)
            if picked:
                return picked if isinstance(picked, str) else str(picked)
        for picked in value.values():
            if picked:
                return picked if isinstance(picked, str) else str(picked)
        return ""
    return str(value)


def _normalize_whitespace(text: str) -> str:
    """NFKC normalize, fold runs of whitespace to a single space, trim."""
    normalized = unicodedata.normalize("NFKC", text)
    collapsed = re.sub(r"\s+", " ", normalized)
    return collapsed.strip()


def strip_parens(text: str) -> str:
    """Remove all bracketed segments (CJK and ASCII) and their contents."""
    return _PAREN_RE.sub("", text)


def is_coach(member: dict) -> bool:
    """Return True if a raw member dict represents a coach / advisor.

    Detected via a truthy ``coach`` field, an explicit ``role`` field
    (e.g. "coach"), or a coach marker anywhere in the resolved raw name
    (inside or outside brackets).
    """
    if member.get("coach"):
        return True
    role = resolve_i18n(member.get("role")).strip().lower()
    if role in _COACH_ROLES:
        return True
    raw_name = resolve_i18n(member.get("name"))
    return bool(_COACH_RE.search(raw_name))


def clean_org(organization) -> str:
    """Normalize an organization field (string or i18n dict) for display/key."""
    return _normalize_whitespace(resolve_i18n(organization))


def display_name(name) -> str:
    """Cleaned name for display: brackets stripped, whitespace normalized.

    Original casing is preserved.
    """
    resolved = resolve_i18n(name)
    return _normalize_whitespace(strip_parens(resolved))


def clean_name_lower(name) -> str:
    """Identity name used inside the player key.

    Brackets are stripped, whitespace normalized, and Latin characters are
    lowercased so that handle casing does not split identities.
    """
    return display_name(name).lower()


def player_key(name, organization) -> str:
    """Build the normalized player key ``f"{clean_name_lower}@{clean_org}"``."""
    return f"{clean_name_lower(name)}@{clean_org(organization)}"
