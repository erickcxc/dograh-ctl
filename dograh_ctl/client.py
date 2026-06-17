"""Thin HTTP client for a self-hosted Dograh instance.

Auth is via the `X-API-Key` header (create a key in Dograh -> Developers).
Reads DOGRAH_BASE_URL and DOGRAH_API_KEY from the environment.
"""
from __future__ import annotations

import os

import httpx


class DograhClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or os.environ.get("DOGRAH_BASE_URL", "")).rstrip("/")
        self.api_key = api_key or os.environ.get("DOGRAH_API_KEY", "")
        if not self.base_url or not self.api_key:
            raise RuntimeError(
                "Set DOGRAH_BASE_URL and DOGRAH_API_KEY in your environment "
                "(see .env.example)."
            )
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"X-API-Key": self.api_key},
            timeout=30.0,
        )

    def get(self, path: str, **kwargs):
        r = self._client.get(path, **kwargs)
        r.raise_for_status()
        return r.json()

    def request(self, method: str, path: str, **kwargs):
        r = self._client.request(method, path, **kwargs)
        r.raise_for_status()
        return r.json() if r.content else None
