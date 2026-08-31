import spidev
import lgpio
import time
import sys

# BCM Pins ONLY FOR ADXL354 (GeoPhone Ch1 ignored)
CS_PINS = [19, 13, 16]
DRDY_PINS = [17, 22, 27] 
ST1 = 23
ST2 = 24
STBY = 25

VREF = 1.8
FULL_SCALE = 8388607

try:
    h = lgpio.gpiochip_open(0)
except Exception:
    h = lgpio.gpiochip_open(4)

# Free pins if previously used
for pin in CS_PINS + [ST1, ST2, STBY] + DRDY_PINS:
    try:
        lgpio.gpio_free(h, pin)
    except:
        pass

for pin in CS_PINS + [ST1, ST2, STBY]:
    lgpio.gpio_claim_output(h, pin, 1 if pin in CS_PINS + [STBY] else 0)

for pin in DRDY_PINS:
    lgpio.gpio_claim_input(h, pin, lgpio.SET_PULL_UP)

spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 4000000  # MUST be 4MHz — ADC reads 0.003V at 1MHz
spi.mode = 0b01
spi.no_cs = True  # We still need this because 19, 13, 16 are standard GPIOs, not hardware CS pins!

def gpio_out(pin, val):
    lgpio.gpio_write(h, pin, 1 if val else 0)

print("Waking up ADXL354 (STBY -> HIGH)...")
gpio_out(ST1, False)
gpio_out(ST2, False)
gpio_out(STBY, True)
print("Warming up sensor... (12 seconds — required on cold start)")
for i in range(12, 0, -1):
    print(f"  {i}s remaining...", end='\r')
    time.sleep(1)
print("Warmup complete.                  ")

# Reset & Config ADCs with PROPER CS TOGGLING
for cs in CS_PINS:
    gpio_out(cs, False)
    time.sleep(0.0001)
    spi.xfer2([0x06])
    gpio_out(cs, True)
    time.sleep(0.1)
    
    gpio_out(cs, False)
    time.sleep(0.0001)
    spi.xfer2([0x42, 0x81, 0x80, 0x40])
    gpio_out(cs, True)
    time.sleep(0.1)

print("Reading live data for ADXL only. Please move the sensor!")

try:
    while True:
        # Start conversion SEQUENTIALLY to avoid MISO short-circuit!
        for cs in CS_PINS:
            gpio_out(cs, False)
            spi.xfer2([0x08])
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
            
        print(f"Ch2 (ENZ): {voltages[0]:.4f}V | Ch3 (ENN): {voltages[1]:.4f}V | Ch4 (ENE): {voltages[2]:.4f}V")
        time.sleep(0.1)

except KeyboardInterrupt:
    print("\nStopped.")
finally:
    spi.close()
    lgpio.gpiochip_close(h)
