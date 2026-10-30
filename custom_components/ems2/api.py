"""Klient API v1 serveru EMS 2.0 (aiohttp)."""
from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from .const import VERSION


class EmsApiError(Exception):
    def __init__(self, status: int, message: str, problems: list | None = None):
        super().__init__(f"{status}: {message}")
        self.status = status
        self.message = message
        self.problems = problems or []


class EmsAuthError(EmsApiError):
    pass


class EmsApi:
    def __init__(self, session: aiohttp.ClientSession, url: str, site_id: str, token: str):
        self._s = session
        self.url = url.rstrip("/")
        self.site_id = site_id.strip()
        self._headers = {"Authorization": f"Bearer {token.strip()}", "X-EMS2-Client": f"ha-ems2/{VERSION}"}

    async def _req(self, method: str, path: str, *, json: Any = None, params: dict | None = None) -> Any:
        url = f"{self.url}/api/v1{path}"
        try:
            async with asyncio.timeout(20):
                async with self._s.request(method, url, json=json, params=params, headers=self._headers) as r:
                    try:
                        data = await r.json(content_type=None)
                    except (aiohttp.ContentTypeError, ValueError):
                        data = {"detail": {"error": (await r.text())[:200]}}
                    if r.status >= 400:
                        detail = (data or {}).get("detail") or {}
                        msg = detail.get("error") if isinstance(detail, dict) else str(detail)
                        probs = detail.get("problems") if isinstance(detail, dict) else []
                        cls = EmsAuthError if r.status in (401, 404) else EmsApiError
                        raise cls(r.status, msg or "chyba", probs)
                    return data
        except (aiohttp.ClientError, TimeoutError) as e:
            raise EmsApiError(0, f"server nedostupný: {e}") from e

    def _site(self, sub: str) -> str:
        return f"/sites/{self.site_id}{sub}"

    async def whoami(self) -> dict:
        return await self._req("GET", self._site("/whoami"))

    async def telemetry(self, samples: list[dict]) -> dict:
        return await self._req("POST", self._site("/telemetry"), json={"samples": samples})

    async def command(self) -> dict:
        return await self._req("GET", self._site("/command"))

    async def plan(self, hours: int = 48) -> dict:
        return await self._req("GET", self._site("/plan"), params={"hours": hours})

    async def settings(self) -> dict:
        return await self._req("GET", self._site("/settings"))

    async def patch_settings(self, patch: dict) -> dict:
        return await self._req("PATCH", self._site("/settings"), json=patch)

    async def set_control(self, enabled: bool) -> dict:
        return await self._req("PUT", self._site("/control"), json={"enabled": enabled})

    async def config(self) -> dict:
        return await self._req("GET", self._site("/config"))

    async def put_config(self, cfg: dict) -> dict:
        return await self._req("PUT", self._site("/config"), json={"config": cfg})

    async def put_tariff(self, tariff: dict) -> dict:
        return await self._req("PUT", self._site("/tariff"), json={"tariff": tariff})

    async def replan(self) -> dict:
        return await self._req("POST", self._site("/replan"))

    async def accounting_today(self) -> dict:
        return await self._req("GET", self._site("/accounting"), params={"group": "day"})

    async def billing(self) -> dict:
        return await self._req("GET", f"/api/v1/sites/{self.site_id}/billing")

    async def load_history(self, body: dict) -> dict:
        return await self._req("POST", self._site("/load_history"), json=body)

    async def event(self, kind: str, data: dict) -> dict:
        return await self._req("POST", self._site("/events"), json={"kind": kind, "data": data})
