#!/usr/bin/env python3
"""
Sensor Manager - Handles all sensor interactions
Clean interface to read from SCD41 and Enviro+ sensors
"""

import time
import logging
from dataclasses import dataclass
import RPi.GPIO as GPIO
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# GPIO pins for PM sensor on Enviro+
PM_ENABLE_PIN = 22  # Controls sleep/wake
PM_RESET_PIN = 27   # Reset pin

@dataclass
class SCD41Data:
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

    # Gas Sensors (MICS6814)
    oxidising: Optional[float] = None  # Ohms
    reducing: Optional[float] = None  # Ohms
    nh3: Optional[float] = None  # Ohms

    # Light (LTR559)
    lux: Optional[float] = None
    proximity: Optional[int] = None

    # Noise
    noise_level: Optional[float] = None  # dB

@dataclass
class PMS5003Data:

    # Particulate Matter
    pm1: Optional[float] = None  # μg/m³
    pm25: Optional[float] = None  # μg/m³
    pm10: Optional[float] = None  # μg/m³
    pm_timestamp: Optional[float] = None  # When PM data was last updated

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

class PMS5003Sensor:
    """PMS5003 Particulate Sensor Interface"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.sensor = None

        # PM sensor wake/sleep state
        self.pm_awake = False
        self.pm_wake_time = 0
        self.pm_timestamp = 0
        self.PM_WARMUP_TIME = config.get('pm_warmup_time', 30)  # seconds
        self.PM_SLEEP_DURATION = config.get('pm_sleep_duration', 180)  # seconds
        self.pm_gpio_initialized = False
        # Caching of last read value for when sensor is sleeping
        self.last_pm1 = None
        self.last_pm25 = None
        self.last_pm10 = None

        self._initialize()

    def _initialize(self):
        try:
            from pms5003 import PMS5003

            # Initialize GPIO for PM sensor control
            if self.config.get('pm_sleep_enabled', True):
                try:
                    # Set up GPIO
                    GPIO.setmode(GPIO.BCM)
                    GPIO.setwarnings(False)
                    GPIO.setup(PM_ENABLE_PIN, GPIO.OUT)

                    # Start with sensor awake (HIGH)
                    GPIO.output(PM_ENABLE_PIN, GPIO.HIGH)
                    self.pm_gpio_initialized = True
                    logger.info(f"GPIO{PM_ENABLE_PIN} configured for PM sensor control")

                except Exception as e:
                    logger.error(f"Failed to initialize GPIO for PM sensor: {e}")

            # Initialize PMS5003 sensor (without GPIO parameters)
            self.pms5003 = PMS5003(device=self.config.get('serialport'))

            logger.info("PMS5003 initialized")

        except Exception as e:
            logger.error(f"Failed to initialize PMS5003: {e}")
            import traceback
            traceback.print_exc()

    def _should_read_pm_sensor(self) -> bool:
        """Check if it's time to read PM sensor based on sleep schedule"""
        if not self.config.get('pm_sleep_enabled', True):
            return True  # Always read if sleep management disabled

        current_time = time.time()

        # If we've never read, read now
        if self.pm_timestamp == 0:
            return True

        # Check if sleep duration has elapsed
        time_since_last_read = current_time - self.pm_timestamp
        return time_since_last_read >= self.PM_SLEEP_DURATION

    def _wake_pm_sensor(self) -> bool:
        """
        Wake up PM sensor by setting GPIO22 HIGH.
        Returns True if ready to read, False if still warming up.
        """
        if not self.pms5003 or not self.pm_gpio_initialized:
            return self.pms5003 is not None  # If no GPIO, sensor is always "awake"

        # If already awake, check if warmup is complete
        if self.pm_awake:
            elapsed = time.time() - self.pm_wake_time
            if elapsed < self.PM_WARMUP_TIME:
                logger.info(f"PM sensor warming up... {elapsed:.0f}/{self.PM_WARMUP_TIME}s")
                return False
            return True  # Awake and ready

        # Wake the sensor by setting enable pin HIGH
        try:
            logger.info("Waking PM sensor...")
            GPIO.output(PM_ENABLE_PIN, GPIO.HIGH)

            self.pm_awake = True
            self.pm_wake_time = time.time()
            logger.info(f"PM sensor awake, waiting {self.PM_WARMUP_TIME}s to stabilize...")
            return False  # Not ready yet, needs warmup

        except Exception as e:
            logger.error(f"Failed to wake PM sensor: {e}")
            return False

    def _sleep_pm_sensor(self):
        """Put PM sensor to sleep by setting GPIO22 LOW"""
        if not self.pms5003 or not self.pm_awake or not self.pm_gpio_initialized:
            return

        if not self.config.get('pm_sleep_enabled', True):
            return  # Don't sleep if management disabled

        try:
            logger.info("Putting PM sensor to sleep...")
            GPIO.output(PM_ENABLE_PIN, GPIO.LOW)
            self.pm_awake = False
            logger.debug(f"PM sensor sleeping (will wake in ~{self.PM_SLEEP_DURATION}s)")

        except Exception as e:
            logger.error(f"Failed to sleep PM sensor: {e}")


    def read(self) -> PMS5003Data:

        data = PMS5003Data()

        try:
            from pms5003 import ReadTimeoutError, SerialTimeoutError

            # Return last known values for when sensor is sleeping
            data.pm1 = self.last_pm1
            data.pm25 = self.last_pm25
            data.pm10 = self.last_pm10
            data.pm_timestamp = self.pm_timestamp if self.pm_timestamp > 0 else None

            # Check if it's time to read the PM sensor
            should_read = self._should_read_pm_sensor()

            if should_read:
                # Wake sensor if needed
                if not self._wake_pm_sensor():
                    logger.debug("PM sensor not ready yet (warming up)")
                else:
                    # Sensor is awake and ready - try to read with retries
                    for attempt in range(3):
                        try:
                            pm_data = self.pms5003.read()
                            self.last_pm1 = data.pm1 = pm_data.pm_ug_per_m3(1.0)
                            self.last_pm25 = data.pm25 = pm_data.pm_ug_per_m3(2.5)
                            self.last_pm10 = data.pm10 = pm_data.pm_ug_per_m3(10)
                            data.pm_timestamp = self.pm_timestamp = time.time()
                            logger.info(f"PM: {data.pm25:.1f} μg/m³ (attempt {attempt + 1})")
                            break
                        except (ReadTimeoutError, SerialTimeoutError):
                            if attempt < 2:
                                logger.debug(f"PM read timeout, retrying... ({attempt + 1}/3)")
                                time.sleep(1)
                            else:
                                logger.warning("PM read timeout after 3 attempts")
                        except Exception as e:
                            logger.error(f"PM read error: {e}")
                            break

                    # Put sensor back to sleep
                    self._sleep_pm_sensor()
            else:
                if self.pm_gpio_initialized and self.pm_timestamp > 0:
                    time_until_wake = self.PM_SLEEP_DURATION - (time.time() - self.pm_timestamp)
                    logger.debug(f"PM sensor sleeping (wake in {time_until_wake:.0f}s)")

        except Exception as e:
            logger.error(f"Error reading PMS5003: {e}")

        return data

    def close(self):
        """Clean shutdown"""
        # Sleep PM sensor before closing (recommended)
        logger.debug(f"Closing PM sensor {self.pms5003 is not None}, {self.pm_gpio_initialized}")
        if self.pms5003 is not None and self.pm_gpio_initialized:
            self._sleep_pm_sensor()

class EnviroSensor:
    """Enviro+ Onboard Sensors - BME280, LTR559, MICS6814"""

    def __init__(self):
        self.bme280 = None
        self.gas = None
        self.light = None
        self._initialize()

    def _initialize(self):
        """Initialize Enviro+ sensors"""
        logger.info("Initializing Enviro+ sensors...")

        # BME280 - Temperature, Humidity, Pressure
        try:
            from bme280 import BME280
            from smbus2 import SMBus

            bus = SMBus(1)
            self.bme280 = BME280(i2c_dev=bus)
            logger.info("BME280 initialized (temp, humidity, pressure)")
        except Exception as e:
            logger.error(f"Failed to initialize BME280: {e}")

        # MICS6814 - Gas Sensors
        try:
            from enviroplus import gas
            self.gas = gas
            logger.info("Gas sensors initialized")
        except Exception as e:
            logger.error(f"Failed to initialize gas sensors: {e}")

        # LTR559 - Light and Proximity
        try:
            from ltr559 import LTR559
            self.light = LTR559()
            logger.info("LTR559 initialized (light, proximity)")
        except Exception as e:
            logger.error(f"Failed to initialize light sensor: {e}")

    def read(self) -> EnviroData:
        """Read all Enviro+ sensors"""
        data = EnviroData()

        # Read BME280
        try:
            data.temperature = round(self.bme280.get_temperature(), 1)
            data.humidity = round(self.bme280.get_humidity(), 1)
            data.pressure = round(self.bme280.get_pressure(), 1)
        except Exception as e:
            logger.error(f"Error reading BME280: {e}")

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

class SensorManager:
    """Manages all sensors"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.scd41 = None
        self.pms5003 = None
        self.enviro = None

        # Initialize sensors based on config
        if config.get('scd41', {}).get('enabled', True):
            self.scd41 = SCD41Sensor(config['scd41'])

        if config.get('pms5003', {}).get('enabled', True):
            self.pms5003 = PMS5003Sensor(config['pms5003'])

        self.enviro = EnviroSensor()

    def read_all(self) -> Dict[str, Any]:
        """Read all sensors and return combined data"""
        data = {
            'scd41': None,
            'pms5003': None,
            'enviro': None,
            'timestamp': time.time()
        }

        data['enviro'] = self.enviro.read()

        if self.scd41:
            data['scd41'] = self.scd41.read()

        if self.pms5003:
            data['pms5003'] = self.pms5003.read()

        return data

    def close(self):
        """Clean shutdown of all sensors"""
        if self.scd41:
            self.scd41.close()

        if self.pms5003:
            self.pms5003.close()

        logger.info("All sensors closed")


if __name__ == "__main__":
    print("Don't run this directly; use main.py.")
