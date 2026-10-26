# Hoymiles BESS Remote Control

A Python bridge to control Hoymiles Hybrid Inverters (BESS) via MQTT, designed for easy integration with Home Assistant.
This has been developed with AI tools such as Gemini CLI and OpenCode. The documentation seems sloppy at times, but it is tested with a real inverter and it is in continuous production use.

## Features
- **Signed Power Control**: Send a single signed integer to control battery power.
  - **Positive**: Force Discharge (power from battery to grid/home).
  - **Negative**: Force Charge (power from grid to battery).
  - **Zero**: Set fixed/manual control to 0 W.
- **Operating Mode**: Select `self_consumption` for the inverter's native
  Self Consumption mode, or `fixed` to enable manual signed-power control.
- **Home Assistant Discovery**: Automatically creates a `number` entity in Home Assistant via MQTT Discovery.
- **Local Control**: Uses the `hoymiles-wifi` library to communicate directly with the DTU over the local network.

## Installation

1. Ensure you have a virtual environment set up and dependencies installed:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Copy the example configuration:
   ```bash
   cp config.yaml.example config.yaml
   ```

3. Edit `config.yaml` with your DTU/Inverter serial numbers, IP address, and MQTT broker details.

## Usage

Run the application:
```bash
python3 app.py
```

## MQTT controls

With the default topic prefix, publish one of the following:

| Topic | Payload | Result |
|---|---|---|
| `hoymiles/battery/set_mode` | `self_consumption` | Sets native Hoymiles Self Consumption mode (`SELF_USE = 1`). |
| `hoymiles/battery/set_mode` | `fixed` | Enables fixed/manual control at 0 W; then set a power value. |
| `hoymiles/battery/set_power` | signed watts | A positive value discharges and a negative value charges. |

The bridge publishes the last successful requested mode to
`hoymiles/battery/mode_state` and the requested power to
`hoymiles/battery/power_state`. These are command states, not live inverter
readbacks. On startup, the mode defaults to `fixed` for backward compatibility
with the existing signed-power-only interface.

## Configuration

| Section | Parameter | Description |
|---------|-----------|-------------|
| **mqtt** | `host` | MQTT Broker IP/hostname. |
| | `topic_prefix` | Prefix for MQTT topics (default: `hoymiles`). |
| **dtu** | `host` | IP address of the Hoymiles DTU. |
| | `serial` | Serial number of the DTU. TODO: Check if this is used, likely it's not |
| | `inverter_serial`| Serial number of the Hybrid Inverter. |
| **battery**| `max_power` | Maximum power in Watts for percentage calculation. |

## Testing
Run unit tests with:
```bash
python3 tests/test_app.py
```
