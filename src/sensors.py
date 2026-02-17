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
        self._initialise()

    def _initialise(self):
        """Initialise the SCD41 sensor"""
        try:
            from scd4x import SCD4X

            logger.info("Initialising SCD41 sensor...")
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
            logger.error(f"Failed to initialise SCD41: {e}")
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
    """PMS5003 Particulate Sensor Interface with Sleep/Wake Management"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.pms5003 = None
        self.gpio_enabled = False

        # Sleep/wake configuration
        self.sleep_enabled = config.get('pm_sleep_enabled', True)
        self.warmup_seconds = config.get('pm_warmup_time', 30)
        self.sleep_seconds = config.get('pm_sleep_duration', 180)

        # State tracking
        self.last_wake_time = 0  # When we last woke the sensor
        self.last_read_time = 0  # When we last successfully read
        self.is_awake = False

        # Cached values (returned when sleeping)
        self.cached_pm1 = None
        self.cached_pm25 = None
        self.cached_pm10 = None

        self._initialise()

    def _initialise(self):
        """Initialise PMS5003 sensor and GPIO"""
        try:
            from pms5003 import PMS5003

            # Set up GPIO for power control
            if self.sleep_enabled:
                try:
                    GPIO.setmode(GPIO.BCM)
                    GPIO.setwarnings(False)
                    GPIO.setup(PM_ENABLE_PIN, GPIO.OUT)
                    GPIO.output(PM_ENABLE_PIN, GPIO.HIGH)  # Start powered on
                    self.gpio_enabled = True
                    self.is_awake = True
                    self.last_wake_time = time.time()
                    logger.info(f"GPIO {PM_ENABLE_PIN} configured for PM sensor power control")
                except Exception as e:
                    logger.error(f"Failed to configure GPIO: {e}")
                    self.gpio_enabled = False

            # Initialise sensor
            self.pms5003 = PMS5003(device=self.config.get('serialport', '/dev/ttyS0'))
            logger.info("PMS5003 initialised")

        except Exception as e:
            logger.error(f"Failed to initialise PMS5003: {e}")
            self.pms5003 = None

    def read(self) -> PMS5003Data:
        """
        Read PM sensor data.
        Returns cached values if sensor is sleeping or warming up.
        """
        data = PMS5003Data()

        # Always return cached values initially
        data.pm1 = self.cached_pm1
        data.pm25 = self.cached_pm25
        data.pm10 = self.cached_pm10
        data.pm_timestamp = self.last_read_time if self.last_read_time > 0 else None

        # If sensor not available, return cached values
        if not self.pms5003:
            return data

        # If sleep management disabled, always try to read
        if not self.sleep_enabled:
            return self._attempt_read(data)

        # Sleep management enabled - check if we should read
        current_time = time.time()

        # Determine if it's time to wake and read
        if self.last_read_time == 0:
            # Never read before - read now
            should_read = True
        else:
            # Check if enough time has passed since last read
            time_since_read = current_time - self.last_read_time
            should_read = time_since_read >= self.sleep_seconds

        if not should_read:
            # Not time yet - keep sleeping, return cached values
            if self.gpio_enabled and self.last_read_time > 0:
                time_until_wake = self.sleep_seconds - (current_time - self.last_read_time)
                logger.debug(f"PM sensor sleeping ({time_until_wake:.0f}s until wake)")
            return data

        # Time to read - ensure sensor is awake and warmed up
        if not self._ensure_awake():
            # Still warming up - return cached values
            return data

        # Sensor is ready - attempt read
        result = self._attempt_read(data)

        # Put sensor back to sleep
        self._sleep()
        return result

    def _ensure_awake(self) -> bool:
        """
        Ensure sensor is awake and warmed up.
        Returns True if ready to read, False if still warming up.
        """
        if not self.gpio_enabled:
            # No GPIO control - always ready
            return True

        current_time = time.time()

        # Check if already awake
        if self.is_awake:
            # Check if warmup complete
            time_awake = current_time - self.last_wake_time
            if time_awake < self.warmup_seconds:
                logger.debug(f"PM sensor warming up ({time_awake:.0f}/{self.warmup_seconds}s)")
                return False
            # Warmup complete
            return True

        # Need to wake sensor
        try:
            logger.info("Waking PM sensor...")
            GPIO.output(PM_ENABLE_PIN, GPIO.HIGH)
            self.is_awake = True
            self.last_wake_time = current_time
            logger.info(f"PM sensor awake, warming up for {self.warmup_seconds}s...")
            return False  # Not ready yet, needs warmup
        except Exception as e:
            logger.error(f"Failed to wake PM sensor: {e}")
            return False

    def _attempt_read(self, data: PMS5003Data) -> PMS5003Data:
        """
        Attempt to read from the sensor with retries.
        Updates data object and returns it.
        """
        from pms5003 import ReadTimeoutError, SerialTimeoutError

        for attempt in range(3):
            try:
                pm_data = self.pms5003.read()

                # Successful read - update cache and data
                self.cached_pm1 = data.pm1 = pm_data.pm_ug_per_m3(1.0)
                self.cached_pm25 = data.pm25 = pm_data.pm_ug_per_m3(2.5)
                self.cached_pm10 = data.pm10 = pm_data.pm_ug_per_m3(10)
                self.last_read_time = data.pm_timestamp = time.time()

                logger.info(f"PM: {data.pm25:.1f} μg/m³")
                return data

            except (ReadTimeoutError, SerialTimeoutError) as e:
                if attempt < 2:
                    logger.debug(f"PM read timeout, retrying ({attempt + 1}/3)...")
                    time.sleep(1)
                else:
                    logger.warning(f"PM read failed after 3 attempts")

            except Exception as e:
                logger.error(f"PM read error: {e}")
                break

        # All attempts failed - return data with cached values
        return data

    def _sleep(self):
        """Put sensor to sleep to save power"""
        if not self.gpio_enabled or not self.is_awake:
            return

        try:
            logger.info("Putting PM sensor to sleep...")
            GPIO.output(PM_ENABLE_PIN, GPIO.LOW)
            self.is_awake = False
            logger.debug(f"PM sensor asleep (will wake in ~{self.sleep_seconds}s)")
        except Exception as e:
            logger.error(f"Failed to sleep PM sensor: {e}")

    def close(self):
        """Clean shutdown"""
        if self.pms5003 and self.gpio_enabled:
            self._sleep()
            logger.info("PM sensor closed")

class EnviroSensor:
    """Enviro+ Onboard Sensors - BME280, LTR559, MICS6814"""

    def __init__(self):
        self.bme280 = None
        self.gas = None
        self.light = None
        self._initialise()

    def _initialise(self):
        """Initialise Enviro+ sensors"""
        logger.info("Initialising Enviro+ sensors...")

        # BME280 - Temperature, Humidity, Pressure
        try:
            from bme280 import BME280
            from smbus2 import SMBus

            bus = SMBus(1)
            self.bme280 = BME280(i2c_dev=bus)
            logger.info("BME280 initialised (temp, humidity, pressure)")
        except Exception as e:
            logger.error(f"Failed to initialise BME280: {e}")

        # MICS6814 - Gas Sensors
        try:
            from enviroplus import gas
            self.gas = gas
            logger.info("Gas sensors initialised")
        except Exception as e:
            logger.error(f"Failed to initialise gas sensors: {e}")

        # LTR559 - Light and Proximity
        try:
            from ltr559 import LTR559
            self.light = LTR559()
            logger.info("LTR559 initialised (light, proximity)")
        except Exception as e:
            logger.error(f"Failed to initialise light sensor: {e}")

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

        # Initialise sensors based on config
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
