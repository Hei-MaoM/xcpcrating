"""Contest prestige tiers and their per-contest weights.

Backs the incremental ladder engine (the single scoring rule).

Why a prestige tier
-------------------
The engine recovers each team's performance rating ``R*`` by inverting an
expected-rank equation summed over the whole field
(:func:`xcpc_rating.perf.compute_performances`). ``R*`` therefore scales with
*field size*, not only opponent strength: the biggest fields are the all-comers
provincial / invitational boards (300-500 teams), whose front-runners lap a long
weak tail and so reverse-solve a *higher* ``R*`` than a small all-elite Final
(~120-320 teams). Left uncorrected, prestige and reward invert ("邀请赛涨幅特别大").

A per-contest prestige weight corrects this and encodes the intended ordering
World / EC Final = CCPC final > regional > invitational > provincial.

The four tiers
--------------
* ``final``        -- ICPC World Finals, ICPC (EC) Finals, CCPC national finals.
* ``regional``     -- ordinary ICPC / CCPC regional sites (the 1.0 baseline).
* ``invitational`` -- national invitationals (邀请赛), incl. the Silk Road
                      invitational (srni / 丝绸之路邀请赛).
* ``provincial``   -- provincial-category contests plus the female-only
                      (女生专场) and vocational (高职专场) special tracks
                      (restricted fields regardless of host category).

Classification precedence (first match wins)
--------------------------------------------
1. ``final``        : id contains ``ecfinal``; or id ends with ``final``; or the
                      title contains 总决赛 / a standalone "Final". CCPC
                      ``...final`` and ICPC ``...ecfinal`` ids both land here.
2. ``provincial``   : ``category == 'provincial'``; or a female / vocational
                      special track (``ladies`` / ``female`` / ``girls`` / 女生,
                      or ``hv`` / ``vocational`` / 高职). Placed *before* the
                      invitational check so a 省赛 co-branded as a 全国邀请赛
                      stays provincial.
3. ``invitational`` : id contains ``invitational`` or ``srni``; or the title
                      contains 邀请赛 (non-provincial categories only).
4. ``regional``     : every remaining official ICPC / CCPC site.

:func:`classify_tier` raises ``ValueError`` on a contest that matches no tier,
so a data drift surfaces loudly rather than silently defaulting.
"""

from __future__ import annotations

import math

# Tier names, ordered most-to-least prestige (documentation only).
TIER_FINAL = "final"
TIER_REGIONAL = "regional"
TIER_INVITATIONAL = "invitational"
TIER_PROVINCIAL = "provincial"

# Per-tier prestige weight: the multiplier on a contest's step before it updates
# a member's rating. It scales how far a single result moves a rating (both up and
# down), so a high-prestige tier separates the field faster while a low-prestige
# tier moves ratings little. Finals and regionals -- the events strong players
# actually contest every season -- carry the most weight; invitationals and
# provincials are damped so they barely shift a rating (provincials are gated as
# well). This is what pulls the tiers apart in the standings.
TIER_WEIGHTS = {
    TIER_FINAL: 1.5,
    TIER_REGIONAL: 1.3,
    TIER_INVITATIONAL: 0.8,
    TIER_PROVINCIAL: 0.7,
}

# Per-tier rating ceiling (legacy cap mechanism). A contest of tier ``t`` cannot
# push a rating above ``TIER_CAPS[t]``; only ``final`` is uncapped, so reaching
# the very top structurally requires Final play. The production engine uses the
# eligibility gates instead of caps (see incremental.py); these caps apply only
# on the no-gates path, kept callable for comparison.
TIER_CAPS = {
    TIER_FINAL: math.inf,
    TIER_REGIONAL: 3300.0,
    TIER_INVITATIONAL: 2800.0,
    TIER_PROVINCIAL: 2300.0,
}

# Cap-mechanism shape constants (used only on the no-gates path). TAPER: the
# headroom band (cap - rating) over which a capped contest's weight ramps from
# EPS_RATIO up to full. EPS / EPS_RATIO: the residual weight a sample keeps once a
# rating reaches or passes the cap (a tiny two-sided nudge, so a capped player who
# wins a low-tier contest neither farms points nor is dragged down).
TAPER = 100.0
EPS = 0.02
EPS_RATIO = 0.02

# Lowercased title / id fragments that identify the female-only and vocational
# special tracks (restricted fields, classified as provincial regardless of the
# host category they were filed under).
_FEMALE_MARKERS = ("ladies", "female", "girls", "女生")
_VOCATIONAL_MARKERS = ("hv", "vocational", "高职")

# Invitational id / title markers (srni == 丝绸之路邀请赛, the Silk Road event).
_INVITATIONAL_ID_MARKERS = ("invitational", "srni")
_INVITATIONAL_TITLE_MARKERS = ("邀请赛",)

# Final markers. ``ecfinal`` is matched explicitly so it cannot be mistaken for
# a regional; a trailing ``final`` covers CCPC national finals; the zh / en
# title words cover any host that names the stage but not the id.
_FINAL_ID_SUFFIX = "final"
_FINAL_TITLE_MARKERS = ("总决赛",)


def _has_any(haystack: str, needles) -> bool:
    """True if any needle is a substring of ``haystack`` (caller lowercases)."""
    return any(needle in haystack for needle in needles)


def _is_female_or_vocational(contest_id: str, title: str) -> bool:
    """A female-only or vocational special track (restricted field)."""
    return (
        _has_any(contest_id, _FEMALE_MARKERS)
        or _has_any(title, _FEMALE_MARKERS)
        or _has_any(contest_id, _VOCATIONAL_MARKERS)
        or _has_any(title, _VOCATIONAL_MARKERS)
    )


def _is_final(contest_id: str, title: str) -> bool:
    """An ICPC (EC) Final / World Finals or a CCPC national final.

    ``ecfinal`` and a trailing ``final`` in the id, or 总决赛 / a standalone
    "final" wording in the title. No invitational id ends in ``final``, so the
    suffix test does not collide with stage 3.
    """
    if "ecfinal" in contest_id or contest_id.endswith(_FINAL_ID_SUFFIX):
        return True
    if _has_any(title, _FINAL_TITLE_MARKERS):
        return True
    # A standalone English "final" in the title, e.g. "... Contest Final" or
    # "East Continent Final Contest". Guard against "finalist"/"finally".
    if "final" in title and "finalist" not in title:
        return True
    return False


def _is_invitational(contest_id: str, title: str) -> bool:
    """A national invitational (邀请赛), incl. the Silk Road (srni) event."""
    return (
        _has_any(contest_id, _INVITATIONAL_ID_MARKERS)
        or _has_any(title, _INVITATIONAL_TITLE_MARKERS)
    )


def classify_tier(contest) -> str:
    """Map a :class:`~xcpc_rating.model.Contest` to its prestige tier.

    Returns one of ``'final'`` / ``'regional'`` / ``'invitational'`` /
    ``'provincial'`` by the precedence documented in the module docstring
    (final > provincial special-track > invitational > regional). Raises
    ``ValueError`` if the contest matches no tier -- an unexpected category with
    no prestige signal -- so silent misclassification can never happen.
    """
    contest_id = (contest.id or "").lower()
    title = (contest.title or "").lower()
    category = (contest.category or "").lower()

    # 1. Finals win outright (highest prestige; small all-elite fields).
    if _is_final(contest_id, title):
        return TIER_FINAL

    # 2. Female / vocational special tracks are restricted fields and stay
    # provincial regardless of branding or host category.
    if _is_female_or_vocational(contest_id, title):
        return TIER_PROVINCIAL

    # 3. National invitationals -- including provincial-category boards
    # co-branded as a 全国邀请赛 (e.g. bjcpc2025 "...暨小米杯全国邀请赛"). A
    # dual-identity 省赛/邀请赛 board takes the higher tier (invitational).
    if _is_invitational(contest_id, title):
        return TIER_INVITATIONAL

    # 4. Plain provincial category.
    if category == TIER_PROVINCIAL:
        return TIER_PROVINCIAL

    # 5. Ordinary official ICPC / CCPC regional sites.
    if category in ("icpc", "ccpc"):
        return TIER_REGIONAL

    raise ValueError(
        f"unclassifiable contest: id={contest.id!r} "
        f"category={contest.category!r} title={contest.title!r}"
    )


def tier_weight(contest) -> float:
    """The per-contest prestige weight for ``contest``."""
    return TIER_WEIGHTS[classify_tier(contest)]


def cap_sample(perf_raw: float, mu_cur: float, cap: float,
               base_weight: float) -> tuple[float, float]:
    """Shape one performance sample under the tier rating-ceiling mechanism.

    Pure helper for the legacy no-gates cap path. Given the raw recovered
    performance ``perf_raw``, the member's pre-update posterior mode ``mu_cur``,
    this contest's tier ceiling ``cap`` (``math.inf`` for ``final``) and the
    contest's ``base_weight`` (the tier multiplier, or ``1.0`` when the
    multiplier mechanism is off), return the ``(p_eff, w_eff)`` actually fused.

    Rules (exactly as specified by the product):

    * ``cap == inf`` (final): no ceiling -- return ``(perf_raw, base_weight)``
      unchanged, so Finals are the only contests that can lift a rating without
      bound.
    * ``headroom = cap - mu_cur <= 0`` (member already at / past this tier's
      ceiling): the sample enters with only ``EPS`` weight and is *still clamped*
      to the cap, ``(min(perf_raw, cap), EPS)``. A tiny two-sided nudge -- a
      capped champion who wins a provincial neither farms points nor is dragged
      down by the weak field, never the felt experience of "won but lost rating".
    * ``headroom > 0``: clamp the performance to the cap,
      ``p_eff = min(perf_raw, cap)``, and taper the weight smoothly over the last
      ``TAPER`` points below the cap,
      ``w_eff = base_weight * clamp(headroom / TAPER, EPS_RATIO, 1.0)``. Because
      ``p_eff`` is capped, this tier's contests can never push ``mu`` past
      ``cap``; the taper makes the approach a smooth fade (no cliff) rather than a
      hard wall.
    """
    if math.isinf(cap):
        return perf_raw, base_weight

    headroom = cap - mu_cur
    if headroom <= 0.0:
        return min(perf_raw, cap), EPS

    ratio = headroom / TAPER
    if ratio < EPS_RATIO:
        ratio = EPS_RATIO
    elif ratio > 1.0:
        ratio = 1.0
    return min(perf_raw, cap), base_weight * ratio
