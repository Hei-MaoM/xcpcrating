"""Abstract rating engine contract shared by all concrete engines."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class PlayerRating:
    """A leaderboard entry for a single player.

    rating:   the display rating used to sort the leaderboard (higher first).
    contests: number of rated contests the player has participated in.
    extra:    engine-specific fields (mu / sigma / raw values, ...).
    """

    key: str
    display_name: str
    org: str
    rating: float
    contests: int
    extra: dict = field(default_factory=dict)


class RatingEngine(ABC):
    """Common interface for predicting and updating player strengths."""

    name: str = "base"

    @abstractmethod
    def predict_scores(self, contest) -> list:
        """Return one float per team in ``contest.teams`` order, BEFORE update.

        Higher means predicted stronger. Ghost teams (no members) receive the
        engine's prior strength.
        """

    @abstractmethod
    def process_contest(self, contest) -> None:
        """Update internal player states from this contest's results."""

    @abstractmethod
    def leaderboard(self, min_contests: int = 3) -> list:
        """Return all players with ``contests >= min_contests``, rating desc."""
