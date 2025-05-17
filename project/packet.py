# packet.py
import zlib
import struct

# Packet types
TYPE_DATA = 1
TYPE_ACK = 2
TYPE_NACK = 3

def compute_checksum(payload: bytes) -> int:
    return zlib.crc32(payload) & 0xffffffff

# def make_packet(seq: int, ptype: int, payload: str) -> bytes:
#     payload_bytes = str(payload).encode('utf-8')
#     payload_len = len(payload_bytes)
#     header = struct.pack('!IBH', seq, ptype, payload_len)
#     checksum = compute_checksum(payload_bytes)
#     return header + payload_bytes + struct.pack('!I', checksum)

def make_packet(seq: int, ptype: int, payload: str) -> bytes:
    payload_bytes = payload.encode('utf-8')
    payload_len = len(payload_bytes)
    header = struct.pack('!IBH', seq, ptype, payload_len)
    checksum = compute_checksum(payload_bytes)
    body = header + payload_bytes + struct.pack('!I', checksum)
    total_len = len(body)
    return struct.pack('!I', total_len) + body  # 4-byte length prefix

def parse_packet(packet: bytes) -> tuple[int, int, str] | None:
    if len(packet) < 11:
        return None
    try:
        header = packet[:7]
        seq, ptype, payload_len = struct.unpack('!IBH', header)
        payload_end = 7 + payload_len
        payload_bytes = packet[7:payload_end]
        received_checksum = struct.unpack('!I', packet[payload_end:payload_end + 4])[0]

        if compute_checksum(payload_bytes) != received_checksum:
            return None
        return seq, ptype, payload_bytes.decode('utf-8')
    except Exception as e:
        print(f"[ERROR] Packet parsing failed: {e}")
        return None
    

def recv_full_packet(sock) -> bytes:
    try:
        # Read the 4-byte length prefix
        length_data = sock.recv(4)
        if len(length_data) < 4:
            return None
        packet_len = struct.unpack('!I', length_data)[0]

        # Now read the full packet
        packet_data = b''
        while len(packet_data) < packet_len:
            chunk = sock.recv(packet_len - len(packet_data))
            if not chunk:
                return None
            packet_data += chunk
        return packet_data
    except:
        return None
