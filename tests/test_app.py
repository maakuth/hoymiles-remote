import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import HoymilesRemoteApp
from hoymiles_wifi.hoymiles import BMSWorkingMode

class TestHoymilesRemote(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config_content = """
mqtt:
  host: "localhost"
  port: 1883
  topic_prefix: "test"
dtu:
  host: "1.1.1.1"
  serial: 123
  inverter_serial: 456
battery:
  max_power: 2000
  rev_soc: 10
  charge_soc: 90
"""
        with open("test_config.yaml", "w") as f:
            f.write(self.config_content)
        
        self.app = HoymilesRemoteApp("test_config.yaml")
        self.app.mqtt_client = MagicMock()

    async def test_handle_power_command_discharge_uses_rev_soc(self):
        with patch("hoymiles_wifi.__main__.async_set_energy_storage_working_mode", new_callable=AsyncMock) as mock_set_mode:
            mock_set_mode.return_value = True
            await self.app.handle_power_command(1000)
            mock_set_mode.assert_called_with(
                unittest.mock.ANY,
                inverter_serial_number=456,
                bms_working_mode=BMSWorkingMode.FORCED_DISCHARGE,
                max_power=50,
                interactive_mode=False,
                rev_soc=10,
            )

    async def test_handle_power_command_charge_uses_charge_soc_as_rev_soc(self):
        with patch("hoymiles_wifi.__main__.async_set_energy_storage_working_mode", new_callable=AsyncMock) as mock_set_mode:
            mock_set_mode.return_value = True
            await self.app.handle_power_command(-500)
            mock_set_mode.assert_called_with(
                unittest.mock.ANY,
                inverter_serial_number=456,
                bms_working_mode=BMSWorkingMode.FORCED_CHARGING,
                max_power=25,
                interactive_mode=False,
                rev_soc=90,
            )

    async def test_handle_power_command_zero_uses_rev_soc(self):
        with patch("hoymiles_wifi.__main__.async_set_energy_storage_working_mode", new_callable=AsyncMock) as mock_set_mode:
            mock_set_mode.return_value = True
            await self.app.handle_power_command(0)
            mock_set_mode.assert_called_with(
                unittest.mock.ANY,
                inverter_serial_number=456,
                bms_working_mode=BMSWorkingMode.FORCED_DISCHARGE,
                max_power=0,
                interactive_mode=False,
                rev_soc=10,
            )

    async def test_handle_power_command_charge_default_soc(self):
        config_no_soc = """
mqtt:
  host: "localhost"
  port: 1883
  topic_prefix: "test"
dtu:
  host: "1.1.1.1"
  serial: 123
  inverter_serial: 456
battery:
  max_power: 2000
"""
        with open("test_config2.yaml", "w") as f:
            f.write(config_no_soc)
        app2 = HoymilesRemoteApp("test_config2.yaml")
        app2.mqtt_client = MagicMock()
        with patch("hoymiles_wifi.__main__.async_set_energy_storage_working_mode", new_callable=AsyncMock) as mock_set_mode:
            mock_set_mode.return_value = True
            await app2.handle_power_command(-500)
            mock_set_mode.assert_called_with(
                unittest.mock.ANY,
                inverter_serial_number=456,
                bms_working_mode=BMSWorkingMode.FORCED_CHARGING,
                max_power=25,
                interactive_mode=False,
                rev_soc=90,
            )
        os.remove("test_config2.yaml")

    async def test_handle_power_command_discharge_default_soc(self):
        config_no_soc = """
mqtt:
  host: "localhost"
  port: 1883
  topic_prefix: "test"
dtu:
  host: "1.1.1.1"
  serial: 123
  inverter_serial: 456
battery:
  max_power: 2000
"""
        with open("test_config3.yaml", "w") as f:
            f.write(config_no_soc)
        app3 = HoymilesRemoteApp("test_config3.yaml")
        app3.mqtt_client = MagicMock()
        with patch("hoymiles_wifi.__main__.async_set_energy_storage_working_mode", new_callable=AsyncMock) as mock_set_mode:
            mock_set_mode.return_value = True
            await app3.handle_power_command(1000)
            mock_set_mode.assert_called_with(
                unittest.mock.ANY,
                inverter_serial_number=456,
                bms_working_mode=BMSWorkingMode.FORCED_DISCHARGE,
                max_power=50,
                interactive_mode=False,
                rev_soc=10,
            )
        os.remove("test_config3.yaml")

    def tearDown(self):
        if os.path.exists("test_config.yaml"):
            os.remove("test_config.yaml")

if __name__ == "__main__":
    unittest.main()