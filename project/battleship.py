"""
battleship.py

Contains core data structures and logic for Battleship, including:
 - Board class for storing ship positions, hits, misses
 - Utility function parse_coordinate for translating e.g. 'B5' -> (row, col)
 - A test harness run_single_player_game() to demonstrate the logic in a local, single-player mode

"""
import threading
import random
import time
import select
import socket

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
    # ("Carrier", 5), # 航空母舰
    # ("Battleship", 4), #战列舰
    # ("Cruiser", 3), #巡洋舰
    ("Submarine", 3), #潜艇
    # ("Destroyer", 2) #驱逐舰
]

total_connections = 0
connection_waiting_queue = []
current_players = {}
lock = threading.Lock()
num_player_ready = 0
shared_boards = {}
current_turn = 0 # 0 for player 1, 1 for player 2
player_ids = {}  # player_id -> player_num
game_status = None
RECONNECT_TIMEOUT = 60
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

def remove_connection(player_id):
    """Remove a specific connection from the connection waiting queue."""
    global connection_waiting_queue
    connection_waiting_queue = [conn for conn in connection_waiting_queue if conn[0] != player_id]

def get_player_number(player_id):
    """Get the current player's number."""
    global current_players
    for key, value in current_players.items():
        if value[0] == player_id:
            return key
        
def send_board(wfile, board):
    """Send the board state to the player."""
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
    try:
        for connection in connection_waiting_queue:
            send(connection[3], msg)  # connection[3] is the writer
    except Exception as e:
        print(f"[ERROR] Error broadcasting to spectators: {e}")

def broadcast_board_to_spectators(board, msg):
    """Send the current board state to all spectators."""
    global connection_waiting_queue
    try:
        with lock:
            for connection in connection_waiting_queue:
                writer = connection[3]
                send(writer, msg)
                send_board(writer, board)
    except Exception as e:  
        print(f"[ERROR] Error broadcasting board to spectators: {e}")

def start_reconnection_timer():
    """Start the reconnection timer."""
    global timer
    try:
        timer = threading.Timer(RECONNECT_TIMEOUT, reconnection_timeout_handler)
        timer.start()
        print("[TIMER] Reconnection timer started.")
    except Exception as e:
        print(f"[ERROR] Error starting reconnection timer: {e}")

def reconnection_timeout_handler():
    """Handle reconnection timeout."""
    global game_status
    try:
        with lock:
            if game_status == "ONE PLAYER LEFT":
                print(f"[INFO] Player {left_player_id} did not reconnect in time. Game forfeited.")
                game_status = "FORFEITED"
                notify_forfeited_w.send(b'FORFEITED')
    except Exception as e:
        print(f"[ERROR] Error in reconnection timeout handler: {e}")

def cancel_reconnection_timer():
    """Cancel the reconnection timer if it exists."""
    global timer
    if timer and timer.is_alive():
        timer.cancel()
        print("[TIMER] Reconnection timer cancelled.")

def countdown(seconds):
    """Countdown timer for reconnection."""
    for i in range(seconds, 0, -1):
        print(f'{i} seconds remaining...')
        time.sleep(1)

def is_next_player(player_id):
    """Check if the current player is the next player in line."""
    global next_players_id
    if player_id in next_players_id:
        next_players_id.remove(player_id)
        remove_connection(player_id) # remove from the waiting queue
        return True
    else:
        return False

def update_next_players():
    """Update the list of next pair of players."""
    global next_players_id, connection_waiting_queue
    if not connection_waiting_queue:
        next_players_id = []
    elif len(connection_waiting_queue) < 2:
        next_players_id = [connection_waiting_queue[0][0]]
    else:
        next_players_id = [connection_waiting_queue[0][0], connection_waiting_queue[1][0]]


###############################Start of PlayerSession Class############################

class PlayerSession:
    def __init__(self, player_id, conn, rfile, wfile):
        self.id = player_id
        self.conn = conn
        self.rfile = rfile
        self.wfile = wfile
        self.spectator_mode = False
        self.restored = False
        self.player_number = None
        self.opponent_number = None
        self.opponent_id = None
        self.opponent_r = None
        self.opponent_w = None
        self.board = None
        self.opponent_board = None

    def run(self):
        """Main loop for the player session."""
        self._initialise_connection()

        if self.spectator_mode:
            is_leaving = self._handle_spectator()
            if is_leaving:
                return

        self._setup_player()
        self._wait_for_game_start()
        self._identify_opponent()
        self._notify_game_start()
        self._game_loop()
        self._cleanup()

    def send_message(self, msg):
        """Send a message to the current client."""
        send(self.wfile, msg)

    def send_opponent_message(self, msg):
        """Send a message to the opponent."""
        try:
            if not self.opponent_w.closed:
                send(self.opponent_w, msg)
            else:
                print(f"Opponent socket is closed. Cannot send message: {msg}")
        except Exception as e:
            print(f"[ERROR] {e}.\nCould not send to opponent {self.opponent_w}: {msg}")

    def _update_opponent_rwfiles(self):
        """Update the read/write files of the opponent."""
        global left_player_id, current_players
        with lock:
            if left_player_id != -1:
                if self.opponent_number in current_players:
                    self.opponent_r, self.opponent_w = current_players[self.opponent_number][2], current_players[self.opponent_number][3]
                else:
                    print(f"[ERROR] Opponent ID {self.opponent_number} not found in current players.")

    def _initialise_connection(self):
        """
        Check if the player is a new player or a reconnection. Check if the player is an active player or a spectator.
        """
        global current_players, connection_waiting_queue, left_player_id, game_status
        with lock:
            if len(current_players) < 2:
                self.player_number = 1 if 0 in current_players else 0
                current_players[self.player_number] = (self.id, self.conn, self.rfile, self.wfile)
            elif self.id == left_player_id and game_status == "ONE PLAYER LEFT":
                self.player_number = get_player_number(self.id)
                current_players[self.player_number] = (self.id, self.conn, self.rfile, self.wfile)
                game_status = "TWO PLAYERS PLAYING"
                self.restored = True
                cancel_reconnection_timer()
            else:
                connection_waiting_queue.append([self.id, self.conn, self.rfile, self.wfile])
                update_next_players()
                self.spectator_mode = True
                print(f"[INFO] Player ID {self.id} is in spectator mode.")

    def _handle_spectator(self):
        """Handle the spectator mode."""
        self.send_message("Connected to server. Currently in the waiting lobby...")
        self.send_message("__SPECTATOR ON__")
        while self.spectator_mode:
            message = self.rfile.readline().strip()
            if message == "QUIT":
                print(f"[INFO] Spectator with ID {self.id} disconnected.")
                with lock:
                    remove_connection(self.id)
                self.conn.close()
                return 1
            elif message == "GAMEOVER":
                with lock:
                    if is_next_player(self.id):
                        self.spectator_mode = False
                        self.player_number = 1 if 0 in current_players else 0
                        current_players[self.player_number] = (self.id, self.conn, self.rfile, self.wfile)
                        msg = f"Player ID{self.id} will be in the next game. Game starting in 2s." if self.player_number == 1 else f"Player ID{self.id} will be in the next game. Waiting for one more player."
                        broadcast_to_spectators(msg)
                        self.send_message("__SPECTATOR OFF__")
        return 0

    def _setup_player(self):
        """Setup the player board or restore the board, and then notify the player."""
        global shared_boards

        self.send_message(f"Welcome back Player ID {self.id}!" if self.restored else f"Welcome Player ID {self.id}!")

        if self.player_number not in shared_boards:
            self.board = Board()
            self.board.place_ships_randomly()
            shared_boards[self.player_number] = self.board
            self.send_message("Your board is ready.")
            if self.player_number == 0:
                self.send_message("Waiting for another player to join...")
            print(f"[GAME] Player ID {self.id}'s board is ready.")
        else:
            self.board = shared_boards[self.player_number]

    def _wait_for_game_start(self):
        """Wait for two players to be ready before starting the game."""
        global num_player_ready, game_status

        if not self.restored:
            with game_ready_cond:
                num_player_ready += 1
                if num_player_ready == 2:
                    game_status = "TWO PLAYERS PLAYING"
                    game_ready_cond.notify_all()
                else:
                    print("[INFO] Waiting for 1 more player to start the game...")
                    game_ready_cond.wait()
        else:
            num_player_ready = 2

    def _identify_opponent(self):
        """Get the opponent's read/write files, ID and board."""
        global current_players, shared_boards
        self.opponent_number = 1 - self.player_number
        while True:
            with lock:
                if self.opponent_number in current_players:
                    self.opponent_r, self.opponent_w, self.opponent_id = current_players[self.opponent_number][2], current_players[self.opponent_number][3], current_players[self.opponent_number][0]
                    self.opponent_board = shared_boards[self.opponent_number]
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
            if self.player_number == 0:
                broadcast_to_spectators(f"Game started! Player ID {self.id} vs Player ID {self.opponent_id}.")
                print(f"[GAME] Game started! Player ID {self.id} vs Player ID {self.opponent_id}.")

    def _game_loop(self):
        """Main game loop for the player."""
        global game_status, current_turn, left_player_id

        while True:
            with lock:
                if game_status in ["FORFEITED", "OVER"]:
                    break
                if game_status == "ONE PLAYER LEFT" and self.id == left_player_id:
                    break

            if current_turn == self.player_number:
                try:
                    if self._play_turn() == 1:
                        break
                except Exception as e:
                    print(f"[ERROR] Game error: {e}")
                    break

    def _notify_player_turn(self):
        """Notify the players about current turn."""
        global current_turn, game_status, left_player_id

        print(f"[GAME] Player ID {self.id}'s turn.")
        self.send_message(f"\nPlayer ID {self.id}, it's your turn.")
        self._update_opponent_rwfiles()

        with lock:
            if game_status not in ["ONE PLAYER LEFT", "FORFEITED"]:
                self.send_opponent_message(f"\nPlayer ID {self.opponent_id}, it's your opponent's turn.")

        send_board(self.wfile, self.opponent_board)
        self.send_message("__YOUR TURN__")
        self.send_message("Enter coordinate to fire at (e.g. B5):")

    def _play_turn(self):
        """Handle the player's turn."""
        global current_turn, game_status, left_player_id

        self._notify_player_turn()

        if game_status == "TWO PLAYERS PLAYING":
            self._update_opponent_rwfiles()
            ready, _, _ = select.select([self.rfile, self.opponent_r], [], [], 30)
            if not ready:
                self.send_message("Timeout! You took too long.")
                self.send_opponent_message("The other player timed out.")
                with lock:
                    current_turn = 1 - current_turn
                return 0
        else:
            ready, _, _ = select.select([self.rfile, notify_forfeited_r], [], [], 30)
            if not ready:
                self.send_message("Timeout! You took too long.")
                with lock:
                    self.send_message("It's your opponent's turn.")
                    time.sleep(5)
                return 0 # if continue the game loop

        if self.opponent_r in ready:
            opponent_msg = self.opponent_r.readline()
            if opponent_msg:
                opponent_msg = opponent_msg.strip()
            if opponent_msg == 'QUIT':
                self.send_message("The other player has disconnected.")
                broadcast_to_spectators(f"Player ID {self.opponent_id} disconnected.")
                with lock:
                    game_status = "ONE PLAYER LEFT"
                    left_player_id = self.opponent_id
                start_reconnection_timer()
                opponent_msg = None

        if notify_forfeited_r in ready:  # todo: improve
            notify_forfeited_r.recv(1024)
            with lock:
                if game_status == "FORFEITED":
                    return 1
                
        self._update_opponent_rwfiles()

        guess = self.rfile.readline()
        if not guess:
            self.send_message("Connection lost.")
            self.send_opponent_message("The other player has disconnected.")
            with lock:
                left_player_id = self.id
                game_status = "ONE PLAYER LEFT"
            start_reconnection_timer()
            with lock:
                current_turn = 1 - current_turn
            return 1

        guess = guess.strip()
        if guess == 'QUIT':
            with lock:
                if game_status != "ONE PLAYER LEFT":
                    self.send_opponent_message("The other player left.")
                    start_reconnection_timer()
                    left_player_id = self.id
                    game_status = "ONE PLAYER LEFT"
                    current_turn = 1 - current_turn
                elif game_status == "ONE PLAYER LEFT":
                    game_status = "OVER"
                    broadcast_to_spectators(f'Both players left. Game ended.\n')
                    print('[GAME] Both players left.')
            return 1

        if 'FIRE' in guess:
            if self._process_fire(guess.split(' ')[1]) == 1:
                return 1
        
        return 0

    def _process_fire(self, coord):
        """Process the fire command from the player."""
        global shared_boards, current_turn, game_status

        row, col = parse_coordinate(coord)
        result, sunk_ship = self.opponent_board.fire_at(row, col)
        shared_boards[self.opponent_number] = self.opponent_board
        broadcast_board_to_spectators(self.opponent_board, f"\nPlayer ID {self.id} fired Player ID {self.opponent_id} at {coord}.")

        if result == 'hit':
            if sunk_ship:
                msg = f"HIT! You sank the {sunk_ship}!"
                broadcast_to_spectators(f"Result: HIT! Player ID {self.id} sank the {sunk_ship}.\n")
                if self.opponent_board.all_ships_sunk():
                    self.send_message("\nCongratulations! You sank all opponent's ships.")
                    send_board(self.wfile, self.opponent_board)
                    self.send_message("__GAME OVER__")
                    self.send_opponent_message("\nYou lose. All your ships have been sunk.")
                    self.send_opponent_message("__GAME OVER__")
                    broadcast_to_spectators(f"Player ID {self.id} sank all Player ID {self.opponent_id}'s ships. Game ended.\n")
                    with lock:
                        game_status = "OVER"
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
            if game_status != "ONE PLAYER LEFT":
                current_turn = 1 - current_turn

    def _cleanup(self):
        """Cleanup the player session."""
        global current_players, shared_boards, num_player_ready, left_player_id, game_status

        try:
            with lock:
                if self.player_number in current_players:
                    num_player_ready -= 1
                    if game_status == "FORFEITED":
                        self.send_message("__FORFEITED__")
                        broadcast_to_spectators(f"Player ID {self.opponent_id} forfeited the game. Player ID {self.id} win!")
                        game_status = "OVER"
                    if game_status == "OVER":
                        cancel_reconnection_timer()
                        current_players.clear()
                        shared_boards.clear()
                        left_player_id = -1
                        num_player_ready = 0
                        update_next_players()
                        broadcast_to_spectators("__GAME OVER SPECTATOR__")
                        print('[GAME] Game over.')
        except Exception as e:
            print(f"[ERROR] Error while closing connection: {e}")
        finally:
            self.rfile.close()
            self.wfile.close()
            self.conn.close()

################################End of PlayerSession Class############################



##################################Start of Board Class################################
    
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
