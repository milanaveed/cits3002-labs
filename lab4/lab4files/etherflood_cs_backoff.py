from enum import IntEnum
import struct
import random

from defs import Event


# The following variables and functions will all be injected by the simulator.
#
# Importantly, nodeinfo and linkinfo always reflect information about the
# currently executing node.

nodeinfo = None
linkinfo = []

def current_time_usec():
  return 0

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

def write_physical_reliable(linknum, framebytes):
  return True # iff write successful (link existed)

def write_application(message):
  return True # iff message accepted

def carrier_sense(linknum):
  return False # true if link is busy (our card still writing, or shared medium has signal)


# Everything below here is our protocol-specific code.
#

class EthernetFrameType(IntEnum):
  DATA = 0

class EthernetFrame:
  MAXDATA = 1500 # bytes
  HEADER_LEN = struct.calcsize('! 6s 6s h')

  def __init__(self):
    self.dest = bytes([0] * 6)
    self.src  = bytes([0] * 6)
    self.type = EthernetFrameType.DATA
    self.payload = bytes([0] * EthernetFrame.MAXDATA)

  def pack(self, payloadlen):
    return struct.pack('! 6s 6s h {}s'.format(payloadlen),
      self.dest, self.src, self.type, self.payload)

  def unpack(self, bytes):
    payloadlen = len(bytes) - EthernetFrame.HEADER_LEN
    self.dest, self.src, self.type, self.payload = struct.unpack_from(
      '! 6s 6s h {}s'.format(payloadlen), bytes)
    return payloadlen


DEFAULT_FREQ = 100000 # 100ms
BACKOFF_SLOT = 52 # microseconds

# The Node class, which must be provided to make the simulator happy. Each node
# (i.e. computer) in the network topology is represented by an instance of Node.
#
class Node:
  def __init__(self):
    self.freq = DEFAULT_FREQ # average number of usec between transmissions

    self.frame = None

    # are we currently backing-off from a collision (of one of our frames)
    self.backing_off = False

    # how many consecutive collisions have we observed?
    self.collisions = 0

    # time until we sense the medium and attempt to send again
    self.send_on_clear_timer = None

    # time until we consider our send successful
    self.finished_sending_timer = None


  def send_frame(self):
    frame = self.frame
    link = 1

    if carrier_sense(link):
      print('carrier busy @ {}'.format(current_time_usec()))
      self.schedule_send_on_clear() #? should we implement this?
      return

    print('sending frame @ {}'.format(current_time_usec()))

    framebytes = frame.pack(len(frame.payload))

    if write_physical(link, framebytes):
      # how long do we expect the write to take (based on link bandwidth)
      write_time = len(framebytes) * 8 * 1000000 // linkinfo[link].bandwidth

      if self.finished_sending_timer:
        stop_timer(self.finished_sending_timer)
      
      self.finished_sending_timer = start_timer(Event.TIMER2, write_time)


  def generate_message(self):
    # generate a new random "message" and try to send it immediately
    print('generating message @ {}'.format(current_time_usec()))
    self.frame = EthernetFrame()

    payloadlen = random.randrange(EthernetFrame.MAXDATA)
    self.frame.payload = bytes([97] * payloadlen)

    self.send_frame()
  

  def finished_sending(self):
    # our frame was sent, and no collisions received! we can reset our collision
    # counter, etc. and prepare for a new frame.
    self.finished_sending_timer = None
    self.frame = None
    self.backing_off = False
    self.collisions = 0

    if self.send_on_clear_timer:
      stop_timer(self.send_on_clear_timer)
      self.send_on_clear_timer = None

    # schedule next "message" generation
    start_timer(Event.TIMER1, random.randrange(self.freq) + 1)
  

  def send_on_clear(self):
    self.backing_off = False
    self.send_frame()


  def schedule_send_on_clear(self, time=BACKOFF_SLOT):
    # if we were already waiting to send-on-clear, cancel the existing timer
    # (we're not waiting to finish receiving a new frame or collision)
    if self.send_on_clear_timer:
      stop_timer(self.send_on_clear_timer)
    
    self.send_on_clear_timer = start_timer(Event.TIMER3, time) # this Event.TIMER3 timer calls send_on_clear() (specified in the set_handler() in reboot_node()) when it expires, which calls send_frame()


  def collision(self):
    if self.frame and self.finished_sending_timer:
      # we were sending a frame, but detected a collision... time to back off
      stop_timer(self.finished_sending_timer)
      self.finished_sending_timer = None

      # todo: replace this with binary exponential backoff based on number of consecutive collisions of this frame.
      # give up on this frame completely! schedule generation of a new frame
    #   self.frame = None
    #   start_timer(Event.TIMER1, random.randrange(self.freq) + 1) # schedule to generate a new message
      # exponential backoff
      self.collisions += 1
      max_slots = min(1024, 2 ** self.collisions) -1
      backoff_slots = random.randint(0, max_slots)
      backoff_time = backoff_slots * BACKOFF_SLOT

      print(f'collision @ {current_time_usec()}, backing off {backoff_slots} slots ({backoff_time} us)')

      self.backing_off = True
      self.schedule_send_on_clear(backoff_time)


    elif self.frame and not self.backing_off:
      # there must be an inter-frame gap, so just *schedule* sending the frame
      # (schedule might be pushed back if we receive more)
      self.schedule_send_on_clear()


  def physical_ready(self, linkno: int, framebytes: bytes):
    # frame = EthernetFrame()
    # payloadlen = frame.unpack(framebytes)

    if self.frame and not self.finished_sending_timer and not self.backing_off:
      # there must be an inter-frame gap, so just *schedule* sending the frame
      # (schedule might be pushed back if we receive more)
      self.schedule_send_on_clear()


  def reboot_node(self, args):
    if len(args):
      self.freq = int(args[0])
      if self.freq < 0:
        raise RuntimeError("bad freq: {}".format(self.freq))
    
    set_handler(Event.PHYSICALREADY, self.physical_ready)
    set_handler(Event.FRAMECOLLISION, self.collision)
    set_handler(Event.TIMER1, self.generate_message)
    set_handler(Event.TIMER2, self.finished_sending)
    set_handler(Event.TIMER3, self.send_on_clear) # this timer triggers send_on_clear() when it expires

    # schedule first "message"
    start_timer(Event.TIMER1, 1000000 + random.randrange(self.freq))
