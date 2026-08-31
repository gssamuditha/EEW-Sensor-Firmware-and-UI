"""
pi3_style.py - Replicates ADXL354.py (Pi 3) exactly, using lgpio
=================================================================
The Pi 3 script (ADXL354.py) uses a different read approach:
  - CS goes LOW before waiting for DRDY
  - CS stays LOW during the read
  - No explicit START per loop iteration
  - No CS toggling between init commands (all in one CS frame)

This script replicates that exactly using lgpio to isolate whether
the issue is the GPIO library or the read/init approach.
"""
import spidev
import lgpio
import time
import sys

# BCM pins - same as Pi 3 ADXL354.py board pins [35,33,36] -> BCM [19,13,16]
CS_PINS   = [19, 13, 16]     # ENZ, ENN, ENE
DRDY_PINS = [17, 22, 27]     # ENZ, ENN, ENE
ST1  = 23
ST2  = 24
STBY = 25

VREF       = 1.8
FULL_SCALE = 8388607

# GPIO setup
try:
    h = lgpio.gpiochip_open(0)
except Exception:
    h = lgpio.gpiochip_open(4)

for pin in CS_PINS + [ST1, ST2, STBY] + DRDY_PINS:
    try:
        lgpio.gpio_free(h, pin)
    except Exception:
        pass

for pin in CS_PINS + [STBY]:
    lgpio.gpio_claim_output(h, pin, 1)   # CS and STBY start HIGH

for pin in [ST1, ST2]:
    lgpio.gpio_claim_output(h, pin, 0)

for pin in DRDY_PINS:
    lgpio.gpio_claim_input(h, pin, lgpio.SET_PULL_UP)

# SPI - 4MHz. No spi.no_cs = True to match Pi 3 behaviour exactly.
spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 4000000
spi.mode = 0b01

def cs_pin(pin, val):
    lgpio.gpio_write(h, pin, 1 if val else 0)

# Step 1: Wake sensor - long warmup matching Pi 3 code (10+ seconds)
print("Setting STBY HIGH, waiting 12 seconds (same delay as Pi 3 code)...")
lgpio.gpio_write(h, ST1, 0)
lgpio.gpio_write(h, ST2, 0)
lgpio.gpio_write(h, STBY, 1)
for i in range(12, 0, -1):
    print(f"  {i}s...", end='\r', flush=True)
    time.sleep(1)
print("Warmup complete.        ")

# Step 2: Init ADCs - EXACTLY like ADXL354.py
# No CS toggle between RESET/WREG/START — all in one CS-LOW frame
print("Initializing ADCs (Pi 3 style: all commands in one CS frame)...")
for pin in CS_PINS:
    cs_pin(pin, False)           # CS LOW — stays LOW through all 3 commands
    time.sleep(0.000001)
    spi.xfer2([0x06])            # RESET
    time.sleep(0.1)
    spi.xfer2([0x42, 0x81, 0x60, 0x40])  # WREG
    spi.xfer2([0x08])            # START
    cs_pin(pin, True)            # CS HIGH
    time.sleep(0.1)

# Step 3: Read - EXACTLY like ADXL354.py
# CS goes LOW first, THEN wait for DRDY, THEN read, THEN CS HIGH
print("Reading (Pi 3 style: CS LOW while waiting for DRDY)...")
print("Expected: ENZ ~1.3V | ENN ~0.88V | ENE ~0.90V\n")

def read_adc(i):
    """Exact replica of ADXL354.py read_adc() logic using lgpio."""
    cs_pin(CS_PINS[i], False)              # CS LOW first
    t0 = time.time()
    while lgpio.gpio_read(h, DRDY_PINS[i]) != 0:   # Wait for THIS ADC's DRDY
        if time.time() - t0 > 2.0:
            print(f"\nDRDY timeout on ADC {i}!")
            return None
        time.sleep(0.0001)
    data = spi.xfer2([0x00, 0x00, 0x00])
    cs_pin(CS_PINS[i], True)              # CS HIGH after read
    raw = (data[0] << 16) | (data[1] << 8) | data[2]
    if raw & (1 << 23):
        raw -= (1 << 24)
    return (raw / FULL_SCALE) * VREF

try:
    while True:
        voltages = []
        for i in range(len(CS_PINS)):
            v = read_adc(i)
            if v is None:
                sys.exit(1)
            voltages.append(v)
        print(f"ENZ: {voltages[0]:.4f}V | ENN: {voltages[1]:.4f}V | ENE: {voltages[2]:.4f}V")

except KeyboardInterrupt:
    print("\nStopped.")
finally:
    spi.close()
    lgpio.gpiochip_close(h)
