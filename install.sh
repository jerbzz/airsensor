#!/bin/bash
# Air Sensor Installation Script
# Run with: bash install.sh

set -e

echo "Installing Airsensor Python Application..."
echo "Your password may be required to install system files."

if [ "$(id -u)" -eq 0 ]; then
    fatal "This script should not be run as root. Try './install.sh'\n"
fi

# Check if running on Raspberry Pi
if ! grep -q "Raspberry Pi" /proc/cpuinfo; then
    echo "Warning: This device doesn't appear to be a Raspberry Pi."
    read -p "This software may not work at all. Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Update system
echo "Updating system packages..."
sudo apt-get update

# Install system dependencies
echo "Installing system dependencies..."
sudo apt-get install -y \
    python3-pip \
    python3-dev \
    python3-smbus \
    i2c-tools \
    git \
    fonts-dejavu \
    fonts-dejavu-core

# Enable I2C and SPI
echo "Enabling I2C and SPI..."
sudo raspi-config nonint do_i2c 0
sudo raspi-config nonint do_spi 0

# Creating airsensor user 
echo "Creating airsensor user to run application as systemd service..."
if id "airsensor" >/dev/null 2>&1; then
    sudo deluser airsensor
    sudo useradd --system --no-create-home --shell /usr/sbin/nologin -U airsensor
else
    sudo useradd --system --no-create-home --shell /usr/sbin/nologin -U airsensor
fi

# Add to various groups to enable hardware access
sudo usermod -a -G gpio airsensor      # GPIO access
sudo usermod -a -G i2c airsensor       # I2C sensors (BME280, LTR559, etc.)
sudo usermod -a -G spi airsensor       # SPI (ST7735 display)
sudo usermod -a -G dialout airsensor   # Serial port (PMS5003)

# Create necessary directories
echo "Creating Application Directory at /opt/airsensor..."

if [ -d "/opt/airsensor" ]; then
  sudo rm -rf /opt/airsensor
  sudo mkdir /opt/airsensor
else
  sudo mkdir /opt/airsensor
fi

sudo chown -R airsensor:airsensor /opt/airsensor

echo "Fetching project files from GitHub..."
sudo -u airsensor git clone https://github.com/jerbzz/airsensor /opt/airsensor

echo "Creating logs directory..."
sudo -u airsensor mkdir /opt/airsensor/logs

echo "Creating Python Virtual Environment..."
sudo -u airsensor python -m venv /opt/airsensor/.venv/airsensor

echo "Installing Python dependencies..."
sudo -u airsensor /opt/airsensor/.venv/airsensor/bin/pip3 install -r /opt/airsensor/requirements.txt --cache-dir=/opt/airsensor/.venv/pip-cache

echo "Checking I2C devices..."
sudo -u airsensor i2cdetect -y 1

echo ""
echo "You should see:"
echo "  - 0x23 (LTR559 light sensor)"
echo "  - 0x49 (MICS6814 gas sensors)"
echo "  - 0x62 (SCD41 CO2 sensor, if connected)"
echo "  - 0x76 (BME280 temp/humidity/pressure)"
echo ""

# Copy example config if needed
echo "Copying default configuration..."
if [ ! -f /opt/airsensor/config/config.yaml ]; then
    sudo -u airsensor cp /opt/airsensor/config/config.yaml.default /opt/airsensor/config/config.yaml
    echo "Config file created at config/config.yaml"
    echo "Please edit this file with your settings before running."
fi

# Install systemd service
sudo cp /opt/airsensor/airsensor.service /etc/systemd/system/

echo "Installation Complete!"
echo ""
echo "Next steps:"
echo "  1. Edit /opt/airsensor/config/config.yaml with your settings incuding updating MQTT broker address for Home Assistant"
echo "  2. Start the service: 'sudo systemctl enable airsensor && sudo systemctl start airsensor'."
echo "  3. Check it's running properly by observing the Enviro+ screen."
echo "  4. 'sudo systemctl status airsensor' will tell you more."
