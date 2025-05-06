"""
client.py

Connects to a Battleship server which runs the single-player game.
Simply pipes user input to the server, and prints all server responses.
"""
import os
import socket
import threading
import re
import time

HOST = '127.0.0.1'
PORT = 5050

running = True
can_fire = False

def receive_messages(rfile):
    global running, can_fire
    """Continuously receive and display messages from the server"""
    while running:
        line = rfile.readline()
        if not line:
            print("[INFO] Server disconnected.")
            os._exit(0) # exit the program immediately
            break

        # Process and display the message
        line = line.strip() # remove whitespaces

        if line == "GRID":
            # Begin reading board lines
            print("\n[Board]")
            while True:
                board_line = rfile.readline()
                if not board_line or board_line.strip() == "":
                    break
                print(board_line.strip())
        elif line == "__YOUR TURN__":
            can_fire = True
        elif line == "__GAME OVER__":
                print("[INFO] Game ended.\n")
                running = False
                os._exit(0) # exit the program immediately
        # elif line == "__CLIENT REJECTED__":
        #     print("[INFO] The game is full at the moment. Please try again later.")
        #     running = False
        #     os._exit(0)
        elif line == "__SPECTATOR__":
            print("You are now in spectator mode. You will see updates but cannot play.")
        else:
            # Normal message
            print(line)

def is_valid_coordinate(coord):
    """Check if input like 'A1', 'B10' is valid (A-J, 1-10)"""
    return re.fullmatch(r"[A-Ja-j](10|[1-9])", coord.strip()) is not None


def main():
    global running, can_fire
    # Set up connection

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.connect((HOST, PORT))
        except ConnectionRefusedError:
            print(f"[ERROR] Could not connect to the server.")
            return
        
        rfile = s.makefile('r')
        wfile = s.makefile('w')

        # Start a thread for receiving messages
        receiver_thread = threading.Thread(target=receive_messages, args=(rfile,), daemon=True)
        receiver_thread.start()

        # Main thread handles sending user input
        try:
            while running:
                user_input = input(">> ")
                if not user_input:
                    continue

                # Convert to uppercase for consistency
                user_input = user_input.strip().upper()

                # Check for quit command
                if user_input == "QUIT":
                    wfile.write("QUIT\n") # write into a buffer
                    wfile.flush() # send the buffered data to the server immediately
                    print('You quit the game.')
                    running = False
                # Check for valid coordinates
                elif is_valid_coordinate(user_input):
                    if can_fire:
                        wfile.write(f"FIRE {user_input}\n")
                        wfile.flush()
                        can_fire = False # Reset the turn
                    else: 
                        print("It's not your turn to fire yet.")
                else: # For invalid input
                    if can_fire:
                        print('Invalid input. Enter a coordinate (e.g. B5) or type "quit" to exit.')
                    else:
                        print("It's not your turn to fire yet.")
        except KeyboardInterrupt:
            wfile.write("QUIT\n") # write into a buffer
            wfile.flush() # send the buffered data to the server 
            print("\n[INFO] Client exiting due to keyboard interruption.")
            print("[INFO] Game ended.\n")
            os._exit(0) # exit the program immediately 
        except Exception as e:
            wfile.write("QUIT\n") # write into a buffer
            wfile.flush() # send the buffered data to the server 
            print(f"[ERROR] An error occurred: {e}")
            print("[INFO] Game ended.\n")
            # Handle other exceptions
            os._exit(0)
        finally: # Always run this block even if another kind of error occurs (eg. broken pipe, socket error)
            print("[INFO] Game ended.\n")
            running = False
            os._exit(0) # exit the program immediately  
            # wfile.close() # close the write file
            # rfile.close()
            # s.close()

if __name__ == "__main__":
    main()