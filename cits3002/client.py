"""
client.py

Battleship client script that connects to a local server, manages game interaction,
and supports spectator mode, chat, and reconnection via client ID.

- Automatically or manually generates a 3-digit client ID (macOS auto, Windows manual).
- Sends user input (commands, coordinates, chat) to the server.
- Receives and displays messages, game state updates, and board views.
- Supports turn-based firing, game quitting, and transition between player/spectator roles.
"""
import os
import socket
import threading
import re
import time
import hashlib
import platform
from packet import *

HOST = '127.0.0.1'
PORT = 5050


running = True
can_fire = False
spectator_mode = False

def countdown(seconds):
    """Countdown timer for the given number of seconds."""
    for i in range(seconds-1, 0, -1):
        print(f'{i} seconds remaining...')
        time.sleep(1)

def get_or_create_client_id():
    """Generate a unique consistent 3-digit ID for each terminal. This is for recognising the same client when reconnecting. Only cover Windows and MacOS."""
    if platform.system() == "Darwin": # MacOS
        tty = os.ttyname(0)  # Get terminal device, e.g., /dev/ttys000
        base_name = os.path.basename(tty)  # e.g., ttys000
        id_file = f"/tmp/battleship_client_id_{base_name}"

        if not os.path.exists(id_file):
            # Generate a unique 3-digit ID identifying that terminal session and store it
            random_bytes = os.urandom(4)
            hashed = hashlib.sha256(random_bytes).hexdigest()
            short_id = int(hashed, 16) % 1000
            with open(id_file, "w") as f:
                f.write(str(short_id))
        else:
            with open(id_file, "r") as f:
                short_id = int(f.read().strip())

    elif platform.system() =="Windows":
        # Ask the user for a 3-digit ID
        short_id = None
        while not short_id:
            user_input = input("Enter your user ID (3 digits): ").strip()
            if user_input and user_input.isdigit() and len(user_input) == 3:
                short_id = int(user_input)
            else:
                print("Invalid input.")

    return short_id


client_id = get_or_create_client_id() # Generate a unique ID for the client

def send_to_server(sock, msg, ptype=TYPE_DATA):
    """Send a message to the server"""
    try:
        pkt = make_packet(0, ptype, str(msg))
        sock.sendall(pkt)
    except Exception as e:
        print(f"[ERROR] Failed to send message: {e}")


def recv_full_packet(sock) -> bytes:
    """Receive a full packet from the server"""
    try:
        # Read the 4-byte length prefix
        length_data = sock.recv(4)
        if len(length_data) < 4:
            return None
        packet_len = struct.unpack('!I', length_data)[0]

        # Now read the full packet
        packet_data = b''
        while len(packet_data) < packet_len:
            chunk = sock.recv(packet_len - len(packet_data))
            if not chunk:
                return None
            packet_data += chunk
        return packet_data
    except:
        return None


def receive_messages(sock):
    global running, can_fire, spectator_mode
    """Continuously receive and display messages from the server"""
    while running:
        try:
            data = recv_full_packet(sock)
            if not data:
                print("[INFO] Server disconnected.")
                os._exit(0) # exit the program immediately
                break
        
            parsed = parse_packet(data)
            if not parsed:
                print("[WARN] Discarded corrupted packet.")
                continue

            _, ptype, line = parsed
        except Exception as e:
            print(f"[ERROR] An error occurred while receiving data: {e}")
            break

        if ptype == TYPE_CHAT: # Chat message
            print(f"{line}")
            continue

        if line == "GRID":
            # Begin reading board lines
            print("[Board]")
            while True:
                board_line = recv_full_packet(sock)
                if not board_line:
                    break
                parsed = parse_packet(board_line)
                if not parsed:
                    print("[WARN] Discarded corrupted packet.")
                    continue
                _, _, board_line = parsed
                if not board_line or board_line.strip() == "":
                    break
                print(board_line.strip())
        elif line == "__YOUR TURN__": # Your turn to fire
            can_fire = True
        elif line == "__GAME OVER__": # Game over
            print("[INFO] Game ended.\n")
            running = False
            os._exit(0) # exit the program immediately
        elif line == "__FORFEITED__": # Other player forfeited
            print("The other player forfeited. You win!\n")
            running = False
            os._exit(0) # exit the program immediately
        elif line == "__SPECTATOR ON__": # Spectator mode
            print("You are now in spectator mode. You will see updates but cannot play.")
            spectator_mode = True
        elif line == "__GAME OVER SPECTATOR__": # Game over in spectator mode
            send_to_server(sock, "GAMEOVER")
        elif line == "__SPECTATOR OFF__": # Exit spectator mode
            spectator_mode = False
            print("You are a player now.")
        else:
            # Normal message
            print(line)


def is_valid_coordinate(coord):
    """Check if input like 'A1', 'B10' is valid (A-J, 1-10)
    returns True if valid, False otherwise
    """
    return re.fullmatch(r"[A-J](10|[1-9])", coord.strip()) is not None


def main():
    global running, can_fire
    # Set up connection
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.connect((HOST, PORT))
        except ConnectionRefusedError:
            print(f"[ERROR] Could not connect to the server.")
            return
        
        send_to_server(s, f"ID {client_id}\n") # Send ID to server

        # Start a thread for receiving messages
        receiver_thread = threading.Thread(target=receive_messages, args=(s,), daemon=True)
        receiver_thread.start()

        # Main thread handles sending user input
        try:
            while running:
                user_input = input("")
                if not user_input:
                    continue

                # Convert to uppercase for consistency
                user_input = user_input.strip()

                # Check for quit command
                if user_input == "quit":
                    send_to_server(s, "__QUIT__")
                    time.sleep(5) # Give the server time to process the quit command
                    print('You quit the game.')
                    running = False
                # Check for chat message
                elif user_input.startswith("chat"): 
                    message = user_input[4:].strip()
                    if message:        
                        send_to_server(s, f'[CHAT] Player ID {client_id}: {message}', TYPE_CHAT)
                # Check for valid coordinates
                elif spectator_mode:
                    print("You are in spectator mode. You cannot fire.")
                elif is_valid_coordinate(user_input):
                    if can_fire:
                        send_to_server(s, f"FIRE {user_input}\n")
                        can_fire = False # Reset the turn
                    else: 
                        print("It's not your turn to fire yet. Enter 'chat' to send a message. Enter 'quit' to exit.")
                else: # For invalid input
                    if can_fire:
                        print('Invalid input. Enter a coordinate (e.g. B5) or type "quit" to exit. Type "chat" to send a message.')
                    else:
                        print("It's not your turn to fire yet.")
        except KeyboardInterrupt:
            send_to_server(s, "__QUIT__") # send QUIT command to server
            print("\n[INFO] Client exiting due to keyboard interruption.")
            print("[INFO] Game ended.\n")
            os._exit(0) # exit the program immediately 
        except Exception as e:
            print(f"[ERROR] An error occurred: {e}")
            print("[INFO] Game ended.\n")
            os._exit(0)
        finally: # Always run this block even if another kind of error occurs (eg. broken pipe, socket error)
            print("[INFO] Game ended.\n")
            running = False
            s.close()
            os._exit(0) # exit the program immediately  

if __name__ == "__main__":
    main()