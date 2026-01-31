from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from findpapers.models import Paper


class SearcherBase(ABC):
    """Abstract base class for searchers.

    Subclasses must implement the `name` property and the `iter_search()` method.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-friendly database name.

        Returns
        -------
        str
            Database identifier used in metrics and logs.
        """

    @abstractmethod
    def iter_search(self) -> tuple[Iterator[list["Paper"]], int, int, int]:
        """Return an iterator and progress metadata for the search.

        Returns
        -------
        tuple
            Iterator that yields lists of papers, the number of steps, papers per step,
            and total papers.

        Raises
        ------
        Exception
            Implementations may raise if a network or parsing failure occurs.
        """

    def search(self) -> list["Paper"]:
        """Execute the search and return a list of papers.

        Returns
        -------
        list[Paper]
            List of paper objects.
        """
        iterator, _, _, _ = self.iter_search()
        papers: list["Paper"] = []
        for batch in iterator:
            papers.extend(batch)
        return papers

    def _empty_search_result(self) -> tuple[Iterator[list["Paper"]], int, int, int]:
        """Return an empty iterator and zeroed progress metadata.

        Returns
        -------
        tuple
            Empty iterator, zero steps, zero papers per step, zero total papers.
        """
        return iter(()), 0, 0, 0
