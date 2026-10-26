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

class HoymilesRemoteApp:
    def __init__(self, config_path):
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.mqtt_config = self.config['mqtt']
        self.dtu_config = self.config['dtu']
        self.battery_config = self.config['battery']
        
        self.topic_prefix = self.mqtt_config.get('topic_prefix', 'hoymiles')
        self.device_id = self.mqtt_config.get('device_id', 'hoymiles_remote')
        
        self.command_topic = f"{self.topic_prefix}/battery/set_power"
        self.state_topic = f"{self.topic_prefix}/battery/power_state"
        self.availability_topic = f"{self.topic_prefix}/status"
        
        self.mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        if self.mqtt_config.get('user'):
            self.mqtt_client.username_pw_set(self.mqtt_config['user'], self.mqtt_config['password'])
        
        self.mqtt_client.on_connect = self.on_mqtt_connect
        self.mqtt_client.on_message = self.on_mqtt_message
        self.mqtt_client.on_subscribe = self.on_mqtt_subscribe
        self.mqtt_client.on_log = self.on_mqtt_log
        
        self.dtu = DTU(self.dtu_config['host'])
        self.loop = None
        self.command_queue = asyncio.Queue()

    def on_mqtt_log(self, client, userdata, level, buf):
        if level <= mqtt.LogLevel.LOG_WARNING:
            logger.debug(f"MQTT Log: {buf}")

    def on_mqtt_subscribe(self, client, userdata, mid, reason_codes, properties=None):
        logger.info(f"Subscribed successfully (mid: {mid})")

    def on_mqtt_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            logger.info(f"Connected to MQTT broker with prefix: {self.topic_prefix}")
            # Subscribe to the specific command topic AND a catch-all for the prefix
            client.subscribe(self.command_topic)
            client.subscribe(f"{self.topic_prefix}/#")
            logger.info(f"Subscribed to {self.command_topic} and {self.topic_prefix}/#")
            self.publish_discovery()
            client.publish(self.availability_topic, "online", retain=True)
        else:
            logger.error(f"Failed to connect to MQTT broker, return code {rc}")

    def on_mqtt_message(self, client, userdata, msg):
        logger.info(f"DEBUG: Received MQTT message on topic '{msg.topic}' with payload: {msg.payload}")
        if msg.topic != self.command_topic:
            return

        try:
            payload = msg.payload.decode()
            watts = int(float(payload))
            if self.loop:
                self.loop.call_soon_threadsafe(self.command_queue.put_nowait, watts)
            else:
                logger.error("Event loop not initialized, cannot process command")
        except Exception as e:
            logger.warning(f"Error handling message: {e}")

    def publish_discovery(self):
        # Home Assistant MQTT Discovery for Number entity
        discovery_topic = f"homeassistant/number/{self.device_id}/battery_power/config"
        max_p = self.battery_config['max_power']
        
        payload = {
            "name": "Hoymiles Battery Power",
            "unique_id": f"{self.device_id}_power_ctrl",
            "cmd_t": self.command_topic,
            "stat_t": self.state_topic,
            "avty_t": self.availability_topic,
            "unit_of_meas": "W",
            "min": -max_p,
            "max": max_p,
            "step": 1,
            "device": {
                "identifiers": [self.device_id],
                "name": "Hoymiles Remote",
                "manufacturer": "Gemini CLI"
            }
        }
        logger.info(f"Sending Discovery Payload to {discovery_topic}")
        self.mqtt_client.publish(discovery_topic, json.dumps(payload), retain=True)
        # Publish initial state
        self.mqtt_client.publish(self.state_topic, "0", retain=True)

    async def process_commands(self):
        logger.info("Command processor started and waiting for commands...")
        last_heartbeat = 0
        while True:
            try:
                # Add a timeout to the queue get to allow for a heartbeat
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
            mode = BMSWorkingMode.SELF_USE
            percentage = 0
            logger.info(f"Setting mode to SELF_USE (0W)")

        # Configure DTU with a longer timeout
        self.dtu.timeout = 30 
        
        dtu_sn = None
        # Try to get gateway info with retries
        for attempt in range(3):
            try:
                logger.info(f"Fetching gateway info (attempt {attempt+1}/3)...")
                gateway_info = await self.dtu.async_get_gateway_info()
                if gateway_info:
                    dtu_sn = gateway_info.serial_number
                    logger.info(f"Dynamic gateway SN found: {dtu_sn}")
                    break
            except Exception as e:
                logger.debug(f"Gateway fetch attempt {attempt+1} failed: {e}")
            await asyncio.sleep(1)

        # Fallback to config if dynamic fetch failed
        if dtu_sn is None:
            dtu_sn = int(self.dtu_config.get('serial', 0))
            logger.warning(f"Failed to fetch gateway info, falling back to config SN: {dtu_sn}")

        try:
            result = await self.dtu.async_set_energy_storage_working_mode(
                dtu_serial_number=dtu_sn,
                inverter_serial_number=int(self.dtu_config['inverter_serial']),
                bms_working_mode=mode,
                rev_soc=self.battery_config.get('rev_soc', 10),
                max_power=percentage,
                peak_soc=self.battery_config.get('peak_soc', 100)
            )
            
            if result:
                logger.info(f"Inverter Command successful")
                self.mqtt_client.publish(self.state_topic, str(watts), retain=True)
            else:
                logger.error("Inverter Command failed (no response)")
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
