# DrayTek Vigor Monitor for Home Assistant

[![Validate](https://github.com/TWIX99b/ha-vigor-monitor/actions/workflows/validate.yaml/badge.svg)](https://github.com/TWIX99b/ha-vigor-monitor/actions/workflows/validate.yaml)
[![hacs](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)

Local monitoring for DrayTek Vigor DSL modems/routers – **traffic and DSL line values in one
integration**, set up entirely in the UI. Read-only: nothing is ever changed on the device.

Developed and tested with a **Vigor167 on DrayOS 5 (firmware 5.2.9)** in modem (bridge) mode on a
synced VDSL2 35b line. DrayOS 4 devices (Vigor 130/165/166 …) are supported via SNMP.

## What you get

| Entity | Source | Notes |
|---|---|---|
| Connection | SNMP | WAN link up/down |
| Connected since | SNMP | when the WAN link came up (`ifLastChange`) |
| Download / Upload | SNMP | current throughput in Mbit/s |
| Data received / sent | SNMP | byte counters, usable in long-term statistics |
| Online since, CPU load, Memory usage | SNMP | diagnostic; CPU/memory only if the device reports them |
| DSL synced | Web API | on while the line is in showtime |
| Sync rate download / upload | Web API or SNMP¹ | kbit/s, shown in Mbit/s |
| Attainable rate download / upload | Web API or SNMP¹ | |
| SNR margin download / upload | Web API or SNMP¹ | dB |
| Attenuation download / upload | Web API or SNMP¹ | dB |
| DSL status, DSL mode, DSL firmware | Web API | e.g. `SHOWTIME`, `VDSL2 35b` |
| CRC errors, errored / severely errored / unavailable seconds | Web API | near and far end, disabled by default |

¹ DrayOS 5 (Vigor167) does not expose DSL values via SNMP, so they are read from the web interface
(optional web login). DrayOS 4 devices report them via the standard xDSL MIBs; the integration uses
those automatically when they answer.

## Requirements

- **SNMP v2c** enabled on the Vigor (*System Maintenance → SNMP*, read community, default `public`),
  UDP 161 reachable from Home Assistant.
- Optional for the DSL values on DrayOS 5: the **web login** of the Vigor (usually `admin`).
  The integration logs in like the browser does (`/cgi-bin/webproc.cgi`), keeps one session open
  and logs out when Home Assistant stops.

## Installation

1. HACS → ⋮ → *Custom repositories* → `https://github.com/TWIX99b/ha-vigor-monitor`, category
   *Integration*.
2. Install **DrayTek Vigor Monitor**, restart Home Assistant.
3. *Settings → Devices & services → Add integration → DrayTek Vigor Monitor*:
   1. host and SNMP community,
   2. WAN interface (DrayOS 5: usually `ptm0`),
   3. optionally the web login for the DSL values (can be added later under *Configure*).

Polling intervals (SNMP 30 s, DSL 60 s), the interface and the web login can be changed under
*Configure*. If the web login is rejected repeatedly, Home Assistant asks for new credentials.

## Notes

- **DrayOS 5 counters are 32 bit**, even on the 64-bit `ifHC*` OIDs. Throughput handles the wrap;
  the byte counters use `total_increasing`, so statistics stay correct across wraps.
- The Vigor only allows a few parallel web sessions. The integration keeps a single one; if you are
  locked out of the web UI, lower the DSL polling or remove the web login.
- *Force HTTPS* on the Vigor: enable the HTTPS option of the web login (self-signed certificates are
  accepted).
- Other models or odd values: open an issue and attach the integration's **diagnostics** download
  (credentials are redacted; it contains the raw DSL status block).

## Credits

Protocol knowledge from [draytek_exporter](https://github.com/SuperQ/draytek_exporter),
[ha-draytek](https://github.com/marcfrederick/ha-draytek) and
[ha-draytek-vigor](https://github.com/skornehl/ha-draytek-vigor) – see [NOTICE](NOTICE).
Not affiliated with DrayTek.

## License

MIT
