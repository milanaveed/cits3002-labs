"""
battleship.py

Implements the core game logic and data structures for Battleship, including networking,
turn management, spectator support, reconnections, and game state coordination.

Key components:
- Board class: Manages ship placement, tracking hits/misses, and win condition.
- PlayerSession class: Handles individual player state, messaging, turn logic, and cleanup.
- Game lifecycle management: Includes timers for reconnection, turn, and game timeouts.
- Spectator support: Allows extra clients to observe the game.
- Utility functions: Coordinate parsing, board display, and a local single-player test harness.
"""
import threading
import random
import time
import select
import socket
from packet import *
import logging


# BOARD_SIZE = 10
# SHIPS = [
#     ("Carrier", 5), # 航空母舰
#     ("Battleship", 4), #战列舰
#     ("Cruiser", 3), #巡洋舰
#     ("Submarine", 3), #潜艇
#     ("Destroyer", 2) #驱逐舰
# ]

# Testing
BOARD_SIZE = 3
SHIPS = [
    ("Submarine", 3), #潜艇
]

lock = threading.Lock() # Lock for thread safety
num_player_ready = 0 # Number of players ready to start the game
current_turn = 0 # 0 for player 1, 1 for player 2
left_player_id = -1 # ID of the player who left
connection_waiting_queue = [] # Act as waiting lobby
current_players = {} # Dictionary to store player ID and connection
active_connections = set() # Set to store active connections
shared_boards = {} # Dictionary to store boards of players
player_ids = {}  # Dictionary to store player IDs
next_players_id = [] # List of next players to play
reconnection_timer = None # Timer for reconnection
game_status = None # Game status
RECONNECT_TIMEOUT = 60 # Timeout for reconnection
GAME_TIMEOUT = 120 # Timeout for game
TURN_TIMEOUT = 30 # Timeout for each turn
game_timer = None   # Timer for game

# Game status constants
GAME_OVER = "OVER" # Game over status
ONE_PLAYER_LEFT = "ONE PLAYER LEFT" # One player left status
FORFEITED = "FORFEITED" # Game forfeited status
TIMEOUT = "TIMEOUT" # Game timeout status
TWO_PLAYERS_PLAYING = "TWO PLAYERS PLAYING" # Two players playing status


game_ready_cond = threading.Condition() # Condition variable for game ready

notify_forfeited_r, notify_forfeited_w = socket.socketpair() # Socket pair for notifying forfeited game
notify_forfeited_r.setblocking(False)
notify_forfeited_w.setblocking(False)

notify_game_timeout_r, notify_game_timeout_w = socket.socketpair() # Socket pair for notifying game timeout
notify_game_timeout_r.setblocking(False)
notify_game_timeout_w.setblocking(False)

# Configure logging
logging.basicConfig(
    filename='errors.txt',
    filemode='a',  # append mode
    level=logging.INFO,  # only log info and above
    format='%(asctime)s [%(levelname)s] %(message)s',
)

def send(conn, msg, ptype=1):
    """Send a message to the player (client side) using custom packet protocol."""
    try:
        packet = make_packet(0, ptype, msg) 
        conn.sendall(packet)  # Use custom packet protocol
    except Exception as e:
        print(f"[ERROR] Failed to send packet to opponent: {e}")

def remove_connection_from_queue(player_id):
    """Remove a specific connection from the connection waiting queue."""
    global connection_waiting_queue
    connection_waiting_queue = [conn for conn in connection_waiting_queue if conn[0] != player_id] # remove the connection with player_id

def get_player_number(player_id):
    """Get the current player's number."""
    global current_players
    for key, value in current_players.items():
        if value[0] == player_id:
            return key

def send_board(conn, board):
    """Send the board state to the player using custom packet protocol."""
    try:
        # Send board header
        conn.sendall(make_packet(0, TYPE_DATA, "GRID"))
        conn.sendall(make_packet(0, TYPE_DATA, "  " + " ".join(str(i + 1).rjust(2) for i in range(board.size))))

        # Send each board row
        for r in range(board.size):
            row_label = chr(ord('A') + r) # get the row label (A, B, C, ...)
            row_str = " ".join(board.display_grid[r][c] for c in range(board.size)) # get the row string
            conn.sendall(make_packet(0, TYPE_DATA, f"{row_label:2} {row_str}")) # send the row string

        # Send end-of-board marker (empty line or a special token)
        conn.sendall(make_packet(0, TYPE_DATA, ""))  
    except Exception as e:
        print(f"[ERROR] Failed to send board: {e}")

def broadcast_to_spectators(msg):
    """Send a message to all spectators."""
    global connection_waiting_queue
    try:
        for connection in connection_waiting_queue:
            send(connection[1], msg) 
    except Exception as e:
        print(f"[ERROR] Error broadcasting to spectators: {e}")

def broadcast_board_to_spectators(board, msg):
    """Send the current board state to all spectators."""
    global connection_waiting_queue
    try:
        with lock:
            for connection in connection_waiting_queue:
                conn = connection[1]
                send(conn, msg)
                send_board(conn, board)
    except Exception as e:  
        print(f"[ERROR] Error broadcasting board to spectators: {e}")

def start_reconnection_timer():
    """Start the reconnection timer."""
    global reconnection_timer
    try:
        reconnection_timer = threading.Timer(RECONNECT_TIMEOUT, reconnection_timeout_handler) # create a timer
        reconnection_timer.start() # start the timer
        print("[TIMER] Reconnection timer started.")
    except Exception as e:
        print(f"[ERROR] Error starting reconnection timer: {e}")

def reconnection_timeout_handler():
    """Handle reconnection timeout."""
    global game_status
    try:
        with lock:
            if game_status == ONE_PLAYER_LEFT:
                print(f"[INFO] Player {left_player_id} did not reconnect in time. Game forfeited.")
                game_status = FORFEITED
                notify_forfeited_w.send(b'FORFEITED') # notify the game is forfeited
    except Exception as e:
        print(f"[ERROR] Error in reconnection timeout handler: {e}")

def cancel_reconnection_timer():
    """Cancel the reconnection timer if it exists."""
    global reconnection_timer
    if reconnection_timer and reconnection_timer.is_alive(): # check if the timer is alive
        reconnection_timer.cancel()
        print("[TIMER] Reconnection timer cancelled.")

def start_game_timer():
    """Start the game timer. Let the game run for a certain time."""
    global game_timer
    try:
        with lock:
            game_timer = threading.Timer(GAME_TIMEOUT, game_timeout_handler) # create a timer
            game_timer.start()
            print("[TIMER] Game timer started.")
    except Exception as e:
        print(f"[ERROR] Error starting game timer: {e}")

def game_timeout_handler():
    """Handle game timeout."""
    global game_status
    try:
        with lock:
            game_status = TIMEOUT
            notify_game_timeout_w.send(b'TIMEOUT') # notify the game is timed out
            print("[INFO] Game timed out. Notifying players.")
    except Exception as e:
        print(f"[ERROR] Error in game timeout handler: {e}")

def cancel_game_timer():
    """Cancel the game timer when the game ends."""
    global game_timer
    try:
        if game_timer and game_timer.is_alive(): # check if the timer is alive
            game_timer.cancel()
            print("[TIMER] Game timer cancelled.")
    except Exception as e:
        print(f"[ERROR] Error cancelling game timer: {e}")

def countdown(seconds):
    """Countdown timer for reconnection."""
    for i in range(seconds, 0, -1):
        print(f'{i} seconds remaining...')
        time.sleep(1)

def is_next_player(player_id):
    """Check if the current player is the next player in line."""
    global next_players_id
    try:
        if player_id in next_players_id:
            next_players_id.remove(player_id) # remove from the next players list
            remove_connection_from_queue(player_id) # remove from the waiting queue
            return True
        else:
            return False
    except Exception as e:
        print(f"[ERROR] Error checking next player: {e}")
        return False

def update_next_players():
    """Update the list of next pair of players."""
    global next_players_id, connection_waiting_queue
    try: 
        if not connection_waiting_queue:
            next_players_id = []
        elif len(connection_waiting_queue) < 2: # only one player in the queue
            next_players_id = [connection_waiting_queue[0][0]] 
        else: # more than 2 players in the queue
            next_players_id = [connection_waiting_queue[0][0], connection_waiting_queue[1][0]]
    except Exception as e:
        print(f"[ERROR] Error updating next players: {e}")

###############################Start of PlayerSession Class############################

class PlayerSession:
    def __init__(self, player_id, conn):
        self.id = player_id
        self.conn = conn
        self.spectator_mode = False
        self.restored = False
        self.player_number = None
        self.opponent_number = None
        self.opponent_id = None
        self.opponent_r = None
        self.opponent_w = None
        self.board = None
        self.opponent_board = None
        self.seq = 0
        self.opponent_conn = None

    def run(self):
        """Main loop for the player session."""
        self._initialise_connection()

        if self.spectator_mode: # if the player is a spectator
            is_leaving = self._handle_spectator()
            if is_leaving:
                return

        self._setup_player() # setup the player board
        self._wait_for_game_start() # wait for the game to start
        self._identify_opponent() # identify the opponent information
        self._notify_game_start() # notify the players about the game start
        self._game_loop() # main game loop
        self._cleanup() # cleanup the player session

    def send_message(self, msg, ptype=TYPE_DATA):
        """Send a message to the player using custom packet protocol."""
        try:
            packet = make_packet(self.seq, ptype, msg) # Use custom packet protocol
            self.conn.sendall(packet)
            self.seq += 1
        except Exception as e:
            print(f"[ERROR] Error sending packet: {e}")

    def recv_packet(self):
        """Receive a packet from the player using custom packet protocol."""
        try:
            data = recv_full_packet(self.conn) # Use custom packet protocol
            if not data:
                return None
            parsed = parse_packet(data)
            return parsed  # (seq, ptype, payload) or None
        except Exception as e:
            print(f"[ERROR] Failed to receive or parse packet: {e}")
            return None

    def recv_opponent_packet(self):
        """Receive a packet from the opponent using custom packet protocol."""
        try:
            if not self.opponent_conn or  self.opponent_conn.fileno() == -1: # check if the opponent connection is valid
                print("Opponent connection is closed.")
                return None
            data = recv_full_packet(self.opponent_conn) # Use custom packet protocol
            if not data:
                return None
            parsed = parse_packet(data)
            return parsed  # or None if checksum fails
        except Exception as e:
            print(f"[ERROR] Failed to read from opponent: {e}")
            return None

    def send_opponent_message(self, msg, ptype=TYPE_DATA):
        """Send a message to the opponent using custom packet protocol."""
        try:
            if self.opponent_conn and self.opponent_conn.fileno() != -1: # check if the opponent connection is valid
                packet = make_packet(self.seq, ptype, msg)
                self.opponent_conn.sendall(packet)  # Use opponent_conn for other player
                self.seq += 1
            else:
                print("Opponent connection not available.")
        except Exception as e:
            print(f"[ERROR] Failed to send packet for msg: {msg} to opponent: {e}")

    def broadcast_to_all(self,msg):
        """Broadcast a chat message to all active connections."""
        global active_connections
        try:
            with lock:
                for conn in active_connections: # loop through all active connections
                    send(conn, msg, TYPE_CHAT) # send the message to all connections
        except Exception as e:
            print(f"[ERROR] Error broadcasting chat message: {e}")

    def _update_opponent_conn(self):
        """Update the connection of the opponent."""
        global left_player_id, current_players
        with lock:
            if left_player_id != -1:
                if self.opponent_number in current_players: # check if the opponent is in current players
                    self.opponent_conn = current_players[self.opponent_number][1] # get the opponent connection
                else:
                    print(f"[ERROR] Opponent ID {self.opponent_number} not found in current players.")

    def _initialise_connection(self):
        """
        Check if the player is a new player or a reconnection. Check if the player is an active player or a spectator.
        """
        global current_players, connection_waiting_queue, left_player_id, game_status, active_connections
        with lock:
            active_connections.add(self.conn) # add the connection to active connections
            if len(current_players) < 2: # if there are less than 2 players
                self.player_number = 1 if 0 in current_players else 0 # get the player number
                current_players[self.player_number] = (self.id, self.conn) # add the player to current players
            elif self.id == left_player_id and game_status == ONE_PLAYER_LEFT: # if the player is a reconnection
                self.player_number = get_player_number(self.id) # get the player number
                current_players[self.player_number] = (self.id, self.conn) # add the player to current players
                game_status = TWO_PLAYERS_PLAYING # update the game status
                self.restored = True # set restored to True
                cancel_reconnection_timer() # cancel the reconnection timer
            else:
                connection_waiting_queue.append([self.id, self.conn]) # add the player to the waiting queue
                update_next_players() # update the next players
                self.spectator_mode = True # set spectator mode to True
                print(f"[INFO] Player ID {self.id} is in spectator mode.")

    def _handle_spectator(self):
        """Handle the spectator mode."""
        self.send_message("Connected to server. Currently in the waiting lobby...")
        self.send_message("__SPECTATOR ON__") # send signal to the client side
        while self.spectator_mode: # loop until the spectator mode is off
            recv = self.recv_packet()   # receive packet from the client
            if recv:
                _, ptype, message = recv
                message = message.strip()
                if message == "__QUIT__":   # if the message is a quit message
                    print(f"[INFO] Spectator with ID {self.id} disconnected.")
                    with lock:
                        remove_connection_from_queue(self.id)
                    self.conn.close()
                    return 1
                elif message.startswith("[CHAT]"): # if the message is a chat message
                    self.broadcast_to_all(message)
                elif message == "GAMEOVER": # if the message is a game over message
                    with lock:
                        if is_next_player(self.id):
                            self.spectator_mode = False # set spectator mode to False
                            self.player_number = 1 if 0 in current_players else 0 # get the player number
                            current_players[self.player_number] = (self.id, self.conn) # add the player to current players
                            msg = f"Player ID{self.id} will be in the next game. Game starting in 2s." if self.player_number == 1 else f"Player ID{self.id} will be in the next game. Waiting for one more player."
                            broadcast_to_spectators(msg) # send player info and game starting time to spectators
                            self.send_message("__SPECTATOR OFF__") # send signal to the client side
        return 0

    def _setup_player(self):
        """Setup the player board or restore the board, and then notify the player."""
        global shared_boards
        self.send_message(f"Welcome back Player ID {self.id}!" if self.restored else f"Welcome Player ID {self.id}!")
        if self.player_number not in shared_boards: # if the player number is not in shared boards, create a new board
            self.board = Board()
            self.board.place_ships_randomly()
            shared_boards[self.player_number] = self.board # add the board to shared boards
            self.send_message("Your board is ready.")
            if self.player_number == 0: # if there is only one player, wait for another player to join
                self.send_message("Waiting for another player to join...")
            print(f"[GAME] Player ID {self.id}'s board is ready.")
        else:
            self.board = shared_boards[self.player_number] # if the player number is in shared boards, restore the board

    def _wait_for_game_start(self):
        """Wait for two players to be ready before starting the game."""
        global num_player_ready, game_status
        if not self.restored:
            with game_ready_cond: # use condition variable to wait for two players
                num_player_ready += 1
                if num_player_ready == 2: # if there are two players ready
                    game_status = TWO_PLAYERS_PLAYING 
                    game_ready_cond.notify_all() # notify all players
                else:
                    print("[INFO] Waiting for 1 more player to start the game...")
                    game_ready_cond.wait() # wait for the other player to be ready
        else:
            num_player_ready = 2

    def _identify_opponent(self):
        """Get the opponent's read/write files, ID and board."""
        global current_players, shared_boards
        self.opponent_number = 1 - self.player_number # get the opponent number
        while True:
            with lock:
                if self.opponent_number in current_players: 
                    self.opponent_id, self.opponent_conn, = current_players[self.opponent_number][0], current_players[self.opponent_number][1] # get the opponent ID and connection
                    self.opponent_board = shared_boards[self.opponent_number] # get the opponent board
                    break

    def _notify_game_start(self):
        """Notify the players and spectators about the game start."""
        if self.restored:
            print('[GAME] Restored game with opponent.')
            self.send_message(f"Restored game with Player ID {self.opponent_id}.")
            self.send_opponent_message(f"Restored game with Player ID {self.id}.")
            broadcast_to_spectators(f"Player ID {self.id} restored game with Player ID {self.opponent_id}.")
        else:
            self.send_message(f"Game started with opponent ID {self.opponent_id}.")
            if self.player_number == 0: # just to control the below only execute once for the pair of players
                start_game_timer() # start the game timer
                broadcast_to_spectators(f"Game started! Player ID {self.id} vs Player ID {self.opponent_id}.")
                print(f"[GAME] Game started! Player ID {self.id} vs Player ID {self.opponent_id}.")

    def _game_loop(self):
        """Main game loop for the player."""
        global game_status, current_turn, left_player_id
        while True:
            with lock:
                if game_status in [FORFEITED, GAME_OVER, TIMEOUT]:  # check if the game is over
                    break
                if game_status == ONE_PLAYER_LEFT and self.id == left_player_id: # if the player is the one who left
                    break

            if current_turn == self.player_number: # if it's the player's turn
                try:
                    if self._play_turn() == 1:
                        return
                except Exception as e:
                    print(f"[ERROR] Game error: {e}")
                    break

    def _notify_player_turn(self):
        """Notify the players about current turn."""
        global current_turn, game_status, left_player_id

        try:
            print(f"[GAME] Player ID {self.id}'s turn.")
            self.send_message(f"\nPlayer ID {self.id}, it's your turn.")
            self._update_opponent_conn() # update the opponent connection in case the opponent reconnected

            with lock:
                if game_status not in [ONE_PLAYER_LEFT, FORFEITED]: 
                    self.send_opponent_message(f"\nPlayer ID {self.opponent_id}, it's your opponent's turn.")

            send_board(self.conn, self.opponent_board) # send the opponent board to the current player
            self.send_message("__YOUR TURN__")
            self.send_message("Enter coordinate to fire at (e.g. B5):")
        except Exception as e:
            print(f"[ERROR] Error notifying player turn: {e}")
        
    def quit_game(self):
        """Handle player quitting the game."""
        global game_status, left_player_id, current_turn
        try:
            with lock:
                if game_status == TWO_PLAYERS_PLAYING: # if there are two players playing
                    self.send_opponent_message("The other player left.")
                    start_reconnection_timer()  # start the reconnection timer
                    left_player_id = self.id # set the left player ID
                    game_status = ONE_PLAYER_LEFT
                    current_turn = 1 - current_turn # switch the turn to the opponent
                elif game_status == ONE_PLAYER_LEFT: # if there is one player left
                    game_status = GAME_OVER
                    broadcast_to_spectators(f'Both players left. Game ended.\n') 
                    print('[GAME] Both players left.')
        except Exception as e:
            print(f"[ERROR] Error quitting game: {e}")

    def _play_turn(self):
        """Handle the player's turn."""
        global current_turn, game_status, left_player_id

        self._notify_player_turn() # notify the player about the turn
        self._update_opponent_conn() # update the opponent connection
        start_time = time.time() # start the timer
        while time.time() - start_time < TURN_TIMEOUT: # check if the time is up for the turn
            try:
                turn_time_left = TURN_TIMEOUT - (time.time() - start_time) # calculate the time left
                sockets = [self.conn, notify_forfeited_r, notify_game_timeout_r] # add the sockets to the list for listening
                        
                if self.opponent_conn and self.opponent_conn.fileno() != -1: # check if the opponent connection is valid
                    logging.info(f"[DEBUG1] opponent_conn exists: {self.opponent_conn}")
                    sockets.append(self.opponent_conn)

                ready, _, _, = select.select(sockets, [], [], turn_time_left) # check if there is any data to read
                if not ready:
                    continue
            except Exception as e:
                print(f"[ERROR] Error in select: {e}")
                break

            for sock in ready:
                if sock == self.conn: # if the message comes from the current player
                    self._update_opponent_conn() # update the opponent connection
                    recv = self.recv_packet()
                    if not recv:
                        return 0
                    _, _, message = recv
                    message = message.strip()
                    if message.startswith("[CHAT]"): # if the message is a chat message
                        self.broadcast_to_all(message)
                        continue
                    elif message == "__QUIT__": # if the message is a quit message
                        self.quit_game()
                        return 1
                    elif message.startswith("FIRE"): # if the message is a fire command
                        if self._process_fire(message.split(' ')[1]) == 1:
                            return 1
                        return 0
                elif self.opponent_conn.fileno()!=-1 and sock == self.opponent_conn: # if the message comes from the opponent
                    opponent_recv = self.recv_opponent_packet()
                    if opponent_recv:
                        _, _, opponent_msg = opponent_recv
                        opponent_msg = opponent_msg.strip()
                        if opponent_msg == '__QUIT__': # if the opponent quits
                            self.send_message("The other player has disconnected.")
                            broadcast_to_spectators(f"Player ID {self.opponent_id} disconnected.")
                            with lock:
                                game_status = ONE_PLAYER_LEFT # update game status
                                left_player_id = self.opponent_id # set the left player ID
                                start_reconnection_timer() # start the reconnection timer
                            opponent_msg = None # reset opponent_msg to None
                            self.opponent_conn.close() # close the opponent connection
                            continue
                        elif opponent_msg.startswith("[CHAT]"): # if the message is a chat message
                            self.broadcast_to_all(opponent_msg)
                            opponent_msg = None # reset opponent_msg to None
                            continue
                elif sock == notify_forfeited_r: # if there is any message coming from the forfeited socket
                    notify_forfeited_r.recv(1024) 
                    with lock:
                        if game_status == FORFEITED:
                            return 1
                elif sock == notify_game_timeout_r: # if there is any message coming from the game timeout socket
                    try:
                        notify_game_timeout_r.recv(1024)
                        return 1
                    except Exception as e:
                        print(f"[ERROR] Error receiving game timeout notification: {e}")
                        return 1
                
        # Timeout handling
        self._update_opponent_conn() # update the opponent connection info
        with lock:
            self.send_message("Timeout! You took too long.")
            if game_status == TWO_PLAYERS_PLAYING:
                self.send_opponent_message("The other player timed out.")
                current_turn = 1 - current_turn # switch the turn to the opponent
                return 0
            elif game_status == ONE_PLAYER_LEFT:
                self.send_message("\nTimeout! It's your opponent's turn.")
                time.sleep(5) # simulate opponent's turn
                return 0

    def _process_fire(self, coord):
        """Process the fire command from the player."""
        global shared_boards, current_turn, game_status

        row, col = parse_coordinate(coord) # parse the coordinate
        result, sunk_ship = self.opponent_board.fire_at(row, col) # fire at the opponent's board
        shared_boards[self.opponent_number] = self.opponent_board # update the shared board
        broadcast_board_to_spectators(self.opponent_board, f"\nPlayer ID {self.id} fired Player ID {self.opponent_id} at {coord}.")

        if result == 'hit': # if the result is a hit
            if sunk_ship: # if a ship is sunk
                msg = f"HIT! You sank the {sunk_ship}!"
                broadcast_to_spectators(f"Result: HIT! Player ID {self.id} sank the {sunk_ship}.\n")
                if self.opponent_board.all_ships_sunk(): # if all ships are sunk
                    self.send_message("\nCongratulations! You sank all opponent's ships.")
                    send_board(self.conn, self.opponent_board) # send the board to the player
                    self.send_message("__GAME OVER__") # send game over signal
                    self.send_opponent_message("\nYou lose. All your ships have been sunk.")
                    self.send_opponent_message("__GAME OVER__") # send game over signal
                    broadcast_to_spectators(f"Player ID {self.id} sank all Player ID {self.opponent_id}'s ships. Game ended.\n")
                    with lock:
                        game_status = GAME_OVER # update game status
                    return 1
            else:
                msg = "HIT!"
        elif result == 'miss':
            msg = "MISS!"
        elif result == 'already_shot':
            msg = "Already fired at that location."
        else:
            msg = "Unknown result."

        self.send_message(msg)
        broadcast_to_spectators(f"Result: {msg}\n")

        with lock:
            if game_status == TWO_PLAYERS_PLAYING: 
                current_turn = 1 - current_turn # switch the turn to the opponent
            else:
                self.send_message("\nIt's your opponent's turn.")
                time.sleep(5)

    def _cleanup(self):
        """Cleanup the player session."""
        global current_players, shared_boards, num_player_ready, left_player_id, game_status, active_connections

        try:
            with lock:
                active_connections.remove(self.conn) # remove the connection from active connections
                # If not a spectator
                if self.player_number in current_players:
                    num_player_ready -= 1 # decrement the number of players ready
                    if game_status == FORFEITED: # if the game is forfeited
                        self.send_message("__FORFEITED__") # send forfeited signal
                        broadcast_to_spectators(f"Player ID {self.opponent_id} forfeited the game. Player ID {self.id} win!")
                        game_status = GAME_OVER 
                    if game_status == TIMEOUT: # if the game is timed out
                        self.send_message("Game timeout. Fair play.")
                        self.send_opponent_message("Game timeout. Fair play.")
                        self.send_message("__GAME OVER__") # send game over signal
                        self.send_opponent_message("__GAME OVER__") # send game over signal
                        broadcast_to_spectators(f"Game timeout. Fair play: Player ID {self.id} vs Player ID {self.opponent_id}.\n")
                        game_status = GAME_OVER
                    if game_status == GAME_OVER:
                        cancel_game_timer() # cancel the game timer
                        cancel_reconnection_timer() # cancel the reconnection timer
                        current_players.clear() # clear the current players
                        shared_boards.clear() # clear the shared boards
                        left_player_id = -1 # reset the left player ID
                        num_player_ready = 0 # reset the number of players ready
                        update_next_players() # update the next players
                        broadcast_to_spectators("__GAME OVER SPECTATOR__") # send game over signal to spectators
                        print('[GAME] Game over.\n')
                        if next_players_id: # if there are next players
                            print('Starting new game with next players...')
        except Exception as e:
            print(f"[ERROR] Error while closing connection: {e}")
        finally:
            self.conn.close() # close the connection

################################End of PlayerSession Class#############################



##########################3##Start of Board Class Provided#############################
    
class Board:
    """
    Represents a single Battleship board with hidden ships.
    We store:
      - self.hidden_grid: tracks real positions of ships ('S'), hits ('X'), misses ('o')
      - self.display_grid: the version we show to the player ('.' for unknown, 'X' for hits, 'o' for misses)
      - self.placed_ships: a list of dicts, each dict with:
          {
             'name': <ship_name>,
             'positions': set of (r, c),
          }
        used to determine when a specific ship has been fully sunk.

    In a full 2-player networked game:
      - Each player has their own Board instance.
      - When a player fires at their opponent, the server calls
        opponent_board.fire_at(...) and sends back the result.
    """

    def __init__(self, size=BOARD_SIZE):
        self.size = size
        # '.' for empty water
        # Grid to store real ship positions ('S'), hits ('X'), and misses ('o')
        self.hidden_grid = [['.' for _ in range(size)] for _ in range(size)]
        # display_grid is what the player or an observer sees (no 'S') (no ships shown)
        self.display_grid = [['.' for _ in range(size)] for _ in range(size)]
        # List of placed ships with their name and positions
        self.placed_ships = []  # e.g. [{'name': 'Destroyer', 'positions': {(r, c), ...}}, ...]

    def place_ships_randomly(self, ships=SHIPS):
        """
        Randomly place each ship in 'ships' on the hidden_grid, storing positions for each ship.
        In a networked version, you might parse explicit placements from a player's commands
        (e.g. "PLACE A1 H BATTLESHIP") or prompt the user for board coordinates and placement orientations; 
        the self.place_ships_manually() can be used as a guide.
        """
        for ship_name, ship_size in ships:
            placed = False
            while not placed:
                orientation = random.randint(0, 1)  # 0 => horizontal, 1 => vertical
                row = random.randint(0, self.size - 1)
                col = random.randint(0, self.size - 1)

                # Try to place ship only if the space is available
                if self.can_place_ship(row, col, ship_size, orientation):
                    occupied_positions = self.do_place_ship(row, col, ship_size, orientation)
                    self.placed_ships.append({
                        'name': ship_name,
                        'positions': occupied_positions
                    })
                    placed = True


    def place_ships_manually(self, ships=SHIPS):
        """
        Prompt the user for each ship's starting coordinate and orientation (H or V).
        Validates the placement; if invalid, re-prompts.
        """
        print("\nPlease place your ships manually on the board.")
        for ship_name, ship_size in ships:
            while True:
                self.print_display_grid(show_hidden_board=True)
                print(f"\nPlacing your {ship_name} (size {ship_size}).")
                coord_str = input("  Enter starting coordinate (e.g. A1): ").strip()
                orientation_str = input("  Orientation? Enter 'H' (horizontal) or 'V' (vertical): ").strip().upper()

                try:
                    row, col = parse_coordinate(coord_str)
                except ValueError as e:
                    print(f"  [!] Invalid coordinate: {e}")
                    continue

                # Convert orientation_str to 0 (horizontal) or 1 (vertical)
                if orientation_str == 'H':
                    orientation = 0
                elif orientation_str == 'V':
                    orientation = 1
                else:
                    print("  [!] Invalid orientation. Please enter 'H' or 'V'.")
                    continue

                # Check if we can place the ship
                if self.can_place_ship(row, col, ship_size, orientation):
                    occupied_positions = self.do_place_ship(row, col, ship_size, orientation)
                    self.placed_ships.append({
                        'name': ship_name,
                        'positions': occupied_positions
                    })
                    break
                else:
                    print(f"  [!] Cannot place {ship_name} at {coord_str} (orientation={orientation_str}). Try again.")


    def can_place_ship(self, row, col, ship_size, orientation):
        """
        Check if we can place a ship of length 'ship_size' at (row, col)
        with the given orientation (0 => horizontal, 1 => vertical).
        Returns True if the space is free, False otherwise.
        """
        if orientation == 0:  # Horizontal
            if col + ship_size > self.size:
                return False
            for c in range(col, col + ship_size):
                if self.hidden_grid[row][c] != '.':
                    return False
        else:  # Vertical
            if row + ship_size > self.size:
                return False
            for r in range(row, row + ship_size):
                if self.hidden_grid[r][col] != '.':
                    return False
        return True

    def do_place_ship(self, row, col, ship_size, orientation):
        """
        Place the ship on hidden_grid by marking 'S', and return the set of occupied positions.
        """
        occupied = set()
        if orientation == 0:  # Horizontal
            for c in range(col, col + ship_size):
                self.hidden_grid[row][c] = 'S'
                occupied.add((row, c))
        else:  # Vertical
            for r in range(row, row + ship_size):
                self.hidden_grid[r][col] = 'S'
                occupied.add((r, col))
        return occupied

    def fire_at(self, row, col):
        """
        Fire at (row, col). Return a tuple (result, sunk_ship_name).
        Possible outcomes:
          - ('hit', None)          if it's a hit but not sunk
          - ('hit', <ship_name>)   if that shot causes the entire ship to sink
          - ('miss', None)         if no ship was there
          - ('already_shot', None) if that cell was already revealed as 'X' or 'o'

        The server can use this result to inform the firing player.
        """
        cell = self.hidden_grid[row][col]
        if cell == 'S':
            # Mark a hit
            self.hidden_grid[row][col] = 'X'
            self.display_grid[row][col] = 'X'
            # Check if that hit sank a ship
            sunk_ship_name = self._mark_hit_and_check_sunk(row, col)
            if sunk_ship_name:
                return ('hit', sunk_ship_name)  # A ship has just been sunk
            else:
                return ('hit', None)
        elif cell == '.':
            # Mark a miss
            self.hidden_grid[row][col] = 'o'
            self.display_grid[row][col] = 'o'
            return ('miss', None)
        elif cell == 'X' or cell == 'o':
            return ('already_shot', None)
        else:
            # In principle, this branch shouldn't happen if 'S', '.', 'X', 'o' are all possibilities
            print(f"  [!] Error: unexpected cell value '{cell}' at ({row}, {col})")
            return ('already_shot', None)

    def _mark_hit_and_check_sunk(self, row, col):
        """
        Remove (row, col) from the relevant ship's positions.
        If that ship's positions become empty, return the ship name (it's sunk).
        Otherwise return None.
        """
        for ship in self.placed_ships: 
            if (row, col) in ship['positions']:
                ship['positions'].remove((row, col))
                if len(ship['positions']) == 0:
                    return ship['name']
                break
        return None

    def all_ships_sunk(self):
        """
        Check if all ships are sunk (i.e. every ship's positions are empty).
        """
        for ship in self.placed_ships:
            if len(ship['positions']) > 0:
                return False
        return True

    def print_display_grid(self, show_hidden_board=False):
        """
        Print the board as a 2D grid.
        
        If show_hidden_board is False (default), it prints the 'attacker' or 'observer' view:
        - '.' for unknown cells,
        - 'X' for known hits,
        - 'o' for known misses.
        
        If show_hidden_board is True, it prints the entire hidden grid:
        - 'S' for ships,
        - 'X' for hits,
        - 'o' for misses,
        - '.' for empty water.
        """
        # Decide which grid to print
        grid_to_print = self.hidden_grid if show_hidden_board else self.display_grid

        # Column headers (1 .. N)
        print("  " + "".join(str(i + 1).rjust(2) for i in range(self.size)))
        # Each row labeled with A, B, C, ...
        for r in range(self.size):
            row_label = chr(ord('A') + r)
            row_str = " ".join(grid_to_print[r][c] for c in range(self.size))
            print(f"{row_label:2} {row_str}")


###################################End of Board Class###################################

def parse_coordinate(coord_str):
    """
    Convert something like 'B5' into zero-based (row, col).
    Example: 'A1' => (0, 0), 'C10' => (2, 9)
    HINT: you might want to add additional input validation here...
    """
    coord_str = coord_str.strip().upper()
    row_letter = coord_str[0]
    col_digits = coord_str[1:]

    row = ord(row_letter) - ord('A')
    col = int(col_digits) - 1  # zero-based

    return (row, col)


def run_single_player_game_locally():
    """
    A test harness for local single-player mode, demonstrating two approaches:
     1) place_ships_manually()
     2) place_ships_randomly()

    Then the player tries to sink them by firing coordinates.
    """
    board = Board(BOARD_SIZE)

    # Ask user how they'd like to place ships
    choice = input("Place ships manually (M) or randomly (R)? [M/R]: ").strip().upper()
    if choice == 'M':
        board.place_ships_manually(SHIPS)
    else:
        board.place_ships_randomly(SHIPS)

    print("\nNow try to sink all the ships!")
    moves = 0
    while True:
        board.print_display_grid()
        guess = input("\nEnter coordinate to fire at (or 'quit'): ").strip()
        if guess.lower() == 'quit':
            print("Thanks for playing. Exiting...")
            return

        try:
            row, col = parse_coordinate(guess)
            result, sunk_name = board.fire_at(row, col)
            moves += 1

            if result == 'hit':
                if sunk_name:
                    print(f"  >> HIT! You sank the {sunk_name}!")
                else:
                    print("  >> HIT!")
                if board.all_ships_sunk():
                    board.print_display_grid()
                    print(f"\nCongratulations! You sank all ships in {moves} moves.")
                    break
            elif result == 'miss':
                print("  >> MISS!")
            elif result == 'already_shot':
                print("  >> You've already fired at that location. Try again.")

        except ValueError as e:
            print("  >> Invalid input:", e)


if __name__ == "__main__":
    # Optional: run this file as a script to test single-player mode
    run_single_player_game_locally()
