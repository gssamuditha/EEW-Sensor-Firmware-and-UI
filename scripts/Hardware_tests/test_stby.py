import spidev
import time
import sys
import RPi.GPIO as GPIO

# BCM Pins
CS_PINS = [8, 19, 13, 16]
DRDY_PINS = [3, 17, 22, 27] 
ST1 = 23
ST2 = 24
STBY = 25

VREF = 1.8
FULL_SCALE = 8388607

# USE RPi.GPIO INSTEAD OF LGPIO TO TEST IF IT'S A SOFTWARE BUG
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
for pin in CS_PINS + [ST1, ST2, STBY]:
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.HIGH if pin in CS_PINS else GPIO.LOW)

for pin in DRDY_PINS:
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 4000000  # MUST be 4MHz — ADC reads 0.003V at 1MHz
spi.mode = 0b01
spi.no_cs = True

def gpio_out(pin, val):
    GPIO.output(pin, GPIO.HIGH if val else GPIO.LOW)

print("Initializing ADCs (Using RPi.GPIO)...")
gpio_out(ST1, False)
gpio_out(ST2, False)
gpio_out(STBY, True)  # WAKE UP!
time.sleep(1)

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

print("Reading live data. Please move the sensor!")

try:
    for _ in range(50):
        # Start conversion
        for cs in CS_PINS:
            gpio_out(cs, False)
        spi.xfer2([0x08])
        for cs in CS_PINS:
            gpio_out(cs, True)

        # Wait DRDY
        start = time.time()
        while True:
            if all(GPIO.input(pin) == 0 for pin in DRDY_PINS):
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
    pass
finally:
    spi.close()
    GPIO.cleanup()
