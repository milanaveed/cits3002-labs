"""
server.py

Launches a multithreaded Battleship server that handles multiple clients, including
players and spectators. Delegates all game logic to battleship.py via PlayerSession.

Key features:
- Accepts and manages concurrent client connections using threads.
- Assigns client IDs and initializes game sessions.
- Supports reconnection, spectator mode, and chat via PlayerSession.
- Listens continuously for new clients and runs the game loop per player.

Each client connection is processed in its own thread to enable real-time multiplayer play.
"""
import socket
import threading
from battleship import *

HOST = '127.0.0.1'
PORT = 5050


def handle_client(conn):
    """Handles a single client connection."""
    try:
        conn.settimeout(10)
        data = recv_full_packet(conn) # receive initial packet from the client side (client ID)
        parsed = parse_packet(data) # parse initial packet
        if not parsed:
            print("[ERROR] Invalid or corrupted initial packet. Dropping connection.")
            conn.close()
            return
        _, _, first_line = parsed
        if not first_line.startswith("ID "): # check if the first line starts with "ID "
            print("[ERROR] Missing client ID.")
            conn.close()
            return
        client_id = first_line[3:].strip() # extract client ID
        print(f"[INFO] Player ID {client_id} connected.")
        player = PlayerSession(client_id, conn) # create a PlayerSession object
        player.run()    # run the game loop
    except Exception as e:
        print(f"[ERROR] Failed to handle client: {e}")
        conn.close()

def main():
    """Main function to start the server."""
    print(f"[INFO] Server listening on {HOST}:{PORT}") 
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s: # create socket
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # allow address reuse
        s.bind((HOST, PORT))  # bind to host and port
        s.listen() # listen for incoming connections

        try:
            while True: # accept connections in a loop
                conn, _ = s.accept() # accept a connection
                threading.Thread(target=handle_client, args=(conn,), daemon=True).start() # handle client in a new thread
        except KeyboardInterrupt:
            print("\n[INFO] Server manually stopped.")
        except Exception as e:
            print(f"[ERROR] Server error: {e}")


if __name__ == "__main__":
    main()
