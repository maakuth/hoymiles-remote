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

    def test_suppress_exceptions_enabled(self):
        """MQTT client should have suppress_exceptions = True to prevent thread death."""
        app = HoymilesRemoteApp("test_config.yaml")
        self.assertTrue(app.mqtt_client.suppress_exceptions)

    def test_check_mqtt_thread_restarts_when_thread_is_none(self):
        """_check_mqtt_thread should restart loop when _thread is None (dead)."""
        self.app.mqtt_client._thread = None
        result = self.app._check_mqtt_thread()
        self.assertTrue(result)
        self.app.mqtt_client.loop_start.assert_called_once()

    def test_check_mqtt_thread_no_action_when_alive(self):
        """_check_mqtt_thread should do nothing when thread is alive."""
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        self.app.mqtt_client._thread = mock_thread
        result = self.app._check_mqtt_thread()
        self.assertFalse(result)
        self.app.mqtt_client.loop_start.assert_not_called()

    def test_check_mqtt_thread_cleans_up_dead_thread(self):
        """_check_mqtt_thread should loop_stop + loop_start when thread exists but is dead."""
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = False
        self.app.mqtt_client._thread = mock_thread
        result = self.app._check_mqtt_thread()
        self.assertTrue(result)
        self.app.mqtt_client.loop_stop.assert_called_once()
        self.app.mqtt_client.loop_start.assert_called_once()

    def test_force_reconnect_stops_and_restarts(self):
        """_force_reconnect should call loop_stop then loop_start."""
        self.app._force_reconnect()
        self.app.mqtt_client.loop_stop.assert_called_once()
        self.app.mqtt_client.loop_start.assert_called_once()

    def test_on_mqtt_message_updates_last_message_time(self):
        """on_mqtt_message should update _last_message_at."""
        self.app._last_message_at = None
        mock_msg = MagicMock()
        mock_msg.topic = self.app.command_topic
        mock_msg.payload = b"1000"
        self.app.on_mqtt_message(self.app.mqtt_client, None, mock_msg)
        self.assertIsNotNone(self.app._last_message_at)

    def test_on_mqtt_connect_resets_last_message_time(self):
        """on_mqtt_connect should set _last_message_at on successful connect."""
        self.app._last_message_at = None
        self.app.on_mqtt_connect(self.app.mqtt_client, None, MagicMock(), 0)
        self.assertIsNotNone(self.app._last_message_at)

    def test_stale_timeout_default(self):
        """Default stale_timeout should be 300 seconds."""
        self.assertEqual(self.app._stale_timeout, 300)

    def test_stale_timeout_from_config(self):
        """stale_timeout should be read from config."""
        config_stale = """
mqtt:
  host: "localhost"
  port: 1883
  topic_prefix: "test"
  stale_timeout: 120
dtu:
  host: "1.1.1.1"
  serial: 123
  inverter_serial: 456
battery:
  max_power: 2000
"""
        with open("test_config_stale.yaml", "w") as f:
            f.write(config_stale)
        app_stale = HoymilesRemoteApp("test_config_stale.yaml")
        self.assertEqual(app_stale._stale_timeout, 120)
        os.remove("test_config_stale.yaml")

    def tearDown(self):
        for f in ("test_config.yaml", "test_config_stale.yaml"):
            if os.path.exists(f):
                os.remove(f)

if __name__ == "__main__":
    unittest.main()