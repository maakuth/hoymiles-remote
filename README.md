# Hoymiles BESS Remote Control

A Python bridge to control Hoymiles Hybrid Inverters (BESS) via MQTT, designed for easy integration with Home Assistant.

## Features
- **Signed Power Control**: Send a single signed integer to control battery power.
  - **Positive**: Force Discharge (power from battery to grid/home).
  - **Negative**: Force Charge (power from grid to battery).
  - **Zero**: Return to "Self-Consumption" (automatic) mode.
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

## Configuration

| Section | Parameter | Description |
|---------|-----------|-------------|
| **mqtt** | `host` | MQTT Broker IP/hostname. |
| | `topic_prefix` | Prefix for MQTT topics (default: `hoymiles`). |
| **dtu** | `host` | IP address of the Hoymiles DTU. |
| | `serial` | Serial number of the DTU. |
| | `inverter_serial`| Serial number of the Hybrid Inverter. |
| **battery**| `max_power` | Maximum power in Watts for percentage calculation. |

## Testing
Run unit tests with:
```bash
python3 tests/test_app.py
```
