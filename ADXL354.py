import spidev
import RPi.GPIO as GPIO
import time
import socket

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

ST1 = 16
ST2 = 18
STBY = 22
# === Sensor Control Pin ===
#STBY = 16

# === SPI and GPIO Setup ===
spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 4000000
spi.mode = 0b01

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BOARD)

GPIO.setup(ST1, GPIO.OUT)
GPIO.setup(ST2, GPIO.OUT)
GPIO.setup(STBY, GPIO.OUT)

GPIO.output(ST1, GPIO.LOW)
GPIO.output(ST2, GPIO.LOW)
GPIO.output(STBY, GPIO.HIGH)
time.sleep(10)

for cs in CS_PINS:
    GPIO.setup(cs, GPIO.OUT)
    GPIO.output(cs, GPIO.HIGH)

for drdy in DRDY_PINS:
    GPIO.setup(drdy, GPIO.IN, pull_up_down=GPIO.PUD_UP)

#GPIO.setup(STBY, GPIO.OUT)
#GPIO.output(STBY, GPIO.LOW)
time.sleep(1)

# === Functions ===
def adc_init_all():
    for i in range(3):
        GPIO.output(CS_PINS[i], GPIO.LOW)
        time.sleep(0.000001)
        spi.xfer2([0x06])
        time.sleep(0.1)
        spi.xfer2([0x42, 0x81, 0x60, 0x40])
        spi.xfer2([0x08])
        GPIO.output(CS_PINS[i], GPIO.HIGH)
        time.sleep(0.1)

def start_conversion_all():
    for cs in CS_PINS:
        GPIO.output(cs, GPIO.LOW)
    spi.xfer2([0x08])
    for cs in CS_PINS:
        GPIO.output(cs, GPIO.HIGH)

def read_adc(i, return_raw=False):
    GPIO.output(CS_PINS[i], GPIO.LOW)
    start = time.time()
    while GPIO.input(DRDY_PINS[i]):
        if time.time() - start > 0.15:
            raise TimeoutError(f"DRDY timeout on ADC {i}")
        time.sleep(0.0001)
    data = spi.xfer2([0x00, 0x00, 0x00])
    GPIO.output(CS_PINS[i], GPIO.HIGH)
    raw = (data[0] << 16) | (data[1] << 8) | data[2]
    if raw & (1 << 23):
        raw -= (1 << 24)
    if return_raw:
        return raw
    voltage = (raw / FULL_SCALE) * VREF_ADCS[i]
    return voltage

def convert_voltage_to_ms2(voltage, axis_index):
    zero_voltage = ACC_ZERO_VOLTAGES[axis_index]
    g_val = (voltage - zero_voltage) / ACC_SENSITIVITY_V_PER_G
    return g_val * G_TO_MS2

def multi_channel_init():
    #GPIO.output(STBY, GPIO.LOW)
    time.sleep(0.1)
    adc_init_all()
    for _ in range(5):
        start_conversion_all()
        for i in range(3):
            try:
                read_adc(i)
            except Exception:
                pass
        time.sleep(0.01)

def calibrate_accelerometer_zero_levels(calibration_time_sec=1):
    print(f"ðŸ› ï¸ Starting accelerometer zero-level calibration for {calibration_time_sec} seconds...")
    samples = [[], [], []]  # For Z, X, Y
    start_time = time.time()

    while time.time() - start_time < calibration_time_sec:
        start_conversion_all()
        for axis in range(3):
            voltage = read_adc(axis)
            samples[axis].append(voltage)
        time.sleep(SAMPLE_INTERVAL)

    for i in range(3):
        ACC_ZERO_VOLTAGES[i] = sum(samples[i]) / len(samples[i])

    print("âœ… Calibration complete. Zero-level voltages (V):")
    print(f"Z: {ACC_ZERO_VOLTAGES[0]:.6f} V, X: {ACC_ZERO_VOLTAGES[1]:.6f} V, Y: {ACC_ZERO_VOLTAGES[2]:.6f} V")

def stream_udp(ip_list, port):
    multi_channel_init()
    calibrate_accelerometer_zero_levels()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"ðŸ“¡ Sending UDP packets to {', '.join(ip_list)}:{port}...")

    total_samples = 0
    total_time = 0

    try:
        buffers = [[] for _ in range(3)]
        timestamp = None

        while True:
            start_conversion_all()
            readings = []

            for i in range(3):
                voltage = read_adc(i)
                acceleration = convert_voltage_to_ms2(voltage, axis_index=i)
                readings.append(acceleration)

            if len(buffers[0]) == 0:
                timestamp = time.time()

            for i in range(3):
                buffers[i].append(readings[i])

            if len(buffers[0]) >= SAMPLES_PER_PACKET:
                end_time = time.time()
                elapsed = end_time - timestamp
                sps = SAMPLES_PER_PACKET / elapsed

                total_samples += SAMPLES_PER_PACKET
                total_time += elapsed
                overall_sps = total_samples / total_time

                print("ðŸ“Š Per-Channel Sample Rates:")
                for i in range(3):
                    print(f"   {CHANNEL_NAMES[i]}: {sps:.2f} samples/sec (current), {overall_sps:.2f} samples/sec (avg)")

                for i in range(3):
                    packet = [CHANNEL_NAMES[i], timestamp] + buffers[i]
                    data = str(packet).encode()

                    for ip in ip_list:
                        sock.sendto(data, (ip, port))

                buffers = [[] for _ in range(3)]
                timestamp = None

            time.sleep(SAMPLE_INTERVAL)

    except KeyboardInterrupt:
        print("ðŸ›‘ Stopped by user.")
    except Exception as e:
        print(f"âŒ Error: {e}")
    finally:
        spi.close()
        GPIO.cleanup()
        sock.close()

# === Main ===
if __name__ == "__main__":
    destination_ips = [
        "10.241.144.172",      # Local network PC IP
        "192.168.194.91"       # ZeroTier IP
        "192.168.8.190"
    ]
    stream_udp(destination_ips, 2098)