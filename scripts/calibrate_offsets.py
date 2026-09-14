"""
calibrate_offsets.py — One-shot ADC DC offset measurement tool
===============================================================
Run this script ONCE on the Raspberry Pi with the sensor at rest to measure
the DC zero level (gravity + manufacturing offset) for each ADC axis.

The printed values are automatically embedded in the StationXML each time
the firmware boots (via the calibrate() call in sensor.py). Run this script
separately if you want to verify or manually record the offset values.

Usage:
    python calibrate_offsets.py [--duration 60] [--output offsets.txt]

Output example:
    === EEW Sensor ADC Calibration ===
    Duration: 60 s  |  Samples per axis: ~6000
    -----------------------------------------------
    Axis      RAW_COUNTS_ZERO    Voltage (V)    Equiv. m/s²
    ENZ (Z)       4194304         0.899991        8.827
    ENN (X)         -1234        -0.000265       -0.003
    ENE (Y)          2048         0.000440        0.004
    -----------------------------------------------
    ObsPy demean command: tr.detrend('demean')
    These values are also embedded in the StationXML <Comment> at download time.
"""

import time
import argparse
import sys
import os

# ---------------------------------------------------------------------------
# Constants — must match sensor.py exactly
# ---------------------------------------------------------------------------
CS_PINS   = [35, 33, 36]
DRDY_PINS = [11, 15, 13]
VREF_ADCS = [1.8, 1.8, 1.8]
FULL_SCALE = 8388607
SAMPLE_INTERVAL = 0.005  # 200 Hz polling
CHANNEL_NAMES = ['ENZ', 'ENN', 'ENE']
AXIS_LABELS   = ['Z (vertical)', 'X (N-S)', 'Y (E-W)']

# Instrument sensitivity for display only
ACC_SENSITIVITY_V_PER_G = 0.4
G_TO_MS2 = 9.80665
INSTRUMENT_SENSITIVITY_MS2_PER_COUNT = (VREF_ADCS[0] * G_TO_MS2) / (FULL_SCALE * ACC_SENSITIVITY_V_PER_G)

# Sensor control pins
ST1, ST2, STBY = 16, 18, 22


def _setup_hardware():
    import spidev
    import RPi.GPIO as GPIO

    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(ST1, GPIO.OUT)
    GPIO.setup(ST2, GPIO.OUT)
    GPIO.setup(STBY, GPIO.OUT)
    GPIO.output(ST1, GPIO.LOW)
    GPIO.output(ST2, GPIO.LOW)
    GPIO.output(STBY, GPIO.HIGH)
    print("Waiting 10 s for sensor STBY line to stabilise...")
    time.sleep(10)

    for cs in CS_PINS:
        GPIO.setup(cs, GPIO.OUT)
        GPIO.output(cs, GPIO.HIGH)
    for drdy in DRDY_PINS:
        GPIO.setup(drdy, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    time.sleep(1)

    spi = spidev.SpiDev()
    spi.open(0, 0)
    spi.max_speed_hz = 4000000
    spi.mode = 0b01

    # Init all three ADCs
    for i in range(3):
        GPIO.output(CS_PINS[i], GPIO.LOW)
        time.sleep(0.000001)
        spi.xfer2([0x06])        # Reset
        time.sleep(0.1)
        # Reg0=0x81 (AIN0/AIN1, PGA disabled), Reg1=0x80 (330SPS), Reg2=0x40 (ext Vref)
        spi.xfer2([0x42, 0x81, 0x80, 0x40])
        spi.xfer2([0x08])        # Start conversion
        GPIO.output(CS_PINS[i], GPIO.HIGH)
        time.sleep(0.1)

    # Flush a few dummy reads
    for _ in range(5):
        for cs in CS_PINS:
            GPIO.output(cs, GPIO.LOW)
        spi.xfer2([0x08])
        for cs in CS_PINS:
            GPIO.output(cs, GPIO.HIGH)
        for i in range(3):
            GPIO.output(CS_PINS[i], GPIO.LOW)
            start = time.time()
            while GPIO.input(DRDY_PINS[i]):
                if time.time() - start > 0.15:
                    break
            spi.xfer2([0x00, 0x00, 0x00])
            GPIO.output(CS_PINS[i], GPIO.HIGH)
        time.sleep(0.01)

    return spi, GPIO


def _read_all_raw(spi, GPIO):
    """Start conversion, read all three axes, return list of 3 signed integers."""
    for cs in CS_PINS:
        GPIO.output(cs, GPIO.LOW)
    spi.xfer2([0x08])
    for cs in CS_PINS:
        GPIO.output(cs, GPIO.HIGH)

    results = []
    for i in range(3):
        GPIO.output(CS_PINS[i], GPIO.LOW)
        start = time.time()
        while GPIO.input(DRDY_PINS[i]):
            if time.time() - start > 0.15:
                raise TimeoutError(f"DRDY timeout on ADC {i}")
        data = spi.xfer2([0x00, 0x00, 0x00])
        GPIO.output(CS_PINS[i], GPIO.HIGH)
        raw = (data[0] << 16) | (data[1] << 8) | data[2]
        if raw & (1 << 23):
            raw -= (1 << 24)
        results.append(raw)
    return results


def run_calibration(duration: int, output_file: str | None):
    print(f"\n=== EEW Sensor ADC DC Offset Calibration ===")
    print(f"Duration: {duration} s  |  Polling at ~200 Hz")
    print("Keep the sensor perfectly at rest.\n")

    spi, GPIO = _setup_hardware()

    samples = [[], [], []]
    end_time = time.time() + duration
    n = 0
    try:
        while time.time() < end_time:
            counts = _read_all_raw(spi, GPIO)
            for i in range(3):
                samples[i].append(counts[i])
            n += 1
            # Print progress every 5 seconds
            if n % 1000 == 0:
                elapsed = duration - (end_time - time.time())
                print(f"  {elapsed:.0f} / {duration} s  ({n} samples collected)...")
            time.sleep(SAMPLE_INTERVAL)
    except KeyboardInterrupt:
        print("\nInterrupted early — using samples collected so far.")
    finally:
        GPIO.cleanup()

    if not any(samples[0]):
        print("ERROR: No samples collected.", file=sys.stderr)
        sys.exit(1)

    means   = [round(sum(s) / len(s)) for s in samples]
    voltages = [m * VREF_ADCS[i] / FULL_SCALE for i, m in enumerate(means)]
    ms2vals  = [v / ACC_SENSITIVITY_V_PER_G * G_TO_MS2 for v in voltages]

    # -----------------------------------------------------------------------
    # Print results
    # -----------------------------------------------------------------------
    sep = "-" * 62
    print(f"\n{sep}")
    print(f"  {'Channel':<12} {'RAW_COUNTS_ZERO':>17}  {'Voltage (V)':>12}  {'Equiv. m/s²':>12}")
    print(sep)
    for i in range(3):
        label = f"{CHANNEL_NAMES[i]} ({AXIS_LABELS[i]})"
        print(f"  {label:<28} {means[i]:>10}   {voltages[i]:>10.6f}   {ms2vals[i]:>10.5f}")
    print(sep)
    print(f"\nTotal samples per axis: {len(samples[0])}")
    print(f"\nTo use in sensor.py, these values are set automatically at boot via calibrate().")
    print(f"They are also embedded in the StationXML <Comment> when you download the XML.")
    print(f"\nObsPy receiver demean command (run before remove_response):")
    print(f"    tr.detrend('demean')  # removes the DC offset listed above")
    print(f"\nRAW_COUNTS_ZERO = {means}")

    if output_file:
        with open(output_file, 'w') as f:
            f.write(f"EEW Sensor ADC DC Offset Calibration\n")
            f.write(f"Duration: {duration} s, Samples: {len(samples[0])}\n")
            f.write(f"Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n\n")
            f.write(f"RAW_COUNTS_ZERO = {means}\n")
            for i in range(3):
                f.write(f"  {CHANNEL_NAMES[i]}: {means[i]} counts  "
                        f"({voltages[i]:.6f} V  /  {ms2vals[i]:.5f} m/s²)\n")
        print(f"\nResults saved to: {output_file}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Measure EEW sensor ADC DC offset (zero level).')
    parser.add_argument('--duration', type=int, default=60,
                        help='Measurement duration in seconds (default: 60)')
    parser.add_argument('--output', type=str, default=None,
                        help='Save results to this file (optional)')
    args = parser.parse_args()

    # Guard: only run on Raspberry Pi
    if sys.platform == 'win32':
        print("This script must be run on the Raspberry Pi (requires spidev + RPi.GPIO).")
        sys.exit(1)

    run_calibration(args.duration, args.output)
