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

for pin in CS_PINS + [ST1, ST2, STBY] + DRDY_PINS:
    try: lgpio.gpio_free(h, pin)
    except: pass

for pin in CS_PINS + [STBY, ST1, ST2]:
    lgpio.gpio_claim_output(h, pin, 1 if pin in CS_PINS else 0)

for pin in DRDY_PINS:
    lgpio.gpio_claim_input(h, pin, lgpio.SET_PULL_UP)

spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 4000000
spi.mode = 0b01

def cs_pin(pin, val):
    lgpio.gpio_write(h, pin, 1 if val else 0)

def init_adcs():
    """Initialises all ADS1234 ADCs (Reset -> Config -> Start)."""
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

# -----------------------------------------------------------------
# TEST FLOW
# config.txt must have: gpio=25=op,dl  (STBY = LOW at boot)
# This script takes over and manually controls the wake/sleep cycle.
# -----------------------------------------------------------------

print("=" * 50)
print("ADXL354 Standby Toggle Test")
print("Expected boot state: STBY = LOW (gpio=25=op,dl)")
print("=" * 50)

# -- STEP 1: Confirm clean standby --------------------------------
print("\n[STEP 1] Explicitly holding STBY = LOW for 500ms (clean standby)")
lgpio.gpio_write(h, STBY, 0)   # Force LOW -- sensor in standby
time.sleep(0.5)

print("Reading while in Standby (all channels should be ~0.003V):")
init_adcs()
read_once()

# -- STEP 2: Wake the sensor --------------------------------------
print("\n[STEP 2] Driving STBY = HIGH (entering measurement mode)")
lgpio.gpio_write(h, STBY, 1)
print("Waiting 500ms for VREFOUT to stabilise...")
time.sleep(0.5)

print("Re-initialising ADCs after wake...")
init_adcs()

print("Reading in Measurement Mode (should be ~1.3V / 0.88V / 0.90V):")
read_once()

# -- STEP 3: Back to standby -------------------------------------
print("\n[STEP 3] Driving STBY = LOW again (back to standby)")
lgpio.gpio_write(h, STBY, 0)
time.sleep(0.5)

print("Reading in Standby again (should be ~0.003V):")
init_adcs()
read_once()

# -- STEP 4: Wake again ------------------------------------------
print("\n[STEP 4] Driving STBY = HIGH again (second recovery test)")
lgpio.gpio_write(h, STBY, 1)
time.sleep(0.5)
init_adcs()

print("Reading in Measurement Mode again (should recover to ~1.3V):")
read_once()

print("\nDone.")
spi.close()
lgpio.gpiochip_close(h)
spi.close()
