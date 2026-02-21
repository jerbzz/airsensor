# Enviro+ Airsensor

A system to collect data from the Pimoroni Enviro+ and deliver it to HomeAssistant.

## Features

✅ **Home Assistant integration** - MQTT with auto-discovery, zero HA configuration required  
✅ **LCD display** - Cycling screens showing all sensor data  
✅ **Easy installation** - Installs with one command, including to run automatically at startup  
✅ **Easy configuration** - Single YAML config file, human-readable with sane defaults  
✅ **Supports Enviro+ sensor suite** - Temperature, humidity, pressure, light level, pollutant gases  
✅ **Particulate matter monitoring (optional)** - Support for PMS5003 particulate sensor (PM1, PM2.5, PM10)  
✅ **True CO2 monitoring (optional)** - Support for SCD41 photoacoustic sensor (400-5000 ppm)  

## Hardware Requirements

**Minimum (Basic Setup):**
- Raspberry Pi Zero 2 W (or any Raspberry Pi)
- Pimoroni Enviro+ HAT
- microSD card (8GB+)
- Power supply

**Optional Add-ons:**
- PMS5003 Particulate Matter sensor (dedicated connector available on Enviro+)
- Pimoroni SCD41 CO2 Sensor Breakout (requires soldering or another method of connection to Enviro+ GPIO headers)

## Quick Start

### 1. Hardware Setup

1. Attach Enviro+ HAT to Raspberry Pi GPIO header
2. Connect SCD41 sensor via I2C (Qwiic/STEMMA QT or GPIO pins 1,3,5,7,9)
3. Use Raspberry Pi Imager (https://www.raspberrypi.com/software/) to download and install Raspberry Pi OS Lite 64-bit on the micro-SD card.
4. Power on the Pi
5. Connect to the Pi over SSH, or using Raspberry Pi Connect

### 2. Software Installation

You can directly download and install the software and its prerequisites in one step. 
You should examine the contents of any script before using it in this way!

```
curl https://raw.githubusercontent.com/jerbzz/airsensor/refs/heads/main/install.sh | bash
```

### 3. Configuration

Edit `config/config.yaml` with your settings:

```yaml
mqtt:
  enabled: true
  broker: 192.168.1.100  # Your Home Assistant IP or domain name
  username: mqtt_user     # If using authentication
  password: mqtt_pass
```

### 4. Run

```bash
# Test run
cd /opt/airsensor
source bin/.venv/activate
python3 src/main.py

# Or run as a service (auto-start on boot)
sudo systemctl enable co2-monitor
sudo systemctl start co2-monitor
```

## Configuration

The `config/config.yaml` file controls all settings:

### Hardware Setup

The CO2 Monitor supports different hardware configurations:

**Configuration 1: Basic Enviro+ Only**
```yaml
scd41:
  enabled: false
enviro:
  pm_sensor: false
mqtt:
  temp_humidity_mode: bme280_only
```

**Configuration 2: Enviro+ + SCD41 CO2 Sensor**
```yaml
scd41:
  enabled: true
  altitude: 0  # Set your altitude
enviro:
  pm_sensor: false
mqtt:
  temp_humidity_mode: scd41_primary
```

**Configuration 3: Full Setup (Enviro+ + PMS5003 + SCD41)**
```yaml
scd41:
  enabled: true
  altitude: 0
enviro:
  pm_sensor: true
  pm_sleep_enabled: true  # Extends PM sensor life 6x+
  pm_sleep_duration: 180  # Sleep 3 min, wake 30s to read
mqtt:
  temp_humidity_mode: scd41_primary
```

**Note on PM Sensor Lifespan:** The PMS5003 has a limited lifespan (~11 months continuous use). Sleep cycling (enabled by default) extends this to 6+ years with no impact on data quality. See `docs/PM_SENSOR_LIFECYCLE.md`.

See `docs/HARDWARE_CONFIG.md` for detailed configuration guide for YOUR specific hardware.

### SCD41 Settings

```yaml
scd41:
  enabled: true
  altitude: 0  # Your altitude in meters
  temperature_offset: 4.0  # Adjust based on your setup
```

### Display Settings

```yaml
display:
  enabled: true
  brightness: 1.0  # 0.0 to 1.0
  screens:
    - co2_main      # Large CO2 display
    - enviro_temp   # Temperature & humidity
    - enviro_pm     # Particulate matter
    - summary       # All-in-one
```

### MQTT / Home Assistant

```yaml
mqtt:
  enabled: true
  broker: homeassistant.local  # MQTT broker address
  discovery: true  # Auto-discovery in Home Assistant
  base_topic: co2_monitor/sensor
  temp_humidity_mode: scd41_primary  # See Temperature Modes section
```

**Temperature/Humidity Reporting:**

You have TWO sensors measuring temp/humidity (SCD41 + BME280). Choose how to report them:

- **`scd41_primary`** (Recommended) - SCD41 as main sensor, BME280 as diagnostic
- **`scd41_only`** - Only report SCD41 (cleanest interface)
- **`average`** - Average of both sensors
- **`both`** - Report all four values separately

See `docs/TEMPERATURE_MODES.md` for detailed comparison and recommendations.

**MQTT Broker Setup:**

The `broker` address is your **MQTT broker**, which could be:

1. **Home Assistant Mosquitto addon**: Use Home Assistant's IP/hostname
   - `homeassistant.local` (if mDNS works)
   - `192.168.1.100` (Home Assistant IP address)

2. **Separate MQTT broker**: Use that broker's IP/hostname
   - `mqtt.local`
   - `192.168.1.50`

3. **External MQTT service**: Use the service hostname
   - `test.mosquitto.org` (public test broker)

**Authentication:**
- If your MQTT broker requires credentials, add them:
  ```yaml
  mqtt:
    username: mqtt_user
    password: mqtt_password
  ```
- Home Assistant Mosquitto addon users: Create a user in Home Assistant for MQTT access

## Display Screens

The LCD cycles through multiple screens:

1. **CO2 Main** - Large CO2 reading with color-coded status
2. **Temperature** - Temp/humidity from both SCD41 and Enviro+
3. **Particulate Matter** - PM1, PM2.5, PM10 levels
4. **Gas Sensors** - Oxidising, reducing, NH3
5. **Weather** - Pressure and light level
6. **Summary** - All key metrics at once

## Home Assistant Integration

The monitor automatically creates entities in Home Assistant via MQTT discovery:

- `sensor.co2` - CO2 level (ppm)
- `sensor.temperature_scd41` - Temperature from SCD41
- `sensor.humidity_scd41` - Humidity from SCD41
- `sensor.temperature_enviro` - Temperature from Enviro+
- `sensor.pm25` - PM2.5 particulate matter
- `sensor.pressure` - Atmospheric pressure
- And more...

### Example Home Assistant Card

```yaml
type: entities
title: CO2 Monitor
entities:
  - entity: sensor.co2
  - entity: sensor.temperature_scd41
  - entity: sensor.humidity_scd41
  - entity: sensor.pm25
  - entity: sensor.pressure
```

## CO2 Levels Guide

| CO2 (ppm) | Status | Color | Action |
|-----------|--------|-------|--------|
| < 800 | Good | Green | Normal ventilation |
| 800-1000 | Moderate | Yellow | Consider ventilation |
| 1000-1500 | Poor | Orange | Increase ventilation |
| > 1500 | Unhealthy | Red | Immediate ventilation needed |

## Troubleshooting

### Sensors Not Detected

```bash
# Check I2C devices
i2cdetect -y 1

# Should show:
# 0x62 - SCD41
# 0x76 or 0x77 - BME280
# 0x23 - LTR559
```

### High Temperature Readings

Adjust `temperature_offset` in config:

```yaml
scd41:
  temperature_offset: 6.0  # Increase if temps are too high
```

### MQTT Not Connecting

1. **Check MQTT broker is running**
   - If using Home Assistant Mosquitto addon:
     - Go to Settings → Add-ons → Mosquitto broker
     - Verify it's started
   
2. **Verify broker address**
   ```bash
   ping homeassistant.local
   # Or
   ping 192.168.1.100
   ```

3. **Check MQTT authentication**
   - If Mosquitto addon requires auth, create user in HA:
     - Settings → People → Users → Add user
     - Or use Home Assistant user credentials
   
4. **Test MQTT connection**
   ```bash
   # Install mosquitto-clients
   sudo apt-get install mosquitto-clients
   
   # Test publish (no auth)
   mosquitto_pub -h 192.168.1.100 -t test -m "hello"
   
   # Test publish (with auth)
   mosquitto_pub -h 192.168.1.100 -u username -P password -t test -m "hello"
   ```

5. **Check logs**
   ```bash
   tail -f logs/co2_monitor.log
   # Look for "Connected to MQTT broker" or error messages
   ```

6. **Common broker addresses:**
   - `homeassistant.local` - If mDNS/Avahi works
   - `192.168.1.X` - Home Assistant IP
   - `localhost` - If running on same machine (rare)
   - `core-mosquitto` - Docker internal (won't work from Pi)

### Display Not Working

1. Check SPI is enabled: `sudo raspi-config`
2. Verify connections
3. Check logs for errors

## Project Structure

```
co2-monitor/
├── src/
│   ├── main.py          # Main application
│   ├── sensors.py       # Sensor management
│   ├── display.py       # LCD display
│   └── mqtt_manager.py  # MQTT/Home Assistant
├── config/
│   └── config.yaml      # Configuration file
├── logs/                # Log files
├── requirements.txt     # Python dependencies
├── install.sh          # Installation script
└── README.md           # This file
```

## Systemd Service Commands

```bash
# Start service
sudo systemctl start co2-monitor

# Stop service
sudo systemctl stop co2-monitor

# View status
sudo systemctl status co2-monitor

# View logs
sudo journalctl -u co2-monitor -f

# Restart after config changes
sudo systemctl restart co2-monitor
```

## Updating

```bash
cd co2-monitor
git pull  # If using git
sudo systemctl restart co2-monitor
```

## Advanced Configuration

### Custom Display Rotation

```yaml
display:
  rotation: 90  # 0, 90, 180, or 270
```

### Data Logging

```yaml
logging:
  enabled: true
  log_file: logs/sensor_data.log
  rotation: daily
```

### Alerts (via MQTT)

```yaml
alerts:
  enabled: true
  co2_high: 1500
  co2_very_high: 2000
```

## Development

### Testing Individual Components

```bash
# Test sensors
python3 src/sensors.py

# Test display
python3 src/display.py

# Test MQTT
python3 src/mqtt_manager.py
```

### Adding New Screens

Edit `src/display.py` and add a new `_render_xxx()` method, then add the screen name to config:

```yaml
display:
  screens:
    - my_custom_screen
```

## License

MIT License - feel free to modify and use as you wish!

## Support

- Check logs: `logs/co2_monitor.log`
- Pimoroni support: https://forums.pimoroni.com/
- SCD41 info: https://github.com/pimoroni/scd4x-python

## Credits

Built with:
- Pimoroni Enviro+ libraries
- Pimoroni SCD4X library
- paho-mqtt for Home Assistant integration

