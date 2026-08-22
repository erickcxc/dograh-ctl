"""Typer plumbing shared by every command group.

GuardedTyper wraps each registered command so that:
- ConfigError  -> one line on stderr, exit 2
- DograhError  -> one line on stderr, exit 1
- a trailing --json on any command flips output.state.json (same as the root --json)
No command ever shows a traceback to the user.
"""
from __future__ import annotations

import functools
import inspect
from typing import Any, Callable

import typer

from . import output
from .client import ConfigError, DograhError

_JSON_PARAM = "json_"


def guarded(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap a command: map known errors to exit codes and accept a trailing --json."""
    sig = inspect.signature(fn)
    json_param = inspect.Parameter(
        _JSON_PARAM,
        inspect.Parameter.KEYWORD_ONLY,
        default=typer.Option(False, "--json", help="Print raw JSON instead of a table."),
        annotation=bool,
    )
    params = [p for p in sig.parameters.values() if p.name != _JSON_PARAM]
    new_sig = sig.replace(parameters=params + [json_param])

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any):
        if kwargs.pop(_JSON_PARAM, False):
            output.state.json = True
        try:
            return fn(*args, **kwargs)
        except ConfigError as exc:
            output.fail(str(exc))
            raise typer.Exit(2) from None
        except DograhError as exc:
            output.fail(str(exc))
            raise typer.Exit(1) from None

    wrapper.__signature__ = new_sig  # type: ignore[attr-defined]
    return wrapper


class GuardedTyper(typer.Typer):
    """A Typer whose commands are all wrapped by `guarded`."""

    def __init__(self, *args: Any, **kwargs: Any):
        kwargs.setdefault("no_args_is_help", True)
        kwargs.setdefault("pretty_exceptions_enable", False)
        super().__init__(*args, **kwargs)

    def command(self, *args: Any, **kwargs: Any):
        register = super().command(*args, **kwargs)

        def decorator(fn: Callable[..., Any]):
            return register(guarded(fn))

        return decorator
