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
        self.base_topic = config.get('base_topic', 'airsensor')
        self.discovery_prefix = config.get('discovery_prefix', 'homeassistant')
        self.device_info = config.get('device', {})
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
            username = self.config.get('username')
            password = self.config.get('password')
            if username and password:
                self.client.username_pw_set(username, password)
            
            # Connect
            broker = self.config.get('broker', 'localhost')
            port = self.config.get('port', 1883)
            
            logger.info(f"Connecting to MQTT broker at {broker}:{port}")
            self.client.connect(broker, port, 60)
            
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
                if self.config.get('discovery', True):
                    self._send_discovery()
            else:
                logger.warning("MQTT connection timeout")
                
        except ImportError:
            logger.error("paho-mqtt library not found. Install with: pip3 install paho-mqtt")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize MQTT: {e}")
            raise
    
    def _on_connect(self, client, userdata, flags, rc):
        """Callback when connected to MQTT broker"""
        if rc == 0:
            self.connected = True
            logger.info("Connected to MQTT broker")
        else:
            logger.error(f"MQTT connection failed with code {rc}")
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback when disconnected from MQTT broker"""
        self.connected = False
        if rc != 0:
            logger.warning(f"Unexpected MQTT disconnection (code {rc})")
    
    def _send_discovery(self):
        """Send Home Assistant MQTT discovery messages"""
        logger.info("Sending Home Assistant discovery messages...")
        
        device = {
            "identifiers": [self.device_info.get('identifier', 'airsensor_01')],
            "name": self.device_info.get('name', 'Air Quality Sensor'),
            "manufacturer": self.device_info.get('manufacturer', 'artyzan.net'),
            }
        
        # Get temperature/humidity reporting mode
        temp_mode = self.config.get('temp_humidity_mode', 'bme280_only')
        
        sensors = []
        
        # SCD41 CO2 sensor (only if enabled)
        if temp_mode in ['both', 'scd41_only', 'average', 'scd41_primary']:
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
        if temp_mode == "both":
            # Report both sensors separately
            sensors.extend([
                {
                    "name": "Temperature (SCD41)",
                    "unique_id": "co2_monitor_temp_scd41",
                    "state_topic": f"{self.base_topic}/temperature_scd41",
                    "unit_of_measurement": "°C",
                    "device_class": "temperature",
                    "state_class": "measurement"
                },
                {
                    "name": "Humidity (SCD41)",
                    "unique_id": "co2_monitor_humidity_scd41",
                    "state_topic": f"{self.base_topic}/humidity_scd41",
                    "unit_of_measurement": "%",
                    "device_class": "humidity",
                    "state_class": "measurement"
                },
                {
                    "name": "Temperature (Enviro)",
                    "unique_id": "co2_monitor_temp_enviro",
                    "state_topic": f"{self.base_topic}/temperature_enviro",
                    "unit_of_measurement": "°C",
                    "device_class": "temperature",
                    "state_class": "measurement"
                },
                {
                    "name": "Humidity (Enviro)",
                    "unique_id": "co2_monitor_humidity_enviro",
                    "state_topic": f"{self.base_topic}/humidity_enviro",
                    "unit_of_measurement": "%",
                    "device_class": "humidity",
                    "state_class": "measurement"
                }
            ])
        
        elif temp_mode == "scd41_only":
            # Only SCD41 temperature and humidity
            sensors.extend([
                {
                    "name": "Temperature",
                    "unique_id": "co2_monitor_temperature",
                    "state_topic": f"{self.base_topic}/temperature",
                    "unit_of_measurement": "°C",
                    "device_class": "temperature",
                    "state_class": "measurement"
                },
                {
                    "name": "Humidity",
                    "unique_id": "co2_monitor_humidity",
                    "state_topic": f"{self.base_topic}/humidity",
                    "unit_of_measurement": "%",
                    "device_class": "humidity",
                    "state_class": "measurement"
                }
            ])
        
        elif temp_mode == "bme280_only":
            # Only BME280 temperature and humidity
            sensors.extend([
                {
                    "name": "Temperature",
                    "unique_id": "co2_monitor_temperature",
                    "state_topic": f"{self.base_topic}/temperature",
                    "unit_of_measurement": "°C",
                    "device_class": "temperature",
                    "state_class": "measurement"
                },
                {
                    "name": "Humidity",
                    "unique_id": "co2_monitor_humidity",
                    "state_topic": f"{self.base_topic}/humidity",
                    "unit_of_measurement": "%",
                    "device_class": "humidity",
                    "state_class": "measurement"
                }
            ])
        
        elif temp_mode == "average":
            # Average of both sensors
            sensors.extend([
                {
                    "name": "Temperature",
                    "unique_id": "co2_monitor_temperature",
                    "state_topic": f"{self.base_topic}/temperature",
                    "unit_of_measurement": "°C",
                    "device_class": "temperature",
                    "state_class": "measurement"
                },
                {
                    "name": "Humidity",
                    "unique_id": "co2_monitor_humidity",
                    "state_topic": f"{self.base_topic}/humidity",
                    "unit_of_measurement": "%",
                    "device_class": "humidity",
                    "state_class": "measurement"
                }
            ])
        
        elif temp_mode == "scd41_primary":
            # SCD41 as primary, BME280 as diagnostic
            sensors.extend([
                {
                    "name": "Temperature",
                    "unique_id": "co2_monitor_temperature",
                    "state_topic": f"{self.base_topic}/temperature",
                    "unit_of_measurement": "°C",
                    "device_class": "temperature",
                    "state_class": "measurement"
                },
                {
                    "name": "Humidity",
                    "unique_id": "co2_monitor_humidity",
                    "state_topic": f"{self.base_topic}/humidity",
                    "unit_of_measurement": "%",
                    "device_class": "humidity",
                    "state_class": "measurement"
                },
                {
                    "name": "Temperature (Enviro)",
                    "unique_id": "co2_monitor_temp_diagnostic",
                    "state_topic": f"{self.base_topic}/temperature_diagnostic",
                    "unit_of_measurement": "°C",
                    "device_class": "temperature",
                    "state_class": "measurement",
                    "entity_category": "diagnostic"
                },
                {
                    "name": "Humidity (Enviro)",
                    "unique_id": "co2_monitor_humidity_diagnostic",
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
            "unique_id": "co2_monitor_pressure",
            "state_topic": f"{self.base_topic}/pressure",
            "unit_of_measurement": "hPa",
            "device_class": "pressure",
            "state_class": "measurement"
        })
        
        # Particulate Matter sensors (only if PM sensor enabled - will be checked in publish)
        sensors.extend([
            {
                "name": "PM1",
                "unique_id": "co2_monitor_pm1",
                "state_topic": f"{self.base_topic}/pm1",
                "unit_of_measurement": "μg/m³",
                "device_class": "pm1",
                "state_class": "measurement",
                "icon": "mdi:air-filter"
            },
            {
                "name": "PM2.5",
                "unique_id": "co2_monitor_pm25",
                "state_topic": f"{self.base_topic}/pm25",
                "unit_of_measurement": "μg/m³",
                "device_class": "pm25",
                "state_class": "measurement",
                "icon": "mdi:air-filter"
            },
            {
                "name": "PM10",
                "unique_id": "co2_monitor_pm10",
                "state_topic": f"{self.base_topic}/pm10",
                "unit_of_measurement": "μg/m³",
                "device_class": "pm10",
                "state_class": "measurement",
                "icon": "mdi:air-filter"
            }
        ])
        
        # Light sensor
        sensors.append({
            "name": "Light Level",
            "unique_id": "co2_monitor_lux",
            "state_topic": f"{self.base_topic}/lux",
            "unit_of_measurement": "lx",
            "device_class": "illuminance",
            "state_class": "measurement"
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
        if not self.connected:
            logger.warning("Not connected to MQTT broker")
            return
        
        try:
            # Get temperature/humidity reporting mode
            temp_mode = self.config.get('temp_humidity_mode', 'bme280_only')
            
            # CO2 (only if SCD41 enabled and available)
            scd41 = data.get('scd41')
            if scd41:
                self.client.publish(f"{self.base_topic}/co2", scd41.co2)
            
            # Temperature and Humidity - based on mode
            enviro = data.get('enviro')
            
            if temp_mode == "both":
                # Publish both sensors separately
                if scd41:
                    self.client.publish(f"{self.base_topic}/temperature_scd41", round(scd41.temperature, 1))
                    self.client.publish(f"{self.base_topic}/humidity_scd41", round(scd41.humidity, 1))
                if enviro and enviro.temperature is not None:
                    self.client.publish(f"{self.base_topic}/temperature_enviro", round(enviro.temperature, 1))
                    self.client.publish(f"{self.base_topic}/humidity_enviro", round(enviro.humidity, 1))
            
            elif temp_mode == "scd41_only":
                # Only SCD41
                if scd41:
                    self.client.publish(f"{self.base_topic}/temperature", round(scd41.temperature, 1))
                    self.client.publish(f"{self.base_topic}/humidity", round(scd41.humidity, 1))
            
            elif temp_mode == "bme280_only":
                # Only BME280
                if enviro and enviro.temperature is not None:
                    self.client.publish(f"{self.base_topic}/temperature", round(enviro.temperature, 1))
                    self.client.publish(f"{self.base_topic}/humidity", round(enviro.humidity, 1))
            
            elif temp_mode == "average":
                # Average of both sensors
                if scd41 and enviro and enviro.temperature is not None:
                    avg_temp = (scd41.temperature + enviro.temperature) / 2
                    avg_humidity = (scd41.humidity + enviro.humidity) / 2
                    self.client.publish(f"{self.base_topic}/temperature", round(avg_temp, 1))
                    self.client.publish(f"{self.base_topic}/humidity", round(avg_humidity, 1))
                elif scd41:
                    # Fallback to SCD41 if Enviro not available
                    self.client.publish(f"{self.base_topic}/temperature", round(scd41.temperature, 1))
                    self.client.publish(f"{self.base_topic}/humidity", round(scd41.humidity, 1))
                elif enviro and enviro.temperature is not None:
                    # Fallback to BME280 if SCD41 not available
                    self.client.publish(f"{self.base_topic}/temperature", round(enviro.temperature, 1))
                    self.client.publish(f"{self.base_topic}/humidity", round(enviro.humidity, 1))
            
            elif temp_mode == "scd41_primary":
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
                # Only publish PM data if PM sensor is enabled and data available
                if enviro.pm1 is not None:
                    self.client.publish(f"{self.base_topic}/pm1", round(enviro.pm1, 1))
                if enviro.pm25 is not None:
                    self.client.publish(f"{self.base_topic}/pm25", round(enviro.pm25, 1))
                if enviro.pm10 is not None:
                    self.client.publish(f"{self.base_topic}/pm10", round(enviro.pm10, 1))
                if enviro.lux is not None:
                    self.client.publish(f"{self.base_topic}/lux", round(enviro.lux, 1))
            
            logger.debug("Published sensor data to MQTT")
            
        except Exception as e:
            logger.error(f"Error publishing to MQTT: {e}")
    
    def close(self):
        """Clean shutdown"""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            logger.info("MQTT client closed")


if __name__ == "__main__":
    # Quick test
    logging.basicConfig(level=logging.INFO)
    
    test_config = {
        'broker': 'localhost',
        'port': 1883,
        'username': '',
        'password': '',
        'discovery': True,
        'base_topic': 'co2_monitor/sensor',
        'discovery_prefix': 'homeassistant',
        'device': {
            'name': 'CO2 Monitor Test',
            'manufacturer': 'Custom',
            'model': 'Test',
            'identifier': 'test_01'
        }
    }
    
    try:
        mqtt = MQTTManager(test_config)
        
        # Mock data
        from sensors import SCD41Data, EnviroData
        
        test_data = {
            'scd41': SCD41Data(co2=850, temperature=22.5, humidity=45.0, timestamp=0),
            'enviro': EnviroData(temperature=23.0, humidity=47.0, pm25=12.5, pressure=1013.2)
        }
        
        mqtt.publish_data(test_data)
        time.sleep(2)
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
    finally:
        if 'mqtt' in locals():
            mqtt.close()
