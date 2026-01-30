from abc import ABC, abstractmethod


class SearcherBase(ABC):
    """Abstract base class for searchers.

    Subclasses must implement the `name` property and the `search()` method.
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
    def search(self) -> list:
        """Execute the search and return a list of papers.

        Returns
        -------
        list
            List of paper objects.

        Raises
        ------
        Exception
            Implementations may raise if a network or parsing failure occurs.
        """
