"""Constants for the DrayTek Vigor Monitor integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "vigor_monitor"
MANUFACTURER: Final = "DrayTek"

CONF_COMMUNITY: Final = "community"
CONF_INTERFACE_INDEX: Final = "interface_index"
CONF_WEB_USERNAME: Final = "web_username"
CONF_WEB_PASSWORD: Final = "web_password"
CONF_WEB_SSL: Final = "web_ssl"
CONF_DSL_SCAN_INTERVAL: Final = "dsl_scan_interval"

DEFAULT_PORT: Final = 161
DEFAULT_COMMUNITY: Final = "public"
DEFAULT_WEB_USERNAME: Final = "admin"
DEFAULT_SCAN_INTERVAL: Final = 30
MIN_SCAN_INTERVAL: Final = 10
MAX_SCAN_INTERVAL: Final = 600
DEFAULT_DSL_SCAN_INTERVAL: Final = 60
MIN_DSL_SCAN_INTERVAL: Final = 30
MAX_DSL_SCAN_INTERVAL: Final = 3600

# Highest interface index probed when discovering interfaces.
MAX_INTERFACE_INDEX: Final = 32

# DrayTek enterprise OID prefix (sysObjectID of every Vigor).
DRAYTEK_ENTERPRISE_OID: Final = "1.3.6.1.4.1.7367"

# --- SNMPv2-MIB ---
OID_SYS_DESCR: Final = "1.3.6.1.2.1.1.1.0"
OID_SYS_OBJECT_ID: Final = "1.3.6.1.2.1.1.2.0"
OID_SYS_UPTIME: Final = "1.3.6.1.2.1.1.3.0"

# --- DrayTek private MIB ---
OID_DRAYTEK_MODEL: Final = "1.3.6.1.4.1.7367.3.1.0"
OID_DRAYTEK_FIRMWARE: Final = "1.3.6.1.4.1.7367.3.2.0"
OID_MEMORY_USAGE: Final = "1.3.6.1.4.1.7367.3.7.0"

# --- CPU load: HOST-RESOURCES-MIB hrProcessorLoad (first instance), UCD ssCpuIdle ---
OID_HR_PROCESSOR_LOAD: Final = "1.3.6.1.2.1.25.3.3.1.2"
OID_UCD_CPU_IDLE: Final = "1.3.6.1.4.1.2021.11.11.0"

# --- IF-MIB (suffix: .<ifIndex>) ---
OID_IF_DESCR: Final = "1.3.6.1.2.1.2.2.1.2"
OID_IF_TYPE: Final = "1.3.6.1.2.1.2.2.1.3"
OID_IF_OPER_STATUS: Final = "1.3.6.1.2.1.2.2.1.8"
OID_IF_LAST_CHANGE: Final = "1.3.6.1.2.1.2.2.1.9"
OID_IF_IN_OCTETS: Final = "1.3.6.1.2.1.2.2.1.10"
OID_IF_OUT_OCTETS: Final = "1.3.6.1.2.1.2.2.1.16"
OID_IF_HC_IN_OCTETS: Final = "1.3.6.1.2.1.31.1.1.1.6"
OID_IF_HC_OUT_OCTETS: Final = "1.3.6.1.2.1.31.1.1.1.10"

# ifType values of DSL interfaces: adsl(94), vdsl(97), vdsl2(251).
DSL_IF_TYPES: Final = frozenset({94, 97, 251})

# --- xDSL MIBs (DrayOS 4 devices such as Vigor 130/165/166; empty on DrayOS 5) ---
# ADSL-LINE-MIB current status tables. DrayTek firmware deviates from the MIB:
# the ATU-C table holds the downstream values and the ATU-R table the upstream
# values, and SNR margin / attenuation are reported in whole dB.
OID_ATUC_CURR: Final = "1.3.6.1.2.1.10.94.1.1.2.1"
OID_ATUR_CURR: Final = "1.3.6.1.2.1.10.94.1.1.3.1"
CURR_SNR_MARGIN: Final = 4
CURR_ATTENUATION: Final = 5
CURR_ATTAINABLE_RATE: Final = 8
# VDSL2-LINE-MIB xdsl2ChStatusActDataRate (bit/s), index ifIndex.unit (1 = down, 2 = up).
OID_XDSL2_ACT_DATA_RATE: Final = "1.3.6.1.2.1.10.251.1.2.2.1.2"

# Interface names that usually carry the xDSL WAN link, in order of preference.
# DrayOS 5 (Linux based, e.g. Vigor167): "ptm0"; DrayOS 4: "VDSL" / "ADSL" / "WAN".
PREFERRED_INTERFACE_HINTS: Final = ("ptm0", "ptm", "vdsl", "adsl", "dsl", "wan")

# IF-MIB ifOperStatus value for "up".
IF_OPER_STATUS_UP: Final = 1
