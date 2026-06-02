import socket
import ast
import argparse
import time

def main():
    parser = argparse.ArgumentParser(description="Record EEW Sensor UDP Data on PC")
    parser.add_argument('--port', type=int, default=2098, help="UDP port to listen on (default 2098)")
    parser.add_argument('--ip', type=str, default='0.0.0.0', help="IP to bind to (0.0.0.0 for all interfaces)")
    parser.add_argument('--output', type=str, default='eew_udp_record.csv', help="Output CSV filename")
    args = parser.parse_args()

    # Set up the UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # Allow port reuse if another process is hanging onto it
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((args.ip, args.port))
    # A timeout is REQUIRED on Windows, otherwise recvfrom() blocks Ctrl+C forever
    sock.settimeout(1.0)

    print(f"==================================================")
    print(f"📡 Listening for EEW UDP data on {args.ip}:{args.port}")
    print(f"💾 Saving data to: {args.output}")
    print(f"Press Ctrl+C to stop recording.")
    print(f"==================================================\n")

    packet_count = 0

    with open(args.output, 'w') as f:
        # We don't know the exact number of samples per packet yet, so we'll just write headers for channel and timestamp
        f.write("channel,timestamp,samples...\n")
        
        try:
            while True:
                try:
                    data, addr = sock.recvfrom(4096)
                except socket.timeout:
                    # This happens every 1 second if no data arrives.
                    continue

                # Print raw packet length to prove we received SOMETHING
                # print(f"Received {len(data)} bytes from {addr[0]}")
                
                try:
                    # The sensor sends data as str(packet).encode(), so we decode and evaluate it back to a Python list
                    decoded = data.decode('utf-8')
                    packet = ast.literal_eval(decoded)
                    
                    if isinstance(packet, list) and len(packet) >= 2:
                        channel = packet[0]
                        timestamp = packet[1]
                        samples = packet[2:]
                        
                        packet_count += 1
                        if packet_count % 10 == 0:
                            print(f"[{time.strftime('%H:%M:%S')}] Received {packet_count} packets. Latest: {channel} from {addr[0]} with {len(samples)} samples")
                        
                        # Write the row to CSV
                        row = f"{channel},{timestamp}," + ",".join(map(str, samples)) + "\n"
                        f.write(row)
                        f.flush() # Ensure it's written to disk immediately
                except Exception as e:
                    print(f"⚠️ Failed to parse packet from {addr[0]}: {e}")
        except KeyboardInterrupt:
            print(f"\n\n🛑 Stopped recording. Total packets received: {packet_count}")
            print(f"Data saved to {args.output}")

if __name__ == "__main__":
    main()
