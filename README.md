# DrayTek Vigor for Home Assistant

Local SNMP (+ optional SSH) integration for DrayTek Vigor DSL modems/routers – set up entirely in the UI, no YAML.
Developed and tested with a **Vigor167 on DrayOS 5 (firmware 5.2.9)** in modem (bridge) mode.

## Features

One device per Vigor with these entities:

| Entity | Description |
|---|---|
| Connection | DSL/WAN link up/down (IF-MIB `ifOperStatus`) |
| Download / Upload | Current throughput in Mbit/s, calculated from the interface counters |
| Data received / sent | Interface byte counters (`total_increasing`, usable in statistics) |
| Memory usage | DrayTek private MIB (only created if the device reports it) |
| Online since | Boot time derived from `sysUpTime` |

Model and firmware version are shown in the device info.

### Optional: DSL line values via SSH (DrayOS 5)

When an SSH user is entered under *Configure*, these entities are added (read from the CLI command
`exec dslinfo`, every 5 minutes by default):

| Entity | Description |
|---|---|
| Sync rate download / upload | DSL line rate (stored in kbit/s, shown in Mbit/s) |
| SNR margin download / upload | Signal-to-noise margin in dB |
| DSL status | e.g. `Showtime` |
| DSL line synced since | Timestamp derived from the line uptime |
| DSL mode, DSL firmware | Diagnostic, e.g. `VDSL2 35b` |

If SSH is not reachable, only these entities become unavailable – the SNMP sensors keep working.

## Requirements

- SNMP v2c enabled on the Vigor (read community, default `public`), reachable from Home Assistant on UDP 161.
- Optional for DSL values: SSH enabled on the Vigor (*System Maintenance → Management*), DrayOS 5.

## Installation (HACS)

1. HACS → ⋮ → *Custom repositories* → add `https://github.com/TWIX99b/ha-draytek-vigor`, category *Integration*.
2. Install **DrayTek Vigor**, restart Home Assistant.
3. *Settings → Devices & services → Add integration → DrayTek Vigor*.
4. Enter host and community, then pick the WAN interface (DrayOS 5: usually `ptm0`).

Polling interval, interface and the optional SSH login can be changed later under *Configure*.
The SSH password is stored in the Home Assistant config entry like any other integration credential.

## Notes

- **DrayOS 5 counters are 32 bit**, even on the 64-bit `ifHC*` OIDs. The integration handles the wrap
  when calculating throughput; for the byte counters Home Assistant treats the wrap as a meter reset.
- **Sync rate and SNR** are not exposed via SNMP on DrayOS 5 (the classic ADSL-LINE-MIB /
  VDSL2-LINE-MIB OIDs return nothing), hence the optional SSH part.
- Other models: please open an issue and attach the integration's diagnostics download.

## License

MIT
