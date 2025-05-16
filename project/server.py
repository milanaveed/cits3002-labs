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
import time
from battleship import *

HOST = '127.0.0.1'
PORT = 5050

total_connections = 0
connection_waiting_queue = []
current_players = {}
lock = threading.Lock()
num_player_ready = 0
shared_boards = {}
current_turn = 0 # 0 for player 1, 1 for player 2
player_ids = {}  # player_id -> player_num
game_status = None
RECONNECT_TIMEOUT = 30
left_player_id = -1
next_players_id = []
timer = None

game_ready_cond = threading.Condition()

notify_forfeited_r, notify_forfeited_w = socket.socketpair()
notify_forfeited_r.setblocking(False)
notify_forfeited_w.setblocking(False)

def send(wfile, msg):
    """Helper function to send a message with newline + flush."""
    try:
        wfile.write(msg + '\n')
        wfile.flush()
    except Exception as e:
        print(f"[ERROR] {e}.\nCould not send to client {wfile}: {msg}")

# def remove_connection(player_id):
#     """Remove a specific connection from the connection waiting queue."""
#     global connection_waiting_queue
#     connection_waiting_queue = [conn for conn in connection_waiting_queue if conn[0] != player_id]

# def get_player_number(player_id):
#     """Get the current player's number."""
#     global current_players
#     for key, value in current_players.items():
#         if value[0] == player_id:
#             return key
        
# def send_board(wfile, board):
#     send(wfile, "GRID")
#     send(wfile, "  " + " ".join(str(i + 1).rjust(2) for i in range(board.size)))
#     for r in range(board.size):
#         row_label = chr(ord('A') + r)
#         row_str = " ".join(board.display_grid[r][c] for c in range(board.size))
#         send(wfile, f"{row_label:2} {row_str}")
#     send(wfile, "")  # end of board

# def broadcast_to_spectators(msg):
#     """Send a message to all spectators."""
#     global connection_waiting_queue
#     try:
#         for connection in connection_waiting_queue:
#             send(connection[3], msg)  # connection[3] is the writer
#     except Exception as e:
#         print(f"[ERROR] Error broadcasting to spectators: {e}")

# def broadcast_board_to_spectators(board, msg):
#     """Send the current board state to all spectators."""
#     global connection_waiting_queue
#     try:
#         with lock:
#             for connection in connection_waiting_queue:
#                 writer = connection[3]
#                 send(writer, msg)
#                 send_board(writer, board)
#     except Exception as e:  
#         print(f"[ERROR] Error broadcasting board to spectators: {e}")

# def start_reconnection_timer():
#     """Start the reconnection timer."""
#     global timer
#     try:
#         timer = threading.Timer(RECONNECT_TIMEOUT, reconnection_timeout_handler)
#         timer.start()
#         print("[TIMER] Reconnection timer started.")
#     except Exception as e:
#         print(f"[ERROR] Error starting reconnection timer: {e}")

# def reconnection_timeout_handler():
#     """Handle reconnection timeout."""
#     global game_status
#     try:
#         with lock:
#             if game_status == "ONE PLAYER LEFT":
#                 print(f"[INFO] Player {left_player_id} did not reconnect in time. Game forfeited.")
#                 game_status = "FORFEITED"
#                 notify_forfeited_w.send(b'FORFEITED')
#     except Exception as e:
#         print(f"[ERROR] Error in reconnection timeout handler: {e}")

# def cancel_reconnection_timer():
#     """Cancel the reconnection timer if it exists."""
#     global timer
#     if timer and timer.is_alive():
#         timer.cancel()
#         print("[TIMER] Reconnection timer cancelled.")

# def update_opponent_rwfiles(opponent_r, opponent_w, opponent_number):
#     """Update the read and write files of the opponent."""
#     global current_players
#     if opponent_number in current_players:
#         return current_players[opponent_number][2], current_players[opponent_number][3]
#         # print(f"[INFO] Updated opponent's read/write files for Player {opponent_number}.")
#     else:
#         print(f"[ERROR] Opponent ID {opponent_number} not found in current players.")

# def countdown(seconds):
#     for i in range(seconds, 0, -1):
#         print(f'{i} seconds remaining...')
#         time.sleep(1)

# def is_next_player(player_id):
#     """Check if the current player is the next player in line."""
#     global next_players_id
#     if player_id in next_players_id:
#         next_players_id.remove(player_id)
#         remove_connection(player_id) # remove from the waiting queue
#         return True
#     else:
#         return False

# def update_next_players():
#     """Update the list of next pair of players."""
#     global next_players_id, connection_waiting_queue
#     if not connection_waiting_queue:
#         next_players_id = []
#     elif len(connection_waiting_queue) < 2:
#         next_players_id = [connection_waiting_queue[0][0]]
#     else:
#         next_players_id = [connection_waiting_queue[0][0], connection_waiting_queue[1][0]]

# def get_opponent_info(opponent_player_number):
#     """Get the opponent's read/write files and ID."""
#     global current_players
#     return current_players[opponent_player_number][2], current_players[opponent_player_number][3], current_players[opponent_player_number][0]

# def send_opponent_message(opponent_w, msg):
#     """Send a message to the opponent."""
#     try:
#         if not opponent_w.closed:
#             send(opponent_w, msg)
#         else:
#             print(f"[ERROR] Opponent socket is closed. Cannot send message: {msg}")
#     except Exception as e:
#         print(f"[ERROR] {e}.\nCould not send to opponent {opponent_w}: {msg}")


# def handle_client(player_id, conn, current_r, current_w, spectator_mode):
#     global connection_waiting_queue, current_players, num_player_ready
#     global shared_boards, current_turn, game_status, left_player_id
#     restored = False

#     # print('current_players:', current_players)
#     # print('left_player_id:', left_player_id)
#     # print('game_status:', game_status)
#     with lock:
#         if len(current_players) < 2:
#             spectator_mode = False
#             if 0 in current_players:
#                 current_players[1] = (player_id, conn, current_r, current_w)
#             else:
#                 current_players[0] = (player_id, conn, current_r, current_w)
#         elif player_id == left_player_id and game_status == "ONE PLAYER LEFT":
#             # print('come on b aby')
#             spectator_mode = False
#             player_number = get_player_number(player_id)
#             current_players[player_number] = (player_id, conn, current_r, current_w)
#             game_status = "TWO PLAYERS PLAYING"
#             restored = True
#             cancel_reconnection_timer()
#         else:
#             # print('game_status:', game_status)
#             # print('num current players:', len(current_players))
#             connection_waiting_queue.append([player_id, conn, current_r, current_w])
#             update_next_players()
#             spectator_mode = True
#             print(f"[INFO] Player ID {player_id} is in spectator mode.")

#     # Spectator handling
#     if spectator_mode:
#         send(current_w, "Connected to server. Currently in the waiting lobby...")
#         send(current_w, "__SPECTATOR ON__")
#         while spectator_mode:
#             message = current_r.readline().strip()
#             if message == "QUIT":
#                 print(f"[INFO] Spectator with ID {player_id} disconnected.")
#                 with lock:
#                     remove_connection(player_id)
#                 conn.close()
#                 return
#             elif message == "GAMEOVER":
#                 with lock:
#                     if is_next_player(player_id):
#                         spectator_mode = False
#                         if 0 in current_players:
#                             current_players[1] = (player_id, conn, current_r, current_w)
#                             broadcast_to_spectators(f"Player ID{player_id} will be in the next game. Game starting in 2s.")
#                         else:
#                             current_players[0] = (player_id, conn, current_r, current_w)
#                             broadcast_to_spectators(f"Player ID{player_id} will be in the next game. Waiting for one more player.")
#                         send(current_w, "__SPECTATOR OFF__")


#     if not restored:
#         with lock:
#             player_number = get_player_number(player_id)


#     # print("f1")
#     send(current_w, f"Welcome back Player ID {player_id}!" if restored else f"Welcome Player ID {player_id}!")
#      # Create or restore board

#     if player_number not in shared_boards:
#         board = Board()
#         board.place_ships_randomly()
#         shared_boards[player_number] = board
#         send(current_w, f"Your board is ready.")
#         if player_number == 0:
#             send(current_w, "Waiting for another player to join...")
#         print(f"[GAME] Player ID {player_id}'s board is ready.") 

#     # Wait for both players to be ready
#     if not restored:
#         with game_ready_cond:
#             num_player_ready += 1
#             if num_player_ready == 2:
#                 game_status = "TWO PLAYERS PLAYING"
#                 game_ready_cond.notify_all()
#             else:
#                 print("[INFO] Waiting for 1 more player to start the game...")
#                 game_ready_cond.wait()
#     else:
#         num_player_ready = 2

#     # Identify opponent
#     opponent_player_number = 1 - player_number
#     while True:
#         with lock:
#             if opponent_player_number in current_players:
#                 opponent_r, opponent_w, opponent_id = get_opponent_info(opponent_player_number)
#                 break
    
#     opponent_board = shared_boards[opponent_player_number]

#     if restored:
#         print('[GAME] Restored game with opponent.')
#         send(current_w, f"Restored game with Player ID {opponent_id}.")
#         send_opponent_message(opponent_w, f"Restored game with Player ID {player_id}.")
#         broadcast_to_spectators(f"Player ID {player_id} restored game with Player ID {opponent_id}.")
#     else:
#         send(current_w, f"Game started with opponent ID {opponent_id}.")
#         if player_number == 0: # only broadcast once
#             broadcast_to_spectators(f"Game started! Player ID {player_id} vs Player ID {opponent_id}.")
#             print(f"[GAME] Game started! Player ID {player_id} vs Player ID {opponent_id}.")

#     # Game loop
#     while True:
#         with lock:
#             if game_status == "FORFEITED" or game_status == "OVER":
#                 break
#             elif game_status == "ONE PLAYER LEFT" and player_id == left_player_id:
#                 break
        
#         if current_turn == player_number:
#             try:
#                 print(f"[GAME] Player ID {player_id}'s turn.")
#                 send(current_w, f"\nPlayer ID {player_id}, it's your turn.")
#                 with lock:
#                     if left_player_id != -1:
#                         opponent_r, opponent_w = update_opponent_rwfiles(opponent_r, opponent_w, opponent_player_number)

#                     if game_status != "ONE PLAYER LEFT" and game_status != "FORFEITED":
#                         send_opponent_message(opponent_w, f"\nPlayer ID {opponent_id}, it's your opponent's turn.")
#                 send_board(current_w, opponent_board)
#                 send(current_w, "__YOUR TURN__")
#                 send(current_w, "Enter coordinate to fire at (e.g. B5):")

#             except Exception as e:
#                 print(f"[ERROR] Game error1: {e}")


#             try:
#                 if game_status == "TWO PLAYERS PLAYING":
#                     # print('i am here')
#                     with lock:
#                         if left_player_id != -1:
#                             opponent_r, opponent_w = update_opponent_rwfiles(opponent_r, opponent_w, opponent_player_number)
#                     ready, _, _ = select.select([current_r, opponent_r], [], [], 30)
#                     if not ready:
#                         send(current_w, "Timeout! You took too long.")
#                         send_opponent_message(opponent_w, "The other player timed out.")
#                         with lock:
#                             current_turn = 1 - current_turn
#                         continue
#                 else:
#                     ready, _, _ = select.select([current_r, notify_forfeited_r], [], [], 30)
#                     if not ready:
#                         send(current_w, "Timeout! You took too long.")
#                         with lock:
#                             send(current_w, "It's your opponent's turn.")
#                             time.sleep(5)
#                         continue
#             except Exception as e:
#                 print(f"[ERROR] Game error2: {e}")
            
#             try:
#                 # Handle disconnect
#                 if opponent_r in ready:
#                     try:
#                         # print(f'player {player_number+1} opponent_r:', opponent_r)
#                         opponent_msg = opponent_r.readline()
#                         if opponent_msg: 
#                             opponent_msg = opponent_msg.strip()
#                     except Exception as e:
#                         print(f"[ERROR6] Game error: {e}")
#                     if opponent_msg == 'QUIT':
#                         # print(f'player {player_number+1} with player ID {player_id} kkkk')
#                         send(current_w, "The other player has disconnected.")
#                         broadcast_to_spectators(f"Player ID {opponent_id} disconnected.")
#                         with lock:
#                             game_status = "ONE PLAYER LEFT"
#                             left_player_id = opponent_id
#                         start_reconnection_timer()
#                         opponent_msg = None
#             except Exception as e:
#                 print(f"[ERROR] Game error3: {e}")

#             try:
#                 if notify_forfeited_r in ready:
#                     notify_forfeited_r.recv(1024)  # Clear the buffer
#                     with lock:
#                         if game_status == "FORFEITED":
#                             break
#             except Exception as e:
#                 print(f"[ERROR] Game error7: {e}")


#             with lock:
#                 if left_player_id != -1:
#                     opponent_r, opponent_w = update_opponent_rwfiles(opponent_r, opponent_w, opponent_player_number)
            
#             try:
#                 guess = current_r.readline()
#                 if not guess:
#                     send(current_w, "Connection lost.")
#                     send_opponent_message(opponent_w, "The other player has disconnected.")
#                     with lock:
#                         left_player_id = player_id
#                         game_status = "ONE PLAYER LEFT"
#                     start_reconnection_timer()
#                     with lock:
#                         current_turn = 1 - current_turn
#                     break

#             except Exception as e:
#                 print(f"[ERROR] Game error4: {e}")

#             try:
#                 guess = guess.strip()
#                 if guess == 'QUIT':
#                     send_opponent_message(opponent_w, "The other player left.")
#                     start_reconnection_timer()
#                     with lock:
#                         left_player_id = player_id
#                         game_status = "ONE PLAYER LEFT"
#                         current_turn = 1 - current_turn 
#                     break
#             except Exception as e:
#                 print(f"[ERROR] Game error5: {e}")

#             try:
#                 if 'FIRE' in guess:
#                     guess = guess.split(' ')[1]
#                     row, col = parse_coordinate(guess)
#                     result, sunk_ship = opponent_board.fire_at(row, col)
#                     shared_boards[opponent_player_number] = opponent_board
#                     broadcast_board_to_spectators(opponent_board, f"\nPlayer ID {player_id} fired Player ID {opponent_id} at {guess}.")

#                     if result == 'hit':
#                         if sunk_ship:
#                             msg = f"HIT! You sank the {sunk_ship}!"
#                             broadcast_to_spectators(f"Result: HIT! Player ID {player_id} sank the {sunk_ship}.\n")
#                             if opponent_board.all_ships_sunk():
#                                 send(current_w, "\nCongratulations! You sank all opponent's ships.")
#                                 send_board(current_w, opponent_board)
#                                 send(current_w, "__GAME OVER__")
#                                 send_opponent_message(opponent_w, "\nYou lose. All your ships have been sunk.")
#                                 send_opponent_message(opponent_w, "__GAME OVER__")
#                                 broadcast_to_spectators(f"Player ID {player_id} sank all Player ID {opponent_id}'s ships. Game ended.\n")
#                                 with lock:
#                                     game_status = "OVER"
#                                 break
#                         else:
#                             msg = "HIT!"
#                     elif result == 'miss':
#                         msg = "MISS!"
#                     elif result == 'already_shot':
#                         msg = "Already fired at that location."
#                     else:
#                         msg = "Unknown result."

#                     send(current_w, msg)
#                     broadcast_to_spectators(f"Result: {msg}\n")

#                     with lock:
#                         if game_status != "ONE PLAYER LEFT":
#                             current_turn = 1 - current_turn
#                         # else:
#                         #     send(current_w, "It's your opponent's turn.")
#                         #     time.sleep(5)
#             except Exception as e:
#                 # send(current_w, "__GAME OVER__")
#                 print(f"[ERROR] Game error: {e}")
#                 break


#     try:
#         with lock:
#             if player_number in current_players:
#                 # print('f1')
#                 num_player_ready -= 1
#                 # print(f"Player {player_id} disconnected. Remaining players: {num_player_ready}")
#                 if game_status == "FORFEITED":
#                     send(current_w, "__FORFEITED__")  #! when calling a function, be careful if it has a lock within the function too (deadlock)
#                     broadcast_to_spectators(f"Player ID {opponent_id} forfeited the game. Player ID {player_id} win!")
#                     game_status = "OVER"
#                     # print('f2')
#                 if game_status == "OVER":
#                     cancel_reconnection_timer()
#                     current_players.clear()
#                     shared_boards.clear()
#                     left_player_id = -1
#                     num_player_ready = 0
#                     update_next_players()
#                     broadcast_to_spectators("__GAME OVER SPECTATOR__")
#                     print('[GAME] Game over.')
#                     # print('game over, len(current_players):', len(current_players))
#     except Exception as e:
#         print(f"[ERROR] Error while closing connection: {e}")

#     current_r.close()
#     current_w.close()
#     conn.close()
#     # print(f"[INFO] Game session ended for player ID {player_id}.")


def handle_client(player_id, conn, current_r, current_w, spectator_mode):
    player = PlayerSession(player_id, conn, current_r, current_w, spectator_mode)
    player.run()


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
                print(f"[INFO] Player ID {client_id} connected.")
                client_thread = threading.Thread(target=handle_client, args=(client_id, conn, rfile, wfile, False), daemon=True)
                client_thread.start() 
        except KeyboardInterrupt:
            print("\n[INFO] Server manually stopped. Shutting down.")
        except Exception as e:
            print(f"[ERROR] Unexpected server error: {e}")


if __name__ == "__main__":
    main()