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
import queue

HOST = '127.0.0.1'
PORT = 5050

total_connections = 0
num_active_players = 0
connection_waiting_queue = queue.Queue()
active_players = {}
player_id = 0
lock = threading.Lock()


def send(wfile, msg):
    """Helper function to send a message with newline + flush."""
    wfile.write(msg + '\n')
    wfile.flush()

def handle_client(conn, addr):
    """Handle a single client connection."""
    #todo: game logic for one connection

    
    pass


def accept_connections(s):
    """Accept incoming connections continuously."""
    global total_connections, connection_waiting_queue, num_active_players, active_players, player_id

    try:
        while True:
            conn, addr = s.accept()
            total_connections += 1
            if num_active_players < 2:
                player_id += 1
                if num_active_players == 0:
                    send(conn.makefile('w'), "Connected to server. Waiting for another player to join...")
                elif num_active_players == 1:
                    send(conn.makefile('w'), "Both players connected. Starting game...")
                    
                print(f"[INFO] A player connected from {addr}.")

                with lock:
                    active_players[player_id] = conn
                
                num_active_players+=1
                
                # client_thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
                # client_thread.start()
            else: # If two players are already connected, reject additional clients
                # send(conn.makefile('w'), "__CLIENT REJECTED__")
                # print(f"[INFO] Rejected connection from {addr}. The game is full at the moment.")
                with lock:
                    connection_waiting_queue.put((conn, addr))
                send(conn.makefile('w'), "__SPECTATOR__")
                print(f"[INFO] New connection from {addr}. The number of total connections: {total_connections}")
                send(conn.makefile('w'), "Connected to server. Currently in the waiting lobby...You are a spectator.")
    except Exception as e:
        print(f"[ERROR] Connection error: {e}")



def main():
    global num_active_players, connection_waiting_queue, active_players

    print(f"[INFO] Server listening on {HOST}:{PORT}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        print("[INFO] Waiting for 2 players to start the game...")

        acceptor_thread = threading.Thread(target=accept_connections, args=(s,), daemon=True)
        acceptor_thread.start()

        try:
            while True:
                if num_active_players == 2:
                    # Wait for two players to connect
                    print("[INFO] Starting game session...")
                    p1_conn = list(active_players.values())[0]
                    p2_conn = list(active_players.values())[1]

                    p1_r = p1_conn.makefile('r')
                    p1_w = p1_conn.makefile('w')
                    p2_r = p2_conn.makefile('r')
                    p2_w = p2_conn.makefile('w')

                    try:
                        run_double_player_game_online(p1_r, p1_w, p2_r, p2_w)
                    except Exception as e:
                        print(f"[ERROR] Game session error: {e}")
                    finally:
                        num_active_players = 0
                        active_players.clear()
                        p1_conn.close()
                        p2_conn.close()
                        print("[INFO] Game session ended. Waiting for players to join...")
        
        except KeyboardInterrupt:
            print("\n[INFO] Server manually stopped. Shutting down.")
        except Exception as e:
            print(f"[ERROR] Unexpected server error: {e}")



if __name__ == "__main__":
    main()