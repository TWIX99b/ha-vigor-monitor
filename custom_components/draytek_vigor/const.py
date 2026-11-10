"""Constants for the DrayTek Vigor integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "draytek_vigor"
MANUFACTURER: Final = "DrayTek"

CONF_COMMUNITY: Final = "community"
CONF_INTERFACE_INDEX: Final = "interface_index"

DEFAULT_PORT: Final = 161
DEFAULT_COMMUNITY: Final = "public"
DEFAULT_SCAN_INTERVAL: Final = 30
MIN_SCAN_INTERVAL: Final = 10
MAX_SCAN_INTERVAL: Final = 600

# Highest interface index probed when discovering interfaces.
MAX_INTERFACE_INDEX: Final = 32

# DrayTek enterprise OID prefix (sysObjectID of every Vigor).
DRAYTEK_ENTERPRISE_OID: Final = "1.3.6.1.4.1.7367"

# --- SNMPv2-MIB ---
OID_SYS_DESCR: Final = "1.3.6.1.2.1.1.1.0"
OID_SYS_OBJECT_ID: Final = "1.3.6.1.2.1.1.2.0"
OID_SYS_UPTIME: Final = "1.3.6.1.2.1.1.3.0"

# --- DrayTek private MIB ---
OID_MEMORY_USAGE: Final = "1.3.6.1.4.1.7367.3.7.0"

# --- IF-MIB (suffix: .<ifIndex>) ---
OID_IF_DESCR: Final = "1.3.6.1.2.1.2.2.1.2"
OID_IF_OPER_STATUS: Final = "1.3.6.1.2.1.2.2.1.8"
OID_IF_IN_OCTETS: Final = "1.3.6.1.2.1.2.2.1.10"
OID_IF_OUT_OCTETS: Final = "1.3.6.1.2.1.2.2.1.16"
OID_IF_HC_IN_OCTETS: Final = "1.3.6.1.2.1.31.1.1.1.6"
OID_IF_HC_OUT_OCTETS: Final = "1.3.6.1.2.1.31.1.1.1.10"

# Interface names that usually carry the xDSL WAN link, in order of preference.
# DrayOS 5 (Linux based, e.g. Vigor167): "ptm0"; DrayOS 4: "VDSL" / "ADSL" / "WAN".
PREFERRED_INTERFACE_HINTS: Final = ("ptm0", "ptm", "vdsl", "adsl", "dsl", "wan")

# IF-MIB ifOperStatus value for "up".
IF_OPER_STATUS_UP: Final = 1
