"""
packet.py

Implements a custom packet protocol for structured and reliable communication between
Battleship clients and the server.

Key features:
- Packet creation (`make_packet`): Includes sequence number, type, length, and CRC32 checksum.
- Packet parsing (`parse_packet`): Validates and extracts payload data with checksum verification.
- Checksum calculation using zlib CRC32 to ensure data integrity.
- Full packet reception (`recv_full_packet`): Handles reading complete packets from a socket.

Supports both game data and chat messages via packet types.
"""
# packet.py
import zlib
import struct

# Packet types
TYPE_DATA = 1
TYPE_CHAT = 4

def compute_checksum(payload: bytes) -> int:
    """Computes a CRC32 checksum for the given payload."""
    return zlib.crc32(payload) & 0xffffffff # Ensure checksum is 32 bits

def make_packet(seq: int, ptype: int, payload: str) -> bytes:
    """Creates a packet with the given sequence number, type, and payload."""
    payload_bytes = payload.encode('utf-8') # Convert payload to bytes
    payload_len = len(payload_bytes) # Length of the payload
    header = struct.pack('!IBH', seq, ptype, payload_len) # Pack the header with sequence number, type, and payload length
    checksum = compute_checksum(payload_bytes)  # Compute checksum for the payload
    body = header + payload_bytes + struct.pack('!I', checksum) # Append checksum to the body
    total_len = len(body) # Total length of the packet
    return struct.pack('!I', total_len) + body  # 4-byte length prefix

def parse_packet(packet: bytes) -> tuple[int, int, str] | None:
    """Parses a packet and returns the sequence number, type, and payload."""
    if len(packet) < 11: # Minimum length for a valid packet
        return None
    try:
        header = packet[:7] # First 7 bytes are the header
        seq, ptype, payload_len = struct.unpack('!IBH', header)   # Unpack the header
        payload_end = 7 + payload_len # Calculate the end of the payload
        payload_bytes = packet[7:payload_end] # Extract the payload
        received_checksum = struct.unpack('!I', packet[payload_end:payload_end + 4])[0] # Extract the checksum

        if compute_checksum(payload_bytes) != received_checksum: # Check if the checksum matches
            return None
        return seq, ptype, payload_bytes.decode('utf-8')
    except Exception as e:
        print(f"[ERROR] Packet parsing failed: {e}")
        return None
    

def recv_full_packet(sock) -> bytes:
    """Receive a full packet from the server."""
    try:
        # Read the 4-byte length prefix
        length_data = sock.recv(4)
        if len(length_data) < 4: # Check if we received the length prefix
            return None
        packet_len = struct.unpack('!I', length_data)[0] # Unpack the length prefix

        # Now read the full packet
        packet_data = b'' # Initialize an empty byte array
        while len(packet_data) < packet_len: # While we haven't received the full packet
            chunk = sock.recv(packet_len - len(packet_data)) # Read the remaining bytes
            if not chunk: # Check if we received any data
                return None
            packet_data += chunk  # Append the chunk to the packet data
        return packet_data
    except:
        return None
