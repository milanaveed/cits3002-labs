"""
client.py

Connects to a Battleship server which runs the single-player game.
Simply pipes user input to the server, and prints all server responses.
"""

import socket
import threading

HOST = '127.0.0.1'
PORT = 5050


def receive_messages(rfile):
    """Continuously receive and display messages from the server"""
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
        else:
            # Normal message
            print(line)

def main():
    global running
    # Set up connection

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((HOST, PORT))
        rfile = s.makefile('r')
        wfile = s.makefile('w')

        # Start a thread for receiving messages
        running = True
        receiver_thread = threading.Thread(target=receive_messages, args=(rfile,), daemon=True)
        receiver_thread.start()

        # Main thread handles sending user input
        try:
            while True:
                user_input = input(">> ")
                if not user_input:
                    continue
                wfile.write(user_input + '\n') # write into a buffer
                wfile.flush() # send the buffered data to the server immediately
        except KeyboardInterrupt:
            print("\n[INFO] Client exiting.") 
        finally: # Always run this block even if another kind of error occurs (eg. broken pipe, socket error)
            running = False
            wfile.close() # close the write file


if __name__ == "__main__":
    main()