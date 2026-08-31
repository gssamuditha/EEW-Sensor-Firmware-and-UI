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
    """Initializes the ADS1234 ADCs."""
    for pin in CS_PINS:
        cs_pin(pin, False)
        time.sleep(0.000001)
        spi.xfer2([0x06]) # Reset
        time.sleep(0.1)
        spi.xfer2([0x42, 0x81, 0x80, 0x40]) # Config
        spi.xfer2([0x08]) # Start
        cs_pin(pin, True)
        time.sleep(0.1)

def read_adc(i):
    """Reads a single ADC."""
    cs_pin(CS_PINS[i], False)
    t0 = time.time()
    while lgpio.gpio_read(h, DRDY_PINS[i]) != 0:
        if time.time() - t0 > 0.5:
            cs_pin(CS_PINS[i], True)
            return None
    data = spi.xfer2([0x00, 0x00, 0x00])
    cs_pin(CS_PINS[i], True)
    raw = (data[0] << 16) | (data[1] << 8) | data[2]
    if raw & (1 << 23):
        raw -= (1 << 24)
    return (raw / FULL_SCALE) * VREF

print("--- ADXL354 Standby Toggle Test ---")
print("1. Waking up ADXL354 (STBY = HIGH)")
lgpio.gpio_write(h, STBY, 1)
time.sleep(1) # Give it time to wake up
init_adcs()

print("\nReading ADCs in Measurement Mode:")
for i in range(3):
    v = read_adc(i)
    print(f"  ADC {i}: {v:.4f}V" if v is not None else f"  ADC {i}: TIMEOUT")

print("\n2. Putting ADXL354 in Standby Mode (STBY = LOW)")
lgpio.gpio_write(h, STBY, 0)
time.sleep(1) # Allow it to power down VREFOUT

print("\nReading ADCs in Standby Mode (Expected: ~0.003V or Timeout):")
for i in range(3):
    v = read_adc(i)
    print(f"  ADC {i}: {v:.4f}V" if v is not None else f"  ADC {i}: TIMEOUT")

print("\n3. Waking up ADXL354 again (STBY = HIGH)")
lgpio.gpio_write(h, STBY, 1)
time.sleep(1) # Give it time to wake up VREFOUT
init_adcs() # Re-init ADCs just in case

print("\nReading ADCs in Measurement Mode (Should recover):")
for i in range(3):
    v = read_adc(i)
    print(f"  ADC {i}: {v:.4f}V" if v is not None else f"  ADC {i}: TIMEOUT")

lgpio.gpiochip_close(h)
spi.close()
