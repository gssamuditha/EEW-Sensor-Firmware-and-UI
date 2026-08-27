import time
import lgpio
import spidev
import socket

# === Pin Definitions (BCM Numbers matching your PCB) ===
CS_PINS = [8, 19, 16, 13]         # CS1, CS2, CS3, CS4
DRDY_PINS = [3, 17, 27, 22]       # DRDY1, DRDY2, DRDY3, DRDY4

# Note: MOSI (10), MISO (9), SCLK (11) are handled exclusively by hardware SPI now.

ST1 = 23
ST2 = 24
STBY = 25

VREF_ADCS = [3.294, 1.781, 1.781, 1.781]
FULL_SCALE = 8388607
CHANNEL_NAMES = ['EHZ', 'ENZ', 'ENE', 'ENN']
SAMPLES_PER_PACKET = 25
SAMPLE_INTERVAL = 0.0065  # ~153 sps (requested interval)

# === Setup Hardware SPI ===
spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 4000000
spi.mode = 0b01
spi.no_cs = True  # CRITICAL: Tell spidev not to internally toggle the hardware CS pins

# === Open GPIO Chip ===
try:
    h = lgpio.gpiochip_open(0)
except Exception:
    h = lgpio.gpiochip_open(4)

# Claim CS and Control Pins as outputs
for pin in CS_PINS + [ST1, ST2, STBY]:
    try:
        lgpio.gpio_claim_output(h, pin, 1 if pin in CS_PINS + [STBY] else 0)
    except lgpio.error:
        lgpio.gpio_free(h, pin)
        lgpio.gpio_claim_output(h, pin, 1 if pin in CS_PINS + [STBY] else 0)

# Claim DRDY Pins as inputs
for pin in DRDY_PINS:
    try:
        lgpio.gpio_claim_input(h, pin, lgpio.SET_PULL_UP)
    except lgpio.error:
        lgpio.gpio_free(h, pin)
        lgpio.gpio_claim_input(h, pin, lgpio.SET_PULL_UP)

# === Functions ===
def gpio_out(pin, val):
    lgpio.gpio_write(h, pin, 1 if val else 0)

def adc_init_all():
    for i in range(4):
        gpio_out(CS_PINS[i], False)
        time.sleep(0.0001)
        spi.xfer2([0x06])
        time.sleep(0.1)
        spi.xfer2([0x42, 0x81, 0x80, 0x40])
        spi.xfer2([0x08])
        gpio_out(CS_PINS[i], True)
        time.sleep(0.1)

def start_conversion_all():
    for cs in CS_PINS:
        gpio_out(cs, False)
        spi.xfer2([0x08])
        gpio_out(cs, True)

def wait_all_drdy(timeout=10):
    """Waits for all 4 DRDY pins to go LOW simultaneously."""
    start = time.time()
    while True:
        # Parallel polling: wait until all are 0 (ready)
        if (lgpio.gpio_read(h, DRDY_PINS[0]) == 0 and 
            lgpio.gpio_read(h, DRDY_PINS[1]) == 0 and 
            lgpio.gpio_read(h, DRDY_PINS[2]) == 0 and 
            lgpio.gpio_read(h, DRDY_PINS[3]) == 0):
            break
        if time.time() - start > timeout:
            raise TimeoutError("Timeout waiting for all DRDY pins to go LOW")

def read_adc_voltage_nowait(i):
    """Reads raw ADC data immediately, assuming DRDY is already LOW."""
    gpio_out(CS_PINS[i], False)
    data = spi.xfer2([0x00, 0x00, 0x00])
    gpio_out(CS_PINS[i], True)
    
    # Sign extension for 24-bit two's complement integer
    raw = (data[0] << 16) | (data[1] << 8) | data[2]
    if raw & (1 << 23):
        raw -= (1 << 24)
        
    # Convert raw count directly to measured Volts
    voltage = (raw / FULL_SCALE) * VREF_ADCS[i]
    return voltage

def multi_channel_init():
    gpio_out(ST1, False)
    gpio_out(ST2, False)
    gpio_out(STBY, True)
    time.sleep(0.1)
    adc_init_all()
    
    for _ in range(5):
        start_conversion_all()
        try:
            wait_all_drdy(timeout=2)
            for i in range(4):
                read_adc_voltage_nowait(i)
        except Exception:
            pass
        time.sleep(0.01)

def stream_udp(ip_list, port):
    multi_channel_init()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"Sending UDP packets to {', '.join(ip_list)}:{port}...")

    total_samples = 0
    total_time = 0

    try:
        buffers = [[] for _ in range(4)]
        timestamp = None

        while True:
            start_conversion_all()
            wait_all_drdy(timeout=10)
            
            readings = []
            for i in range(4):
                voltage = read_adc_voltage_nowait(i)
                readings.append(voltage)

            if len(buffers[0]) == 0:
                timestamp = time.time()

            for i in range(4):
                buffers[i].append(readings[i])

            if len(buffers[0]) >= SAMPLES_PER_PACKET:
                end_time = time.time()
                elapsed = end_time - timestamp
                sps = SAMPLES_PER_PACKET / elapsed

                total_samples += SAMPLES_PER_PACKET
                total_time += elapsed
                overall_sps = total_samples / total_time

                print("Per-Channel Sample Rates:")
                for i in range(4):
                    print(f"   {CHANNEL_NAMES[i]}: {sps:.2f} samples/sec (current), {overall_sps:.2f} samples/sec (avg)")

                # Package and send data
                for i in range(4):
                    # Format: ['ChannelName', Timestamp, val1, val2, ... val25]
                    packet = [CHANNEL_NAMES[i], timestamp] + buffers[i]
                    data = str(packet).encode()

                    for ip in ip_list:
                        sock.sendto(data, (ip, port))

                # Reset buffers for the next packet
                buffers = [[] for _ in range(4)]
                timestamp = None

            time.sleep(SAMPLE_INTERVAL)

    except KeyboardInterrupt:
        print("\nStopped by user.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        spi.close()
        lgpio.gpiochip_close(h)
        sock.close()

if __name__ == "__main__":
    destination_ips = [
        "10.241.144.172",      # Local network PC IP
        "192.168.194.91",      # ZeroTier IP
        "192.168.8.190",        # Local network IP
        "192.168.8.101"

    ]
    stream_udp(destination_ips, 2098)
