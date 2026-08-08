"""
clock_offset_probe.py - NTP-Independent UDP Clock Offset Estimator
===================================================================
Uses Cristian's algorithm (1989) to estimate the clock offset between
your PC and the EEW sensor RPi WITHOUT relying on NTP comparison.

This is the gold standard cross-check: if your NTP offset says ~0 ms
but Cristian's algorithm gives a very different value, investigate your
NTP configuration.

How it works
------------
1. PC sends a probe UDP packet containing t_send (PC UTC epoch) to the RPi.
2. RPi echoes the packet back, adding t_echo_recv and t_echo_send.
3. PC receives the reply and records t_reply_recv.
4. Computation:
     RTT    = t_reply_recv - t_send
     offset = t_echo_recv - (t_send + RTT/2)

The RTT/2 estimate assumes symmetric network delay (usually true within 10%).
Running 100 probes and taking the MEDIAN minimises outliers from asymmetric
bursts (recommended by RFC 5905 NTP specification).

Setup
-----
  RPi:  python clock_echo_server.py         (run this first)
  PC:   python clock_offset_probe.py --host <zerotier_ip_of_rpi>

Output
------
  Prints median offset, std, and per-probe table.
  Recommended: subtract the median offset from OWD values in your analysis.
"""

import argparse
import socket
import struct
import time
import statistics

PROBE_PORT   = 9876
N_PROBES     = 100
PROBE_FORMAT = '!dd'   # network-byte-order: t_send(8B) + padding(8B)
REPLY_FORMAT = '!ddd'  # t_send(8B) + t_echo_recv(8B) + t_echo_send(8B)
PROBE_SIZE   = struct.calcsize(PROBE_FORMAT)
REPLY_SIZE   = struct.calcsize(REPLY_FORMAT)


def run_probe(host, port, n_probes, timeout_s):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout_s)
    sock.connect((host, port))

    results = []

    print(f"Probing {host}:{port}  ({n_probes} probes)...")
    print(f"{'#':>4}  {'RTT_MS':>10}  {'OFFSET_MS':>12}  {'STATUS':10}")
    print("-" * 45)

    for i in range(n_probes):
        t_send = time.time()
        pkt    = struct.pack(PROBE_FORMAT, t_send, 0.0)
        try:
            sock.send(pkt)
            reply       = sock.recv(REPLY_SIZE)
            t_recv      = time.time()
            t_s, t_er, t_es = struct.unpack(REPLY_FORMAT, reply)

            rtt_s    = t_recv - t_s
            offset_s = t_er - (t_s + rtt_s / 2.0)
            rtt_ms   = rtt_s   * 1000.0
            off_ms   = offset_s * 1000.0

            results.append((rtt_ms, off_ms))
            print(f"{i+1:>4}  {rtt_ms:>10.3f}  {off_ms:>12.3f}  OK")
        except socket.timeout:
            print(f"{i+1:>4}  {'---':>10}  {'---':>12}  TIMEOUT")
        except Exception as e:
            print(f"{i+1:>4}  {'---':>10}  {'---':>12}  ERROR: {e}")

        time.sleep(0.05)  # 50 ms between probes

    sock.close()
    return results


def main():
    parser = argparse.ArgumentParser(
        description="NTP-independent clock offset probe using Cristian's algorithm"
    )
    parser.add_argument('--host',     required=True, help="RPi ZeroTier IP address")
    parser.add_argument('--port',     type=int, default=PROBE_PORT)
    parser.add_argument('--n',        type=int, default=N_PROBES, help="Number of probes")
    parser.add_argument('--timeout',  type=float, default=2.0, help="Per-probe timeout (s)")
    args = parser.parse_args()

    results = run_probe(args.host, args.port, args.n, args.timeout)

    if not results:
        print("\nNo successful probes. Check that clock_echo_server.py is running on the RPi.")
        return

    rtts    = [r[0] for r in results]
    offsets = [r[1] for r in results]

    print()
    print("=" * 60)
    print("  CRISTIAN'S ALGORITHM -- CLOCK OFFSET ESTIMATION")
    print("=" * 60)
    print(f"  Successful probes : {len(results)} / {args.n}")
    print()
    print("  RTT Statistics (ms):")
    print(f"    Mean   : {statistics.mean(rtts):.3f}")
    print(f"    Std    : {statistics.stdev(rtts):.3f}" if len(rtts) > 1 else "")
    print(f"    Median : {statistics.median(rtts):.3f}")
    print(f"    Min    : {min(rtts):.3f}")
    print(f"    Max    : {max(rtts):.3f}")
    print()
    print("  Clock Offset Statistics (ms)  [positive = RPi clock ahead of PC]:")
    print(f"    Mean   : {statistics.mean(offsets):.3f}")
    print(f"    Std    : {statistics.stdev(offsets):.3f}" if len(offsets) > 1 else "")
    median_off = statistics.median(offsets)
    print(f"    Median : {median_off:.3f}  <-- USE THIS VALUE")
    print()
    print("  INTERPRETATION:")
    print(f"    True OWD = measured_OWD + {median_off:.3f} ms")
    print()
    if abs(median_off) < 10:
        print("  [OK] Clock offset < 10 ms -- NTP is working correctly.")
    elif abs(median_off) < 50:
        print("  [WARN] Clock offset 10-50 ms -- NTP may be poorly converged.")
        print("         Wait 10+ minutes for chrony to fully discipline the clock.")
    else:
        print("  [ERROR] Clock offset > 50 ms -- significant NTP problem.")
        print("          Check 'chronyc tracking' on RPi and 'w32tm /query /status' on PC.")
    print()


if __name__ == '__main__':
    main()
