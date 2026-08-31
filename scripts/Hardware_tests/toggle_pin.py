import lgpio
import time

PIN = 25 # BCM 25, Physical Board Pin 22

try:
    h = lgpio.gpiochip_open(0)
except Exception:
    h = lgpio.gpiochip_open(4)

try:
    lgpio.gpio_claim_output(h, PIN, 0)
except:
    lgpio.gpio_free(h, PIN)
    lgpio.gpio_claim_output(h, PIN, 0)

print(f"Toggling BCM GPIO {PIN} (Physical Board Pin 22) every 5 seconds.")
print("Use your multimeter to measure the voltage between Pin 22 and Ground (e.g. Pin 39).")
print("Press Ctrl+C to stop.\n")

state = 0
try:
    while True:
        state = 1 if state == 0 else 0
        lgpio.gpio_write(h, PIN, state)
        if state == 1:
            print("Pin is now commanded HIGH (Should measure ~3.3V)")
        else:
            print("Pin is now commanded LOW  (Should measure ~0.0V)")
        time.sleep(5)
except KeyboardInterrupt:
    print("\nStopped.")
finally:
    lgpio.gpiochip_close(h)
