import socket
import time

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# Send a fake packet just like sensor.py does
packet = ['ENZ', time.time()] + [0.1]*25
data = str(packet).encode()

sock.sendto(data, ('192.168.8.101', 2098))
print("Sent test packet to 192.168.8.101:2098")
