#!/bin/bash
# Air Sensor Installation Script
# Run with: bash install.sh

set -e

echo "=========================================="
echo "  Air Sensor Installation"
echo "=========================================="
echo ""

# Check if running on Raspberry Pi
if ! grep -q "Raspberry Pi" /proc/cpuinfo; then
    echo "Warning: This device doesn't appear to be a Raspberry Pi."
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Update system
echo "Updating system packages..."
sudo apt-get update

# Enable I2C and SPI
echo "Enabling I2C and SPI..."
sudo raspi-config nonint do_i2c 0
sudo raspi-config nonint do_spi 0

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
	
# Install Python packages
echo "Installing Python dependencies..."
pip3 install -r requirements.txt

# Create necessary directories
echo "Creating directories..."
mkdir -p logs
mkdir -p config

# Check I2C devices
echo ""
echo "=========================================="
echo "Checking I2C devices..."
echo "=========================================="
i2cdetect -y 1

echo ""
echo "You should see:"
echo "  - 0x23 (LTR559 light sensor)"
echo "  - 0x49 (MICS6814 gas sensors)"
echo "  - 0x62 (SCD41 CO2 sensor, if connected)"
echo "  - 0x76 (BME280 temp/humidity/pressure)"
echo ""

# Copy example config if needed
if [ ! -f config/config.yaml ]; then
    cp config/config.yaml.default config/config.yaml
    echo "Config file created at config/config.yaml"
    echo "Please edit this file with your settings before running."
fi

echo ""
echo "=========================================="
echo "  Installation Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Edit config/config.yaml with your settings"
echo "  2. Update MQTT broker address for Home Assistant"
echo "  3. Run: python3 src/main.py"
echo ""
echo "To run automatically on boot:"
echo "  sudo cp airsensor.service /etc/systemd/system/"
echo "  sudo systemctl enable airsensor"
echo "  sudo systemctl start airsensor"
echo ""
