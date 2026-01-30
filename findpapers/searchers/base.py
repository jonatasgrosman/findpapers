from abc import ABC, abstractmethod


class SearcherBase(ABC):
    """Abstract base class for searchers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-friendly database name."""

    @abstractmethod
    def search(self) -> list:
        """Execute the search and return a list of papers."""

