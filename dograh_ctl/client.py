"""Thin HTTP client for a self-hosted Dograh instance.

Auth is the `X-API-Key` header (create a key in Dograh -> Developers).
Reads DOGRAH_BASE_URL and DOGRAH_API_KEY from the environment.

Every failure surfaces as one of two exceptions so the CLI can print one line and exit:
- ConfigError: the environment is not set up (exit 2)
- DograhError: the instance answered with an error, or could not be reached (exit 1)
"""
from __future__ import annotations

import os
from typing import Any, Optional

import httpx


class ConfigError(RuntimeError):
    """Missing or invalid local configuration (env vars)."""


class DograhError(RuntimeError):
    """The Dograh API refused or failed a request, or was unreachable."""

    def __init__(self, message: str, status: Optional[int] = None, detail: Any = None):
        super().__init__(message)
        self.status = status
        self.detail = detail


def _detail_from(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text.strip()[:200]
    if isinstance(body, dict):
        detail = body.get("detail", body)
        if isinstance(detail, (dict, list)):
            return str(detail)[:300]
        return str(detail)
    return str(body)[:300]


class DograhClient:
    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        self.base_url = (base_url or os.environ.get("DOGRAH_BASE_URL", "")).rstrip("/")
        self.api_key = api_key or os.environ.get("DOGRAH_API_KEY", "")
        missing = [
            name
            for name, value in (
                ("DOGRAH_BASE_URL", self.base_url),
                ("DOGRAH_API_KEY", self.api_key),
            )
            if not value
        ]
        if missing:
            raise ConfigError(
                f"missing {', '.join(missing)}: set them in your environment (see .env.example)"
            )
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"X-API-Key": self.api_key},
            timeout=30.0,
        )

    def request(self, method: str, path: str, **kwargs):
        try:
            r = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise DograhError(f"cannot reach {self.base_url}: {exc}") from exc
        if r.is_error:
            detail = _detail_from(r)
            raise DograhError(
                f"{method.upper()} {path} failed ({r.status_code}): {detail}",
                status=r.status_code,
                detail=detail,
            )
        if not r.content:
            return None
        try:
            return r.json()
        except ValueError:
            return r.text

    def get(self, path: str, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs):
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs):
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs):
        return self.request("DELETE", path, **kwargs)

    def get_public(self, url: str) -> httpx.Response:
        """Fetch a public artifact URL (transcript/recording); no API key is sent."""
        try:
            r = httpx.get(url, timeout=60.0, follow_redirects=True)
        except httpx.HTTPError as exc:
            raise DograhError(f"cannot fetch {url}: {exc}") from exc
        if r.is_error:
            raise DograhError(f"GET {url} failed ({r.status_code})", status=r.status_code)
        return r
