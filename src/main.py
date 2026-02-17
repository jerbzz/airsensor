#!/usr/bin/env python3
"""
CO2 Monitor - Main Application
Clean, modern environmental monitoring system
Hardware: Raspberry Pi Zero 2 W + Enviro+ + SCD41
"""

import sys
import time
import signal
import logging
from pathlib import Path
from typing import Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

import yaml
from sensors import SensorManager
from display import DisplayManager
from mqtt_manager import MQTTManager

logger = logging.getLogger(__name__)

class Airsensor:
    """Main application class"""

    def __init__(self, config_path: str = "config/config.yaml"):
        self.config = self._load_config(config_path)
        self.running = False
        self.firstcycle = True

        # Components
        self.sensors: Optional[SensorManager] = None
        self.display: Optional[DisplayManager] = None
        self.mqtt: Optional[MQTTManager] = None

        # Timing
        self.update_interval = self.config['general']['update_interval']
        self.display_cycle_time = self.config['display']['cycle_time']
        self.last_update = 0
        self.last_display_cycle = 0

        # Setup logging
        self._setup_logging()

        # Register signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _load_config(self, config_path: str) -> dict:
        """Load configuration from YAML file"""
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            return config
        except FileNotFoundError:
            print(f"Error: Config file not found: {config_path}")
            sys.exit(1)
        except yaml.YAMLError as e:
            print(f"Error parsing config file: {e}")
            sys.exit(1)

    def _setup_logging(self):
        """Setup logging configuration"""
        log_level = getattr(logging, self.config['general']['log_level'])

        # Create logs directory if it doesn't exist
        Path("logs").mkdir(exist_ok=True)

        # Configure logging
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('logs/co2_monitor.log'),
                logging.StreamHandler(sys.stdout)
            ]
        )

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, shutting down...")
        self.stop()

    def initialise(self):
        """Initialise all components"""
        logger.info("Enviro+ Air Quality Sensor Service is starting...")

        try:
            # Initialise display
            if self.config['display']['enabled']:
                logger.info("Initialising display...")
                self.display = DisplayManager(self.config['display'])

            # Initialise sensors
            logger.info("Initialising sensors...")
            self.sensors = SensorManager(self.config)

            # Initialise MQTT
            if self.config['mqtt']['enabled']:
                logger.info("Initialising MQTT...")
                self.mqtt = MQTTManager(self.config)

            logger.info("Initialisation complete!")

        except Exception as e:
            logger.error(f"Initialisation failed: {e}")
            raise

    def run(self):
        """Main application loop"""
        self.running = True

        logger.info("Starting main loop...")
        logger.info(f"Update interval: {self.update_interval}s")
        logger.info(f"Display cycle time: {self.display_cycle_time}s")

        try:
            while self.running:
                current_time = time.time()

                # Read sensors and update display
                if current_time - self.last_update >= self.update_interval:
                    self._update_cycle()
                    self.last_update = current_time

                # Cycle display screens
                if self.display and (current_time - self.last_display_cycle >= self.display_cycle_time):
                    self.display.next_screen()
                    self.last_display_cycle = current_time

                # Small sleep to prevent CPU spinning
                time.sleep(0.1)

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
        finally:
            self.stop()

    def _update_cycle(self):
        """Single update cycle - read sensors, update display, publish data"""
        #try:
        # Read all sensors
        data = self.sensors.read_all()

        if self.firstcycle:
            logger.info("Waiting 10 seconds on first cycle for sensors to stabilise...")
            time.sleep(10)
            data = self.sensors.read_all()
            self.firstcycle = False

        # Log readings
        if data['scd41']:
            scd = data['scd41']
            logger.info(f"SCD41: CO2 = {scd.co2} ppm, T = {scd.temperature} °C, RH = {scd.humidity} %")

        if data['pms5003']:
            pms = data['pms5003']
            # only log fresh data
            if pms.pm_timestamp is not None and (time.time() - pms.pm_timestamp) < 5:
                logger.info(f"PMS5003: PM1 = {pms.pm1}, PM2.5 = {pms.pm25}, PM10 = {pms.pm10} µg/m³")

        env = data['enviro']
        logger.info(f"Enviro+: P = {env.pressure} hPa, L = {env.lux} lux")
        logger.info(f"MICS6814: Oxi = {env.oxidising / 1000:.0f} kΩ, Red = {env.reducing / 1000:.0f} kΩ, NH₃ = {env.nh3 / 1000:.0f} kΩ")

        # Update display
        if self.display:
            self.display.update(data)

        # Publish to MQTT
        if self.mqtt:
            self.mqtt.publish_data(data)

        # Optional: Log to file
        if self.config.get('logging', {}).get('enabled', False):
            self._log_data(data)

        #except Exception as e:
        #    logger.error(f"Error in update cycle: {e}")

    def _log_data(self, data: dict):
        """Log sensor data to file"""
        # TODO: Implement CSV or JSON logging if needed
        pass

    def stop(self):
        """Clean shutdown"""
        logger.info("Shutting down...")
        self.running = False

        if self.sensors:
            self.sensors.close()

        if self.display:
            self.display.close()

        if self.mqtt:
            self.mqtt.close()

        logger.info("Shutdown complete")


def main():
    """Entry point"""

    # Create and run application
    app = Airsensor()

    try:
        app.initialise()
        app.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
