"""
metadata.py — FDSN StationXML v1.2 instrument response generator
=================================================================
Generates a standards-compliant FDSN StationXML v1.2 document describing the
EEW sensor hardware chain.

Hardware chain (M/S**2 → COUNTS):
    ADXL354BEZ   MEMS accelerometer  ±2 g, 400 mV/g (DC-coupled, ratiometric to 1.8 V)
    ADA4522-1ARZ RC unity-gain buffer + low-pass anti-aliasing network
    ADS1220IPWR  24-bit delta-sigma ADC               (Gain=1, Vref=1.8 V, 330 SPS)
    [software]   2nd-order Butterworth IIR low-pass   (fc=50 Hz at 200 SPS)
                 + ×2 software decimation             (200 SPS → 100 SPS)

Three-stage response (M/S**2 → COUNTS):
    Stage 1 — PolesZeros      sensor output   M/S**2 → V
    Stage 2 — Coefficients    ADC conversion  V      → COUNTS  (Factor=1, 200 SPS → 200 SPS)
    Stage 3 — Coefficients    IIR anti-alias  COUNTS → COUNTS  (Factor=2, 200 SPS → 100 SPS)

NOTE on the RS4D FIR coefficients
----------------------------------
This sensor uses a completely different hardware chain from the Raspberry Shake 4D.
The RS4D ``RF-DL100.stage_2`` FIR taps represent a proprietary hardware FIR filter
inside the RS custom ASIC — they are NOT applicable here.

Our Stage 3 is a 2nd-order Butterworth IIR low-pass anti-aliasing filter (fc=50 Hz, fs=200 Hz)
followed by stride-2 decimation. This is explicitly applied in the sensor's hardware loop.
The SOS coefficients are computed at module import time and embedded in the StationXML
as IIR numerator/denominator sections.

Sensitivity derivation
----------------------
    VREF              = 1.8 V    (ADXL354 V1P8ANA rail = ADS1220 external Vref)
    FULL_SCALE        = 2^23 − 1 = 8,388,607  (24-bit two's complement, positive FS)
    SENSITIVITY       = 0.4 V/g  (ADXL354BEZ ±2 g range, typical, ratiometric)
    G_TO_MS2          = 9.80665 m/s²

    Stage 1 gain (M/S**2 → V):
        = SENSITIVITY / G_TO_MS2
        = 0.4 / 9.80665 ≈ 0.040789 V·s²/m

    Stage 2 gain (V → COUNTS):
        = FULL_SCALE / VREF = 8,388,607 / 1.8 ≈ 4,660,337 counts/V

    Stage 3 gain = 1.0  (IIR filter + decimation, unity passband gain)

    Overall InstrumentSensitivity (M/S**2 → COUNTS):
        = Stage1 × Stage2 × Stage3
        = 0.040789 × 4,660,337 × 1.0 ≈ 190,067 counts/(m/s²)

ObsPy usage
-----------
    from obspy.core.inventory import read_inventory
    inv = read_inventory('CRISIS-NODE-01_response.xml')
    st.attach_response(inv)
    acc = st.remove_response(output='ACC')   # → m/s²

References
----------
    FDSN StationXML v1.2:  https://docs.fdsn.org/projects/stationxml/en/v1.2/
    ADXL354BEZ datasheet:  https://www.analog.com/media/en/technical-documentation/data-sheets/adxl354_adxl355.pdf
    ADS1220 datasheet:     https://www.ti.com/lit/ds/symlink/ads1220.pdf
    ADA4522-1 datasheet:   https://www.analog.com/en/products/ada4522-1.html
"""

from datetime import datetime, timezone

import numpy as np
from scipy.signal import butter

from sensor import (
    FULL_SCALE,
    VREF_ADCS,
    ACC_SENSITIVITY_V_PER_G,
    G_TO_MS2,
)

# ---------------------------------------------------------------------------
# Instrument constants
# ---------------------------------------------------------------------------

# Stage 1: ADXL354BEZ sensor gain  (M/S**2 → V)
# ADXL354 is DC-coupled with flat response from 0 Hz to ~1500 Hz.
_SENSOR_GAIN_V_PER_MS2: float = ACC_SENSITIVITY_V_PER_G / G_TO_MS2   # ≈ 0.040789

# Stage 2: ADS1220 ADC gain  (V → COUNTS)
# Gain=1 (PGA bypassed, Reg0=0x81), external Vref=1.8 V (Reg2=0x40)
_ADC_GAIN_COUNTS_PER_V: float = FULL_SCALE / VREF_ADCS[0]             # ≈ 4,660,337

# Overall InstrumentSensitivity  (M/S**2 → COUNTS)
INSTRUMENT_SENSITIVITY_COUNTS_PER_MS2: float = (
    _SENSOR_GAIN_V_PER_MS2 * _ADC_GAIN_COUNTS_PER_V
)

# FDSN reference frequency (Hz) used for gain values and normalisation
_REF_FREQ_HZ: float = 5.0

# ADS1220 configured output data rate (SPS, see Reg1=0x80, DR[2:0]=100 → 330 SPS)
# The hw_loop double-reads per decimated sample → effective input rate seen by software
_HW_SPS: float = 200.0

# Output sample rate after software decimation
_OUT_SPS: float = 100.0

# Decimation factor
_DECIMATION_FACTOR: int = int(_HW_SPS / _OUT_SPS)  # = 2

# Network code for this EEW deployment
NETWORK_CODE: str = "EW"

# Conservative deployment epoch
_EPOCH_START: str = "2024-01-01T00:00:00.000000Z"

# Channel definitions: (SEED_code, azimuth_deg, dip_deg)
_CHANNELS = [
    ("ENZ",   0.0, -90.0),   # Vertical    (Z-axis)
    ("ENN",   0.0,   0.0),   # North–South (N-axis)
    ("ENE",  90.0,   0.0),   # East–West   (E-axis)
]


# ---------------------------------------------------------------------------
# Stage 3 — 2nd-order Butterworth IIR anti-alias (fc=50 Hz at 200 SPS)
# ---------------------------------------------------------------------------
# Compute actual scipy SOS coefficients once at import time and embed them in
# the StationXML. This represents the explicit arithmetic low-pass filter
# applied in sensor.py::_hw_loop for anti-aliasing prior to downsampling.
#
# SOS matrix shape: (n_sections, 6) where each row is [b0,b1,b2,a0,a1,a2].
# StationXML <Coefficients> with CfTransferFunctionType=DIGITAL accepts
# separate Numerator and Denominator coefficient lists for IIR filters.
# We flatten the SOS rows into ba (transfer function) form for StationXML.

def _compute_butterworth_sos() -> np.ndarray:
    """Return the SOS coefficients for the 2nd-order hardware anti-alias low-pass filter."""
    # order=2, fc=50 Hz, fs=200 Hz
    nyq = _HW_SPS / 2.0
    fc = 50.0 / nyq
    return butter(2, fc, btype="low", output="sos")


def _sos_to_xml_lines(sos: np.ndarray) -> str:
    """Convert SOS matrix rows to StationXML <Numerator>/<Denominator> lines.

    Each SOS section has coefficients [b0, b1, b2, a0, a1, a2].
    For DIGITAL CfTransferFunctionType, StationXML expects Numerator
    (feedforward) and Denominator (feedback) coefficients separately.
    We normalise each section by a0 (should be 1.0 from scipy) and emit:

        <Numerator i="k">b_k</Numerator>    for b coefficients
        <Denominator i="k">a_k</Denominator> for a coefficients  (excluding a0=1)
    """
    num_lines = []
    den_lines = []
    num_idx = 0
    den_idx = 0

    for section in sos:
        b0, b1, b2, a0, a1, a2 = section
        # normalise by a0 (scipy always sets a0=1, but be safe)
        b0 /= a0; b1 /= a0; b2 /= a0
        a1 /= a0; a2 /= a0

        for coeff in (b0, b1, b2):
            num_lines.append(
                f'              <Numerator i="{num_idx}">{coeff:.10e}</Numerator>'
            )
            num_idx += 1

        # a0=1 is implicit (not listed); emit a1 and a2 only
        for coeff in (a1, a2):
            den_lines.append(
                f'              <Denominator i="{den_idx}">{coeff:.10e}</Denominator>'
            )
            den_idx += 1

    return "\n".join(num_lines + den_lines)


# Compute once at module load
_BUTTERWORTH_SOS = _compute_butterworth_sos()
_BUTTERWORTH_XML_LINES = _sos_to_xml_lines(_BUTTERWORTH_SOS)


# ---------------------------------------------------------------------------
# Channel XML builder
# ---------------------------------------------------------------------------

def _build_channel_xml(
    seed_code: str,
    azimuth: float,
    dip: float,
    latitude: float,
    longitude: float,
    elevation: float,
    start_date: str,
    dc_offset_counts: int = 0,
) -> str:
    """Return the complete <Channel> XML block for one SEED channel code."""
    dc_comment = f"""
        <!-- ── DC Offset (calibration) ──────────────────────────────────────
             Raw UDP counts include the full ADC DC bias (gravity + manufacturing
             offset). Before calling remove_response(), demean the trace:

               tr.detrend('demean')   # or tr.detrend('linear')
               tr.remove_response(inventory=inv, output='ACC')

             Measured DC offset for this channel: {dc_offset_counts} counts
             (= {dc_offset_counts * _SENSOR_GAIN_V_PER_MS2 * _ADC_GAIN_COUNTS_PER_V:.1f} counts,
              equivalent to {dc_offset_counts / (_SENSOR_GAIN_V_PER_MS2 * _ADC_GAIN_COUNTS_PER_V):.4f} m/s²
              measured during startup calibration) ── -->
        <Comment>
          <Value>DC offset (ADC zero level, measured at startup calibration): {dc_offset_counts} counts. Remove with tr.detrend(demean) before ObsPy remove_response().</Value>
        </Comment>"""
    return f"""    <Channel code="{seed_code}" startDate="{start_date}" restrictedStatus="open" locationCode="00">
        <Latitude unit="DEGREES">{latitude:.9f}</Latitude>
        <Longitude unit="DEGREES">{longitude:.9f}</Longitude>
        <Elevation>{elevation:.1f}</Elevation>
        <Depth>0.0</Depth>
        <Azimuth unit="DEGREES">{azimuth:.1f}</Azimuth>
        <Dip unit="DEGREES">{dip:.1f}</Dip>
        <SampleRate unit="SAMPLES/S">{_OUT_SPS:.1f}</SampleRate>
        <SampleRateRatio>
          <NumberSamples>{int(_OUT_SPS)}</NumberSamples>
          <NumberSeconds>1</NumberSeconds>
        </SampleRateRatio>
        <ClockDrift unit="SECONDS/SAMPLE">0.0</ClockDrift>{dc_comment}
        <Sensor resourceId="Sensor-EEW-ADXL354BEZ-ACC">
          <Type>EEW Sensor</Type>
          <Description>Acceleration</Description>
          <Manufacturer>Analog Devices</Manufacturer>
          <Model>ADXL354BEZ</Model>
        </Sensor>
        <DataLogger resourceId="Datalogger-EEW-ADS1220-{int(_OUT_SPS)}hz"/>
        <Response>

          <!-- Overall sensitivity: M/S**2 → COUNTS
               = Stage1 ({_SENSOR_GAIN_V_PER_MS2:.6f} V·s²/m)
               × Stage2 ({_ADC_GAIN_COUNTS_PER_V:.2f} counts/V)
               × Stage3 (1.0)
               = {INSTRUMENT_SENSITIVITY_COUNTS_PER_MS2:.4f} counts/(m/s²) -->
          <InstrumentSensitivity>
            <Value>{INSTRUMENT_SENSITIVITY_COUNTS_PER_MS2:.4f}</Value>
            <Frequency>{_REF_FREQ_HZ:.1f}</Frequency>
            <InputUnits>
              <Name>M/S**2</Name>
              <Description>Acceleration in Meters Per Second Squared</Description>
            </InputUnits>
            <OutputUnits>
              <Name>COUNTS</Name>
            </OutputUnits>
          </InstrumentSensitivity>

          <!-- ── Stage 1: ADXL354BEZ MEMS accelerometer ─────────────────
               DC-coupled, flat response from 0 Hz to ~1500 Hz.
               No poles or zeros required in the seismic band (0.1–50 Hz).
               StageGain = SENSITIVITY / G = {ACC_SENSITIVITY_V_PER_G} V/g / {G_TO_MS2} m/s²/g
                         = {_SENSOR_GAIN_V_PER_MS2:.8f} V / (m/s²)
               NormalizationFactor = 1.0 (flat DC response → H(ω)=1 everywhere) ── -->
          <Stage number="1">
            <PolesZeros name="RP-EEW-ADXL354BEZ-ACC" resourceId="ResponsePAZ-EEW-ADXL354BEZ-ACC">
              <InputUnits>
                <Name>M/S**2</Name>
                <Description>Acceleration in Meters Per Second Squared</Description>
              </InputUnits>
              <OutputUnits>
                <Name>V</Name>
              </OutputUnits>
              <PzTransferFunctionType>LAPLACE (RADIANS/SECOND)</PzTransferFunctionType>
              <NormalizationFactor>1.0</NormalizationFactor>
              <NormalizationFrequency unit="HERTZ">{_REF_FREQ_HZ:.1f}</NormalizationFrequency>
            </PolesZeros>
            <StageGain>
              <Value>{_SENSOR_GAIN_V_PER_MS2:.8f}</Value>
              <Frequency>{_REF_FREQ_HZ:.1f}</Frequency>
            </StageGain>
          </Stage>

          <!-- ── Stage 2: ADS1220IPWR 24-bit ADC ─────────────────────────
               Config: Reg0=0x81 (AIN0/AIN1, PGA bypassed, Gain=1)
                       Reg1=0x80 (330 SPS, Normal mode)
                       Reg2=0x40 (External Vref = {VREF_ADCS[0]} V)
               StageGain = FULL_SCALE / VREF
                         = {FULL_SCALE} / {VREF_ADCS[0]}
                         = {_ADC_GAIN_COUNTS_PER_V:.4f} counts/V
               Note: ADS1220 sinc³ digital filter is intrinsic to the
               delta-sigma modulator and is represented implicitly here. ── -->
          <Stage number="2">
            <Coefficients>
              <InputUnits>
                <Name>V</Name>
              </InputUnits>
              <OutputUnits>
                <Name>COUNTS</Name>
              </OutputUnits>
              <CfTransferFunctionType>DIGITAL</CfTransferFunctionType>
            </Coefficients>
            <Decimation>
              <InputSampleRate unit="HERTZ">{_HW_SPS:.1f}</InputSampleRate>
              <Factor>1</Factor>
              <Offset>0</Offset>
              <Delay>0.0</Delay>
              <Correction>0.0</Correction>
            </Decimation>
            <StageGain>
              <Value>{_ADC_GAIN_COUNTS_PER_V:.4f}</Value>
              <Frequency>0.0</Frequency>
            </StageGain>
          </Stage>

          <!-- ── Stage 3: 2nd-order Butterworth IIR anti-alias + ×2 decimation ──
               Software filter implemented in sensor.py::_hw_loop for anti-aliasing
               prior to decimation. Parameters: low-pass fc=50 Hz, fs=200 SPS, order=2.
               Coefficients below are the actual scipy SOS sections flattened
               to transfer-function Numerator/Denominator form.
               Stage passband gain = 1.0 (Butterworth unity passband). ── -->
          <Stage number="3">
            <Coefficients>
              <InputUnits>
                <Name>COUNTS</Name>
              </InputUnits>
              <OutputUnits>
                <Name>COUNTS</Name>
              </OutputUnits>
              <CfTransferFunctionType>DIGITAL</CfTransferFunctionType>
{_BUTTERWORTH_XML_LINES}
            </Coefficients>
            <Decimation>
              <InputSampleRate unit="HERTZ">{_HW_SPS:.1f}</InputSampleRate>
              <Factor>{_DECIMATION_FACTOR}</Factor>
              <Offset>0</Offset>
              <Delay>0.0</Delay>
              <Correction>0.0</Correction>
            </Decimation>
            <StageGain>
              <Value>1.0</Value>
              <Frequency>0.0</Frequency>
            </StageGain>
          </Stage>

        </Response>
      </Channel>"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_stationxml(
    device_name: str,
    latitude: float,
    longitude: float,
    elevation: float = 0.0,
    start_date: str | None = None,
    dc_offset_counts: list[int] | None = None,
) -> str:
    """Generate a complete FDSN StationXML v1.2 document for this EEW sensor node.

    Parameters
    ----------
    device_name : str
        Human-readable node identifier, e.g. ``'CRISIS-NODE-01'``.
        First five characters become the SEED station code (uppercased).
    latitude : float
        WGS-84 latitude in decimal degrees.
    longitude : float
        WGS-84 longitude in decimal degrees.
    elevation : float, optional
        Elevation above sea level in metres.  Default 0.0.
    start_date : str, optional
        ISO-8601 station start date.  Default: ``_EPOCH_START``.
    dc_offset_counts : list[int], optional
        Calibrated ADC zero level per axis [Z, X, Y] in raw counts, measured
        at device startup.  Embedded in each Channel <Comment> for receivers
        to reference when demeaning before response removal.

    Returns
    -------
    str
        UTF-8 encoded StationXML string ready to serve or write to disk.
    """
    if start_date is None:
        start_date = _EPOCH_START
    if dc_offset_counts is None:
        dc_offset_counts = [0, 0, 0]

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    station_code = device_name[:5].upper()

    channel_blocks = "\n".join(
        _build_channel_xml(code, az, dip, latitude, longitude, elevation, start_date,
                           dc_offset_counts[idx])
        for idx, (code, az, dip) in enumerate(_CHANNELS)
    )

    return f"""<?xml version='1.0' encoding='UTF-8'?>
<FDSNStationXML xmlns="http://www.fdsn.org/xml/station/1" schemaVersion="1.2">
  <Source>{device_name}</Source>
  <Sender>EEW</Sender>
  <Module/>
  <ModuleURI/>
  <Created>{now_iso}</Created>
  <Network code="{NETWORK_CODE}" startDate="{_EPOCH_START}" restrictedStatus="open">
    <Description>EEW Sensor Network</Description>
    <Station code="{station_code}" startDate="{start_date}" restrictedStatus="open">
      <Latitude unit="DEGREES">{latitude:.9f}</Latitude>
      <Longitude unit="DEGREES">{longitude:.9f}</Longitude>
      <Elevation>{elevation:.1f}</Elevation>
      <Site>
        <Name>{device_name} — EEW Sensor Station</Name>
      </Site>
      <CreationDate>{start_date}</CreationDate>
{channel_blocks}
    </Station>
  </Network>
</FDSNStationXML>
"""
