import unittest
from unittest.mock import MagicMock, AsyncMock
import asyncio
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import HoymilesRemoteApp
from hoymiles_wifi.hoymiles import BMSWorkingMode

class TestHoymilesRemote(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Create a dummy config
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
"""
        with open("test_config.yaml", "w") as f:
            f.write(self.config_content)
        
        self.app = HoymilesRemoteApp("test_config.yaml")
        self.app.dtu = AsyncMock()
        self.app.mqtt_client = MagicMock()

    async def test_handle_power_command_discharge(self):
        # 1000W discharge (50% of 2000W)
        await self.app.handle_power_command(1000)
        self.app.dtu.async_set_energy_storage_working_mode.assert_called_with(
            dtu_serial_number=123,
            inverter_serial_number=456,
            bms_working_mode=BMSWorkingMode.FORCED_DISCHARGE,
            max_power=50
        )

    async def test_handle_power_command_charge(self):
        # -500W charge (25% of 2000W)
        await self.app.handle_power_command(-500)
        self.app.dtu.async_set_energy_storage_working_mode.assert_called_with(
            dtu_serial_number=123,
            inverter_serial_number=456,
            bms_working_mode=BMSWorkingMode.FORCED_CHARGING,
            max_power=25
        )

    async def test_handle_power_command_zero(self):
        # 0W (Self-Use)
        await self.app.handle_power_command(0)
        self.app.dtu.async_set_energy_storage_working_mode.assert_called_with(
            dtu_serial_number=123,
            inverter_serial_number=456,
            bms_working_mode=BMSWorkingMode.SELF_USE,
            max_power=0
        )

if __name__ == "__main__":
    unittest.main()
