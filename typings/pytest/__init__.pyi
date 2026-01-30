from typing import Pattern, Type

class RaisesContext:
    def __enter__(self) -> BaseException: ...
    def __exit__(
        self,
        exc_type: Type[BaseException] | None,
        exc: BaseException | None,
        tb: object | None,
    ) -> bool | None: ...

class _RaisesExc:
    def __call__(
        self,
        expected_exception: Type[BaseException] | tuple[Type[BaseException], ...],
        *,
        match: str | Pattern[str] | None = ...
    ) -> RaisesContext: ...

raises: _RaisesExc
