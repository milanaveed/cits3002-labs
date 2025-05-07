from enum import Enum
import struct

from defs import Event
import checksums


# This is an implementation of a stop-and-wait data link protocol.
# It is based on Tanenbaum's `protocol 4', 2nd edition, p227.
# This protocol employs only data and acknowledgement frames -
# piggybacking and negative acknowledgements are not used.
#
# It is currently written so that only one node (number 0) will
# generate and transmit messages and the other (number 1) will receive
# them. This restriction seems to best demonstrate the protocol to
# those unfamiliar with it.
# The restriction can easily be removed by "commenting out" the line
#
#   if (nodeinfo.nodenumber == 0):
#
# in reboot_node(). Both nodes will then transmit and receive (why?).
#
# Note that this file only provides a reliable data-link layer for a
# network of 2 nodes.


# The following variables and functions will all be injected by the simulator.
#
# Importantly, nodeinfo and linkinfo always reflect information about the
# currently executing node.

nodeinfo = None
linkinfo = []

def enable_application(nodenumber = None):
  pass

def disable_application(nodenumber = None):
  pass

def start_timer(event, usecs, data = None):
  return 0 # returns a timerid

def stop_timer(timerid):
  pass

def timer_data(timerid):
  pass

def set_handler(event, callback):
  pass

def write_physical(linknum, framebytes):
  return True # iff write successful (link existed)

def write_application(message):
  return True # iff message accepted


# Everything below here is our protocol-specific code.
#
# Note that we don't want to pass any data between Nodes unless it goes through
# the network simulation (i.e. through write_physical). Passing data around via
# other means (e.g. global variables) would defeat the purpose of the
# simulation (which is to construct your mental model of the protocol, not to
# construct some code that passes data around).

DL_DATA = 0
DL_ACK = 1
DL_NACK = 2

class Frame:
  def __init__(self):
    self.kind = None  # only ever DL_DATA or DL_ACK
    self.len = 0      # the length of the msg field only
    self.checksum = 0 # checksum of the whole frame
    self.seq = 0      # only ever 0 or 1
    self.msg = None

  # packs our frame data into a sequence of bytes with a specified format, so
  # that the receiver can understand it. in our case the format is four integers
  # (of 4 bytes each) containing the frame kind, message length (N), checksum,
  # and sequence number, followed by N bytes containing the message contents.
  #   see https://docs.python.org/3/library/struct.html
  # for more details about the struct library used for packing and unpacking
  def pack(self):
    return struct.pack('iiii{}s'.format(len(self.msg)), self.kind, self.len, self.checksum, self.seq, self.msg)
  
  # unpack frame data from a sequence of bytes. note that we calculate the
  # maximum length of the message contents (byte string) by comparing the number
  # of bytes received vs. the size required for the frame header (non-contents
  # data)... why do we do this instead of just reading the message length from
  # the frame header?
  def unpack(self, bytes):
    maxbytelen = len(bytes) - struct.calcsize('iiii')
    self.kind, self.len, self.checksum, self.seq, self.msg = struct.unpack_from(
      'iiii{}s'.format(maxbytelen), bytes)


# The Node class, which must be provided to make the simulator happy. Each node
# (i.e. computer) in the network topology is represented by an instance of Node.
class Node:
  def __init__(self):
    self.lastmsg = None                  # The last application message sent (for possible retransmission)
    self.lasttimer = None               # The timer ID of the last active timer
    self.ackexpected = 0                # The sequence number of the ACK we are expecting (0 or 1)
    self.nextframetosend = 0            # The next sequence number to send (flip-flops between 0 and 1)
    self.frameexpected = 0              # The sequence number of the DATA frame we're expecting from the other node
    self.printspaces = '\t' * (nodeinfo.nodenumber * 4)  # Pretty-printing indentation based on node number


  # A convenience method that constructs and sends frames according to our protocol's format.
  def transmit_frame(self, msg, kind, seqno):
    f = Frame()                         # Create a new frame object

    f.kind = kind                      # Set the frame kind (DL_DATA or DL_ACK)
    f.seq = seqno                      # Set the sequence number
    f.checksum = 0                     # Placeholder before calculating real checksum
    f.len = len(msg)                   # Length of the payload (even if it's empty for ACKs)
    f.msg = msg                        # The actual message or empty bytes for ACKs

    packed = f.pack()                  # Pack the frame with a temporary checksum (0 for now)

    f.checksum = checksums.checksum_ccitt(packed)  # Compute the real checksum

    packed = f.pack()                  # Repack the frame with the real checksum

    link = 1                           # Assume link 1 is always used in this topology
    success = write_physical(link, packed)  # Send the packed frame

    if success:
      if kind == DL_ACK:
        print('{}ACK transmitted, seq={}'.format(self.printspaces, seqno))
      elif kind == DL_NACK:
        print('{}NACK transmitted, seq={}'.format(self.printspaces, seqno))
      elif kind == DL_DATA:
        print('{}DATA transmitted, seq={}'.format(self.printspaces, seqno))

        # Estimate a suitable timeout based on frame size and link characteristics
        timeout = (len(packed) * (8000000 // linkinfo[link].bandwidth)
          + linkinfo[link].propagationdelay)

        # Start a timer to wait for an ACK
        self.lasttimer = start_timer(Event.TIMER1, 3 * timeout, None)
      else:
        raise RuntimeError('invalid frame kind {}'.format(kind))
    else:
      print('{}failed to write_physical!'.format(self.printspaces))


  # Called by the simulator when the application has data ready to send.
  def application_ready(self, destination, message):
    self.lastmsg = message             # Store the message in case we need to retransmit
    disable_application()              # Prevent further application messages until this one is ACKed

    print('{}down from application, seq={}'.format(self.printspaces, self.nextframetosend))

    self.transmit_frame(self.lastmsg, DL_DATA, self.nextframetosend)  # Send the DATA frame
    self.nextframetosend = 1 - self.nextframetosend  # Toggle between 0 and 1 for next frame


  # Called by the simulator when a frame is received from the network.
  def physical_ready(self, linkno, framebytes):
    f = Frame()
    f.unpack(framebytes)              # Unpack the incoming bytes into a frame

    checksum = f.checksum             # Store the original checksum
    f.checksum = 0                    # Zero out checksum before recomputing
    if (checksum != checksums.checksum_ccitt(f.pack())):
      # If checksums don’t match, the frame is corrupted
      print('{}BAD checksum - frame ignored'.format(self.printspaces))
      self.transmit_frame(bytes([]), DL_NACK, self.ackexpected)
      return

    if (f.kind == DL_ACK):
      if (f.seq == self.ackexpected):
        print('{}ACK received, seq={}'.format(self.printspaces, f.seq))
        stop_timer(self.lasttimer)    # Stop the timer as ACK was received
        self.ackexpected = 1 - self.ackexpected  # Toggle expected ACK
        enable_application()          # Allow the application to send the next message
    elif (f.kind == DL_NACK):
        if (f.seq == self.ackexpected) and (self.lastmsg is not None):
          # If we receive a NACK for the expected ACK, we retransmit the last message
          print('{}NACK received, seq={}'.format(self.printspaces, f.seq))
          stop_timer(self.lasttimer)      # Stop the timer as NACK was received
          self.transmit_frame(self.lastmsg, DL_DATA, self.ackexpected)  
    elif (f.kind == DL_DATA):
      if (f.seq == self.frameexpected):
        write_application(f.msg)      # Deliver the message to the application layer
        self.frameexpected = 1 - self.frameexpected  # Toggle expected frame seq
        result = 'up to application'
      else:
        result = 'ignored'            # Duplicate frame, already received
      print('{}DATA received, seq={}, {}'.format(self.printspaces, f.seq, result))
      self.transmit_frame(bytes([]), DL_ACK, f.seq)  # Send ACK regardless of duplicate
    else:
      # Unexpected frame type (shouldn’t happen in this protocol)
      print('{}UNEXPECTED FRAME KIND {}'.format(self.printspaces, f.kind))


  # Called by the simulator when the timer expires (no ACK received in time).
  def timeouts(self):
    print('{}timeout, seq={}'.format(self.printspaces, self.ackexpected))
    self.transmit_frame(self.lastmsg, DL_DATA, self.ackexpected)  # Retransmit the message


  # Called once at node startup to register event handlers.
  def reboot_node(self):
    if (nodeinfo.nodenumber > 1):
      print('This is not a 2-node network!')
      exit(1)

    set_handler(Event.APPLICATIONREADY, self.application_ready)  # App layer ready to send
    set_handler(Event.PHYSICALREADY, self.physical_ready)        # Frame received
    set_handler(Event.TIMER1, self.timeouts)                     # Timer expired

    if (nodeinfo.nodenumber == 0):
      enable_application()            # Start generating application messages for node 0