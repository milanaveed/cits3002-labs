"""
client.py

Connects to a Battleship server which runs the single-player game.
Simply pipes user input to the server, and prints all server responses.

TODO: Fix the message synchronization issue using concurrency (Tier 1, item 1).
"""

import socket
import threading

HOST = '127.0.0.1'
PORT = 5050

# HINT: The current problem is that the client is reading from the socket,
# then waiting for user input, then reading again. This causes server
# messages to appear out of order.
#
# Consider using Python's threading module to separate the concerns:
# - One thread continuously reads from the socket and displays messages
# - The main thread handles user input and sends it to the server

# def main():
#     with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
#         s.connect((HOST, PORT))
#         rfile = s.makefile('r')
#         wfile = s.makefile('w')

#         try:
#             while True:
#                 # PROBLEM: This design forces the client to alternate between
#                 # reading a message and sending input, which doesn't work when
#                 # the server sends multiple messages in sequence
                
#                 line = rfile.readline()
#                 if not line:
#                     print("[INFO] Server disconnected.")
#                     break

#                 line = line.strip()

#                 if line == "GRID":
#                     # Begin reading board lines
#                     print("\n[Board]")
#                     while True:
#                         board_line = rfile.readline()
#                         if not board_line or board_line.strip() == "":
#                             break
#                         print(board_line.strip())
#                 else:
#                     # Normal message
#                     print(line)

#                 user_input = input(">> ")
#                 wfile.write(user_input + '\n')
#                 wfile.flush()

#         except KeyboardInterrupt:
#             print("\n[INFO] Client exiting.")

# HINT: A better approach would be something like:

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