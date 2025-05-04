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
import threading
from battleship import run_single_player_game_online, run_double_player_game_online

HOST = '127.0.0.1'
PORT = 5050

def send(wfile, msg):
    """Helper function to send a message with newline + flush."""
    wfile.write(msg + '\n')
    wfile.flush()


def handle_game(p1_conn, p2_conn):
    """Sets up file-like objects and starts a multiplayer game."""
    print("[INFO] Starting a new 2-player game session.")

    p1_r = p1_conn.makefile('r')
    p1_w = p1_conn.makefile('w')
    p2_r = p2_conn.makefile('r')
    p2_w = p2_conn.makefile('w')

    try:
        run_double_player_game_online(p1_r, p1_w, p2_r, p2_w)
    except Exception as e:
        print(f"[ERROR] Game session error: {e}")
    finally:
        p1_conn.close()
        p2_conn.close()
        print("[INFO] Game session ended. Connections closed.")


def main():
    print(f"[INFO] Server listening on {HOST}:{PORT}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()

        try:
            while True:
                print("[INFO] Waiting for Player 1...")
                p1_conn, addr1 = s.accept()
                print(f"[INFO] Player 1 connected from {addr1}")
                send(p1_conn.makefile('w'), "Waiting for Player 2 to join...")

                print("[INFO] Waiting for Player 2...")
                p2_conn, addr2 = s.accept()
                print(f"[INFO] Player 2 connected from {addr2}")

                send(p1_conn.makefile('w'), "Player 2 has joined. Starting game...")

                p1_r = p1_conn.makefile('r')
                p1_w = p1_conn.makefile('w')
                p2_r = p2_conn.makefile('r')
                p2_w = p2_conn.makefile('w')

                try:
                    run_double_player_game_online(p1_r, p1_w, p2_r, p2_w)
                except Exception as e:
                    print(f"[ERROR] Game session error: {e}")
                finally:
                    print("hello time to close here") #TODO: failed to close when game ends or one player disconnects
                    p1_conn.close()
                    p2_conn.close()
                    print("[INFO] Game session ended. Connections closed.")

        except KeyboardInterrupt:
            print("\n[INFO] Server manually stopped. Shutting down.")
        except Exception as e:
            print(f"[ERROR] Unexpected server error: {e}")


# def main():
#     # Print a message indicating that the server is starting and listening on the specified host and port
#     print(f"[INFO] Server listening on {HOST}:{PORT}")
    
#     # Create a TCP/IP socket using IPv4 (AF_INET) and TCP (SOCK_STREAM)
#     with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
#         s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
#         try: 
#             # Bind the socket to the host and port so it can receive incoming connections
#             s.bind((HOST, PORT))
#             # Start listening for incoming connections; allow up to 2 queued connections
#             s.listen(2)
#             # Wait for a client to connect; this call blocks until a connection is received
#             conn, addr = s.accept()
#             # Print the address of the connected client
#             print(f"[INFO] Client connected from {addr}")
#             # Handle the connection in a context manager to ensure it's closed afterward
#             with conn:
#                 # Wrap the socket in file-like objects for easier text-based reading/writing
#                 rfile = conn.makefile('r')  # To read from client (input stream)
#                 wfile = conn.makefile('w')  # To write to client (output stream)
#                 # Run the single-player Battleship game over the connected socket streams
#                 run_single_player_game_online(rfile, wfile)
#         except Exception as e:
#             # After the connection is closed, print a message indicating the client disconnected
#             print(f"[ERROR] {e}")
#         finally:
#             print("[INFO] Client disconnected.")


# HINT: For multiple clients, you'd need to:
# 1. Accept connections in a loop
# 2. Handle each client in a separate thread
# 3. Import threading and create a handle_client function

if __name__ == "__main__":
    main()