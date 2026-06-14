"""Time-ordered backtesting framework and predictive metrics.

For each contest, in chronological order, the engine first predicts a
strength score per team (``predict_scores``) which is scored against the
realized standings, and only then updates its internal state
(``process_contest``). This avoids look-ahead leakage.

Two per-contest metrics are computed:

* pairwise concordance -- over all team pairs with differing ranks, the
  fraction where the higher predicted score belongs to the better-ranked
  team (ties in prediction count as 0.5).
* spearman -- Spearman rank correlation between negated predicted scores and
  actual ranks (so that "stronger prediction" aligns with "smaller rank").
"""

from collections import defaultdict

import numpy as np

try:  # Prefer scipy when available; fall back to a numpy implementation.
    from scipy.stats import spearmanr as _scipy_spearmanr

    _HAVE_SCIPY = True
except ImportError:  # pragma: no cover - exercised only without scipy
    _scipy_spearmanr = None
    _HAVE_SCIPY = False


def _rankdata(values):
    """Average-rank tie handling, mirroring scipy.stats.rankdata('average')."""
    arr = np.asarray(values, dtype=float)
    order = np.argsort(arr, kind="mergesort")
    ranks = np.empty(len(arr), dtype=float)
    sorted_vals = arr[order]
    i = 0
    n = len(arr)
    while i < n:
        j = i
        while j + 1 < n and sorted_vals[j + 1] == sorted_vals[i]:
            j += 1
        average = (i + j) / 2.0 + 1.0  # 1-based average rank
        ranks[order[i : j + 1]] = average
        i = j + 1
    return ranks


def _spearman_numpy(scores, ranks):
    """Pure-numpy Spearman: Pearson correlation of the rank-transformed data."""
    rank_scores = _rankdata(scores)
    rank_actual = _rankdata(ranks)
    if np.std(rank_scores) == 0 or np.std(rank_actual) == 0:
        return 0.0
    corr = np.corrcoef(rank_scores, rank_actual)[0, 1]
    return float(corr)


def spearman(predicted_scores, actual_ranks):
    """Spearman correlation of negated predicted scores vs actual ranks.

    Returns 0.0 for degenerate inputs (fewer than two teams or zero variance).
    """
    if len(predicted_scores) < 2:
        return 0.0
    neg_scores = [-s for s in predicted_scores]
    if _HAVE_SCIPY:
        corr, _p = _scipy_spearmanr(neg_scores, actual_ranks)
        if corr is None or np.isnan(corr):
            return 0.0
        return float(corr)
    return _spearman_numpy(neg_scores, actual_ranks)


def pairwise_concordance(predicted_scores, actual_ranks):
    """Fraction of correctly-ordered team pairs (ties in prediction = 0.5)."""
    n = len(predicted_scores)
    total = 0
    agree = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            if actual_ranks[i] == actual_ranks[j]:
                continue
            total += 1
            better = actual_ranks[i] < actual_ranks[j]  # i is the better team
            si, sj = predicted_scores[i], predicted_scores[j]
            if si == sj:
                agree += 0.5
            elif (si > sj) == better:
                agree += 1.0
    if total == 0:
        return None
    return agree / total


def _contest_year(contest):
    return contest.start_at.year


def replay(contests, engine):
    """Run the time-ordered backtest of ``engine`` over ``contests``.

    Returns a structured dict with overall / per-category / per-year mean
    metrics plus a per-contest detail list. Contests are assumed to be in
    chronological order already (loader guarantees this); the engine sees
    each contest exactly once, predicting before updating.
    """
    per_contest = []

    for contest in contests:
        ranks = [team.rank for team in contest.teams]
        scores = engine.predict_scores(contest)

        conc = pairwise_concordance(scores, ranks)
        spear = spearman(scores, ranks)

        engine.process_contest(contest)

        per_contest.append(
            {
                "id": contest.id,
                "category": contest.category,
                "year": _contest_year(contest),
                "teams": len(contest.teams),
                "concordance": conc,
                "spearman": spear,
            }
        )

    summary = _summarize(per_contest)
    summary["per_contest"] = per_contest
    summary["engine"] = engine.name
    return summary


def _mean(values):
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return float(np.mean(clean))


def _summarize(per_contest):
    """Aggregate per-contest metrics into overall / category / year means."""
    overall = {
        "concordance": _mean([c["concordance"] for c in per_contest]),
        "spearman": _mean([c["spearman"] for c in per_contest]),
        "contests": len(per_contest),
    }

    by_category = _group_means(per_contest, key="category")
    by_year = _group_means(per_contest, key="year")

    return {
        "overall": overall,
        "by_category": by_category,
        "by_year": by_year,
    }


def _group_means(per_contest, key):
    groups = defaultdict(list)
    for entry in per_contest:
        groups[entry[key]].append(entry)
    result = {}
    for group_key, entries in groups.items():
        result[group_key] = {
            "concordance": _mean([e["concordance"] for e in entries]),
            "spearman": _mean([e["spearman"] for e in entries]),
            "contests": len(entries),
        }
    return result
