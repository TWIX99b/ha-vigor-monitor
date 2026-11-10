"""Read DSL line statistics from a DrayTek Vigor (DrayOS 5) via its SSH CLI."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import re

import asyncssh

_LOGGER = logging.getLogger(__name__)

DSL_INFO_COMMAND = "exec dslinfo"

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b[()][A-Za-z0-9]|\r")
_USERNAME_RE = re.compile(r"(?:user ?name|login)\s*:\s*$", re.IGNORECASE)
_PASSWORD_RE = re.compile(r"password\s*:\s*$", re.IGNORECASE)
_PROMPT_RE = re.compile(r"(?:^|\n)[\w.@-]*[>#]\s*$")
_KEY_VALUE_RE = re.compile(r"^\s*([^:\n]+?)\s*:\s*(.*?)\s*$", re.MULTILINE)
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
_DURATION_RE = re.compile(r"(\d+)\s*([dhms])", re.IGNORECASE)
_DURATION_FACTORS = {"d": 86400, "h": 3600, "m": 60, "s": 1}


class DrayTekSshError(Exception):
    """Generic SSH/CLI error."""


class DrayTekSshAuthError(DrayTekSshError):
    """Username or password rejected."""


class DrayTekSshUnsupportedError(DrayTekSshError):
    """The CLI does not know the DSL info command (e.g. DrayOS 4)."""


@dataclass(slots=True)
class DslInfo:
    """Parsed output of `exec dslinfo`."""

    status: str | None
    mode: str | None
    profile: str | None
    annex: str | None
    dsl_version: str | None
    line_uptime: int | None  # seconds
    downstream_kbps: int | None
    upstream_kbps: int | None
    snr_downstream: float | None  # dB
    snr_upstream: float | None  # dB


def _number(value: str | None) -> float | None:
    if not value:
        return None
    match = _NUMBER_RE.search(value)
    return float(match.group()) if match else None


def _duration(value: str | None) -> int | None:
    """Parse '36d 23h  4m 52s' into seconds."""
    if not value:
        return None
    parts = _DURATION_RE.findall(value)
    if not parts:
        return None
    return sum(int(num) * _DURATION_FACTORS[unit.lower()] for num, unit in parts)


def parse_dsl_info(text: str) -> DslInfo:
    """Parse the `exec dslinfo` output.

    Example:
        Status : Showtime
        Mode : VDSL2
        Profile : 35b
        Annex : ANNEX B
        DSL Version : 5.12.31.0_B_A60901
        Line Uptime : 36d 23h  4m 52s
        Downstream Line Rate : 124999 kbps
        Upstream Line Rate : 42438 kbps
        SNR Downstream : 9.9 dB
        SNR Upstream : 8.1 dB
    """
    values = {k.strip().lower(): v.strip() for k, v in _KEY_VALUE_RE.findall(text)}

    def get(key: str) -> str | None:
        return values.get(key) or None

    down = _number(get("downstream line rate"))
    up = _number(get("upstream line rate"))
    return DslInfo(
        status=get("status"),
        mode=get("mode"),
        profile=get("profile"),
        annex=get("annex"),
        dsl_version=get("dsl version"),
        line_uptime=_duration(get("line uptime")),
        downstream_kbps=int(down) if down is not None else None,
        upstream_kbps=int(up) if up is not None else None,
        snr_downstream=_number(get("snr downstream")),
        snr_upstream=_number(get("snr upstream")),
    )


class DrayTekSshClient:
    """Run CLI commands on a DrayTek Vigor over SSH."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        timeout: float = 20,
    ) -> None:
        """Initialise the client."""
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._timeout = timeout

    async def async_get_dsl_info(self) -> DslInfo:
        """Return the parsed DSL statistics."""
        output = await self.async_run(DSL_INFO_COMMAND)
        if "invalid command" in output.lower() or "incomplete command" in output.lower():
            raise DrayTekSshUnsupportedError(output.strip())
        info = parse_dsl_info(output)
        if info.status is None and info.downstream_kbps is None:
            raise DrayTekSshUnsupportedError(f"Unexpected output: {output!r}")
        return info

    async def async_run(self, command: str) -> str:
        """Log in, run one command and return its output (without echo/prompt)."""
        try:
            async with asyncio.timeout(self._timeout):
                return await self._async_run(command)
        except asyncssh.PermissionDenied as err:
            raise DrayTekSshAuthError(str(err)) from err
        except TimeoutError as err:
            raise DrayTekSshError(f"Timeout talking to {self._host}") from err
        except (OSError, asyncssh.Error) as err:
            raise DrayTekSshError(f"SSH error with {self._host}: {err}") from err

    async def _async_run(self, command: str) -> str:
        async with asyncssh.connect(
            self._host,
            port=self._port,
            username=self._username,
            password=self._password,
            # The Vigor uses a self-generated host key; this is a LAN device.
            known_hosts=None,
            client_keys=None,
            agent_path=None,
            preferred_auth=("password", "keyboard-interactive"),
        ) as conn:
            # Wide terminal so long lines are not wrapped.
            process = await conn.create_process(
                term_type="vt100", term_size=(250, 100), encoding="utf-8"
            )
            try:
                await self._async_login(process)
                process.stdin.write(f"{command}\n")
                output = await self._async_read_until(process, _PROMPT_RE)
                process.stdin.write("quit\n")
            finally:
                process.close()
        # Drop the echoed command line and the trailing prompt.
        lines = output.split("\n")
        if lines and command in lines[0]:
            lines = lines[1:]
        if lines and _PROMPT_RE.search("\n" + lines[-1]):
            lines = lines[:-1]
        return "\n".join(lines)

    async def _async_login(self, process: asyncssh.SSHClientProcess) -> None:
        """Handle the CLI's own Username/Password prompt (if any) until the prompt."""
        sent_user = sent_password = False
        for _ in range(4):
            text = await self._async_read_until(
                process, _USERNAME_RE, _PASSWORD_RE, _PROMPT_RE
            )
            if _PROMPT_RE.search(text):
                return
            if _USERNAME_RE.search(text):
                if sent_user:
                    raise DrayTekSshAuthError("CLI login rejected")
                process.stdin.write(f"{self._username}\n")
                sent_user = True
            elif _PASSWORD_RE.search(text):
                if sent_password:
                    raise DrayTekSshAuthError("CLI password rejected")
                process.stdin.write(f"{self._password}\n")
                sent_password = True
        raise DrayTekSshError("No CLI prompt after login")

    @staticmethod
    async def _async_read_until(
        process: asyncssh.SSHClientProcess, *patterns: re.Pattern[str]
    ) -> str:
        """Read stdout until one of the patterns matches the end of the buffer."""
        buffer = ""
        while True:
            chunk = await process.stdout.read(4096)
            if not chunk:
                raise DrayTekSshError(f"Connection closed, last output: {buffer!r}")
            buffer += _ANSI_RE.sub("", chunk)
            if any(p.search(buffer) for p in patterns):
                return buffer
