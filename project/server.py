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
connection_waiting_queue = queue.Queue()
current_players = {}
lock = threading.Lock()
num_player_ready = 0
shared_boards = {}
current_turn = 0 # 0 for player 1, 1 for player 2
player_ids = {}  # id -> player_num
game_status = None
RECONNECT_TIMEOUT = 60
left_player_id = -1

game_ready_cond = threading.Condition()

def send(wfile, msg):
    """Helper function to send a message with newline + flush."""
    try:
        wfile.write(msg + '\n')
        wfile.flush()
    except (BrokenPipeError, OSError):
        print(f"[ERROR] Could not send to client {wfile}: {msg}")

def remove_connection(id):
    """Remove a specific connection from the connection waiting queue."""
    global connection_waiting_queue
    temp = queue.Queue()
    with lock:
        while not connection_waiting_queue.empty():
            conn = connection_waiting_queue.get()
            if conn[0] != id:
                temp.put(conn)
        # Restore remaining connections
        while not temp.empty():
            connection_waiting_queue.put(temp.get())

def get_player_number(id):
    """Get the current player's number."""
    global current_players
    for key, value in current_players.items():
        if value[0] == id:
            return key
    # return player_ids.get(id) #todo: confirm
        
def send_board(wfile, board):
        send(wfile, "GRID")
        send(wfile, "  " + " ".join(str(i + 1).rjust(2) for i in range(board.size)))
        for r in range(board.size):
            row_label = chr(ord('A') + r)
            row_str = " ".join(board.display_grid[r][c] for c in range(board.size))
            send(wfile, f"{row_label:2} {row_str}")
        send(wfile, "")  # end of board

def broadcast_to_spectators(msg):
    """Send a message to all spectators."""
    global connection_waiting_queue
    with lock:
        for connection in list(connection_waiting_queue.queue):
            send(connection[3], msg)  # connection[3] is the writer

def broadcast_board_to_spectators(board, msg):
    """Send the current board state to all spectators."""
    global connection_waiting_queue
    with lock:
        for connection in list(connection_waiting_queue.queue):
            writer = connection[3]
            send(writer, msg)
            send_board(writer, board)

def reconnection_timeout_handler():
    """Handle reconnection timeout."""
    global game_status
    with lock:
        if game_status == "ONE PLAYER LEFT":
            game_status = "FORFEITED"

def handle_client(id, conn, current_r, current_w, spectator_mode):
    global connection_waiting_queue, current_players, num_player_ready
    global shared_boards, current_turn, game_status, left_player_id
    restored = False

    # print('current_players:', current_players)
    # print('left_player_id:', left_player_id)
    # print('game_status:', game_status)
    with lock:
        if len(current_players) < 2:
            spectator_mode = False
            if 0 in current_players:
                current_players[1] = (id, conn, current_r, current_w)
            else:
                current_players[0] = (id, conn, current_r, current_w)
        elif id == left_player_id and game_status == "ONE PLAYER LEFT":
            # print('come on b aby')
            spectator_mode = False
            restored = True
            game_status = "RUNNING"
            print('game_status:', game_status)
        else:
            print('game_status:', game_status)
            print('num current players:', len(current_players))
            connection_waiting_queue.put((id, conn, current_r, current_w))
            spectator_mode = True

    # Spectator handling
    if spectator_mode:
        send(current_w, "Connected to server. Currently in the waiting lobby...")
        send(current_w, "__SPECTATOR__")
        while spectator_mode: #todo: when GAME OVER OR FORFEITED, check if this is going to be the next player, delay new game start in 5s, also need to send(current_w, "__PLAYER__") to cancel spectator mode
            message = current_r.readline().strip()
            if message == "QUIT":
                print(f"[INFO] Spectator with ID {id} disconnected.")
                with lock:
                    remove_connection(id)
                conn.close()
                return

    with lock:
        player_number = get_player_number(id)
        # restored = True if player_number in shared_boards else False 

    # print("f1")
    send(current_w, f"Welcome back Player {id}!" if restored else f"Welcome Player {id}!")
     # Create or restore board

    if player_number not in shared_boards:
        board = Board()
        board.place_ships_randomly()
        shared_boards[player_number] = board
        send(current_w, f"Your board is ready.")
        print(f"[GAME] Player {id}'s board is ready.") 

    # Wait for both players to be ready
    if not restored:
        with game_ready_cond:
            num_player_ready += 1
            if num_player_ready == 2:
                game_status = "RUNNING"
                print(f"[GAME] Game started.")
                game_ready_cond.notify_all()
            else:
                game_ready_cond.wait()
    else:
        num_player_ready = 2
        print('num_player_ready:', num_player_ready)

    # Identify opponent
    opponent_player_number = 1 - player_number
    while True:
        with lock:
            if opponent_player_number in current_players:
                opponent_r = current_players[opponent_player_number][2]
                opponent_w = current_players[opponent_player_number][3]
                opponent_id = current_players[opponent_player_number][0]
                break
    
    opponent_board = shared_boards[opponent_player_number]

    if restored:
        send(current_w, f"Restored game with Player {opponent_id}. It's opponent's turn.")
        send(opponent_w, f"Restored game with Player {id}.")
        broadcast_to_spectators(f"Player {id} restored game with Player {opponent_id}.")
    else:
        send(current_w, f"Game started.")
        broadcast_to_spectators(f"Game started! Player {id} vs Player {opponent_id}.")

    # Game loop
    while True:
        with lock:
            if game_status == "FORFEITED" or game_status == "OVER":
                break
            elif game_status == "ONE PLAYER LEFT" and id == left_player_id:
                break

            # print('current_turn:', current_turn)
            # print('player_number:', player_number)
        
        if current_turn == player_number:
            try:
                print(f"[GAME] Player {id}'s turn.")
                send(current_w, f"\nPlayer {player_number + 1}, it's your turn.")
                with lock:
                    print('game_status2:', game_status)
                    if game_status != "ONE PLAYER LEFT" and game_status != "FORFEITED":
                        send(opponent_w, f"\nPlayer {opponent_player_number+1}, it's your opponent's turn.")
                send_board(current_w, opponent_board)
                send(current_w, "__YOUR TURN__")
                send(current_w, "Enter coordinate to fire at (e.g. B5):")

            except Exception as e:
                print(f"[ERROR] Game error1: {e}")


            try:
                if game_status == "RUNNING":
                    ready, _, _ = select.select([current_r, opponent_r], [], [], 30)
                    if not ready:
                        send(current_w, "Timeout! You took too long.")
                        send(opponent_w, "The other player timed out.")
                        with lock:
                            current_turn = 1 - current_turn
                        continue
                else:
                    ready, _, _ = select.select([current_r], [], [], 30)
                    if not ready:
                        send(current_w, "Timeout! You took too long.")
                        with lock:
                            send(current_w, "It's your opponent's turn.")
                            time.sleep(20)
                        continue
            except Exception as e:
                print(f"[ERROR] Game error2: {e}")
            
            try:
                # Handle disconnect
                print('hello')
                if opponent_r in ready:
                    print('????')
                    opponent_msg = opponent_r.readline().strip()
                    print('oooo')
                    if opponent_msg == 'QUIT':
                        print('kkkk')
                        send(current_w, "The other player has disconnected.")
                        broadcast_to_spectators(f"Player {opponent_id} disconnected.")
                        with lock:
                            game_status = "ONE PLAYER LEFT"
                            left_player_id = opponent_id
                            # print('left_player_id:', left_player_id)
                            # print('left_player_number', opponent_player_number+1)
                            # game_ready_cond.notify_all()
                        timer = threading.Timer(RECONNECT_TIMEOUT, reconnection_timeout_handler)
                        timer.start()

                        # send(current_w, "__GAME OVER__")
                        # with game_ready_cond:
                        #     game_status = "DISCONNECTED"
                        #     game_ready_cond.notify_all()
                        # break
            except Exception as e:
                print(f"[ERROR] Game error3: {e}")

            try:
                guess = current_r.readline()
                if not guess:
                    send(current_w, "Connection lost.")
                    send(opponent_w, "The other player has disconnected.")
                    # send(opponent_w, "__GAME OVER__")
                    with lock:
                        left_player_id = id
                        game_status = "ONE PLAYER LEFT"
                        # game_ready_cond.notify_all()
                    timer = threading.Timer(RECONNECT_TIMEOUT, reconnection_timeout_handler)
                    timer.start()
                    with lock:
                        current_turn = 1 - current_turn
                    break

            except Exception as e:
                print(f"[ERROR] Game error4: {e}")

            try:
                guess = guess.strip()
                if guess == 'QUIT':
                    send(opponent_w, "The other player left.")
                    # send(opponent_w, "__GAME OVER__")
                    with lock:
                        left_player_id = id
                        game_status = "ONE PLAYER LEFT"
                        # game_ready_cond.notify_all()
                    timer = threading.Timer(RECONNECT_TIMEOUT, reconnection_timeout_handler)
                    timer.start()
                    with lock:
                        current_turn = 1 - current_turn 
                    break
            except Exception as e:
                print(f"[ERROR] Game error5: {e}")

            try:
                if 'FIRE' in guess:
                    guess = guess.split(' ')[1]
                    row, col = parse_coordinate(guess)
                    result, sunk_ship = opponent_board.fire_at(row, col)
                    shared_boards[opponent_player_number] = opponent_board
                    broadcast_board_to_spectators(opponent_board, f"\nPlayer {id} fired Player {opponent_id} at {guess}.")

                    if result == 'hit':
                        if sunk_ship:
                            msg = f"HIT! You sank the {sunk_ship}!"
                            broadcast_to_spectators(f"Result: HIT! Player {id} sank the {sunk_ship}.\n")
                            if opponent_board.all_ships_sunk():
                                send(current_w, "\nCongratulations! You sank all opponent's ships.")
                                send_board(current_w, opponent_board)
                                send(current_w, "__GAME OVER__")
                                send(opponent_w, "\nYou lose. All your ships have been sunk.")
                                send(opponent_w, "__GAME OVER__")
                                broadcast_to_spectators(f"Player {id} sank all Player {opponent_id}'s ships. Game ended.\n")
                                with lock:
                                    game_status = "OVER"
                                    # game_ready_cond.notify_all()
                                break
                        else:
                            msg = "HIT!"
                            broadcast_to_spectators("Result: HIT!\n")
                    elif result == 'miss':
                        msg = "MISS!"
                        broadcast_to_spectators("Result: MISS!\n")
                    elif result == 'already_shot':
                        msg = "You already fired at that location."
                        broadcast_to_spectators("Result: Already shot.\n")
                    else:
                        msg = "Unknown result."

                    send(current_w, msg)

                    with lock: #todo: improve
                        if game_status != "ONE PLAYER LEFT":
                            current_turn = 1 - current_turn
                        else:
                            send(current_w, "It's your opponent's turn.")
                            time.sleep(20)
            except Exception as e:
                send(current_w, "__GAME OVER__")
                print(f"[ERROR] Game error: {e}")
                break


    with lock:
        if player_number in current_players:
            num_player_ready -= 1
            # print(f"Player {id} disconnected. Remaining players: {num_player_ready}")
            if game_status == "FORFEITED":
                send(current_w, "__FORFEITED__") #? why it didn't execute the next line? stuck here with >>?
                broadcast_to_spectators(f"Player {opponent_id} forfeited the game. Player {id} win!")
                game_status = "OVER"
            if game_status == "OVER":
                current_players.clear()
                shared_boards.clear()
                left_player_id = -1
                num_player_ready = 0
                # print('game over, len(current_players):', len(current_players))

    conn.close()
    print(f"[INFO] Game session ended for player {player_number+1}.")


def main():
    global total_connections, connection_waiting_queue, current_players

    print(f"[INFO] Server listening on {HOST}:{PORT}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        print("[INFO] Waiting for 2 players to start the game...")

        try:
            while True:
                conn, addr = s.accept()
                rfile = conn.makefile('r')
                wfile = conn.makefile('w')
                first_line = rfile.readline().strip()
                if first_line.startswith("ID "):
                    client_id = first_line[3:]
                else:
                    send(wfile, "Missing client ID. Disconnecting.")
                    conn.close()
                    continue

                print(f"[INFO] Player {client_id} connected.")
                # with lock:
                #     connection_waiting_queue.put((client_id, conn, rfile, wfile))
                client_thread = threading.Thread(target=handle_client, args=(client_id, conn, rfile, wfile, False), daemon=True)
                client_thread.start()
                

                # total_connections += 1 
                # if num_active_players < 2:
                #     # client_id += 1
                #     send(conn.makefile('w'), "Connected to server. Waiting for opponent...")
                #     print(f"[INFO] A player connected from {addr}.")

                #     with lock:
                #         if 0 in current_players:
                #             current_players[1] = (client_id, conn, rfile, wfile)
                #         else:
                #             current_players[0] = (client_id, conn, rfile, wfile)
                    
                    
                #     client_thread = threading.Thread(target=handle_client, args=(client_id, conn, rfile, wfile, False), daemon=True)
                #     client_thread.start()
                # else: # If two players are already connected
                #     with lock:
                #         connection_waiting_queue.put((client_id, conn, rfile, wfile))
                #     client_thread = threading.Thread(target=handle_client, args=(client_id, conn, rfile, wfile, True), daemon=True)
                #     client_thread.start()
                    
        except KeyboardInterrupt:
            print("\n[INFO] Server manually stopped. Shutting down.")
        except Exception as e:
            print(f"[ERROR] Unexpected server error: {e}")



if __name__ == "__main__":
    main()