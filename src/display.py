#!/usr/bin/env python3
"""
Display Manager - Handles the Enviro+ ST7735 LCD display
Clean, modular screen management
"""

import time
import logging
from typing import Optional, Dict, Any
from PIL import Image, ImageDraw, ImageFont
from ST7735 import ST7735


logger = logging.getLogger(__name__)

# Display dimensions
WIDTH = 160
HEIGHT = 80

class DisplayManager:
    """Manages the Enviro+ ST7735 LCD display"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.disp = None
        self.img = None
        self.draw = None
        self.fonts = {}
        self.current_screen = 0
        self.screens = config.get('screens')
        self._initialise()

    def _initialise(self):
        """Initialise the display"""
        try:

            logger.info("Initialising ST7735 display...")

            self.disp = ST7735(
                port=0,
                cs=1,
                dc=9,
                backlight=12,
                rotation=self.config.get('rotation', 0),
                spi_speed_hz=10000000
            )

            self.disp.begin()

            # Set brightness
            brightness = self.config.get('brightness', 1.0)
            self.disp.set_backlight(int(brightness * 255))

            # Create image buffer
            self.img = Image.new('RGB', (WIDTH, HEIGHT), color=(0, 0, 0))
            self.draw = ImageDraw.Draw(self.img)

            # Load fonts
            self._load_fonts()

            # Show startup screen
            self._show_startup()

            logger.info("Display initialised")

        except Exception as e:
            logger.error("Failed to initialise display: %s", e)
            raise

    def _load_fonts(self):
        """Load fonts for display"""
        try:
            # Try to load nice fonts
            self.fonts = {
                'tiny': ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10),
                'small': ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12),
                'medium': ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16),
                'large': ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24),
                'huge': ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32)
            }
        except Exception:
            # Fallback to default font
            logger.warning("Could not load TrueType fonts, using default")
            self.fonts = {
                'tiny': ImageFont.load_default(),
                'small': ImageFont.load_default(),
                'medium': ImageFont.load_default(),
                'large': ImageFont.load_default(),
                'huge': ImageFont.load_default()
            }

    def _show_startup(self):
        """Show startup screen"""
        self.draw.rectangle((0, 0, WIDTH, HEIGHT), (0, 0, 0))
        self.draw.text((10, 25), "Enviro+", font=self.fonts['large'], fill=(0, 255, 0))
        self.draw.text((10, 50), "Initialising...", font=self.fonts['small'], fill=(255, 255, 255))
        self.disp.display(self.img)

    def clear(self):
        """Clear the display"""
        self.draw.rectangle((0, 0, WIDTH, HEIGHT), (0, 0, 0))

    def update(self, data: Dict[str, Any]):
        """Update display with current sensor data"""
        if not self.disp:
            return

        # Get current screen
        screen_name = self.screens[self.current_screen]

        # Check if screen is available based on sensors
        if not self._is_screen_available(screen_name, data):
            # Skip to next screen if current one isn't available
            self.next_screen()
            screen_name = self.screens[self.current_screen]

        # Render the screen
        if screen_name == 'co2':
            self._render_co2(data)
        elif screen_name == 'temp':
            self._render_temp(data)
        elif screen_name == 'pm':
            self._render_pm(data)
        elif screen_name == 'gas':
            self._render_gas(data)
        elif screen_name == 'baro':
            self._render_baro(data)
        elif screen_name == 'summary':
            self._render_summary(data)

        # Display
        self.disp.display(self.img)

    def _is_screen_available(self, screen_name: str, data: Dict[str, Any]) -> bool:
        """Check if a screen can be displayed based on available sensor data"""
        scd41 = data.get('scd41')
        pms5003 = data.get('pms5003')

        if screen_name == 'co2':
            return scd41 is not None
        if screen_name == 'pm':
            return pms5003 is not None

        return True # it's only CO2 and PM we would want to disable

    def next_screen(self):
        """Switch to next screen"""
        self.current_screen = (self.current_screen + 1) % len(self.screens)

    def _get_co2_color(self, co2: int) -> tuple:
        """Get color based on CO2 level"""
        if co2 < 800:
            return (0, 255, 0)  # Green - Good
        elif co2 < 1000:
            return (255, 255, 0)  # Yellow - Moderate
        elif co2 < 1500:
            return (255, 165, 0)  # Orange - Poor
        else:
            return (255, 0, 0)  # Red - Unhealthy

    def _get_co2_label(self, co2: int) -> str:
        """Get label based on CO2 level"""
        if co2 < 800:
            return "GOOD"
        elif co2 < 1000:
            return "MODERATE"
        elif co2 < 1500:
            return "POOR"
        else:
            return "UNHEALTHY"

    def _render_co2(self, data: Dict[str, Any]):
        """Render main CO2 screen (large CO2 value)"""
        self.clear()

        scd41 = data.get('scd41')
        if not scd41:
            self.draw.text((10, 30), "No SCD41 data", font=self.fonts['small'], fill=(255, 0, 0))
            return

        co2 = scd41.co2
        color = self._get_co2_color(co2)
        label = self._get_co2_label(co2)

        # Title
        self.draw.text((5, 2), "CO2", font=self.fonts['medium'], fill=(200, 200, 200))

        # Large CO2 value
        self.draw.text((10, 20), str(co2), font=self.fonts['huge'], fill=color)

        # Unit and status
        self.draw.text((110, 30), "ppm", font=self.fonts['small'], fill=(200, 200, 200))
        self.draw.text((5, 58), label, font=self.fonts['small'], fill=color)

        # Temperature and humidity (small)
        temp_text = f"{scd41.temperature:.1f}°C  {scd41.humidity:.0f}%"
        self.draw.text((80, 58), temp_text, font=self.fonts['tiny'], fill=(150, 150, 150))

    def _render_temp(self, data: Dict[str, Any]):
        """Render temperature/humidity screen"""
        self.clear()

        enviro = data.get('enviro')
        scd41 = data.get('scd41')

        # Title
        self.draw.text((5, 2), "Temperature & Humidity", font=self.fonts['small'], fill=(200, 200, 200))

        y = 22

        # SCD41 readings
        if scd41:
            self.draw.text((5, y), "SCD41:", font=self.fonts['tiny'], fill=(100, 100, 100))
            y += 12
            self.draw.text((10, y), f"{scd41.temperature:.1f}°C", font=self.fonts['medium'], fill=(255, 150, 0))
            self.draw.text((90, y), f"{scd41.humidity:.0f}%", font=self.fonts['medium'], fill=(100, 200, 255))
            y += 20

        # Enviro+ readings
        if enviro and enviro.temperature is not None:
            self.draw.text((5, y), "Enviro:", font=self.fonts['tiny'], fill=(100, 100, 100))
            y += 12
            self.draw.text((10, y), f"{enviro.temperature:.1f}°C", font=self.fonts['medium'], fill=(255, 150, 0))
            self.draw.text((90, y), f"{enviro.humidity:.0f}%", font=self.fonts['medium'], fill=(100, 200, 255))

    def _render_pm(self, data: Dict[str, Any]):
        """Render particulate matter screen"""
        self.clear()

        pms = data.get('pms5003')
        if not pms or pms.pm25 is None:
            self.draw.text((5, 2), "Particulate Matter", font=self.fonts['small'], fill=(200, 200, 200))
            self.draw.text((10, 30), "No PM data", font=self.fonts['small'], fill=(255, 0, 0))
            return

        # Title
        self.draw.text((5, 2), "Particulate Matter", font=self.fonts['small'], fill=(200, 200, 200))

        # Show data age if available
        if pms.pm_timestamp is not None:
            age_seconds = time.time() - pms.pm_timestamp
            if age_seconds < 60:
                age_text = "Live"
                age_color = (0, 255, 0)
            elif age_seconds < 180:
                age_text = f"{int(age_seconds)}s"
                age_color = (255, 255, 0)
            else:
                age_minutes = int(age_seconds / 60)
                age_text = f"{age_minutes}m"
                age_color = (150, 150, 150)

            self.draw.text((130, 2), age_text, font=self.fonts['tiny'], fill=age_color)

        # PM2.5 - most important
        pm25_color = (0, 255, 0) if pms.pm25 < 12 else (255, 255, 0) if pms.pm25 < 35 else (255, 0, 0)
        self.draw.text((5, 22), "PM2.5:", font=self.fonts['small'], fill=(150, 150, 150))
        self.draw.text((10, 38), f"{pms.pm25:.0f}", font=self.fonts['large'], fill=pm25_color)
        self.draw.text((80, 44), "μg/m³", font=self.fonts['tiny'], fill=(150, 150, 150))

        # PM1 and PM10 (smaller)
        y = 64
        if pms.pm1 is not None:
            self.draw.text((5, y), f"PM1: {pms.pm1:.0f}", font=self.fonts['tiny'], fill=(100, 100, 100))
        if pms.pm10 is not None:
            self.draw.text((85, y), f"PM10: {pms.pm10:.0f}", font=self.fonts['tiny'], fill=(100, 100, 100))

    def _render_gas(self, data: Dict[str, Any]):
        """Render gas sensor screen"""
        self.clear()

        enviro = data.get('enviro')

        # Title
        self.draw.text((5, 2), "Gas Sensors", font=self.fonts['small'], fill=(200, 200, 200))

        if not enviro or enviro.oxidising is None:
            self.draw.text((10, 30), "No gas data", font=self.fonts['small'], fill=(255, 0, 0))
            return

        y = 22
        self.draw.text((5, y), f"Oxidising: {enviro.oxidising:.0f} Ω", font=self.fonts['small'], fill=(255, 150, 0))
        y += 18
        self.draw.text((5, y), f"Reducing:  {enviro.reducing:.0f} Ω", font=self.fonts['small'], fill=(100, 200, 255))
        y += 18
        self.draw.text((5, y), f"NH3:       {enviro.nh3:.0f} Ω", font=self.fonts['small'], fill=(150, 255, 150))

    def _render_baro(self, data: Dict[str, Any]):
        """Render weather/pressure screen"""
        self.clear()

        enviro = data.get('enviro')

        # Title
        self.draw.text((5, 2), "Weather", font=self.fonts['small'], fill=(200, 200, 200))

        if not enviro or enviro.pressure is None:
            self.draw.text((10, 30), "No data", font=self.fonts['small'], fill=(255, 0, 0))
            return

        # Pressure (large)
        self.draw.text((10, 25), f"{enviro.pressure:.0f}", font=self.fonts['large'], fill=(255, 255, 255))
        self.draw.text((100, 32), "hPa", font=self.fonts['small'], fill=(150, 150, 150))

        # Light level
        if enviro.lux is not None:
            self.draw.text((5, 58), f"Light: {enviro.lux:.0f} lux", font=self.fonts['tiny'], fill=(200, 200, 100))

    def _render_summary(self, data: Dict[str, Any]):
        """Render all-in-one summary screen"""
        self.clear()

        scd41 = data.get('scd41')
        # enviro = data.get('enviro')
        pms = data.get('pms5003')

        # Title
        self.draw.text((5, 2), "Summary", font=self.fonts['small'], fill=(200, 200, 200))

        y = 18

        # CO2
        if scd41:
            color = self._get_co2_color(scd41.co2)
            self.draw.text((5, y), f"CO2: {scd41.co2}ppm", font=self.fonts['small'], fill=color)
            y += 14

        # Temperature
        if scd41:
            self.draw.text((5, y), f"Temp: {scd41.temperature:.1f}°C", font=self.fonts['tiny'], fill=(255, 150, 0))
            y += 11

        # Humidity
        if scd41:
            self.draw.text((5, y), f"RH: {scd41.humidity:.0f}%", font=self.fonts['tiny'], fill=(100, 200, 255))
            y += 11

        # PM2.5
        if pms and pms.pm25 is not None:
            pm_color = (0, 255, 0) if pms.pm25 < 12 else (255, 255, 0) if pms.pm25 < 35 else (255, 0, 0)
            self.draw.text((5, y), f"PM2.5: {pms.pm25:.0f} μg/m³", font=self.fonts['tiny'], fill=pm_color)

    def close(self):
        """Clean shutdown"""
        if self.disp:
            self.clear()
            self.disp.display(self.img)
            self.disp.set_backlight(0)
            logger.info("Display closed and backlight switched off.")


if __name__ == "__main__":
    print("Don't run this directly; use main.py.")
