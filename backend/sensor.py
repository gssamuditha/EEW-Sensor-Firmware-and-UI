import time
import socket
import threading
import asyncio
import random
import sys
import json

from database import insert_batch

# === ADC Config ===
CS_PINS = [35, 33, 36]        # Acc Z, Acc X, Acc Y
DRDY_PINS = [11, 15, 13]
VREF_ADCS = [1.8, 1.8, 1.8]
FULL_SCALE = 8388607
CHANNEL_NAMES = ['ENZ', 'ENN', 'ENE']
SAMPLES_PER_PACKET = 25
SAMPLE_INTERVAL = 0.0035  # 100 sps

# === Accelerometer Settings ===
ACC_ZERO_VOLTAGES = [0.0, 0.0, 0.0]  # To be calibrated
ACC_SENSITIVITY_V_PER_G = 0.4
G_TO_MS2 = 9.80665

# === Sensor Control Pins ===
ST1 = 16
ST2 = 18
STBY = 22

class MockSensor:
    def __init__(self):
        self.sample_interval = 0.01  # 100 sps
        self.channels = ['ENZ', 'ENN', 'ENE']
        
    def init_sensor(self):
        print("Mock sensor initialized")
        
    def calibrate(self):
        print("Mock sensor calibrated")
        time.sleep(1)
        
    def read_all(self):
        # Generate some realistic looking sine wave + noise data
        t = time.time()
        z = 0.5 * random.random() + 0.1
        x = 0.5 * random.random() - 0.2
        y = 0.5 * random.random() + 0.05
        return (t, z, x, y)


class RealSensor:
    def __init__(self):
        import spidev
        import RPi.GPIO as GPIO
        self.spidev = spidev
        self.GPIO = GPIO
        
        self.spi = spidev.SpiDev()
        self.spi.open(0, 0)
        self.spi.max_speed_hz = 4000000
        self.spi.mode = 0b01
        
    def init_sensor(self):
        self.GPIO.setwarnings(False)
        self.GPIO.setmode(self.GPIO.BOARD)

        self.GPIO.setup(ST1, self.GPIO.OUT)
        self.GPIO.setup(ST2, self.GPIO.OUT)
        self.GPIO.setup(STBY, self.GPIO.OUT)

        self.GPIO.output(ST1, self.GPIO.LOW)
        self.GPIO.output(ST2, self.GPIO.LOW)
        self.GPIO.output(STBY, self.GPIO.HIGH)
        time.sleep(10)

        for cs in CS_PINS:
            self.GPIO.setup(cs, self.GPIO.OUT)
            self.GPIO.output(cs, self.GPIO.HIGH)

        for drdy in DRDY_PINS:
            self.GPIO.setup(drdy, self.GPIO.IN, pull_up_down=self.GPIO.PUD_UP)
            
        time.sleep(1)
        self._adc_init_all()
        for _ in range(5):
            self._start_conversion_all()
            for i in range(3):
                try:
                    self._read_adc(i)
                except Exception:
                    pass
            time.sleep(0.01)
            
    def _adc_init_all(self):
        for i in range(3):
            self.GPIO.output(CS_PINS[i], self.GPIO.LOW)
            time.sleep(0.000001)
            self.spi.xfer2([0x06])
            time.sleep(0.1)
            self.spi.xfer2([0x42, 0x81, 0x60, 0x40])
            self.spi.xfer2([0x08])
            self.GPIO.output(CS_PINS[i], self.GPIO.HIGH)
            time.sleep(0.1)

    def _start_conversion_all(self):
        for cs in CS_PINS:
            self.GPIO.output(cs, self.GPIO.LOW)
        self.spi.xfer2([0x08])
        for cs in CS_PINS:
            self.GPIO.output(cs, self.GPIO.HIGH)

    def _read_adc(self, i, return_raw=False):
        self.GPIO.output(CS_PINS[i], self.GPIO.LOW)
        start = time.time()
        while self.GPIO.input(DRDY_PINS[i]):
            if time.time() - start > 0.15:
                raise TimeoutError(f"DRDY timeout on ADC {i}")
            time.sleep(0.0001)
        data = self.spi.xfer2([0x00, 0x00, 0x00])
        self.GPIO.output(CS_PINS[i], self.GPIO.HIGH)
        raw = (data[0] << 16) | (data[1] << 8) | data[2]
        if raw & (1 << 23):
            raw -= (1 << 24)
        if return_raw:
            return raw
        voltage = (raw / FULL_SCALE) * VREF_ADCS[i]
        return voltage
        
    def calibrate(self, calibration_time_sec=1):
        print(f"Starting accelerometer zero-level calibration for {calibration_time_sec} seconds...")
        samples = [[], [], []]  # For Z, X, Y
        start_time = time.time()
        while time.time() - start_time < calibration_time_sec:
            self._start_conversion_all()
            for axis in range(3):
                voltage = self._read_adc(axis)
                samples[axis].append(voltage)
            time.sleep(SAMPLE_INTERVAL)

        for i in range(3):
            ACC_ZERO_VOLTAGES[i] = sum(samples[i]) / len(samples[i])

        print("Calibration complete. Zero-level voltages (V):")
        print(f"Z: {ACC_ZERO_VOLTAGES[0]:.6f} V, X: {ACC_ZERO_VOLTAGES[1]:.6f} V, Y: {ACC_ZERO_VOLTAGES[2]:.6f} V")

    def read_all(self):
        self._start_conversion_all()
        readings = []
        for i in range(3):
            voltage = self._read_adc(i)
            zero_voltage = ACC_ZERO_VOLTAGES[i]
            g_val = (voltage - zero_voltage) / ACC_SENSITIVITY_V_PER_G
            ms2 = g_val * G_TO_MS2
            readings.append(ms2)
        return (time.time(), readings[0], readings[1], readings[2])

class SensorManager:
    def __init__(self, use_mock=False):
        self.use_mock = use_mock
        if use_mock:
            self.sensor = MockSensor()
        else:
            self.sensor = RealSensor()
            
        self.running = False
        self.thread = None
        self.subscribers = []  # asyncio queues
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.hardware_sps = 0
        self.avg_sps = 0
        
    def start(self):
        self.sensor.init_sensor()
        self.sensor.calibrate()
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
            
    def subscribe(self, queue):
        self.subscribers.append(queue)
        
    def unsubscribe(self, queue):
        if queue in self.subscribers:
            self.subscribers.remove(queue)
            
    def _run_loop(self):
        from database import get_settings
        buffer = []
        udp_buffers = [[], [], []]

        # SPS tracking (matching ADXL354.py)
        total_samples = 0
        total_time = 0
        packet_start_time = None
        sample_count = 0

        while self.running:
            try:
                # Track packet timing
                if sample_count == 0:
                    packet_start_time = time.time()

                t, z, x, y = self.sensor.read_all()
                record = (t, z, x, y)
                buffer.append(record)
                sample_count += 1

                # Push to websockets (evict oldest on overflow instead of dropping)
                for q in self.subscribers:
                    try:
                        q.put_nowait(record)
                    except asyncio.QueueFull:
                        try:
                            q.get_nowait()  # evict oldest
                        except:
                            pass
                        try:
                            q.put_nowait(record)
                        except:
                            pass

                # SPS calculation per packet batch (matching ADXL354.py)
                if sample_count >= SAMPLES_PER_PACKET:
                    end_time = time.time()
                    elapsed = end_time - packet_start_time
                    sps = SAMPLES_PER_PACKET / elapsed if elapsed > 0 else 0

                    total_samples += SAMPLES_PER_PACKET
                    total_time += elapsed
                    overall_sps = total_samples / total_time if total_time > 0 else 0

                    self.hardware_sps = round(sps, 2)
                    self.avg_sps = round(overall_sps, 2)

                    print(f"📊 Per-Channel Sample Rates:")
                    for name in CHANNEL_NAMES:
                        print(f"   {name}: {sps:.2f} samples/sec (current), {overall_sps:.2f} samples/sec (avg)")

                    sample_count = 0

                # Prepare UDP
                settings = get_settings()
                targets_str = settings.get('targets', '[]')
                try:
                    targets = json.loads(targets_str)
                except:
                    targets = []

                if targets:
                    if len(udp_buffers[0]) == 0:
                        timestamp = t
                    udp_buffers[0].append(z)
                    udp_buffers[1].append(x)
                    udp_buffers[2].append(y)

                    if len(udp_buffers[0]) >= SAMPLES_PER_PACKET:
                        for i, name in enumerate(CHANNEL_NAMES):
                            packet = [name, timestamp] + udp_buffers[i]
                            data = str(packet).encode()
                            for target in targets:
                                self.sock.sendto(data, (target['ip'], target['port']))
                        udp_buffers = [[], [], []]

                # Batch save to DB every 50 samples
                if len(buffer) >= 50:
                    insert_batch(buffer)
                    buffer = []

                time.sleep(SAMPLE_INTERVAL)
            except Exception as e:
                print(f"Sensor read error: {e}")
                time.sleep(1)

# Global manager instance
sensor_manager = SensorManager(use_mock=sys.platform == 'win32')
