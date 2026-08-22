"""Shared fixtures: a fake Dograh instance (respx) and a CLI runner.

Response shapes in tests/fixtures mirror the Pydantic schemas in dograh-hq/dograh at commit
b32187d8 (api/schemas/*.py, api/routes/*.py). If a shape changes upstream, update the fixture
and cite the new commit; never invent fields.
"""
from __future__ import annotations

import json
import pathlib

import pytest
import respx
from typer.testing import CliRunner

BASE_URL = "https://dograh.test"
API_KEY = "dgr_test_key_not_real"
FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    return json.loads((FIXTURES / f"{name}.json").read_text())


@pytest.fixture(autouse=True)
def wide_terminal(monkeypatch):
    """Keep rich tables on one line so assertions can match cell text."""
    monkeypatch.setenv("COLUMNS", "200")


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("DOGRAH_BASE_URL", BASE_URL)
    monkeypatch.setenv("DOGRAH_API_KEY", API_KEY)


@pytest.fixture
def no_env(monkeypatch):
    monkeypatch.delenv("DOGRAH_BASE_URL", raising=False)
    monkeypatch.delenv("DOGRAH_API_KEY", raising=False)


@pytest.fixture
def api(env):
    """A respx router scoped to the fake instance; every test declares the routes it expects."""
    with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
        yield router


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def cli(runner):
    """Invoke the CLI: cli('agents', 'list') -> click Result."""
    from dograh_ctl.main import app

    def _invoke(*args, input=None):
        return runner.invoke(app, list(args), input=input)

    return _invoke
