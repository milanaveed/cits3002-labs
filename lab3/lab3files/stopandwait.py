from enum import IntEnum
import struct

from defs import Event
import checksums

#! For sliding window

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

class FrameType(IntEnum):
  DLL_DATA = 0
  DLL_ACK = 1
  DLL_NACK = 2

class Frame:
  def __init__(self):
    self.kind = FrameType.DLL_DATA  # only ever DL_DATA or DL_ACK
    self.len = 0      # the length of the msg field only
    self.checksum = 0 # checksum of the whole frame
    self.seq = 0      # only ever 0 or 1
    self.msg = bytes()

  # packs our frame data into a sequence of bytes with a specified format, so
  # that the receiver can understand it. in our case the format is four integers
  # (of 4 bytes each) containing the frame kind, message length (N), checksum,
  # and sequence number, followed by N bytes containing the message contents.
  #   see https://docs.python.org/3/library/struct.html
  # for more details about the struct library used for packing and unpacking
  def pack(self):
    return struct.pack('!HHiH{}s'.format(len(self.msg)), self.kind, self.len, self.checksum, self.seq, self.msg)
  
  # unpack frame data from a sequence of bytes. note that we calculate the
  # maximum length of the message contents (byte string) by comparing the number
  # of bytes received vs. the size required for the frame header (non-contents
  # data)... why do we do this instead of just reading the message length from
  # the frame header?
  def unpack(self, bytes):
    maxbytelen = len(bytes) - struct.calcsize('!HHiH')
    self.kind, self.len, self.checksum, self.seq, self.msg = struct.unpack_from(
      '!HHiH{}s'.format(maxbytelen), bytes)


# The Node class, which must be provided to make the simulator happy. Each node
# (i.e. computer) in the network topology is represented by an instance of Node.
#
class Node:
  def __init__(self):
    self.lastmsg = None
    self.lasttimer = None
    self.ackexpected = 0
    self.nextframetosend = 0
    self.frameexpected = 0
    self.printspaces = '\t' * (nodeinfo.nodenumber * 4)


  # a convenience method that constructs and sends frames according to our
  # protocol's frame format.
  def transmit_frame(self, msg: bytes, kind: FrameType, seqno: int):
    f = Frame()
    f.kind = kind
    f.seq = seqno
    f.checksum = 0
    f.len = len(msg)
    f.msg = msg

    packed = f.pack()
    f.checksum = checksums.checksum_ccitt(packed)
    packed = f.pack()

    link = 1
    write_physical(link, packed)

    if kind == FrameType.DLL_ACK:
      print('{}ACK transmitted, seq={}'.format(self.printspaces, seqno))
    elif kind == FrameType.DLL_DATA:
      print('{}DATA transmitted, seq={}'.format(self.printspaces, seqno))

      timeout = (len(packed) * (8000000 // linkinfo[link].bandwidth)
        + linkinfo[link].propagationdelay)

      self.lasttimer = start_timer(Event.TIMER1, 3 * timeout, None)


  # called by the simulator when this node's application layer has a new message
  # that it wants to deliver.
  #   destination = the node number of the intended recipient
  #   message = bytes() containing the message data
  # note that there is only one other node in this topology, so the destination
  # is not important.
  def application_ready(self, destination: int, message: bytes):
    self.lastmsg = message
    disable_application()

    print('down from application, seq={}'.format(self.nextframetosend))

    self.transmit_frame(self.lastmsg, FrameType.DLL_DATA, self.nextframetosend)
    self.nextframetosend = 1 - self.nextframetosend


  # called by the simulator when data is received from one of this node's
  # network links.
  #   linkno = the number of the link that the data was received on
  #   framebytes = bytes() containing the frame data
  def physical_ready(self, linkno: int, framebytes: bytes):
    f = Frame()
    f.unpack(framebytes)

    checksum = f.checksum
    f.checksum = 0

    if (checksum != checksums.checksum_ccitt(f.pack())):
      print('{}BAD checksum - frame ignored'.format(self.printspaces))
      return
    
    if (f.kind == FrameType.DLL_ACK):
      if (f.seq == self.ackexpected):
        print('{}ACK received, seq={}'.format(self.printspaces, f.seq))
        stop_timer(self.lasttimer)
        self.ackexpected = 1 - self.ackexpected
        enable_application()
    
    elif (f.kind == FrameType.DLL_DATA):
      if (f.seq == self.frameexpected):
        write_application(f.msg)
        self.frameexpected = 1 - self.frameexpected
        result = 'up to application'
      else:
        result = 'ignored'
      
      print('DATA received, seq={}, {}'.format(
        f.seq, result))
      
      self.transmit_frame(bytes(),
        FrameType.DLL_ACK, f.seq)


  # called by the simulator when a timer expires for the TIMER1 event (which we
  # use to detect that an ACK hasn't been received in our expected timeframe)
  def timeouts(self):
    print('{}timeout, seq={}'.format(self.printspaces, self.ackexpected))
    self.transmit_frame(self.lastmsg, FrameType.DLL_DATA, self.ackexpected)


  # called by the simulator when this node 'boots up'. this is where we should
  # connect simulator events (such as APPLICATIONREADY) to our event handlers,
  # such as application_ready()
  def reboot_node(self):
    if (nodeinfo.nodenumber > 1):
      print('This is not a 2-node network!')
      exit(1)

    set_handler(Event.APPLICATIONREADY, self.application_ready)
    set_handler(Event.PHYSICALREADY, self.physical_ready)
    set_handler(Event.TIMER1, self.timeouts)

    if (nodeinfo.nodenumber == 0):
      enable_application()
