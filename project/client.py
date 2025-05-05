"""
client.py

Connects to a Battleship server which runs the single-player game.
Simply pipes user input to the server, and prints all server responses.
"""
import os
import socket
import threading
import re

HOST = '127.0.0.1'
PORT = 5050

running = True

def receive_messages(rfile):
    """Continuously receive and display messages from the server"""
    global running
    while running:
        line = rfile.readline()
        if not line:
            print("[INFO] Server disconnected.")
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
        elif line == "__GAME OVER__":
                print("\n[INFO] Game ended. Exiting client.\n")
                running = False
                os._exit(0) # exit the program immediately
                break
        else:
            # Normal message
            print(line)

def is_valid_coordinate(coord):
    """Check if input like 'A1', 'B10' is valid (A-J, 1-10)"""
    return re.fullmatch(r"[A-Ja-j](10|[1-9])", coord.strip()) is not None


def main():
    global running
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
                    print('[INFO] You quit the game.')
                    break
                # Check for valid coordinates
                elif is_valid_coordinate(user_input):
                    wfile.write(f"FIRE {user_input}\n")
                    wfile.flush()
                else: # For invalid input
                    print('Invalid input. Enter a coordinate (e.g. B5) or type "quit" to exit.')
        except KeyboardInterrupt:
            print("\n[INFO] Client exiting due to keyboard interruption.") 
        finally: # Always run this block even if another kind of error occurs (eg. broken pipe, socket error)
            #? Are these necessary?
            running = False
            wfile.close() # close the write file
            rfile.close()
            s.close()
            print("\n[INFO] Client shutdown complete.") 


if __name__ == "__main__":
    main()