# DrayTek Vigor for Home Assistant

Local SNMP integration for DrayTek Vigor DSL modems/routers – set up entirely in the UI, no YAML.
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

## Requirements

- SNMP v2c enabled on the Vigor (read community, default `public`), reachable from Home Assistant on UDP 161.

## Installation (HACS)

1. HACS → ⋮ → *Custom repositories* → add `https://github.com/TWIX99b/ha-draytek-vigor`, category *Integration*.
2. Install **DrayTek Vigor**, restart Home Assistant.
3. *Settings → Devices & services → Add integration → DrayTek Vigor*.
4. Enter host and community, then pick the WAN interface (DrayOS 5: usually `ptm0`).

Polling interval and interface can be changed later under *Configure*.

## Notes

- **DrayOS 5 counters are 32 bit**, even on the 64-bit `ifHC*` OIDs. The integration handles the wrap
  when calculating throughput; for the byte counters Home Assistant treats the wrap as a meter reset.
- **Sync rate, SNR, attenuation** are not exposed via SNMP on DrayOS 5 (the classic ADSL-LINE-MIB /
  VDSL2-LINE-MIB OIDs return nothing). Planned via SSH (`vdsl status`).
- Other models: please open an issue and attach the integration's diagnostics download.

## License

MIT
