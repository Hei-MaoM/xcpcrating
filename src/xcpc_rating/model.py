"""Core data contracts shared across the rating pipeline.

These dataclasses are the cross-agent interface. Field names and their
semantics must not change: loaders produce them, engines and validators
consume them.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Member:
    """A single (non-coach) competitor on a team.

    key:          normalized identity, ``f"{clean_name_lower}@{clean_org}"``.
    display_name: cleaned name for display (parenthetical segments stripped),
                  original casing preserved.
    org:          cleaned organization string.
    """

    key: str
    display_name: str
    org: str


@dataclass(frozen=True)
class Team:
    """One standings row, after coach removal and identity normalization.

    rank:         1-based; tied teams share the same (minimum) rank.
    solved:       number of problems solved.
    penalty:      numeric penalty value as found (unit-free within a contest).
    members:      ``tuple[Member, ...]``; an empty tuple denotes a ghost team.
    official:     whether the team is an official (ranked) participant.
    participated: whether the row made at least one submission (a 0-submission
                  row is *displayed* but is *not* a scoring participant). Derived
                  in the loader as ``total submissions > 0``; a row with
                  ``solved > 0`` is necessarily participated. Defaults to ``True``
                  so hand-built test fixtures stay scored.
    """

    rank: int
    solved: int
    penalty: float
    members: tuple
    official: bool
    participated: bool = True


@dataclass(frozen=True)
class Contest:
    """A single ranked contest in standings order.

    id:        relative path without the ``.srk.json`` suffix, e.g.
               ``"ccpc/ccpc2023/ccpc2023final"``.
    title:     fallback / zh-CN title for display.
    start_at:  contest start time parsed from ``contest.startAt``.
    category:  one of ``"icpc"``, ``"ccpc"``, ``"provincial"``.
    teams:     ``tuple[Team, ...]`` in standings order (rank ascending).
    """

    id: str
    title: str
    start_at: datetime
    category: str
    teams: tuple
