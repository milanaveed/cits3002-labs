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
import time

HOST = '127.0.0.1'
PORT = 5050

def send(wfile, msg):
    """Helper function to send a message with newline + flush."""
    wfile.write(msg + '\n')
    wfile.flush()


# def handle_game(p1_conn, p2_conn):
#     """Sets up file-like objects and starts a multiplayer game."""
#     print("[INFO] Starting a new 2-player game session.")

#     p1_r = p1_conn.makefile('r')
#     p1_w = p1_conn.makefile('w')
#     p2_r = p2_conn.makefile('r')
#     p2_w = p2_conn.makefile('w')

#     try:
#         run_double_player_game_online(p1_r, p1_w, p2_r, p2_w)
#     except Exception as e:
#         print(f"[ERROR] Game session error: {e}")
#     finally:
#         p1_conn.close()
#         p2_conn.close()
#         print("[INFO] Game session ended. Connections closed.")


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
                    p1_conn.close()
                    p2_conn.close()
                    print("[INFO] Game session ended. Starting a new game session...")
                    

        except KeyboardInterrupt:
            print("\n[INFO] Server manually stopped. Shutting down.")
        except Exception as e:
            print(f"[ERROR] Unexpected server error: {e}")



if __name__ == "__main__":
    main()