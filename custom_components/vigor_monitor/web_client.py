"""Async client for the DrayOS 5 web API (DSL status, read-only)."""

from __future__ import annotations

import asyncio
import logging
import secrets
from typing import Any

import aiohttp

from .protocol import (
    CSRF_HEADER,
    DSL_OP,
    DSL_PID,
    DSL_QUERY,
    EVENT_PID,
    LOGIN_OP,
    LOGOUT_OP,
    WEB_PATH,
    DslStatus,
    ProtocolError,
    decode,
    encode,
    is_ok,
    login_payload,
    logout_payload,
    parse_web_dsl_status,
)

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=15)
# Logout is best effort and must never hold up an unload.
_LOGOUT_TIMEOUT = aiohttp.ClientTimeout(total=5)


class VigorWebError(Exception):
    """Base error of the web client."""


class VigorWebConnectionError(VigorWebError):
    """Not reachable, or the answer is not the expected API format."""


class VigorWebAuthError(VigorWebError):
    """Login rejected (wrong credentials, too many sessions or lockout)."""


class VigorWebClient:
    """One web session on the Vigor.

    The aiohttp session must use CookieJar(unsafe=True): aiohttp drops cookies
    set by plain IP hosts otherwise and the login would never stick. The session
    is kept between polls so the device does not collect web sessions (it only
    allows a few at once).
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        username: str,
        password: str,
        use_ssl: bool = False,
    ) -> None:
        """Initialise the client."""
        self._session = session
        self._url = f"{'https' if use_ssl else 'http'}://{host}{WEB_PATH}"
        self._username = username
        self._password = password
        self._csrf = ""
        self._logged_in = False
        self._lock = asyncio.Lock()

    async def _post(
        self,
        pid: str,
        op: str,
        payload: dict[str, Any],
        timeout: aiohttp.ClientTimeout = _TIMEOUT,
    ) -> dict[str, Any]:
        # Reads also work with a random token; writes would need the real one.
        token = self._csrf or secrets.token_hex(16)
        form = {"pid": pid, "op": op, "ct": encode(payload), "_token": token}
        try:
            async with self._session.post(
                self._url,
                data=form,
                headers={CSRF_HEADER: token},
                timeout=timeout,
                allow_redirects=False,
                ssl=False,  # self-signed certificate on the device
            ) as resp:
                body = await resp.text(errors="replace")
                if new_token := resp.headers.get(CSRF_HEADER):
                    self._csrf = new_token
                status = resp.status
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise VigorWebConnectionError(f"{self._url}: {err}") from err
        try:
            return decode(body)
        except ProtocolError as err:
            raise VigorWebConnectionError(
                f"unexpected answer from {self._url} (HTTP {status}): {err}"
            ) from err

    def _forget_session(self) -> None:
        self._csrf = ""
        self._logged_in = False
        self._session.cookie_jar.clear()

    async def _logout_unlocked(self) -> None:
        if self._logged_in:
            try:
                await self._post(
                    EVENT_PID, LOGOUT_OP, logout_payload(self._username), _LOGOUT_TIMEOUT
                )
            except VigorWebError as err:
                _LOGGER.debug("Logout failed: %s", err)
        self._forget_session()

    async def _login_unlocked(self) -> None:
        # End the old session first so re-logins do not pile up on the device.
        await self._logout_unlocked()
        data = await self._post(
            EVENT_PID, LOGIN_OP, login_payload(self._username, self._password)
        )
        if not is_ok(data):
            raise VigorWebAuthError(f"login rejected (rid {data.get('rid')})")
        self._logged_in = True

    async def async_get_dsl_status(self) -> DslStatus:
        """Return the DSL status; logs in (again) when needed."""
        async with self._lock:
            if self._logged_in:
                try:
                    data = await self._post(DSL_PID, DSL_OP, DSL_QUERY)
                    if is_ok(data):
                        return parse_web_dsl_status(data)
                    _LOGGER.debug("DSL request answered rid %s, logging in again", data.get("rid"))
                except (VigorWebConnectionError, ProtocolError) as err:
                    _LOGGER.debug("DSL request failed (%s), logging in again", err)
            await self._login_unlocked()
            data = await self._post(DSL_PID, DSL_OP, DSL_QUERY)
            if not is_ok(data):
                raise VigorWebConnectionError(
                    f"DSL request failed after login (rid {data.get('rid')})"
                )
            try:
                return parse_web_dsl_status(data)
            except ProtocolError as err:
                raise VigorWebConnectionError(str(err)) from err

    async def async_logout(self) -> None:
        """End the web session (best effort)."""
        async with self._lock:
            await self._logout_unlocked()

    async def async_close(self) -> None:
        """Log out and release the aiohttp session (created with auto_cleanup=False)."""
        await self.async_logout()
        self._session.detach()
