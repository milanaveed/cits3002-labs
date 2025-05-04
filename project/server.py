"""
server.py

Serves a single-player Battleship session to one connected client.
Game logic is handled entirely on the server using battleship.py.
Client sends FIRE commands, and receives game feedback.

For Tier 1, item 1, you don't need to modify this file much. 
The core issue is in how the client handles incoming messages.
However, if you want to support multiple clients (i.e. progress through further Tiers), you'll need concurrency here too.
"""

import socket
from battleship import run_single_player_game_online

HOST = '127.0.0.1'
PORT = 5050


def main():
    # Print a message indicating that the server is starting and listening on the specified host and port
    print(f"[INFO] Server listening on {HOST}:{PORT}")
    
    # Create a TCP/IP socket using IPv4 (AF_INET) and TCP (SOCK_STREAM)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try: 
            # Bind the socket to the host and port so it can receive incoming connections
            s.bind((HOST, PORT))
            # Start listening for incoming connections; allow up to 2 queued connections
            s.listen(2)
            # Wait for a client to connect; this call blocks until a connection is received
            conn, addr = s.accept()
            # Print the address of the connected client
            print(f"[INFO] Client connected from {addr}")
            # Handle the connection in a context manager to ensure it's closed afterward
            with conn:
                # Wrap the socket in file-like objects for easier text-based reading/writing
                rfile = conn.makefile('r')  # To read from client (input stream)
                wfile = conn.makefile('w')  # To write to client (output stream)
                # Run the single-player Battleship game over the connected socket streams
                run_single_player_game_online(rfile, wfile)
        except Exception as e:
            # After the connection is closed, print a message indicating the client disconnected
            print(f"[ERROR] {e}")
        finally:
            print("[INFO] Client disconnected.")


# HINT: For multiple clients, you'd need to:
# 1. Accept connections in a loop
# 2. Handle each client in a separate thread
# 3. Import threading and create a handle_client function

if __name__ == "__main__":
    main()