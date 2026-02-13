#!/usr/bin/env python3
"""
Sensor Manager - Handles all sensor interactions
Clean interface to read from SCD41 and Enviro+ sensors
"""

import time
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class SCD41Data:
    """Data from SCD41 CO2 sensor"""
    co2: int  # ppm
    temperature: float  # °C
    humidity: float  # %
    timestamp: int


@dataclass
class EnviroData:
    """Data from Enviro+ sensors"""
    # Temperature & Humidity (BME280)
    temperature: Optional[float] = None  # °C
    humidity: Optional[float] = None  # %
    pressure: Optional[float] = None  # hPa
    
    # Particulate Matter (PMS5003)
    pm1: Optional[float] = None  # μg/m³
    pm25: Optional[float] = None  # μg/m³
    pm10: Optional[float] = None  # μg/m³
    pm_timestamp: Optional[float] = None  # When PM data was last updated
    
    # Gas Sensors (MICS6814)
    oxidising: Optional[float] = None  # Ohms
    reducing: Optional[float] = None  # Ohms
    nh3: Optional[float] = None  # Ohms
    
    # Light (LTR559)
    lux: Optional[float] = None
    proximity: Optional[int] = None
    
    # Noise
    noise_level: Optional[float] = None  # dB


class SCD41Sensor:
    """SCD41 CO2 Sensor Interface"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.sensor = None
        self._initialize()
    
    def _initialize(self):
        """Initialize the SCD41 sensor"""
        try:
            from scd4x import SCD4X
            
            logger.info("Initializing SCD41 sensor...")
            self.sensor = SCD4X(quiet=False)
            
            # Set altitude compensation
            altitude = self.config.get('altitude', 0)
            self.sensor.set_ambient_pressure(altitude)
            logger.info(f"SCD41 altitude set to {altitude}m")
            
            # Start measurements
            self.sensor.start_periodic_measurement()
            logger.info("SCD41 measurements started")
            
            # Wait for first reading
            time.sleep(5)
            
            # Verify
            if self.sensor.data_ready:
                co2, temp, hum, ts = self.sensor.measure()
                logger.info(f"SCD41 ready: CO2={co2}ppm, T={temp:.1f}°C, RH={hum:.1f}%")
            
        except ImportError:
            logger.error("SCD4X library not found. Install with: pip3 install scd4x")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize SCD41: {e}")
            raise
    
    def read(self) -> Optional[SCD41Data]:
        """Read current data from SCD41"""
        if not self.sensor or not self.sensor.data_ready:
            return None
        
        try:
            co2, temp_raw, humidity, timestamp = self.sensor.measure()
            
            # Apply temperature offset
            temp_offset = self.config.get('temperature_offset', 4.0)
            temperature = temp_raw - temp_offset
            
            return SCD41Data(
                co2=int(co2),
                temperature=round(temperature, 1),
                humidity=round(humidity, 1),
                timestamp=timestamp
            )
        except Exception as e:
            logger.error(f"Error reading SCD41: {e}")
            return None
    
    def close(self):
        """Clean shutdown"""
        if self.sensor:
            try:
                self.sensor.stop_periodic_measurement()
                logger.info("SCD41 stopped")
            except Exception as e:
                logger.error(f"Error stopping SCD41: {e}")


class EnviroSensor:
    """Enviro+ Sensor Interface"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.bme280 = None
        self.pms5003 = None
        self.gas = None
        self.light = None
        
        # PM sensor power management
        self.pm_sleep_enabled = config.get('pm_sleep_enabled', True)
        self.pm_sleep_duration = config.get('pm_sleep_duration', 180)  # 3 minutes
        self.pm_warmup_duration = config.get('pm_warmup_duration', 30)  # 30 seconds
        self.pm_last_reading_time = 0
        self.pm_is_sleeping = False
        self.pm_wake_time = 0
        
        # Cache last PM reading to show during sleep/warmup
        self.pm_last_reading = {
            'pm1': None,
            'pm25': None,
            'pm10': None,
            'timestamp': None
        }
        
        self._initialize()
    
    def _initialize(self):
        """Initialize Enviro+ sensors"""
        logger.info("Initializing Enviro+ sensors...")
        
        # BME280 - Temperature, Humidity, Pressure
        if self.config.get('temperature_humidity', True):
            try:
                from bme280 import BME280
                from smbus2 import SMBus
                
                bus = SMBus(1)
                self.bme280 = BME280(i2c_dev=bus)
                logger.info("BME280 initialized (temp, humidity, pressure)")
            except Exception as e:
                logger.error(f"Failed to initialize BME280: {e}")
        
        # PMS5003 - Particulate Matter
        if self.config.get('pm_sensor', True):
            try:
                from pms5003 import PMS5003, ReadTimeoutError
                
                self.pms5003 = PMS5003()
                logger.info("PMS5003 initialized (particulate matter)")
                
                # Start with sensor awake for initial reading
                if self.pm_sleep_enabled:
                    logger.info(f"PM sensor sleep cycling enabled: sleep {self.pm_sleep_duration}s, warmup {self.pm_warmup_duration}s")
                    self._pm_wake()
                else:
                    logger.info("PM sensor sleep cycling disabled (always on)")
                    
            except Exception as e:
                logger.error(f"Failed to initialize PMS5003: {e}")
        
        # MICS6814 - Gas Sensors
        if self.config.get('gas_sensors', False):
            try:
                from enviroplus import gas
                self.gas = gas
                logger.info("Gas sensors initialized")
            except Exception as e:
                logger.error(f"Failed to initialize gas sensors: {e}")
        
        # LTR559 - Light and Proximity
        if self.config.get('light', True):
            try:
                from ltr559 import LTR559
                self.light = LTR559()
                logger.info("LTR559 initialized (light, proximity)")
            except Exception as e:
                logger.error(f"Failed to initialize light sensor: {e}")
    
    def _pm_wake(self):
        """Wake up the PM sensor"""
        if not self.pms5003:
            return
        
        try:
            # The PMS5003 library handles the GPIO pin internally
            # Calling read() or reset() wakes the sensor
            self.pms5003.reset()
            self.pm_is_sleeping = False
            self.pm_wake_time = time.time()
            logger.debug("PM sensor woken up")
        except Exception as e:
            logger.error(f"Failed to wake PM sensor: {e}")
    
    def _pm_sleep(self):
        """Put PM sensor to sleep"""
        if not self.pms5003 or not self.pm_sleep_enabled:
            return
        
        try:
            # Set GPIO pin low to sleep the sensor
            # The Pimoroni library uses GPIO22 (BCM) for PMS5003 enable/reset
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            PM_ENABLE_PIN = 22
            GPIO.setup(PM_ENABLE_PIN, GPIO.OUT)
            GPIO.output(PM_ENABLE_PIN, GPIO.LOW)
            
            self.pm_is_sleeping = True
            logger.debug(f"PM sensor sleeping for {self.pm_sleep_duration}s")
        except Exception as e:
            logger.error(f"Failed to sleep PM sensor: {e}")
    
    def _should_read_pm(self) -> bool:
        """Determine if we should read PM sensor now"""
        if not self.pms5003 or not self.pm_sleep_enabled:
            return True  # Always read if sleep not enabled
        
        current_time = time.time()
        
        # If sleeping, check if it's time to wake
        if self.pm_is_sleeping:
            time_since_reading = current_time - self.pm_last_reading_time
            if time_since_reading >= self.pm_sleep_duration:
                self._pm_wake()
                return False  # Just woke up, don't read yet
            return False  # Still sleeping
        
        # If awake, check if warmed up enough
        time_since_wake = current_time - self.pm_wake_time
        if time_since_wake >= self.pm_warmup_duration:
            return True  # Warmed up, ready to read
        
        return False  # Still warming up
    
    def read(self) -> EnviroData:
        """Read all Enviro+ sensors"""
        data = EnviroData()
        
        # Read BME280
        if self.bme280:
            try:
                data.temperature = round(self.bme280.get_temperature(), 1)
                data.humidity = round(self.bme280.get_humidity(), 1)
                data.pressure = round(self.bme280.get_pressure(), 1)
            except Exception as e:
                logger.error(f"Error reading BME280: {e}")
        
        # Read PMS5003 with sleep cycling
        if self.pms5003:
            if self._should_read_pm():
                try:
                    from pms5003 import ReadTimeoutError
                    pm_data = self.pms5003.read()
                    
                    # Update cache with fresh reading
                    self.pm_last_reading['pm1'] = pm_data.pm_ug_per_m3(1.0)
                    self.pm_last_reading['pm25'] = pm_data.pm_ug_per_m3(2.5)
                    self.pm_last_reading['pm10'] = pm_data.pm_ug_per_m3(10)
                    self.pm_last_reading['timestamp'] = time.time()
                    
                    self.pm_last_reading_time = time.time()
                    logger.debug(f"PM sensor read: PM2.5={self.pm_last_reading['pm25']:.1f}μg/m³")
                    
                    # Put sensor to sleep after reading
                    if self.pm_sleep_enabled:
                        self._pm_sleep()
                        
                except ReadTimeoutError:
                    logger.debug("PMS5003 read timeout (normal)")
                except Exception as e:
                    logger.error(f"Error reading PMS5003: {e}")
            else:
                # Sensor sleeping or warming up - log status
                if self.pm_is_sleeping:
                    logger.debug("PM sensor sleeping (using cached values)")
                else:
                    logger.debug("PM sensor warming up (using cached values)")
            
            # Always use cached values (either fresh or from last reading)
            if self.pm_last_reading['pm1'] is not None:
                data.pm1 = self.pm_last_reading['pm1']
                data.pm25 = self.pm_last_reading['pm25']
                data.pm10 = self.pm_last_reading['pm10']
                data.pm_timestamp = self.pm_last_reading['timestamp']
        
        # Read Gas Sensors
        if self.gas:
            try:
                gas_data = self.gas.read_all()
                data.oxidising = round(gas_data.oxidising, 0)
                data.reducing = round(gas_data.reducing, 0)
                data.nh3 = round(gas_data.nh3, 0)
            except Exception as e:
                logger.error(f"Error reading gas sensors: {e}")
        
        # Read Light Sensor
        if self.light:
            try:
                data.lux = round(self.light.get_lux(), 1)
                data.proximity = self.light.get_proximity()
            except Exception as e:
                logger.error(f"Error reading light sensor: {e}")
        
        return data
    
    def close(self):
        """Clean shutdown"""
        # Wake sensor before closing to leave it in known state
        if self.pms5003 and self.pm_is_sleeping:
            self._pm_wake()
        logger.info("Enviro sensors closed")


class SensorManager:
    """Manages all sensors"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.scd41 = None
        self.enviro = None
        
        # Initialize sensors based on config
        if config.get('scd41', {}).get('enabled', True):
            self.scd41 = SCD41Sensor(config['scd41'])
        
        if config.get('enviro', {}).get('enabled', True):
            self.enviro = EnviroSensor(config['enviro'])
    
    def read_all(self) -> Dict[str, Any]:
        """Read all sensors and return combined data"""
        data = {
            'scd41': None,
            'enviro': None,
            'timestamp': time.time()
        }
        
        if self.scd41:
            data['scd41'] = self.scd41.read()
        
        if self.enviro:
            data['enviro'] = self.enviro.read()
        
        return data
    
    def close(self):
        """Clean shutdown of all sensors"""
        if self.scd41:
            self.scd41.close()
        
        logger.info("All sensors closed")


if __name__ == "__main__":
    # Quick test
    logging.basicConfig(level=logging.INFO)
    
    test_config = {
        'scd41': {
            'enabled': True,
            'altitude': 0,
            'temperature_offset': 4.0
        },
        'enviro': {
            'enabled': True,
            'temperature_humidity': True,
            'pm_sensor': True,
            'gas_sensors': False,
            'light': True
        }
    }
    
    manager = SensorManager(test_config)
    
    try:
        for i in range(3):
            print(f"\n--- Reading {i+1} ---")
            data = manager.read_all()
            
            if data['scd41']:
                scd = data['scd41']
                print(f"SCD41: CO2={scd.co2}ppm, T={scd.temperature}°C, RH={scd.humidity}%")
            
            if data['enviro']:
                env = data['enviro']
                print(f"Enviro: T={env.temperature}°C, P={env.pressure}hPa, PM2.5={env.pm25}μg/m³")
            
            time.sleep(5)
    finally:
        manager.close()
