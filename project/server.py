"""
server.py

Serves a single-player Battleship session to one connected client.
Game logic is handled entirely on the server using battleship.py.
Client sends FIRE commands, and receives game feedback.
"""

import socket
import threading
from battleship import *

HOST = '127.0.0.1'
PORT = 5050

def handle_client(conn):
    try:
        conn.settimeout(10)
        data = recv_full_packet(conn)
        parsed = parse_packet(data)
        if not parsed:
            print("[ERROR] Invalid or corrupted initial packet. Dropping connection.")
            conn.close()
            return
        _, _, first_line = parsed
        if not first_line.startswith("ID "):
            print("[ERROR] Missing client ID.")
            conn.close()
            return
        client_id = first_line[3:].strip()
        print(f"[INFO] Player ID {client_id} connected.")
        player = PlayerSession(client_id, conn)
        player.run()
    except Exception as e:
        print(f"[ERROR] Failed to handle client: {e}")
        conn.close()

def main():
    print(f"[INFO] Server listening on {HOST}:{PORT}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()

        try:
            while True:
                conn, _ = s.accept()
                threading.Thread(target=handle_client, args=(conn,), daemon=True).start()
        except KeyboardInterrupt:
            print("\n[INFO] Server manually stopped.")
        except Exception as e:
            print(f"[ERROR] Server error: {e}")


if __name__ == "__main__":
    main()
