import spidev
import lgpio
import time
import sys

# BCM Pins
CS_PINS = [8, 19, 13, 16]   # EHZ, ENZ, ENN, ENE
DRDY_PINS = [3, 17, 22, 27] 
ST1 = 23
ST2 = 24
STBY = 25

VREF = 1.8
FULL_SCALE = 8388607

# Setup GPIO
try:
    h = lgpio.gpiochip_open(0)
except Exception:
    h = lgpio.gpiochip_open(4)

for pin in CS_PINS + [ST1, ST2, STBY]:
    try:
        lgpio.gpio_claim_output(h, pin, 1 if pin in CS_PINS + [STBY] else 0)
    except:
        lgpio.gpio_free(h, pin)
        lgpio.gpio_claim_output(h, pin, 1 if pin in CS_PINS + [STBY] else 0)

for pin in DRDY_PINS:
    try:
        lgpio.gpio_claim_input(h, pin, lgpio.SET_PULL_UP)
    except:
        lgpio.gpio_free(h, pin)
        lgpio.gpio_claim_input(h, pin, lgpio.SET_PULL_UP)

# Setup SPI
spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 1000000
spi.mode = 0b01
spi.no_cs = True

def gpio_out(pin, val):
    lgpio.gpio_write(h, pin, 1 if val else 0)

print("Initializing ADCs...")
# STBY high
gpio_out(ST1, False)
gpio_out(ST2, False)
gpio_out(STBY, True)
time.sleep(0.5)

# Reset & Config ADCs
for cs in CS_PINS:
    gpio_out(cs, False)
    time.sleep(0.0001)
    spi.xfer2([0x06])
    time.sleep(0.1)
    spi.xfer2([0x42, 0x81, 0x80, 0x40])
    spi.xfer2([0x08]) # start
    gpio_out(cs, True)
    time.sleep(0.1)

print("Reading live data. Please move the sensor!")
print("Press Ctrl+C to stop.\n")

try:
    while True:
        # Start conversion
        for cs in CS_PINS:
            gpio_out(cs, False)
        spi.xfer2([0x08])
        for cs in CS_PINS:
            gpio_out(cs, True)

        # Wait DRDY
        start = time.time()
        while True:
            if all(lgpio.gpio_read(h, pin) == 0 for pin in DRDY_PINS):
                break
            if time.time() - start > 2:
                print("Timeout waiting for DRDY!")
                sys.exit(1)
                
        # Read data
        voltages = []
        for cs in CS_PINS:
            gpio_out(cs, False)
            data = spi.xfer2([0x00, 0x00, 0x00])
            gpio_out(cs, True)
            
            raw = (data[0] << 16) | (data[1] << 8) | data[2]
            if raw & (1 << 23):
                raw -= (1 << 24)
                
            voltage = (raw / FULL_SCALE) * VREF
            voltages.append(voltage)
            
        print(f"Ch1: {voltages[0]:.4f}V | Ch2 (ENZ): {voltages[1]:.4f}V | Ch3 (ENN): {voltages[2]:.4f}V | Ch4 (ENE): {voltages[3]:.4f}V")
        time.sleep(0.1)

except KeyboardInterrupt:
    print("\nStopped.")
finally:
    spi.close()
    lgpio.gpiochip_close(h)
