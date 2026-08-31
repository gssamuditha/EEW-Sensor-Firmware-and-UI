import spidev
import lgpio
import time
import sys

CS_PINS = [8, 19, 13, 16]

try:
    h = lgpio.gpiochip_open(0)
except Exception:
    h = lgpio.gpiochip_open(4)

for pin in CS_PINS:
    try:
        lgpio.gpio_claim_output(h, pin, 1)
    except:
        lgpio.gpio_free(h, pin)
        lgpio.gpio_claim_output(h, pin, 1)

spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 1000000
spi.mode = 0b01
spi.no_cs = True

def gpio_out(pin, val):
    lgpio.gpio_write(h, pin, 1 if val else 0)

try:
    print("Configuring ADCs...")
    for cs in CS_PINS:
        # Reset
        gpio_out(cs, False)
        time.sleep(0.0001)
        spi.xfer2([0x06])
        time.sleep(0.1)
        gpio_out(cs, True)
        time.sleep(0.1)
        
        # Write Config
        gpio_out(cs, False)
        time.sleep(0.0001)
        spi.xfer2([0x42, 0x81, 0x80, 0x40])
        gpio_out(cs, True)
        time.sleep(0.1)

    print("\nReading Registers back...")
    for i, cs in enumerate(CS_PINS):
        gpio_out(cs, False)
        time.sleep(0.0001)
        spi.xfer2([0x23])
        resp = spi.xfer2([0x00, 0x00, 0x00, 0x00])
        gpio_out(cs, True)
        
        hex_resp = [hex(x) for x in resp]
        print(f"ADC {i+1} (CS {cs}): {hex_resp}")
        if resp != [0x81, 0x80, 0x40, 0x00]:
            print(f"  -> ERROR! ADC {i+1} configuration failed.")
        else:
            print(f"  -> SUCCESS! ADC {i+1} configured correctly.")
        time.sleep(0.1)

finally:
    spi.close()
    lgpio.gpiochip_close(h)
