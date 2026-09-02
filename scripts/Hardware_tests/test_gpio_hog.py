import spidev
import lgpio
import time
import sys

CS_PINS = [19, 13, 16]
DRDY_PINS = [17, 22, 27]
ST1 = 23
ST2 = 24
STBY = 25

VREF = 1.8
FULL_SCALE = 8388607

# GPIO Setup
try:
    h = lgpio.gpiochip_open(0)
except:
    h = lgpio.gpiochip_open(4)

for pin in CS_PINS + [ST1, ST2] + DRDY_PINS:
    try: lgpio.gpio_free(h, pin)
    except: pass

# Claim standard pins
for pin in CS_PINS + [ST1, ST2]:
    lgpio.gpio_claim_output(h, pin, 1 if pin in CS_PINS else 0)

# ---------------------------------------------------------
# STBY PIN HANDLING FOR GPIO-HOG
# ---------------------------------------------------------
try:
    lgpio.gpio_claim_output(h, STBY, 1)
    print("Warning: Claimed STBY successfully. The GPIO hog might not be working!")
except Exception as e:
    print(f"Info: Could not claim STBY ({e}). This is expected if the kernel GPIO hog is active!")

for pin in DRDY_PINS:
    lgpio.gpio_claim_input(h, pin, lgpio.SET_PULL_UP)

spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 4000000
spi.mode = 0b01

def cs_pin(pin, val):
    lgpio.gpio_write(h, pin, 1 if val else 0)

def init_adcs():
    """Initialises all ADS1234 ADCs."""
    print("Initialising ADCs...")
    for pin in CS_PINS:
        cs_pin(pin, False)
        time.sleep(0.000001)
        spi.xfer2([0x06])                    # RESET
        time.sleep(0.1)
        spi.xfer2([0x42, 0x81, 0x80, 0x40]) # WREG: configure
        spi.xfer2([0x08])                    # START conversion
        cs_pin(pin, True)
        time.sleep(0.1)

def read_once():
    """Reads all 3 ADC channels once and prints the voltages."""
    results = []
    for i in range(3):
        cs_pin(CS_PINS[i], False)
        t0 = time.time()
        while lgpio.gpio_read(h, DRDY_PINS[i]) != 0:
            if time.time() - t0 > 1.0:
                cs_pin(CS_PINS[i], True)
                results.append(None)
                break
        else:
            data = spi.xfer2([0x00, 0x00, 0x00])
            cs_pin(CS_PINS[i], True)
            raw = (data[0] << 16) | (data[1] << 8) | data[2]
            if raw & (1 << 23):
                raw -= (1 << 24)
            results.append((raw / FULL_SCALE) * VREF)
    labels = ["ENZ", "ENN", "ENE"]
    for i, v in enumerate(results):
        print(f"  {labels[i]}: {v:.4f}V" if v is not None else f"  {labels[i]}: DRDY TIMEOUT")

print("=" * 50)
print("ADXL354 GPIO Hog Test")
print("=" * 50)

init_adcs()

print("\nReading data (assuming STBY is held HIGH by the kernel):")
for _ in range(3):
    read_once()
    time.sleep(0.5)

print("\nDone.")
spi.close()
lgpio.gpiochip_close(h)
