#!/usr/bin/env python3
"""
MQTT Manager - Handles Home Assistant MQTT integration
Includes auto-discovery and clean data publishing
"""

import json
import logging
from typing import Dict, Any, Optional
import time

logger = logging.getLogger(__name__)

class MQTTManager:
    """Manages MQTT publishing to Home Assistant"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.client = None
        self.connected = False
        self.base_topic = config.get('mqtt', {}).get('base_topic', 'airsensor')
        self.discovery_prefix = config.get('mqtt', {}).get('discovery_prefix', 'homeassistant')
        self.device_info = config.get('mqtt', {}).get('device', {})
        self._initialize()

    def _initialize(self):
        """Initialize MQTT client"""
        try:
            import paho.mqtt.client as mqtt

            logger.info("Initializing MQTT client...")

            self.client = mqtt.Client()

            # Set callbacks
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect

            # Set credentials if provided
            username = self.config['mqtt'].get('username')
            password = self.config['mqtt'].get('password')
            if username and password:
                self.client.username_pw_set(username, password)

            # Connect
            broker = self.config.get('mqtt', {}).get('broker', 'homeassistant.local')
            port = self.config.get('mqtt', {}).get('port', 1883)

            logger.info(f"Connecting to MQTT broker at {broker}:{port}")
            
            try:
                self.client.connect(broker, port, 60)
            except OSError as e:
                # OSError includes socket.gaierror (name resolution) and other network errors
                if "Name or service not known" in str(e) or "nodename nor servname provided" in str(e):
                    logger.error(f"Failed to resolve MQTT broker hostname '{broker}'")
                    logger.error("Check that the broker hostname/IP is correct in config.yaml")
                elif "Connection refused" in str(e):
                    logger.error(f"MQTT broker at {broker}:{port} refused the connection")
                    logger.error("Check if MQTT broker is running")
                elif "No route to host" in str(e):
                    logger.error(f"No network route to MQTT broker at {broker}")
                    logger.error("Check your network connection, verify the broker is on the same network and accessible")
                else:
                    logger.error(f"Network error connecting to MQTT broker at {broker}:{port}: {e}")
                logger.warning("MQTT will be disabled. Sensor will continue running without MQTT.")
                self.client = None
                return
            except (ConnectionRefusedError, TimeoutError) as e:
                logger.error(f"Connection to MQTT broker at {broker}:{port} failed: {e}")
                logger.error("→ Check if MQTT broker is running and accessible")
                logger.warning("MQTT will be disabled. Sensor will continue running without MQTT.")
                self.client = None
                return

            # Start loop in background
            self.client.loop_start()

            # Wait for connection
            timeout = 5
            start = time.time()
            while not self.connected and (time.time() - start) < timeout:
                time.sleep(0.1)

            if self.connected:
                logger.info("MQTT connected successfully")

                # Send discovery messages if enabled
                if self.config.get('mqtt', {}).get('discovery', True):
                    self._send_discovery()
            else:
                logger.error("MQTT failed to connect after retrying.")
                logger.warning("MQTT will be disabled. Sensor will continue running without MQTT.")
                self.client.loop_stop()
                self.client = None

        except ImportError:
            logger.error("paho-mqtt library not found. Install with: pip3 install paho-mqtt")
            logger.warning("MQTT will be disabled. Sensor will continue running without MQTT.")
            self.client = None
        except Exception as e:
            logger.error(f"Unexpected error initializing MQTT: {e}")
            logger.warning("MQTT will be disabled. Sensor will continue running without MQTT.")
            if self.client:
                try:
                    self.client.loop_stop()
                except:
                    pass
            self.client = None

    def _on_connect(self, client, userdata, flags, rc):
        """Callback when connected to MQTT broker"""
        if rc == 0:
            self.connected = True
            logger.info("Connected to MQTT broker")
        else:
            # Provide friendly error messages for connection failures
            error_messages = {
                1: "Connection refused - incorrect protocol version. Check your MQTT broker version.",
                2: "Connection refused - invalid client identifier. Try changing the client ID.",
                3: "Connection refused - server unavailable. MQTT broker may be down or not accepting connections.",
                4: "Connection refused - bad username or password. Check your MQTT credentials in config.yaml.",
                5: "Connection refused - not authorized. Your MQTT user may not have permission to connect. Check Home Assistant MQTT user settings.",
            }
            
            error_msg = error_messages.get(rc, f"Connection failed with unknown code {rc}")
            logger.error(f"MQTT connection failed: {error_msg}")
            
            # Provide specific help for common issues
            if rc == 4 or rc == 5:
                logger.error("Check your MQTT username and password in config.yaml")
            elif rc == 3:
                broker = self.config.get('mqtt', {}).get('broker', 'homeassistant.local')
                logger.error(f"Check if MQTT broker is running at {broker}")

    def _on_disconnect(self, client, userdata, rc):
        """Callback when disconnected from MQTT broker"""
        self.connected = False
        if rc != 0:
            # Provide friendly disconnect messages
            disconnect_messages = {
                1: "Disconnected - incorrect protocol version",
                2: "Disconnected - invalid client identifier",
                3: "Disconnected - server unavailable",
                4: "Disconnected - bad username or password",
                5: "Disconnected - not authorized",
                7: "Disconnected - connection lost (network issue or broker restart)",
            }
            
            error_msg = disconnect_messages.get(rc, f"Unexpected disconnection (code {rc})")
            logger.warning(f"MQTT {error_msg}")
            
            if rc == 7:
                logger.info("Will attempt to reconnect automatically...")

    def _send_discovery(self):
        """Send Home Assistant MQTT discovery messages"""
        logger.info("Sending Home Assistant discovery messages...")

        device = {
            "identifiers": [self.device_info.get('identifier', 'airsensor_01')],
            "name": self.device_info.get('name', 'Air Quality Sensor'),
            "manufacturer": self.device_info.get('manufacturer', 'artyzan.net'),
            }

        # Check config of optional sensors
        self.scd41_enabled = self.config['scd41']['enabled']
        self.pms5003_enabled = self.config['pms5003']['enabled']

        sensors = []

        # SCD41 CO2 sensor (only if enabled)
        if self.scd41_enabled:
            sensors.append({
                "name": "CO2",
                "unique_id": "airsensor_co2",
                "state_topic": f"{self.base_topic}/co2",
                "unit_of_measurement": "ppm",
                "device_class": "carbon_dioxide",
                "state_class": "measurement",
                "icon": "mdi:molecule-co2"
            })

        # Temperature and Humidity - based on mode
        if not self.scd41_enabled:
            # Only BME280 temperature and humidity
            sensors.extend([
                {
                    "name": "Temperature",
                    "unique_id": "airsensor_temperature",
                    "state_topic": f"{self.base_topic}/temperature",
                    "unit_of_measurement": "°C",
                    "device_class": "temperature",
                    "state_class": "measurement"
                },
                {
                    "name": "Humidity",
                    "unique_id": "airsensor_humidity",
                    "state_topic": f"{self.base_topic}/humidity",
                    "unit_of_measurement": "%",
                    "device_class": "humidity",
                    "state_class": "measurement"
                }
            ])

        else:
            # SCD41 is enabled, use as primary, BME280 as diagnostic
            sensors.extend([
                {
                    "name": "Temperature",
                    "unique_id": "airsensor_temperature",
                    "state_topic": f"{self.base_topic}/temperature",
                    "unit_of_measurement": "°C",
                    "device_class": "temperature",
                    "state_class": "measurement"
                },
                {
                    "name": "Humidity",
                    "unique_id": "airsensor_humidity",
                    "state_topic": f"{self.base_topic}/humidity",
                    "unit_of_measurement": "%",
                    "device_class": "humidity",
                    "state_class": "measurement"
                },
                {
                    "name": "Temperature (BME280)",
                    "unique_id": "airsensor_temp_diagnostic",
                    "state_topic": f"{self.base_topic}/temperature_diagnostic",
                    "unit_of_measurement": "°C",
                    "device_class": "temperature",
                    "state_class": "measurement",
                    "entity_category": "diagnostic"
                },
                {
                    "name": "Humidity (BME280)",
                    "unique_id": "airsensor_humidity_diagnostic",
                    "state_topic": f"{self.base_topic}/humidity_diagnostic",
                    "unit_of_measurement": "%",
                    "device_class": "humidity",
                    "state_class": "measurement",
                    "entity_category": "diagnostic"
                }
            ])

        # Pressure (always from Enviro+)
        sensors.append({
            "name": "Pressure",
            "unique_id": "airsensor_pressure",
            "state_topic": f"{self.base_topic}/pressure",
            "unit_of_measurement": "hPa",
            "device_class": "pressure",
            "state_class": "measurement"
        })

        # Particulate Matter sensors (only if PM sensor enabled - will be checked in publish)

        if self.pms5003_enabled:
            sensors.extend([
                {
                    "name": "PM1",
                    "unique_id": "airsensor_pm1",
                    "state_topic": f"{self.base_topic}/pm1",
                    "unit_of_measurement": "μg/m³",
                    "device_class": "pm1",
                    "state_class": "measurement",
                    "icon": "mdi:smoke"
                },
                {
                    "name": "PM2.5",
                    "unique_id": "airsensor_pm25",
                    "state_topic": f"{self.base_topic}/pm25",
                    "unit_of_measurement": "μg/m³",
                    "device_class": "pm25",
                    "state_class": "measurement",
                    "icon": "mdi:smoke"
                },
                {
                    "name": "PM10",
                    "unique_id": "airsensor_pm10",
                    "state_topic": f"{self.base_topic}/pm10",
                    "unit_of_measurement": "μg/m³",
                    "device_class": "pm10",
                    "state_class": "measurement",
                    "icon": "mdi:smoke"
                }
            ])

        # Light sensor
        sensors.append({
            "name": "Light Level",
            "unique_id": "airsensor_lux",
            "state_topic": f"{self.base_topic}/lux",
            "unit_of_measurement": "lx",
            "device_class": "illuminance",
            "state_class": "measurement"
        })

        # MICS6814
        sensors.append({
            "name": "Oxidising Gases",
            "unique_id": "airsensor_oxi",
            "state_topic": f"{self.base_topic}/oxi",
            "unit_of_measurement": "Ω",
            "state_class": "measurement",
            "icon": "mdi:molecule"
        })

        sensors.append({
            "name": "Reducing Gases",
            "unique_id": "airsensor_red",
            "state_topic": f"{self.base_topic}/red",
            "unit_of_measurement": "Ω",
            "state_class": "measurement",
            "icon": "mdi:molecule"
        })

        sensors.append({
            "name": "Ammonia",
            "unique_id": "airsensor_nh3",
            "state_topic": f"{self.base_topic}/nh3",
            "unit_of_measurement": "Ω",
            "state_class": "measurement",
            "icon": "mdi:molecule"
        })

        # Send discovery for each sensor
        for sensor in sensors:
            sensor['device'] = device

            topic = f"{self.discovery_prefix}/sensor/{sensor['unique_id']}/config"
            payload = json.dumps(sensor)

            self.client.publish(topic, payload, retain=True)
            logger.debug(f"Sent discovery: {sensor['name']}")

        logger.info(f"Sent {len(sensors)} discovery messages")

    def publish_data(self, data: Dict[str, Any]):
        """Publish sensor data to MQTT"""
        if not self.client or not self.connected:
            logger.debug("Not connected to MQTT broker - skipping publish")
            return

        try:

            # CO2 (only if SCD41 enabled and available)
            scd41 = data.get('scd41')
            if scd41:
                self.client.publish(f"{self.base_topic}/co2", scd41.co2)

            pms = data.get('pms5003')
            # Only publish PM data if PM sensor is enabled and data available
            if pms and pms.pm1 is not None:
                self.client.publish(f"{self.base_topic}/pm1", round(pms.pm1, 1))
            if pms and pms.pm25 is not None:
                self.client.publish(f"{self.base_topic}/pm25", round(pms.pm25, 1))
            if pms and pms.pm10 is not None:
                self.client.publish(f"{self.base_topic}/pm10", round(pms.pm10, 1))

            # Temperature and Humidity - based on mode
            enviro = data.get('enviro')

            if not self.scd41_enabled:
                # Only BME280
                if enviro and enviro.temperature is not None:
                    self.client.publish(f"{self.base_topic}/temperature", round(enviro.temperature, 1))
                    self.client.publish(f"{self.base_topic}/humidity", round(enviro.humidity, 1))

            else:
                # SCD41 as primary, BME280 as diagnostic
                if scd41:
                    self.client.publish(f"{self.base_topic}/temperature", round(scd41.temperature, 1))
                    self.client.publish(f"{self.base_topic}/humidity", round(scd41.humidity, 1))
                if enviro and enviro.temperature is not None:
                    self.client.publish(f"{self.base_topic}/temperature_diagnostic", round(enviro.temperature, 1))
                    self.client.publish(f"{self.base_topic}/humidity_diagnostic", round(enviro.humidity, 1))

            # Other Enviro+ sensors (always published if available)
            if enviro:
                if enviro.pressure is not None:
                    self.client.publish(f"{self.base_topic}/pressure", round(enviro.pressure, 1))
                if enviro.lux is not None:
                    self.client.publish(f"{self.base_topic}/lux", round(enviro.lux, 1))
                if enviro.oxidising is not None:
                    self.client.publish(f"{self.base_topic}/oxi", enviro.oxidising)
                if enviro.reducing is not None:
                    self.client.publish(f"{self.base_topic}/red", enviro.reducing)
                if enviro.nh3 is not None:
                    self.client.publish(f"{self.base_topic}/nh3", enviro.nh3)

            logger.debug("Published sensor data to MQTT")

        except Exception as e:
            logger.error(f"Error publishing to MQTT: {e}")

    def close(self):
        """Clean shutdown"""
        if self.client:
            try:
                self.client.loop_stop()
                self.client.disconnect()
                logger.info("MQTT client closed")
            except:
                pass


if __name__ == "__main__":
    print("Don't run this directly; use main.py.")
