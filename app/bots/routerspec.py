"""A reusable blueprint for aiogram routers.

An aiogram ``Router`` can only ever be attached to one ``Dispatcher`` — the
second ``include_router`` raises. This fleet gives every bot its own
dispatcher (so one bot can be started or stopped without touching the
others), which means each of them needs its *own* router objects.

``RouterSpec`` records the handler registrations at import time using the same
decorator syntax as a real router, then stamps out a fresh ``Router`` per bot
in :meth:`build`. Registration order inside an observer is preserved, which is
what decides which handler wins.
"""

from __future__ import annotations

from typing import Any, Callable

from aiogram import Router

OBSERVERS = (
    "message",
    "edited_message",
    "channel_post",
    "callback_query",
    "chat_member",
    "my_chat_member",
    "chat_join_request",
    "poll_answer",
)


class _ObserverSpec:
    """Stands in for ``router.<event>`` while the module is being imported."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.observer_filters: list[Any] = []
        self.handlers: list[tuple[Callable[..., Any], tuple[Any, ...], dict[str, Any]]] = []

    def filter(self, *filters: Any) -> None:
        """Filter applied to every handler on this observer."""
        self.observer_filters.extend(filters)

    def __call__(self, *filters: Any, **kwargs: Any):
        def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
            self.handlers.append((handler, filters, kwargs))
            return handler

        return decorator

    def register(self, handler: Callable[..., Any], *filters: Any, **kwargs: Any) -> None:
        self.handlers.append((handler, filters, kwargs))


class RouterSpec:
    """Drop-in replacement for a module-level ``Router``."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._observers = {key: _ObserverSpec(key) for key in OBSERVERS}

    def __getattr__(self, item: str) -> _ObserverSpec:
        try:
            return self.__dict__["_observers"][item]
        except KeyError as exc:  # pragma: no cover - typo guard
            raise AttributeError(
                f"{item!r} is not a supported router event; "
                f"expected one of {', '.join(OBSERVERS)}"
            ) from exc

    def build(self) -> Router:
        """Create a fresh, fully wired ``Router``."""
        router = Router(name=self.name)
        for key, spec in self._observers.items():
            observer = getattr(router, key)
            if spec.observer_filters:
                observer.filter(*spec.observer_filters)
            for handler, filters, kwargs in spec.handlers:
                observer.register(handler, *filters, **kwargs)
        return router
