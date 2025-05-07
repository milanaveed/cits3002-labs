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
from battleship import run_double_player_game_online
import time
import queue
from battleship import *

HOST = '127.0.0.1'
PORT = 5050

total_connections = 0
num_active_players = 0
connection_waiting_queue = queue.Queue()
active_players = {}
client_id = 0
lock = threading.Lock()
num_player_ready = 0
game_ready = False
shared_boards = {}
current_turn = 0 # 0 for player 1, 1 for player 2
game_status = None

game_ready_cond = threading.Condition()

def send(wfile, msg):
    """Helper function to send a message with newline + flush."""
    wfile.write(msg + '\n')
    wfile.flush()

def remove_connection(id):
    """Remove a specific connection from the connection waiting queue."""
    global connection_waiting_queue
    temp = queue.Queue()
    removed = False

    with lock:
        while not connection_waiting_queue.empty():
            conn = connection_waiting_queue.get()
            if conn[0] != id:
                temp.put(conn)
            else:
                removed = True  # Only remove the first match

        # Restore remaining connections
        while not temp.empty():
            connection_waiting_queue.put(temp.get())

    return removed

def get_player_number(id):
    """Get the current player's number."""
    global active_players
    for key, value in active_players.items():
        if value[0] == id:
            return key
        
def send_board(wfile, board):
        send(wfile, "GRID")
        send(wfile, "  " + " ".join(str(i + 1).rjust(2) for i in range(board.size)))
        for r in range(board.size):
            row_label = chr(ord('A') + r)
            row_str = " ".join(board.display_grid[r][c] for c in range(board.size))
            send(wfile, f"{row_label:2} {row_str}")
        send(wfile, "")  # end of board

def broad_cast_to_spectators(msg):
    """Send a message to all spectators."""
    global connection_waiting_queue
    with lock:
        for connection in list(connection_waiting_queue.queue):
            send(connection[3], msg)  # connection[3] is the writer

def handle_client(id, conn, current_r, current_w, spectator_mode):
    """Handle a single client connection."""
    global total_connections, num_active_players, connection_waiting_queue, active_players, num_player_ready, game_ready, shared_boards, current_turn
    # If in spectator mode
    if spectator_mode:
        send(current_w, "Connected to server. Currently in the waiting lobby...")
        send(current_w, "__SPECTATOR__")

    while spectator_mode:
        message = current_r.readline().strip()
        if message == "QUIT":
            print(f"[INFO] Spectator with ID {id} disconnected.")
            with lock:
                total_connections -= 1
                remove_connection(id)
                print("connection waiting queue:", connection_waiting_queue)
            conn.close()
            break

        #todo: game status changes and spectator_mode might change

    if not spectator_mode:
        # If not in spectator mode, start the game
        #if not disconnected, if it's the start of a new game
        send(current_w, f"Welcome player {id}!")

        player_number = get_player_number(id)

        board = Board()
        board.place_ships_randomly()
        shared_boards[player_number] = board
        send(current_w, f"You board is ready.")
        print(f"[GAME] Player {id}'s board is ready.")

        # Waiting for opponent to join and initialise the board
        with game_ready_cond:
            num_player_ready += 1
            if num_player_ready == 2:
                print(f"[GAME] Game started from player {player_number+1}.")
                game_ready_cond.notify_all()  # Notify all waiting threads
            else:
                game_ready_cond.wait()
        
        opponent_player_number = 1 - player_number
        while True:
            with lock:
                if opponent_player_number in active_players:
                    opponent_r = active_players[opponent_player_number][2]
                    opponent_w = active_players[opponent_player_number][3]
                    break
        
        send(current_w, f"Game started.")
        opponent_board = shared_boards[opponent_player_number]

        while True:
            if current_turn == player_number:
                print(f"[GAME] Player {id}'s turn.")
                send(current_w, f"\nPlayer {player_number+1}, it's your turn.")
                send_board(current_w, opponent_board)
                send(current_w, "__YOUR TURN__")
                send(current_w, "Enter coordinate to fire at (e.g. B5):")

                # wait for input with a timeout
                ready, _, _ = select.select([current_r, opponent_r], [], [], 30) # wait for input for 30 seconds
                if not ready:
                    send(current_w, "Timeout! You took too long to respond. It's now the other player's turn.")
                    send(opponent_w, "The other player took too long to respond.")
                    current_turn = 1 - current_turn  # Switch turns
                    continue
                
                if opponent_r in ready:
                    opponent_msg = opponent_r.readline().strip()
                    if opponent_msg == 'QUIT':
                        send(current_w, "The other player has disconnected and forfeited.")
                        send(current_w, "__GAME OVER__")
                        break
                
                guess = current_r.readline().strip()
                if guess == 'QUIT':
                    send(opponent_w, "The other player has forfeited the game.")
                    send(opponent_w, "__GAME OVER__")
                    break
                elif 'FIRE' in guess:
                    guess = guess.split(' ')[1]
                    try:
                        row, col = parse_coordinate(guess)
                        result, sunk_ship = opponent_board.fire_at(row, col)
                        shared_boards[opponent_player_number] = opponent_board  # update shared board

                        if result == 'hit':
                            if sunk_ship:
                                msg = f"HIT! You sank the {sunk_ship}!"
                                if opponent_board.all_ships_sunk():
                                    send(current_w, "\nCongratulations! You sank all opponent's ships.")
                                    send_board(current_w, opponent_board)
                                    send(current_w, "__GAME OVER__")
                                    send(opponent_w,  msg="\nYou lose. All your ships have been sunk.")
                                    send(opponent_w, "__GAME OVER__")
                                    break
                            else:
                                msg = "HIT!"
                        elif result == 'miss':
                            msg = "MISS!"
                        elif result == 'already_shot':
                            msg = "You already fired at that location."
                        else:
                            # In principle, this should not happen
                            msg = "Unknown result."

                        send(current_w, msg)

                        current_turn = 1 - current_turn  # Switch turns

                    except Exception as e:
                        send(current_w, f"Invalid input: {e}")
                        continue

        # Close both writers after game ends
        with lock:
            num_active_players = 0
            active_players.clear()
            current_turn = 0
        conn.close()
        print("[INFO] Game session ended. Waiting for players to join...")


def main():
    global total_connections, connection_waiting_queue, num_active_players, active_players, client_id

    print(f"[INFO] Server listening on {HOST}:{PORT}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        print("[INFO] Waiting for 2 players to start the game...")

        # acceptor_thread = threading.Thread(target=accept_connections, args=(s,), daemon=True)
        # acceptor_thread.start()

        try:
            while True:
                conn, addr = s.accept()
                rfile = conn.makefile('r')
                wfile = conn.makefile('w')

                total_connections += 1
                # num_active_players = 3 #!testing
                if num_active_players < 2:
                    client_id += 1
                    send(conn.makefile('w'), "Connected to server. Waiting for opponent...")
                    print(f"[INFO] A player connected from {addr}.")

                    with lock:
                        if 0 in active_players:
                            active_players[1] = (client_id, conn, rfile, wfile)
                        else:
                            active_players[0] = (client_id, conn, rfile, wfile)
                    
                    num_active_players+=1
                    
                    client_thread = threading.Thread(target=handle_client, args=(client_id, conn, rfile, wfile, False), daemon=True)
                    client_thread.start()
                else: # If two players are already connected
                    with lock:
                        connection_waiting_queue.put((client_id, conn, rfile, wfile))
                    client_thread = threading.Thread(target=handle_client, args=(client_id, conn, rfile, wfile, True), daemon=True)
                    client_thread.start()
                    
                # finally:
                #     num_active_players = 0
                #     active_players.clear()
                #     p1_conn.close()
                #     p2_conn.close()
                #     print("[INFO] Game session ended. Waiting for players to join...")
        except KeyboardInterrupt:
            print("\n[INFO] Server manually stopped. Shutting down.")
        except Exception as e:
            print(f"[ERROR] Unexpected server error: {e}")



if __name__ == "__main__":
    main()