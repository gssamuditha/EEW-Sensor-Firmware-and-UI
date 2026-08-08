"""
clock_echo_server.py - UDP Clock Echo Server for Cristian's Algorithm
======================================================================
Run this on the Raspberry Pi BEFORE running clock_offset_probe.py on your PC.

Usage
-----
  python clock_echo_server.py             # default port 9876
  python clock_echo_server.py --port 9876
"""

import argparse
import socket
import struct
import time

PROBE_FORMAT = '!dd'    # t_send(8B) + padding(8B)
REPLY_FORMAT = '!ddd'   # t_send(8B) + t_echo_recv(8B) + t_echo_send(8B)
PROBE_SIZE   = struct.calcsize(PROBE_FORMAT)


def main():
    parser = argparse.ArgumentParser(description="UDP echo server for clock offset probing")
    parser.add_argument('--port', type=int, default=9876, help="UDP port to listen on")
    parser.add_argument('--ip',   default='0.0.0.0', help="Bind IP")
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((args.ip, args.port))
    sock.settimeout(1.0)

    print(f"Clock Echo Server listening on {args.ip}:{args.port}")
    print("Ctrl+C to stop.")

    n = 0
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            t_echo_recv = time.time()   # record receive time immediately

            if len(data) >= PROBE_SIZE:
                t_send, _ = struct.unpack(PROBE_FORMAT, data[:PROBE_SIZE])
                t_echo_send = time.time()
                reply = struct.pack(REPLY_FORMAT, t_send, t_echo_recv, t_echo_send)
                sock.sendto(reply, addr)
                n += 1
                if n % 20 == 0:
                    print(f"  Echoed {n} probes from {addr[0]}")
        except socket.timeout:
            continue
        except KeyboardInterrupt:
            print(f"\nStopped after {n} probes.")
            break

    sock.close()


if __name__ == '__main__':
    main()
