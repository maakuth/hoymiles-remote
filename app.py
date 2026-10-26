import asyncio
import json
import logging
import yaml
import paho.mqtt.client as mqtt
from hoymiles_wifi.dtu import DTU
from hoymiles_wifi.hoymiles import BMSWorkingMode

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("hoymiles_remote")
# logging.getLogger("hoymiles_wifi").setLevel(logging.DEBUG)

class HoymilesRemoteApp:
    def __init__(self, config_path):
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.mqtt_config = self.config['mqtt']
        self.dtu_config = self.config['dtu']
        self.battery_config = self.config['battery']
        
        self.topic_prefix = self.mqtt_config.get('topic_prefix', 'hoymiles').strip('/')
        self.device_id = self.mqtt_config.get('device_id', 'hoymiles_remote')
        
        self.command_topic = f"{self.topic_prefix}/battery/set_power"
        self.state_topic = f"{self.topic_prefix}/battery/power_state"
        self.availability_topic = f"{self.topic_prefix}/status"
        
        logger.info(f"Initialized with command topic: {self.command_topic}")

        self.mqtt_client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"{self.device_id}_remote_app"
        )
        if self.mqtt_config.get('user'):
            self.mqtt_client.username_pw_set(self.mqtt_config['user'], self.mqtt_config['password'])
        
        self.mqtt_client.on_connect = self.on_mqtt_connect
        self.mqtt_client.on_message = self.on_mqtt_message
        self.mqtt_client.on_subscribe = self.on_mqtt_subscribe
        self.mqtt_client.on_log = self.on_mqtt_log
        self.mqtt_client.on_disconnect = self.on_mqtt_disconnect
        self.mqtt_client.on_publish = self.on_publish
        
        self.dtu = DTU(self.dtu_config['host'])
        self.loop = None
        self.command_queue = asyncio.Queue()

    def on_mqtt_log(self, client, userdata, level, buf):
        if level == mqtt.LogLevel.LOG_ERR:
            logger.error(f"MQTT Log: {buf}")
        elif level == mqtt.LogLevel.LOG_WARNING:
            logger.warning(f"MQTT Log: {buf}")
        elif level == mqtt.LogLevel.LOG_NOTICE or level == mqtt.LogLevel.LOG_INFO:
            logger.info(f"MQTT Log: {buf}")
        else:
            logger.debug(f"MQTT Log: {buf}")

    def on_mqtt_disconnect(self, client, userdata, flags, rc, properties=None):
        logger.warning(f"Disconnected from MQTT broker with rc: {rc}")

    def on_mqtt_subscribe(self, client, userdata, mid, reason_codes, properties=None):
        logger.info(f"Subscribed successfully (mid: {mid}, reason_codes: {reason_codes})")

    def on_publish(self, client, userdata, mid, reason_code=None, properties=None):
        logger.debug(f"Message published (mid: {mid})")

    def on_mqtt_connect(self, client, userdata, flags, rc, properties=None):
        logger.info(f"MQTT connected with rc: {rc}")
        if rc == 0:
            logger.info("Subscribing to everything (#) for diagnostics...")
            client.subscribe("#")
            
            # Publish discovery first
            self.publish_discovery()
            
            # Online status
            client.publish(self.availability_topic, "online", retain=True)
            
            # SELF-TEST: Delayed slightly to ensure subscription is active
            if self.loop:
                self.loop.call_later(2, lambda: client.publish(self.command_topic, "888"))
        else:
            logger.error(f"Failed to connect, rc {rc}")

    def on_mqtt_message(self, client, userdata, msg):
        try:
            payload = msg.payload.decode(errors='replace').strip()
            # Only log interesting topics to avoid spam, but log ALL hoymiles traffic
            if "hoymiles" in msg.topic or msg.topic == self.command_topic:
                logger.info(f"MQTT RECV: Topic=[{msg.topic}] Payload=[{payload}]")
            else:
                logger.debug(f"MQTT RECV: Topic=[{msg.topic}] Payload=[{payload}]")
            
            if msg.topic != self.command_topic:
                return

            logger.info(f"!!! MATCH !!! Topic: {msg.topic}, Value: {payload}")
            try:
                watts = int(float(payload))
                if self.loop:
                    self.loop.call_soon_threadsafe(self.command_queue.put_nowait, watts)
            except ValueError:
                logger.error(f"Non-numeric payload: {payload}")
        except Exception as e:
            logger.error(f"Msg handler error: {e}")

    def publish_discovery(self):
        # Use a new discovery object ID to force HA to re-create
        discovery_topic = f"homeassistant/number/{self.device_id}_ctrl/config"
        max_p = self.battery_config['max_power']
        
        payload = {
            "name": "Hoymiles Power Control v5",
            "unique_id": f"{self.device_id}_pwr_v5",
            "command_topic": self.command_topic,
            "state_topic": self.state_topic,
            "availability_topic": self.availability_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
            "unit_of_measurement": "W",
            "min": -max_p,
            "max": max_p,
            "step": 1,
            "optimistic": True,
            "device": {
                "identifiers": [f"{self.device_id}_hw"],
                "name": "Hoymiles Remote Bridge",
                "manufacturer": "Gemini CLI",
                "model": "MQTT-Inverter-Bridge"
            }
        }
        logger.info(f"Publishing Discovery v5 to {discovery_topic}")
        self.mqtt_client.publish(discovery_topic, json.dumps(payload), retain=True)
        self.mqtt_client.publish(self.state_topic, "0", retain=True)

    async def process_commands(self):
        logger.info("Command processor started and waiting for commands...")
        while True:
            try:
                watts = await asyncio.wait_for(self.command_queue.get(), timeout=30.0)
                await self.handle_power_command(watts)
                self.command_queue.task_done()
            except asyncio.TimeoutError:
                logger.info("Heartbeat: App is alive and waiting for MQTT messages...")
            except Exception as e:
                logger.error(f"Error in command loop: {e}")

    async def handle_power_command(self, watts):
        max_p = self.battery_config['max_power']
        percentage = min(100, max(0, int(abs(watts) / max_p * 100)))
        
        if watts > 0:
            mode = BMSWorkingMode.FORCED_DISCHARGE
            logger.info(f"Setting mode to FORCED_DISCHARGE at {percentage}% ({watts}W)")
        elif watts < 0:
            mode = BMSWorkingMode.FORCED_CHARGING
            logger.info(f"Setting mode to FORCED_CHARGING at {percentage}% ({abs(watts)}W)")
        else:
            mode = BMSWorkingMode.FORCED_DISCHARGE
            percentage = 0
            logger.info(f"Setting mode to FORCED_DISCHARGE (0W)")

        # Use host and inverter serial from config
        dtu_host = str(self.dtu_config.get('host', '')).strip()
        inv_sn = int(self.dtu_config.get('inverter_serial', 0))
        dtu_sn = int(self.dtu_config.get('serial', 0))
        
        if not dtu_host or not inv_sn:
            logger.error("DTU host or Inverter serial missing in config!")
            return

        # Import the same function the CLI uses
        try:
            from hoymiles_wifi.__main__ import async_set_energy_storage_working_mode as set_mode_cli
        except ImportError:
            logger.error("Could not import async_set_energy_storage_working_mode from hoymiles_wifi.__main__")
            return

        # Create a fresh DTU instance like the CLI does for every command
        logger.info(f"Connecting to DTU at {dtu_host}...")
        dtu = DTU(dtu_host, timeout=15)
        
        try:
            # This library function handles the gateway info and registry fetch internally
            result = await set_mode_cli(
                dtu,
                bms_working_mode=mode,
                dtu_serial_number=dtu_sn,
                inverter_serial_number=inv_sn,
                interactive_mode=False,
                rev_soc=self.battery_config.get('rev_soc', 10),
                max_power=percentage,
                peak_soc=self.battery_config.get('peak_soc', 100)
            )
            
            if result:
                logger.info("Inverter Command successful (via CLI logic)")
                self.mqtt_client.publish(self.state_topic, str(watts), retain=True)
            else:
                logger.error("Inverter Command failed (CLI logic returned None)")
        except Exception as e:
            logger.error(f"Exception during inverter command: {e}")

    async def run(self):
        self.loop = asyncio.get_running_loop()
        self.mqtt_client.connect(self.mqtt_config['host'], self.mqtt_config['port'], 60)
        self.mqtt_client.loop_start()
        
        try:
            await self.process_commands()
        finally:
            self.mqtt_client.publish(self.availability_topic, "offline", retain=True)
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()

if __name__ == "__main__":
    app = HoymilesRemoteApp("config.yaml")
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        pass
