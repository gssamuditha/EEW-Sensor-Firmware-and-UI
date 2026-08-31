import lgpio
import time
import subprocess

STBY = 25

try:
    h = lgpio.gpiochip_open(0)
except:
    h = lgpio.gpiochip_open(4)

try:
    lgpio.gpio_claim_output(h, STBY, 1)
except:
    lgpio.gpio_free(h, STBY)
    lgpio.gpio_claim_output(h, STBY, 1)

print("I have told lgpio to set GPIO 25 (STBY) HIGH.")
print("Let's ask the Pi hardware what the actual physical pin state is...")

# Run pinctrl to get the hardware state
result = subprocess.run(['pinctrl', 'get', '25'], capture_output=True, text=True)
if not result.stdout:
    result = subprocess.run(['raspi-gpio', 'get', '25'], capture_output=True, text=True)

print("\nHardware Pin State:")
print(result.stdout)

print("\nKeeping pin high for 10 seconds...")
time.sleep(10)
lgpio.gpiochip_close(h)
