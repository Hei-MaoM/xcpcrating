"""Pure helpers for problem type profiles and calibrated problem ratings.

The exporter will eventually join contest problems to a separately curated
manifest.  This module deliberately contains no I/O and no rating-engine
coupling: it validates manifest records, normalises multi-label weights,
fits problem intercept ratings from team outcomes, and aggregates deduplicated
team-level problem evidence into mastery values.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import quote, urlparse

from .problem_tags import normalize_detail_tags


PROBLEM_TYPE_AXES = (
    "adhoc",
    "technique",
    "search",
    "offline",
    "random",
    "dataStructure",
    "graph",
    "flow",
    "dp",
    "string",
    "math",
    "probability",
    "geometry",
)

PROBLEM_TYPE_LABELS = {
    "adhoc": "思维与模拟",
    "technique": "基础技巧",
    "search": "搜索",
    "offline": "分治与离线",
    "random": "随机与近似",
    "dataStructure": "数据结构",
    "graph": "图论",
    "flow": "网络流与匹配",
    "dp": "动态规划",
    "string": "字符串",
    "math": "数学",
    "probability": "概率与博弈",
    "geometry": "计算几何",
}

DIFFICULTY_LEVELS = (
    ("veryHard", "极难", 0.10),
    ("hard", "困难", 0.30),
    ("medium", "中等", 0.60),
    ("easy", "简单", 0.85),
    ("veryEasy", "容易", 1.00),
)

# Public problem-rating bands.  These are absolute item-rating intervals, so
# the same problem keeps its difficulty label across contest sites with very
# different field strengths.  Regional medal references are calibration
# anchors, not guarantees: roughly bronze sits around easy-mid/mid, silver
# around mid/mid-hard, and gold around mid-hard/hard.
PROBLEM_RATING_LEVELS = (
    ("veryEasy", "极易", 1300.0),
    ("easy", "简单", 1500.0),
    # The middle bands are intentionally wider and shifted upward.  This
    # keeps a just-below-silver regional problem in easy-mid/mid rather than
    # labeling it mid-hard solely because one host has a stronger field.
    ("easyMid", "简单-中等", 1800.0),
    ("mid", "中等", 1950.0),
    ("midHard", "中等-困难", 2150.0),
    ("hard", "困难", 2350.0),
    ("veryHard", "极难", math.inf),
)

# Problem and team ratings share the engine's Elo-like scale.  The intercept
# is defined so that a team whose rating equals a problem's rating has a 50%
# chance of solving it.
PROBLEM_RATING_ALPHA = math.log(10.0) / 400.0
PROBLEM_RATING_PRIOR_MEAN = 1700.0
PROBLEM_RATING_PRIOR_SD = 600.0

# A 2PL slope is useful only after a problem has enough successes, failures,
# and rating spread to identify the transition curve.  Sparse or one-sided
# boards stay on the fixed-slope Rasch model.
PROBLEM_2PL_MIN_SAMPLE = 100
PROBLEM_2PL_MIN_AC = 20
PROBLEM_2PL_MIN_WA = 20
PROBLEM_2PL_MIN_RATING_SPREAD = 300.0
PROBLEM_2PL_LOG_SLOPE_PRIOR_SD = 0.25
PROBLEM_2PL_MIN_DISCRIMINATION = 0.5
PROBLEM_2PL_MAX_DISCRIMINATION = 2.0
# A numerical profile search approaches a hard bound without landing on it
# exactly.  Treat the small boundary strip as unidentified and fall back to
# fixed-slope 1PL instead of publishing a clipped discrimination.
PROBLEM_2PL_BOUNDARY_TOLERANCE = 0.02
PROBLEM_2PL_MAX_LOG_SLOPE_POSTERIOR_SD = 0.5

_MANIFEST_STATUSES = {"classified", "unknown", "conflict", "withdrawn"}
_IRT_MIN_PROBABILITY = 0.01
_IRT_MAX_PROBABILITY = 0.99
_IRT_PRIOR_SD = 1.5
_IRT_RANK_Z = 0.84
# Outcome updates are weighted by how surprising the result was under the
# team/problem baseline.  A hard failure is therefore weak evidence, while a
# failure on an easy problem remains strongly negative.  The small floor keeps
# repeated hard failures informative without allowing one to dominate.
_IRT_SURPRISE_POWER = 1.0
_IRT_MIN_OUTCOME_WEIGHT = 0.05
# A single contest contains correlated observations: the same team, contest
# environment and time pressure affect every problem.  Cap the information
# contributed by one contest per axis so a long board cannot make the panel
# look more certain than the evidence supports.
_IRT_CONTEST_WEIGHT_CAP = 1.5
_IRT_DEFAULT_RATING_SD = 400.0
_CONTEST_EVIDENCE_CAP = 1.0


def _problem_title(
    raw_problem: Mapping[str, Any],
    curated: Mapping[str, Any],
    catalog: Mapping[str, Any] | None = None,
) -> str | None:
    """Return a display title, ignoring colour codes stored as SRK titles.

    A few upstream ranklists put the problem colour in the ``title`` field
    (for example ``"EDE3A0"``).  Treating that value as a problem name makes
    the explorer look broken, so only non-empty human-readable strings are
    retained.  Curated titles take precedence over source titles.
    """

    catalog = catalog if isinstance(catalog, Mapping) else {}
    for candidate in (
        curated.get("title"),
        catalog.get("title"),
        raw_problem.get("title"),
    ):
        if isinstance(candidate, Mapping):
            candidate = (
                candidate.get("zh-CN")
                or candidate.get("zh_cn")
                or candidate.get("en")
                or candidate.get("fallback")
            )
        if not isinstance(candidate, str):
            continue
        value = " ".join(candidate.split()).strip()
        if (
            not value
            or "\ufffd" in value
            or value.lower() in {"ccpc", "icpc", "problem", "unknown", "null", "题目", "未命名题目"}
            or (len(value) == 6 and all(ch in "0123456789abcdefABCDEF" for ch in value))
        ):
            continue
        return value
    return None


def _problem_url(
    raw_problem: Mapping[str, Any],
    curated: Mapping[str, Any],
    *,
    canonical_id: str | None,
    alias: str,
    contest_links: Iterable[Any] | None = None,
    catalog: Mapping[str, Any] | None = None,
) -> str | None:
    """Choose a stable clickable URL for one problem.

    Direct links in the SRK row or curated catalog are preferred.  A contest,
    standings, ranklist, download or tutorial URL is never exposed as a
    problem URL: those pages do not identify the selected problem.  When an
    upstream row only stores a Codeforces gym link, a problem-specific path is
    derived by appending the alias.  A two-part ``qoj:<problem-id>`` canonical
    ID is an individual QOJ problem and can therefore link directly to its
    statement.
    """

    catalog = catalog if isinstance(catalog, Mapping) else {}
    # The audit publication gate records an explicit pending link decision in
    # the manifest.  In that state raw SRK links are only candidate evidence;
    # exposing them here would bypass the two-reviewer requirement and often
    # turns a contest/rank page into a misleading problem link.  For legacy
    # manifests without a review object we retain the historical fallback
    # behaviour.
    link_review = curated.get("review", {}).get("links", {}) if isinstance(curated.get("review"), Mapping) else {}
    link_pending = isinstance(link_review, Mapping) and link_review.get("status") == "pending"
    if link_pending:
        direct_values = (
            curated.get("problemUrl"),
            catalog.get("problemUrl"),
            catalog.get("url"),
            catalog.get("link"),
            curated.get("url"),
            curated.get("link"),
        )
    else:
        direct_values = (
            raw_problem.get("link"),
            raw_problem.get("url"),
            curated.get("problemUrl"),
            catalog.get("problemUrl"),
            catalog.get("url"),
            catalog.get("link"),
            curated.get("url"),
            curated.get("link"),
        )
    for value in direct_values:
        if isinstance(value, str) and value.strip():
            parsed = urlparse(value.strip())
            if (
                parsed.scheme in {"http", "https"}
                and parsed.netloc
                and _looks_like_individual_problem_url(parsed)
            ):
                return value.strip()

    if link_pending:
        return None

    # ``sourceUrl`` is useful evidence, but it is often an editorial PDF or a
    # rank board.  Only use it when its path itself names one problem.
    for value in (curated.get("sourceUrl"), catalog.get("sourceUrl")):
        if not isinstance(value, str) or not value.strip():
            continue
        parsed = urlparse(value.strip())
        if (
            parsed.scheme in {"http", "https"}
            and parsed.netloc
            and _looks_like_individual_problem_url(parsed)
        ):
            return value.strip()

    for item in contest_links or ():
        value = item.get("link") if isinstance(item, Mapping) else item
        if not isinstance(value, str) or not value.strip():
            continue
        parsed = urlparse(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        parts = [part for part in parsed.path.split("/") if part]
        host = parsed.netloc.lower()
        if len(parts) >= 2 and parts[0] in {"gym", "contest"} and host.endswith("codeforces.com"):
            base = f"{parsed.scheme}://{parsed.netloc}/{'/'.join(parts[:2])}"
            return f"{base}/problem/{quote(alias, safe='')}"
        if len(parts) >= 2 and parts[0] == "contest" and (
            host.endswith("ucup.ac") or host.endswith("qoj.ac")
        ):
            # A contest dashboard is deliberately not used as a substitute
            # for a problem statement.  The audit layer must provide an
            # individual QOJ/UCUP problem id before this row becomes linked.
            continue
        # A non-specific platform link is still useful as a source link.
        return value.strip()

    parts = str(canonical_id or "").split(":")
    if len(parts) == 2 and parts[0] == "qoj" and parts[1].isdigit():
        return f"https://qoj.ac/problem/{parts[1]}"
    return None


def _looks_like_individual_problem_url(parsed) -> bool:
    """Recognise URLs that identify one problem rather than a collection."""

    path = parsed.path.rstrip("/").lower()
    if any(token in path for token in ("/rank", "/standings", "/download", "/tutorial", ".pdf")):
        return False
    if "/problem/" in path or "/problems/" in path:
        return True
    # Common platforms encode the problem alias directly after a contest id.
    parts = [part for part in path.split("/") if part]
    host = parsed.netloc.lower()
    if host.endswith("nowcoder.com") and len(parts) >= 4 and parts[-1].isalnum():
        return True
    if host.endswith("luogu.com.cn") and len(parts) >= 2 and parts[-2] == "problem":
        return True
    if host.endswith("vjudge.net") and len(parts) >= 3 and parts[-2] in {"problem", "problemset"}:
        return True
    # Generic statement mirrors use an explicit problem-like final segment;
    # reject bare contest paths and opaque rank identifiers.
    if len(parts) >= 2 and parts[-1] not in {"contest", "rankings", "rank", "standings"}:
        return parts[-1] not in {parts[0]} and not parts[-1].isdigit()
    return False


def problem_pass_probability(
    team_rating: Any, problem_rating: Any, *, alpha: float = PROBLEM_RATING_ALPHA
) -> float:
    """Probability that a team solves a problem on the shared rating scale."""
    team = _number(team_rating, field="team_rating")
    problem = _number(problem_rating, field="problem_rating")
    slope = _number(alpha, field="alpha")
    if slope <= 0:
        raise ValueError("alpha must be positive")
    return _sigmoid(slope * (team - problem))


def _problem_2pl_objective(
    prepared: list[tuple[float, float]],
    candidate: tuple[float, float],
    *,
    prior_mean: float,
    prior_sd: float,
    alpha: float,
    log_slope_prior_sd: float,
) -> tuple[float, float, float, float, float, float]:
    """Return objective, gradient, and 2x2 Hessian for the 2PL MAP.

    The second parameter is ``eta = log(discrimination)``.  Keeping the Elo
    slope ``alpha`` fixed makes the item scale identifiable while allowing a
    well-supported problem to have a steeper or flatter transition curve.
    """

    difficulty, eta = candidate
    discrimination = math.exp(eta)
    prior_precision = 1.0 / (prior_sd * prior_sd)
    slope_precision = 1.0 / (log_slope_prior_sd * log_slope_prior_sd)
    objective = (
        0.5 * (difficulty - prior_mean) ** 2 * prior_precision
        + 0.5 * eta * eta * slope_precision
    )
    gradient_difficulty = (difficulty - prior_mean) * prior_precision
    gradient_eta = eta * slope_precision
    hessian_dd = prior_precision
    hessian_de = 0.0
    hessian_ee = slope_precision
    for team, signed_weight in prepared:
        weight = abs(signed_weight)
        solved = 1.0 if signed_weight > 0 else 0.0
        transformed = discrimination * alpha * (team - difficulty)
        probability = _sigmoid(transformed)
        probability_variance = probability * (1.0 - probability)
        # Clipping only protects the logarithms for extreme bounded values.
        objective -= weight * (
            solved * math.log(max(probability, 1e-15))
            + (1.0 - solved) * math.log(max(1.0 - probability, 1e-15))
        )
        term = discrimination * alpha * (team - difficulty)
        gradient_difficulty += weight * discrimination * alpha * (solved - probability)
        gradient_eta += weight * (probability - solved) * term
        hessian_dd += weight * (discrimination * alpha) ** 2 * probability_variance
        hessian_de += weight * discrimination * alpha * (
            solved - probability - probability_variance * term
        )
        hessian_ee += weight * (
            probability_variance * term * term + (probability - solved) * term
        )
    return (
        objective,
        gradient_difficulty,
        gradient_eta,
        hessian_dd,
        hessian_de,
        hessian_ee,
    )


def _estimate_problem_2pl(
    prepared: list[tuple[float, float]],
    *,
    prior_mean: float,
    prior_sd: float,
    alpha: float,
    max_iterations: int,
) -> dict[str, float | int | str | bool] | None:
    """Fit a bounded, regularised 2PL item using a profiled MAP solve.

    For each log-slope we solve the item intercept with a monotone bracketed
    Newton step, then minimise the one-dimensional profile objective.  This is
    slower than an unconstrained two-dimensional Newton solve but remains
    dependency-free and is stable when the joint Hessian is indefinite near
    the prior centre.
    """

    eta_min = math.log(PROBLEM_2PL_MIN_DISCRIMINATION)
    eta_max = math.log(PROBLEM_2PL_MAX_DISCRIMINATION)
    prior_precision = 1.0 / (prior_sd * prior_sd)
    slope_prior_sd = PROBLEM_2PL_LOG_SLOPE_PRIOR_SD
    slope_prior_precision = 1.0 / (slope_prior_sd * slope_prior_sd)

    def solve_difficulty(eta: float) -> tuple[float, float]:
        discrimination = math.exp(eta)
        lower, upper = 300.0, 4500.0

        def gradient(candidate: float) -> tuple[float, float]:
            slope = discrimination * alpha
            value = (candidate - prior_mean) * prior_precision
            information = prior_precision
            for team, signed_weight in prepared:
                weight = abs(signed_weight)
                solved = 1.0 if signed_weight > 0 else 0.0
                probability = _sigmoid(slope * (team - candidate))
                value += weight * slope * (solved - probability)
                information += weight * slope * slope * probability * (1.0 - probability)
            return value, information

        lower_gradient, _ = gradient(lower)
        upper_gradient, _ = gradient(upper)
        if lower_gradient >= 0:
            difficulty = lower
        elif upper_gradient <= 0:
            difficulty = upper
        else:
            difficulty = min(max(prior_mean, lower), upper)
            # The difficulty subproblem is strictly convex; a dozen to twenty
            # safeguarded Newton steps is ample even for the widest rating
            # brackets.  Keeping this cap below the public iteration budget
            # prevents a full catalog export from multiplying work needlessly.
            for _ in range(min(int(max_iterations), 12)):
                value, information = gradient(difficulty)
                if abs(value) < 1e-10:
                    break
                if value < 0:
                    lower = difficulty
                else:
                    upper = difficulty
                proposal = difficulty - value / max(information, 1e-12)
                if not math.isfinite(proposal) or proposal <= lower or proposal >= upper:
                    proposal = (lower + upper) / 2.0
                if abs(proposal - difficulty) < 1e-8:
                    difficulty = proposal
                    break
                difficulty = proposal
        objective = _problem_2pl_objective(
            prepared,
            (difficulty, eta),
            prior_mean=prior_mean,
            prior_sd=prior_sd,
            alpha=alpha,
            log_slope_prior_sd=slope_prior_sd,
        )[0]
        return difficulty, objective

    golden = (math.sqrt(5.0) - 1.0) / 2.0
    left, right = eta_min, eta_max
    c = right - golden * (right - left)
    d = left + golden * (right - left)
    fc = solve_difficulty(c)[1]
    fd = solve_difficulty(d)[1]
    # Golden-section convergence is more than sufficient at rating precision
    # once the final difficulty is rounded to 1e-6.  Fourteen evaluations keep
    # the dependency-free fit practical for thousands of catalog items.
    for _ in range(14):
        if fc <= fd:
            right, d, fd = d, c, fc
            c = right - golden * (right - left)
            fc = solve_difficulty(c)[1]
        else:
            left, c, fc = c, d, fd
            d = left + golden * (right - left)
            fd = solve_difficulty(d)[1]
    eta = (left + right) / 2.0
    difficulty, _ = solve_difficulty(eta)
    final = _problem_2pl_objective(
        prepared,
        (difficulty, eta),
        prior_mean=prior_mean,
        prior_sd=prior_sd,
        alpha=alpha,
        log_slope_prior_sd=slope_prior_sd,
    )
    _, _, _, h_dd, h_de, h_ee = final
    determinant = h_dd * h_ee - h_de * h_de

    # Estimate curvature numerically from the profile objective.  It is the
    # relevant uncertainty for eta after allowing difficulty to re-optimise.
    profile_step = 1e-3
    eta_left = max(eta_min, eta - profile_step)
    eta_right = min(eta_max, eta + profile_step)
    center_objective = solve_difficulty(eta)[1]
    left_objective = solve_difficulty(eta_left)[1]
    right_objective = solve_difficulty(eta_right)[1]
    width = max((eta_right - eta_left) / 2.0, 1e-8)
    profile_curvature = (left_objective - 2.0 * center_objective + right_objective) / (width * width)
    slope_posterior_sd = (
        math.sqrt(1.0 / profile_curvature)
        if profile_curvature > 1e-12 and math.isfinite(profile_curvature)
        else math.inf
    )
    if (
        not math.isfinite(slope_posterior_sd)
        or slope_posterior_sd > PROBLEM_2PL_MAX_LOG_SLOPE_POSTERIOR_SD
        or eta <= eta_min + PROBLEM_2PL_BOUNDARY_TOLERANCE
        or eta >= eta_max - PROBLEM_2PL_BOUNDARY_TOLERANCE
    ):
        return None

    if determinant > 1e-12 and h_ee > 1e-12:
        information = h_dd - (h_de * h_de / h_ee)
    else:
        information = h_dd
    if information <= 1e-12 or not math.isfinite(information):
        return None
    discrimination = math.exp(eta)
    return {
        "problemRating": round(difficulty, 6),
        "posteriorSd": round(math.sqrt(1.0 / information), 6),
        "discrimination": round(discrimination, 6),
        "slopePosteriorSd": round(slope_posterior_sd, 6),
        "slopeSource": "estimated",
        "model": "2PL",
        "slopeAtBound": False,
        "ratingSpread": round(
            max(team for team, _ in prepared) - min(team for team, _ in prepared), 6
        ),
        "expectedPassRateAtReference": round(
            problem_pass_probability(
                prior_mean,
                difficulty,
                alpha=alpha * discrimination,
            ),
            6,
        ),
    }

def estimate_problem_rating(
    observations: Iterable[Mapping[str, Any]],
    *,
    prior_mean: float = PROBLEM_RATING_PRIOR_MEAN,
    prior_sd: float = PROBLEM_RATING_PRIOR_SD,
    alpha: float = PROBLEM_RATING_ALPHA,
    max_iterations: int = 32,
) -> dict[str, Any]:
    """Estimate a problem intercept with a one-dimensional MAP solve.

    Each observation supplies ``teamRating`` and a boolean ``solved``. Missing
    statuses are ignored. A weak normal prior keeps all-AC/all-WA problems
    finite; the score remains interpretable because equal team/problem ratings
    always imply a 50% predicted pass probability.
    """
    mean = _number(prior_mean, field="prior_mean")
    sd = _number(prior_sd, field="prior_sd")
    slope = _number(alpha, field="alpha")
    if sd <= 0 or slope <= 0 or int(max_iterations) < 1:
        raise ValueError("prior_sd, alpha and max_iterations must be positive")
    prepared: list[tuple[float, float]] = []
    for raw in observations:
        if not isinstance(raw, Mapping) or raw.get("solved") is None:
            continue
        try:
            rating = _number(raw.get("teamRating"), field="teamRating")
            weight = _number(raw.get("weight", 1.0), field="weight")
        except ValueError:
            continue
        if weight <= 0:
            continue
        prepared.append((rating, weight if bool(raw.get("solved")) else -weight))
    # Report the number of aligned team observations separately from the
    # information total.  The latter remains useful if callers provide
    # fractional weights for recovered or auxiliary evidence.
    sample_count = len(prepared)
    effective_sample_count = round(sum(abs(v) for _, v in prepared), 6)
    ac_count = int(round(sum(v for _, v in prepared if v > 0)))
    ac_observation_count = sum(1 for _, value in prepared if value > 0)
    wa_observation_count = sample_count - ac_observation_count
    if not prepared:
        return {"problemRating": mean, "posteriorSd": sd, "sampleCount": 0,
                "effectiveSampleCount": 0.0, "acCount": 0,
                "waCount": 0, "model": "1PL", "discrimination": 1.0,
                "slopeSource": "fixed_prior", "slopePosteriorSd": None,
                "slopeAtBound": False, "boundaryOutcome": False,
                "ratingSpread": 0.0,
                "gateReasons": ["no_observations"],
                "expectedPassRateAtReference": 0.5}

    rating_spread = max(team for team, _ in prepared) - min(team for team, _ in prepared)
    effective_ac_count = sum(value for _, value in prepared if value > 0)
    effective_wa_count = sum(-value for _, value in prepared if value < 0)

    gate_reasons: list[str] = []
    if effective_sample_count < PROBLEM_2PL_MIN_SAMPLE:
        gate_reasons.append("sample_threshold")
    if effective_ac_count < PROBLEM_2PL_MIN_AC:
        gate_reasons.append("ac_threshold")
    if effective_wa_count < PROBLEM_2PL_MIN_WA:
        gate_reasons.append("wa_threshold")
    if rating_spread < PROBLEM_2PL_MIN_RATING_SPREAD:
        gate_reasons.append("rating_spread")
    boundary_outcome = ac_observation_count == 0 or wa_observation_count == 0
    if boundary_outcome:
        gate_reasons.append("outcome_boundary")
    if not gate_reasons:
        fitted = _estimate_problem_2pl(
            prepared,
            prior_mean=mean,
            prior_sd=sd,
            alpha=slope,
            max_iterations=max_iterations,
        )
        if fitted is not None:
            fitted.update(
                {
                    "sampleCount": sample_count,
                    "effectiveSampleCount": effective_sample_count,
                    "acCount": ac_count,
                    "waCount": wa_observation_count,
                    "ratingSpread": rating_spread,
                    "boundaryOutcome": False,
                    "gateReasons": [],
                }
            )
            return fitted
        gate_reasons.append("unstable_2pl")

    precision = 1.0 / (sd * sd)

    def score_gradient(candidate: float) -> tuple[float, float]:
        """Return the score gradient and observed information at ``candidate``.

        The gradient is strictly decreasing in the problem rating. Keeping
        the information alongside it lets the solver use a Newton proposal
        while the outer bracket guarantees that a proposal cannot jump over
        the unique MAP root.
        """

        gradient = -(candidate - mean) * precision
        information = precision
        for team, signed_weight in prepared:
            weight = abs(signed_weight)
            solved = 1.0 if signed_weight > 0 else 0.0
            probability = problem_pass_probability(team, candidate, alpha=slope)
            gradient += slope * weight * (probability - solved)
            information += slope * slope * weight * probability * (1.0 - probability)
        return gradient, information

    # A plain Newton iteration can take a very large step when all responses
    # are near one side of the logistic curve. It then alternates between the
    # hard bounds (the 2025 EC-Final D data exposed this as a false score of
    # exactly 300). The score equation is monotone, so maintain a bracket and
    # fall back to its midpoint whenever Newton leaves it.
    lower, upper = 300.0, 4500.0
    lower_gradient, _ = score_gradient(lower)
    upper_gradient, _ = score_gradient(upper)
    if lower_gradient <= 0:
        rating = lower
    elif upper_gradient >= 0:
        rating = upper
    else:
        rating = min(max(mean, lower), upper)
        for _ in range(int(max_iterations)):
            gradient, information = score_gradient(rating)
            if abs(gradient) < 1e-10:
                break
            if gradient > 0:
                lower = rating
            else:
                upper = rating
            step = gradient / max(information, 1e-12)
            next_rating = rating + step
            if (
                not math.isfinite(next_rating)
                or next_rating <= lower
                or next_rating >= upper
            ):
                next_rating = (lower + upper) / 2.0
            if abs(next_rating - rating) < 1e-8:
                rating = next_rating
                break
            rating = next_rating
    information = precision
    reference = mean
    for team, signed_weight in prepared:
        p = problem_pass_probability(team, rating, alpha=slope)
        information += slope * slope * abs(signed_weight) * p * (1.0 - p)
    return {
        "problemRating": round(rating, 6),
        "posteriorSd": round(math.sqrt(1.0 / information), 6),
        "sampleCount": sample_count,
        "effectiveSampleCount": effective_sample_count,
        "acCount": ac_count,
        "waCount": wa_observation_count,
        "model": "1PL",
        "discrimination": 1.0,
        "slopePosteriorSd": None,
        "slopeSource": "fixed_prior",
        "slopeAtBound": False,
        "boundaryOutcome": boundary_outcome,
        "ratingSpread": rating_spread,
        "gateReasons": gate_reasons,
        "expectedPassRateAtReference": round(problem_pass_probability(reference, rating, alpha=slope), 6),
    }


def build_problem_rating_index(
    observations: Mapping[str, Iterable[Mapping[str, Any]]], **kwargs: Any
) -> dict[str, dict[str, Any]]:
    """Fit ratings for every canonical problem identity."""
    return {key: estimate_problem_rating(rows, **kwargs) for key, rows in observations.items()}


def _number(value: Any, *, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def smoothed_solve_rate(
    *, accepted: Any, eligible_teams: Any, prior: float = 1.0
) -> float:
    """Return a Laplace-smoothed problem solve rate in ``[0, 1]``.

    ``accepted`` is used only to calibrate the problem's expected difficulty;
    it is never treated as a player's own success.  With no eligible rows the
    neutral prior (50%) is returned instead of pretending the problem was easy.
    """

    accepted_value = _number(accepted, field="accepted")
    teams_value = _number(eligible_teams, field="eligible_teams")
    prior_value = _number(prior, field="prior")
    if accepted_value < 0:
        raise ValueError("accepted must be non-negative")
    if teams_value < 0:
        raise ValueError("eligible_teams must be non-negative")
    if accepted_value > teams_value:
        raise ValueError("accepted cannot exceed eligible_teams")
    if prior_value <= 0:
        raise ValueError("prior must be positive")
    if teams_value == 0:
        return 0.5
    return min(
        max(
            (accepted_value + prior_value)
            / (teams_value + 2 * prior_value),
            0.0,
        ),
        1.0,
    )


def normalize_label_weights(
    labels: Mapping[str, Any],
    *,
    allowed_axes: Iterable[str] = PROBLEM_TYPE_AXES,
) -> dict[str, float]:
    """Validate and normalise one problem's multi-label axis weights.

    Labels are fractions of one problem's exposure, not extra opportunities.
    Consequently the returned positive values sum to one.  Unknown axis names,
    negative values, and an all-zero label map are rejected so a malformed
    manifest cannot silently bias a player's profile.
    """

    if not isinstance(labels, Mapping):
        raise ValueError("labels must be a mapping")
    allowed = set(allowed_axes)
    values: dict[str, float] = {}
    for axis, raw_weight in labels.items():
        if axis not in allowed:
            raise ValueError(f"unknown problem type: {axis}")
        weight = _number(raw_weight, field=f"label weight {axis}")
        if weight < 0:
            raise ValueError(
                "label weights must be non-negative and positive when used"
            )
        if weight > 0:
            values[str(axis)] = weight
    total = sum(values.values())
    if total <= 0:
        raise ValueError("at least one label weight must be positive")
    return {axis: weight / total for axis, weight in values.items()}


def difficulty_weight_from_solve_rate(solve_rate: Any) -> float:
    """Map a smoothed solve rate to a bounded challenge weight.

    A universally solved problem has weight ``0.5`` and an unsolved problem
    has weight ``1.5``.  The bounded range prevents one anomalous contest from
    dominating the profile while still making difficult solves count more.
    """

    rate = _number(solve_rate, field="solve_rate")
    rate = min(max(rate, 0.0), 1.0)
    return min(max(1.5 - rate, 0.5), 1.5)


def smooth_difficulty_weight(
    *, accepted: Any, eligible_teams: Any, prior: float = 1.0
) -> float:
    """Calculate a difficulty weight from contest solve statistics.

    Laplace smoothing uses ``(accepted + prior) / (teams + 2*prior)``.  When a
    contest has no eligible teams, there is no empirical difficulty signal, so
    the neutral weight ``1.0`` is returned.
    """

    rate = smoothed_solve_rate(
        accepted=accepted, eligible_teams=eligible_teams, prior=prior
    )
    return difficulty_weight_from_solve_rate(rate)


def difficulty_level_from_solve_rate(solve_rate: Any) -> tuple[str, str]:
    """Map an expected solve rate to a stable, human-readable difficulty band."""

    rate = _number(solve_rate, field="solve_rate")
    rate = min(max(rate, 0.0), 1.0)
    for key, label, upper_bound in DIFFICULTY_LEVELS:
        if rate <= upper_bound:
            return key, label
    return DIFFICULTY_LEVELS[-1][0], DIFFICULTY_LEVELS[-1][1]


def difficulty_level_from_problem_rating(problem_rating: Any) -> tuple[str, str]:
    """Map the shared absolute problem rating to the seven public bands."""

    rating = _number(problem_rating, field="problem_rating")
    lower = 0.0
    for key, label, upper in PROBLEM_RATING_LEVELS:
        if rating < upper:
            return key, label
        lower = upper
    return PROBLEM_RATING_LEVELS[-1][0], PROBLEM_RATING_LEVELS[-1][1]


def _optional_count(value: Any) -> int | float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return int(number) if number.is_integer() else number


def build_contest_problem_overview(
    *,
    contest_id: str,
    raw_problems: Iterable[Mapping[str, Any]],
    raw_rows: Iterable[Mapping[str, Any]],
    manifest: Mapping[str, Any],
    problem_rating_index: Mapping[str, Mapping[str, Any]] | None = None,
    contest_links: Iterable[Any] | None = None,
    problem_catalog: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Join raw contest statistics with curated type labels for the web page.

    The source ``accepted`` statistic is used only as a contest-wide difficulty
    signal.  ``eligibleTeams`` comes from the aligned status rows, and missing
    statistics stay unknown instead of being treated as a zero-success problem.
    """

    problems = list(raw_problems or ())
    rows = list(raw_rows or ())
    manifest_problems = manifest.get("problems", {}) if isinstance(manifest, Mapping) else {}
    if not isinstance(manifest_problems, Mapping):
        manifest_problems = {}
    catalog_problems = problem_catalog if isinstance(problem_catalog, Mapping) else {}

    observed_counts = [0] * len(problems)
    for row in rows:
        statuses = row.get("statuses") if isinstance(row, Mapping) else None
        if not isinstance(statuses, list):
            continue
        for index in range(min(len(statuses), len(problems))):
            if isinstance(statuses[index], Mapping):
                observed_counts[index] += 1

    result: list[dict[str, Any]] = []
    for index, raw_problem in enumerate(problems):
        if not isinstance(raw_problem, Mapping):
            continue
        alias = str(raw_problem.get("alias") or index)
        curated = manifest_problems.get(f"{contest_id}:{alias}")
        curated = curated if isinstance(curated, Mapping) else {}
        catalog = catalog_problems.get(f"{contest_id}:{alias}")
        catalog = catalog if isinstance(catalog, Mapping) else {}

        labels: dict[str, float] = {}
        raw_labels = curated.get("labels", {})
        if isinstance(raw_labels, Mapping) and raw_labels:
            try:
                labels = normalize_label_weights(raw_labels)
            except ValueError:
                labels = {}
        ordered_labels = sorted(labels, key=lambda axis: (-labels[axis], axis))
        try:
            detail_tags = normalize_detail_tags(curated.get("detailTags"))
        except ValueError:
            # Invalid fine-grained metadata must not leak into the public
            # bundle.  The full manifest validator reports the actionable
            # error when a normal export loads the manifest.
            detail_tags = []
        status = curated.get("status", "unknown")
        if status not in _MANIFEST_STATUSES:
            status = "unknown"

        stats = raw_problem.get("statistics")
        stats = stats if isinstance(stats, Mapping) else {}
        accepted = _optional_count(stats.get("accepted"))
        submitted = _optional_count(stats.get("submitted"))
        expected_rate: float | None = None
        eligible_teams = observed_counts[index]
        if accepted is not None:
            eligible_teams = max(eligible_teams, int(math.ceil(accepted)), 1)
            accepted_for_rate = min(float(accepted), float(eligible_teams))
            expected_rate = smoothed_solve_rate(
                accepted=accepted_for_rate,
                eligible_teams=eligible_teams,
            )
            expected_rate = round(expected_rate, 6)
        rating = None
        if problem_rating_index:
            rating_record = problem_rating_index.get(str(curated.get("canonicalId") or ""))
            if isinstance(rating_record, Mapping):
                rating = rating_record

        result.append(
            {
                "alias": alias,
                "title": _problem_title(raw_problem, curated, catalog),
                "canonicalId": curated.get("canonicalId"),
                "problemUrl": _problem_url(
                    raw_problem,
                    curated,
                    canonical_id=(
                        str(curated.get("canonicalId"))
                        if curated.get("canonicalId")
                        else None
                    ),
                    alias=alias,
                    contest_links=contest_links,
                    catalog=catalog,
                ),
                "typeKeys": ordered_labels if status == "classified" else [],
                "typeLabels": (
                    [PROBLEM_TYPE_LABELS[axis] for axis in ordered_labels]
                    if status == "classified" else []
                ),
                "detailTags": detail_tags if status == "classified" else [],
                "status": status,
                "confidence": (
                    float(curated.get("confidence", 0.0))
                    if isinstance(curated.get("confidence", 0.0), (int, float))
                    else 0.0
                ),
                "accepted": accepted,
                "submitted": submitted,
                "eligibleTeams": eligible_teams,
                "solveRate": expected_rate,
                "problemRating": rating.get("problemRating") if rating else None,
                "difficultyKey": (
                    difficulty_level_from_problem_rating(rating["problemRating"])[0]
                    if rating and rating.get("problemRating") is not None else None
                ),
                "difficultyLabel": (
                    difficulty_level_from_problem_rating(rating["problemRating"])[1]
                    if rating and rating.get("problemRating") is not None else None
                ),
                "posteriorSd": rating.get("posteriorSd") if rating else None,
                "ratingSampleCount": int(rating.get("sampleCount", 0)) if rating else 0,
                "ratingEffectiveSampleCount": (
                    rating.get("effectiveSampleCount", 0.0) if rating else 0.0
                ),
                "expectedPassRateAtReference": (
                    rating.get("expectedPassRateAtReference") if rating else None
                ),
            }
        )
    return result


def _sigmoid(value: float) -> float:
    """Numerically safe logistic function used by the small MAP solver."""

    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def _logit(value: float) -> float:
    value = min(max(float(value), _IRT_MIN_PROBABILITY), _IRT_MAX_PROBABILITY)
    return math.log(value / (1.0 - value))


def _rating_observation_offset(raw: Mapping[str, Any]) -> float | None:
    """Return the expected log-odds for one team/problem observation.

    New evidence carries the same absolute team and problem rating scales used
    by the problem-rating fit.  The optional posterior standard deviations are
    folded into the logit with a logistic-normal shrinkage approximation.  Old
    evidence remains valid through ``expectedSolveRate`` and
    ``difficultyWeight``.
    """

    team = raw.get("teamPreRating", raw.get("teamRating"))
    problem = raw.get("problemRating")
    try:
        discrimination = _number(raw.get("problemDiscrimination", 1.0), field="problemDiscrimination")
    except ValueError:
        discrimination = 1.0
    if discrimination <= 0:
        discrimination = 1.0
    if team is not None and problem is not None:
        try:
            team_value = _number(team, field="teamPreRating")
            problem_value = _number(problem, field="problemRating")
            team_sd = 0.0 if raw.get("teamRatingSd") is None else _number(raw.get("teamRatingSd"), field="teamRatingSd")
            problem_sd = 0.0 if raw.get("problemPosteriorSd") is None else _number(raw.get("problemPosteriorSd"), field="problemPosteriorSd")
            if team_sd < 0 or problem_sd < 0:
                return None
            # The logistic-normal mean is approximately sigmoid(mu / sqrt(1 +
            # pi*variance/8)).  This keeps uncertain new teams close to 50%
            # instead of treating a default 1400/1590.85 as exact evidence.
            alpha = PROBLEM_RATING_ALPHA * discrimination
            variance = (alpha * (team_sd * team_sd + problem_sd * problem_sd) ** 0.5) ** 2
            attenuation = math.sqrt(1.0 + math.pi * variance / 8.0)
            return alpha * (team_value - problem_value) / attenuation
        except ValueError:
            pass
    expected = raw.get("expectedSolveRate")
    if expected is None:
        difficulty = raw.get("difficultyWeight", 1.0)
        try:
            expected = 1.5 - _number(difficulty, field="difficultyWeight")
        except ValueError:
            expected = 0.5
    try:
        expected_value = _number(expected, field="expectedSolveRate")
    except ValueError:
        expected_value = 0.5
    expected_value = min(max(expected_value, _IRT_MIN_PROBABILITY), _IRT_MAX_PROBABILITY)
    # ``expectedSolveRate`` is already a probability.  Keep this legacy
    # fallback on its log-odds scale; discrimination applies only to calibrated
    # team/problem rating differences above.
    return _logit(expected_value)


def _outcome_surprise_weight(
    expected_offset: float,
    solved: bool,
    power: float,
) -> float:
    """Return the difficulty-aware weight for one binary outcome.

    ``expected_offset`` is the log-odds implied by the team/problem baseline,
    before the player's residual is fitted.  Passing a hard problem is
    surprising and informative; failing it is comparatively ordinary.  The
    converse holds for an easy problem.  A floor prevents a long sequence of
    hard failures from becoming literally invisible.
    """

    if power <= 0:
        return 1.0
    expected = _sigmoid(expected_offset)
    surprise = (1.0 - expected) if solved else expected
    return max(_IRT_MIN_OUTCOME_WEIGHT, surprise ** power)


def estimate_offset_irt(
    observations: Iterable[Mapping[str, Any]],
    *,
    prior_sd: float = _IRT_PRIOR_SD,
    rank_z: float = _IRT_RANK_Z,
    max_iterations: int = 8,
    contest_weight_cap: float = _IRT_CONTEST_WEIGHT_CAP,
    surprise_power: float = _IRT_SURPRISE_POWER,
) -> dict[str, float]:
    """Estimate one player's ability against calibrated problem expectations.

    Each observation has ``solved`` (boolean).  New exports additionally carry
    ``teamPreRating`` and ``problemRating`` (with optional uncertainty); these
    define the baseline probability before the personal axis residual.  The
    legacy ``expectedSolveRate``/``difficultyWeight`` fields remain a fallback.
    A normal prior keeps sparse samples conservative.  ``contestId`` enables a
    per-contest information cap because problems from one board are correlated.

    The implementation is a one-dimensional Newton MAP solve, deliberately
    dependency-free and deterministic so exports remain reproducible.
    """

    prior_sd_value = _number(prior_sd, field="prior_sd")
    rank_z_value = _number(rank_z, field="rank_z")
    contest_cap = _number(contest_weight_cap, field="contest_weight_cap")
    surprise_power_value = _number(surprise_power, field="surprise_power")
    iterations = int(max_iterations)
    if prior_sd_value <= 0:
        raise ValueError("prior_sd must be positive")
    if rank_z_value < 0 or iterations < 1 or surprise_power_value < 0:
        raise ValueError(
            "rank_z/max_iterations must be valid and surprise_power non-negative"
        )

    prepared: list[tuple[float, float, float, float, str]] = []
    for raw in observations:
        if not isinstance(raw, Mapping):
            continue
        solved = raw.get("solved")
        if solved is None:
            # Missing status is an unknown observation, not a failed solve.
            continue
        expected_offset = _rating_observation_offset(raw)
        if expected_offset is None:
            continue
        try:
            weight = _number(raw.get("weight", 1.0), field="observation weight")
        except ValueError:
            continue
        if weight <= 0:
            continue
        solved_value = bool(solved)
        prepared.append(
            (
                1.0 if solved_value else 0.0,
                expected_offset,
                weight,
                _outcome_surprise_weight(
                    expected_offset, solved_value, surprise_power_value
                ),
                str(raw.get("contestId") or ""),
            )
        )

    if not prepared:
        return {
            "ability": 0.0,
            "displayMastery": 0.5,
            "posteriorSd": prior_sd_value,
            "lowerBound": _sigmoid(-rank_z_value * prior_sd_value),
            "expectedMastery": 0.5,
            "effectiveWeight": 0.0,
            "information": 0.0,
            "confidence": 0.0,
        }

    # Scale each contest's observations together.  This changes information,
    # not the direction of the evidence, and leaves single-problem contests
    # untouched.
    if contest_cap > 0:
        by_contest: dict[str, float] = {}
        for _, _, weight, _, contest_id in prepared:
            by_contest[contest_id] = by_contest.get(contest_id, 0.0) + weight
        prepared = [
            (
                solved,
                offset,
                weight * min(1.0, contest_cap / by_contest.get(contest_id, weight)),
                outcome_weight,
                contest_id,
            )
            for solved, offset, weight, outcome_weight, contest_id in prepared
        ]

    prior_precision = 1.0 / (prior_sd_value * prior_sd_value)
    theta = 0.0
    for _ in range(iterations):
        gradient = -theta * prior_precision
        information = prior_precision
        for solved, expected_offset, weight, outcome_weight, _ in prepared:
            probability = _sigmoid(theta + expected_offset)
            effective_weight = weight * outcome_weight
            gradient += effective_weight * (solved - probability)
            information += effective_weight * probability * (1.0 - probability)
        step = gradient / information
        next_theta = min(max(theta + step, -8.0), 8.0)
        if abs(next_theta - theta) < 1e-10:
            theta = next_theta
            break
        theta = next_theta

    information = prior_precision
    expected_total = 0.0
    weight_total = 0.0
    for _, expected_offset, weight, outcome_weight, _ in prepared:
        probability = _sigmoid(theta + expected_offset)
        effective_weight = weight * outcome_weight
        information += effective_weight * probability * (1.0 - probability)
        expected_total += _sigmoid(expected_offset) * effective_weight
        weight_total += effective_weight
    posterior_sd = math.sqrt(1.0 / information)
    lower_bound = _sigmoid(theta - rank_z_value * posterior_sd)
    return {
        "ability": theta,
        "displayMastery": _sigmoid(theta),
        "posteriorSd": posterior_sd,
        "lowerBound": lower_bound,
        "expectedMastery": expected_total / weight_total,
        "effectiveWeight": weight_total,
        "information": information - prior_precision,
        "confidence": max(0.0, min(1.0, (information - prior_precision) / information)),
    }


def validate_problem_manifest(manifest: Mapping[str, Any]) -> None:
    """Validate the stable, JSON-shaped problem classification manifest.

    Required top-level fields are a non-empty string ``version`` and a
    ``problems`` mapping.  A classified record must carry at least one label;
    unknown/conflict records may intentionally carry no labels.
    """

    if not isinstance(manifest, Mapping):
        raise ValueError("manifest must be a mapping")
    version = manifest.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("manifest version is required")
    problems = manifest.get("problems")
    if not isinstance(problems, Mapping):
        raise ValueError("manifest problems must be a mapping")

    for problem_key, record in problems.items():
        if not isinstance(problem_key, str) or not problem_key.strip():
            raise ValueError("problem keys must be non-empty strings")
        if not isinstance(record, Mapping):
            raise ValueError(f"problem {problem_key} must be a mapping")
        canonical_id = record.get("canonicalId")
        if not isinstance(canonical_id, str) or not canonical_id.strip():
            raise ValueError(f"problem {problem_key} canonicalId is required")
        status = record.get("status")
        if status not in _MANIFEST_STATUSES:
            raise ValueError(f"problem {problem_key} status is invalid")
        confidence = _number(
            record.get("confidence"), field=f"problem {problem_key} confidence"
        )
        if not 0 <= confidence <= 1:
            raise ValueError(f"problem {problem_key} confidence must be in [0, 1]")

        labels = record.get("labels", {})
        if status == "classified" and not labels:
            raise ValueError(f"problem {problem_key} needs labels")
        if labels:
            normalize_label_weights(labels)

        if "detailTags" in record:
            try:
                normalize_detail_tags(record.get("detailTags"))
            except ValueError as exc:
                raise ValueError(f"problem {problem_key} detailTags are invalid: {exc}") from exc

        if "difficultyWeight" in record:
            difficulty = _number(
                record["difficultyWeight"],
                field=f"problem {problem_key} difficultyWeight",
            )
            if difficulty <= 0:
                raise ValueError(
                    f"problem {problem_key} difficultyWeight must be positive"
                )


def deduplicate_problem_evidence(
    evidence: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Deduplicate repeated evidence by an explicit identity namespace.

    ``identityKey`` (or the compatibility alias ``evidenceKey``) identifies one
    contest/source opportunity.  Falling back to ``canonicalId`` preserves the
    old API for callers that intentionally want cross-appearance deduplication.
    A missing solve observation remains unknown rather than becoming a failed
    solve.  Conflicting labels or statuses are marked ``conflict`` and are
    therefore treated as unknown by :func:`aggregate_skill_mastery`.
    """

    merged: dict[str, dict[str, Any]] = {}
    for raw in evidence:
        if not isinstance(raw, Mapping):
            raise ValueError("problem evidence must be a mapping")
        canonical_id = raw.get("canonicalId")
        if not isinstance(canonical_id, str) or not canonical_id.strip():
            raise ValueError("problem evidence canonicalId is required")
        identity_key = raw.get("identityKey", raw.get("evidenceKey", canonical_id))
        if not isinstance(identity_key, str) or not identity_key.strip():
            raise ValueError("problem evidence identityKey is required")
        solved_raw = raw.get("solved")
        solved = None if solved_raw is None else bool(solved_raw)
        appearances = int(raw.get("appearances", 1))
        solved_appearances = int(
            raw.get("solvedAppearances", int(solved is True))
        )
        if appearances < 1 or solved_appearances < 0:
            raise ValueError("problem evidence appearance counters are invalid")

        labels = raw.get("labels", {})
        normalised_labels = normalize_label_weights(labels) if labels else {}
        difficulty = _number(
            raw.get("difficultyWeight", 1.0),
            field="problem evidence difficultyWeight",
        )
        if difficulty <= 0:
            raise ValueError("problem evidence difficultyWeight must be positive")
        status = raw.get("status")
        if status not in _MANIFEST_STATUSES:
            status = "unknown"
        if solved is None and status == "classified":
            # A classified item with no aligned team status is not evidence of
            # failure; it only reduces the player's known-data coverage.
            status = "unknown"
        confidence = _number(
            raw.get("classificationConfidence", raw.get("confidence", 1.0)),
            field="problem evidence classificationConfidence",
        )
        if not 0 <= confidence <= 1:
            raise ValueError("problem evidence classificationConfidence must be in [0, 1]")
        try:
            evidence_weight = _number(
                raw.get("evidenceWeight", raw.get("teamWeight", 1.0)),
                field="problem evidence evidenceWeight",
            )
        except ValueError:
            evidence_weight = 1.0
        if evidence_weight <= 0:
            raise ValueError("problem evidence evidenceWeight must be positive")

        current = merged.get(identity_key)
        if current is None:
            merged[identity_key] = {
                "canonicalId": canonical_id,
                "identityKey": identity_key,
                "labels": normalised_labels,
                "difficultyWeight": difficulty,
                "expectedSolveRate": raw.get("expectedSolveRate"),
                "contestId": raw.get("contestId"),
                "contestStartAt": raw.get("contestStartAt"),
                "teamPreRating": raw.get("teamPreRating", raw.get("teamRating")),
                "playerPreRating": raw.get("playerPreRating"),
                "problemRating": raw.get("problemRating"),
                "problemDiscrimination": raw.get("problemDiscrimination", 1.0),
                "problemPosteriorSd": raw.get("problemPosteriorSd"),
                "teamRatingSd": raw.get("teamRatingSd"),
                "teamWeight": raw.get("teamWeight", 1.0),
                "solved": solved,
                "status": status,
                "classificationConfidence": confidence,
                "evidenceWeight": evidence_weight,
                "appearances": appearances,
                "solvedAppearances": solved_appearances,
                "observedAppearances": int(solved is not None),
            }
            continue

        if current["labels"] != normalised_labels:
            current["status"] = "conflict"
            current["labels"] = {}
        elif current["status"] == "conflict" or status == "conflict":
            current["status"] = "conflict"
        elif current["status"] == "unknown" and status == "classified":
            # A later aligned observation can resolve an earlier missing-status
            # record without turning the whole identity into a conflict.
            current["status"] = "classified"
        elif current["status"] == "classified" and status == "unknown":
            pass
        elif current["status"] != status:
            current["status"] = "conflict"
        previous_solved = current.get("solved")
        if previous_solved is True or solved is True:
            current["solved"] = True
        elif previous_solved is False or solved is False:
            current["solved"] = False
        else:
            current["solved"] = None
        current["difficultyWeight"] = max(current["difficultyWeight"], difficulty)
        if current.get("expectedSolveRate") is None:
            current["expectedSolveRate"] = raw.get("expectedSolveRate")
        if current.get("problemDiscrimination") is None:
            current["problemDiscrimination"] = raw.get("problemDiscrimination", 1.0)
        for field in ("teamPreRating", "playerPreRating", "problemRating", "problemPosteriorSd", "teamRatingSd", "contestId", "contestStartAt", "teamWeight"):
            if current.get(field) is None and raw.get(field) is not None:
                current[field] = raw.get(field)
        current["classificationConfidence"] = min(
            float(current.get("classificationConfidence", 1.0)), confidence
        )
        current["evidenceWeight"] = max(
            float(current.get("evidenceWeight", 1.0)), evidence_weight
        )
        current["appearances"] += appearances
        current["solvedAppearances"] += solved_appearances
        current["observedAppearances"] += int(solved is not None)

    return list(merged.values())


def aggregate_skill_mastery(
    evidence: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Aggregate unique problem evidence into thirteen calibrated skill axes.

    ``rawMastery`` and the success/exposure weights remain the transparent
    observed solve-rate diagnostics.  ``mastery`` is now the posterior ability
    display value from :func:`estimate_offset_irt`: a solved hard problem counts
    more than a solved easy problem, while an expected hard failure is down
    weighted because it is ordinary at that baseline.  A failure on an easy
    problem remains strongly negative.  Sparse samples are pulled toward the
    neutral prior.  Unknown/conflicting/missing-status problems are excluded
    from ability observations but included in coverage accounting.
    """

    unique = deduplicate_problem_evidence(evidence)
    axes: dict[str, dict[str, Any]] = {
        axis: {
            "mastery": None,
            "rawMastery": None,
            "successWeight": 0.0,
            "exposureWeight": 0.0,
            "uniqueProblems": 0,
            "effectiveProblems": 0.0,
            "classificationConfidence": 0.0,
            "expectedMastery": None,
            "ability": None,
            "posteriorSd": None,
            "abilityLowerBound": None,
            "modelConfidence": 0.0,
            "axisCoverage": 0.0,
            "_observations": [],
        }
        for axis in PROBLEM_TYPE_AXES
    }
    classified_exposure = 0.0
    unknown_exposure = 0.0

    for problem in unique:
        difficulty = float(problem["difficultyWeight"])
        try:
            evidence_weight = _number(
                problem.get("evidenceWeight", problem.get("teamWeight", 1.0)),
                field="evidenceWeight",
            )
        except ValueError:
            evidence_weight = 1.0
        evidence_weight = max(0.0, evidence_weight)
        labels = problem["labels"]
        status = problem.get("status")
        if status != "classified" or not labels or problem.get("solved") is None:
            unknown_exposure += difficulty * evidence_weight
            continue
        classified_exposure += difficulty * evidence_weight
        solved = bool(problem.get("solved"))
        confidence = float(problem.get("classificationConfidence", problem.get("confidence", 1.0)))
        confidence = min(max(confidence, 0.0), 1.0)
        if evidence_weight <= 0:
            unknown_exposure += difficulty
            continue
        expected_rate = problem.get("expectedSolveRate")
        if expected_rate is None:
            expected_rate = 1.5 - difficulty
        try:
            expected_rate = min(
                max(float(expected_rate), _IRT_MIN_PROBABILITY),
                _IRT_MAX_PROBABILITY,
            )
        except (TypeError, ValueError):
            expected_rate = 0.5
        for axis, label_weight in labels.items():
            exposure = float(label_weight) * difficulty * evidence_weight
            item = axes[axis]
            item["exposureWeight"] += exposure
            item["successWeight"] += exposure if solved else 0.0
            item["uniqueProblems"] += 1
            q = float(label_weight) * confidence * evidence_weight
            item.setdefault("_qSum", 0.0)
            item.setdefault("_qSquared", 0.0)
            item["_qSum"] += q
            item["_qSquared"] += q * q
            item["classificationConfidence"] += q
            item["_observations"].append(
                {
                    "solved": solved,
                    "expectedSolveRate": expected_rate,
                    "weight": q,
                    "exposure": exposure,
                    "difficultyWeight": difficulty,
                    "contestId": problem.get("contestId"),
                    "teamPreRating": problem.get("teamPreRating"),
                    "problemRating": problem.get("problemRating"),
                    "problemDiscrimination": problem.get("problemDiscrimination", 1.0),
                    "problemPosteriorSd": problem.get("problemPosteriorSd"),
                    "teamRatingSd": problem.get("teamRatingSd"),
                }
            )

    for item in axes.values():
        observations = item["_observations"]
        # Multiple problems from one contest are correlated.  Cap the total
        # exposure per axis/contest, scaling both diagnostics and IRT weight so
        # confidence cannot grow linearly with board length.
        by_contest: dict[str, float] = {}
        for observation in observations:
            key = observation.get("contestId")
            if not key:
                continue
            key = str(key)
            by_contest[key] = by_contest.get(key, 0.0) + float(observation.get("exposure", 0.0))
        for observation in observations:
            key = observation.get("contestId")
            if not key:
                continue
            key = str(key)
            total = by_contest.get(key, 0.0)
            if total > _CONTEST_EVIDENCE_CAP:
                scale = _CONTEST_EVIDENCE_CAP / total
                observation["weight"] = float(observation.get("weight", 0.0)) * scale
                observation["exposure"] = float(observation.get("exposure", 0.0)) * scale
        if observations:
            item["exposureWeight"] = sum(float(o.get("exposure", 0.0)) for o in observations)
            item["successWeight"] = sum(
                float(o.get("exposure", 0.0)) for o in observations if bool(o.get("solved"))
            )
            item["_qSum"] = sum(float(o.get("weight", 0.0)) for o in observations)
            item["_qSquared"] = sum(float(o.get("weight", 0.0)) ** 2 for o in observations)
            item["axisCoverage"] = (
                item["exposureWeight"]
                / (item["exposureWeight"] + unknown_exposure)
                if item["exposureWeight"] + unknown_exposure > 0 else 0.0
            )
        exposure = item["exposureWeight"]
        if exposure > 0:
            raw = item["successWeight"] / exposure
            item["rawMastery"] = raw
            q_sum = float(item.pop("_qSum", 0.0))
            q_squared = float(item.pop("_qSquared", 0.0))
            item["classificationConfidence"] = (
                q_sum / max(float(item["uniqueProblems"]), 1.0)
            )
            item["effectiveProblems"] = (
                min(q_sum, (q_sum * q_sum) / q_squared) if q_squared > 0 else 0.0
            )
            model = estimate_offset_irt(item["_observations"])
            item["mastery"] = model["displayMastery"]
            item["expectedMastery"] = model["expectedMastery"]
            item["ability"] = model["ability"]
            item["posteriorSd"] = model["posteriorSd"]
            item["abilityLowerBound"] = model["lowerBound"]
            item["modelConfidence"] = model["confidence"]
        else:
            item.pop("_qSum", None)
            item.pop("_qSquared", None)
            item.pop("_observations", None)
        item["successWeight"] = round(item["successWeight"], 12)
        item["exposureWeight"] = round(item["exposureWeight"], 12)
        item["effectiveProblems"] = round(float(item.get("effectiveProblems", 0.0)), 12)
        item["classificationConfidence"] = round(float(item.get("classificationConfidence", 0.0)), 6)
        for key in ("mastery", "expectedMastery", "ability", "posteriorSd", "abilityLowerBound", "modelConfidence"):
            if item.get(key) is not None:
                item[key] = round(float(item[key]), 12)

    total_exposure = classified_exposure + unknown_exposure
    coverage = classified_exposure / total_exposure if total_exposure else 0.0
    return {
        "axes": axes,
        "classifiedExposure": round(classified_exposure, 12),
        "unknownExposure": round(unknown_exposure, 12),
        "coverage": coverage,
        "uniqueProblems": len(unique),
    }


def aggregate_skill_mastery_sequential(
    evidence: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Replay player/type evidence chronologically on the absolute rating scale.

    This is the production estimator for the next panel model.  Unlike the
    retrospective batch estimator above, it takes each contest as one update
    block.  ``playerPreRating`` is the player's ladder rating immediately before
    that contest; it is the prior anchor, while the posterior axis rating is
    carried from one contest to the next.  ``effectiveProblems`` is retained as
    a diagnostic only.  Public eligibility uses ``uniqueProblems``.
    """

    from .skill_sequential import SEQUENTIAL_SKILL_MODEL, update_sequential_skill

    unique = deduplicate_problem_evidence(evidence)
    axes: dict[str, dict[str, Any]] = {
        axis: {
            "mastery": None,
            "rawMastery": None,
            "successWeight": 0.0,
            "exposureWeight": 0.0,
            "uniqueProblems": 0,
            "effectiveProblems": 0.0,
            "classificationConfidence": 0.0,
            "expectedMastery": None,
            "ability": None,
            "posteriorSd": None,
            "abilityLowerBound": None,
            "modelConfidence": 0.0,
            "scoreModel": SEQUENTIAL_SKILL_MODEL,
        }
        for axis in PROBLEM_TYPE_AXES
    }
    classified_exposure = 0.0
    unknown_exposure = 0.0
    observations: dict[str, list[dict[str, Any]]] = {
        axis: [] for axis in PROBLEM_TYPE_AXES
    }

    for problem in unique:
        difficulty = float(problem.get("difficultyWeight", 1.0))
        evidence_weight = max(
            0.0,
            _number(
                problem.get("evidenceWeight", problem.get("teamWeight", 1.0)),
                field="evidenceWeight",
            ),
        )
        labels = problem.get("labels", {})
        if (
            problem.get("status") != "classified"
            or not labels
            or problem.get("solved") is None
            or problem.get("problemRating") is None
        ):
            unknown_exposure += difficulty * evidence_weight
            continue
        classified_exposure += difficulty * evidence_weight
        confidence = min(
            max(
                float(problem.get("classificationConfidence", problem.get("confidence", 1.0))),
                0.0,
            ),
            1.0,
        )
        for axis, label_weight in labels.items():
            if axis not in axes:
                continue
            label_weight = max(0.0, float(label_weight))
            exposure = label_weight * difficulty * evidence_weight
            item = axes[axis]
            item["exposureWeight"] += exposure
            if bool(problem.get("solved")):
                item["successWeight"] += exposure
            item["uniqueProblems"] += 1
            item["classificationConfidence"] += label_weight * confidence * evidence_weight
            observations[axis].append(
                {
                    "contestId": problem.get("contestId"),
                    "contestStartAt": problem.get("contestStartAt"),
                    "canonicalId": problem.get("canonicalId"),
                    "solved": bool(problem.get("solved")),
                    "problemRating": problem.get("problemRating"),
                    "problemDiscrimination": problem.get("problemDiscrimination", 1.0),
                    "playerPreRating": problem.get("playerPreRating"),
                    "teamPreRating": problem.get("teamPreRating"),
                    "weight": label_weight * confidence * evidence_weight,
                }
            )

    for axis, item in axes.items():
        rows = observations[axis]
        if not rows:
            continue
        model_state, model = update_sequential_skill(rows)
        exposure = float(item["exposureWeight"])
        item["rawMastery"] = (
            float(item["successWeight"]) / exposure if exposure > 0 else None
        )
        item["effectiveProblems"] = float(model.get("effectiveWeight", 0.0) or 0.0)
        item["mastery"] = model["displayMastery"]
        item["expectedMastery"] = model["expectedMastery"]
        item["ability"] = model["ability"]
        item["posteriorSd"] = model["posteriorSd"]
        item["abilityLowerBound"] = model["lowerBound"]
        item["modelConfidence"] = model["confidence"]
        item["uniqueProblems"] = int(model["uniqueProblems"])
        item["classificationConfidence"] /= max(item["uniqueProblems"], 1)
        item["scoreModel"] = SEQUENTIAL_SKILL_MODEL
        for key in (
            "mastery",
            "rawMastery",
            "successWeight",
            "exposureWeight",
            "effectiveProblems",
            "classificationConfidence",
            "expectedMastery",
            "ability",
            "posteriorSd",
            "abilityLowerBound",
            "modelConfidence",
        ):
            if item.get(key) is not None:
                item[key] = round(float(item[key]), 12)

    total_exposure = classified_exposure + unknown_exposure
    return {
        "axes": axes,
        "classifiedExposure": round(classified_exposure, 12),
        "unknownExposure": round(unknown_exposure, 12),
        "coverage": classified_exposure / total_exposure if total_exposure else 0.0,
        "uniqueProblems": len(unique),
        "scoreModel": SEQUENTIAL_SKILL_MODEL,
    }
