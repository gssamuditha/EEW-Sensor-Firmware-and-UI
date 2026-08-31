import time
import sys
import os

# Add backend dir to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))
from sensor import RealSensor

try:
    sensor = RealSensor()
    sensor.init_sensor()

    print("Starting diagnostics...")
    for _ in range(5):
        t0 = time.time()
        sensor._start_conversion_all()
        t1 = time.time()
        v0 = sensor._read_adc(0)
        t2 = time.time()
        v1 = sensor._read_adc(1)
        t3 = time.time()
        v2 = sensor._read_adc(2)
        t4 = time.time()
        print(f"Start: {(t1-t0)*1000:.3f}ms, ADC0: {(t2-t1)*1000:.3f}ms, ADC1: {(t3-t2)*1000:.3f}ms, ADC2: {(t4-t3)*1000:.3f}ms, Total: {(t4-t0)*1000:.3f}ms")
        time.sleep(0.01)
except Exception as e:
    print(f"Error: {e}")
