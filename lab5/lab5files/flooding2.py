from enum import IntEnum
import struct
import random

import defs
from defs import Event

from nltable import NLTable


# This file implements a better flooding algorithm exhibiting slightly more
# "intelligence" than the naive algorithm in flooding1.py
# These additions, implemented using flood2(), include:
#
# 1) data packets are initially sent on all links.
# 2) packets are forwarded on all links except the one on which they arrived.
# 3) acknowledgement packets are initially sent on the link on which their
#    data packet arrived (only).
#
# This algorithm exhibits better efficiency than flooding1.py . Over the 8 nodes
# in FLOODING2, the efficiency is typically about 5%.


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

MAXHOPS = 4

class Frame:
  MAX_FRAME_SIZE = defs.MAX_MESSAGE_SIZE + 1024

  def __init__(self, packet: bytes):
    self.packet = packet

  def pack(self):
    result = struct.pack('!{}s'.format(len(self.packet)), self.packet)
    # print('pack frame with {} payload -> {}'.format(len(self.packet), len(result)))
    return result

  def unpack(self, data: bytes):
    packetlen = len(data)
    self.packet, = struct.unpack_from('!{}s'.format(packetlen), data)
    # print('unpack frame from {} -> payload {}'.format(packetlen, len(self.packet)))
    return packetlen

class PacketKind(IntEnum):
  NL_DATA = 0
  NL_ACK = 1

class Packet:
  HEADER_SIZE = struct.calcsize('!LLLBB')

  def __init__(self):
    self.src = 0 # 32 bit unsigned
    self.dest = 0 # 32 bit unsigned
    self.seqno = 0 # 32 bit unsigned
    self.kind = PacketKind.NL_DATA # 8 bit unsigned
    self.hopcount = 0 # 8 bit unsigned
    self.msg = bytes()
  
  def pack(self):
    result = struct.pack('!LLLBB{}s'.format(len(self.msg)),
      self.src, self.dest, self.seqno, self.kind, self.hopcount, self.msg)
    # print('pack packet from msg {} -> {}'.format(len(self.msg), len(result)))
    return result

  def unpack(self, data: bytes):
    msglen = len(data) - Packet.HEADER_SIZE
    # print('unpack packet from {} -> msg {}'.format(len(data), msglen))
    if msglen:
      self.src, self.dest, self.seqno, self.kind, self.hopcount, self.msg = struct.unpack_from(
        '!LLLBB{}s'.format(msglen), data)
    else:
      self.src, self.dest, self.seqno, self.kind, self.hopcount = struct.unpack_from(
        '!LLLBB', data)
      self.msg = bytes()



# The Node class, which must be provided to make the simulator happy. Each node
# (i.e. computer) in the network topology is represented by an instance of Node.
#
class Node:
  def __init__(self):
    self.nltable = NLTable()


  def flood2(self, packetbytes: bytes, links_wanted: int):
    """flood1 is a basic routing strategy which transmits the outgoing packet
    on every link specified in the bitmap named links_wanted."""
    for link in range(1, len(linkinfo)):
      if (links_wanted & (1 << link)):
        self.down_to_datalink(link, packetbytes)


  def down_to_network(self, destination: int, message: bytes):
    """receives new messages from the application layer and prepares them for
    transmission to other nodes."""

    p = Packet()

    p.src = nodeinfo.nodenumber
    p.dest = destination

    p.seqno = self.nltable.nextpackettosend(destination)
    self.nltable.inc_nextpackettosend(destination)

    p.kind = PacketKind.NL_DATA
    p.hopcount = 0
    p.msg = message

    self.flood2(p.pack(), NLTable.ALL_LINKS)


  def up_to_network(self, linkno: int, packetbytes: bytes):
    """called from the data link layer to accept a packet for this node, or to
    re-route it to the intended destination"""

    p = Packet()
    p.unpack(packetbytes)

    if p.dest == nodeinfo.nodenumber:
      # this packet is for me
      if p.kind == PacketKind.NL_DATA:
        if p.seqno == self.nltable.packetexpected(p.src):
          write_application(p.msg)
          self.nltable.inc_packetexpected(p.src)

          p.dest = p.src
          p.src = nodeinfo.nodenumber

          p.kind = PacketKind.NL_ACK
          p.hopcount = 0
          p.msg = bytes()

          # send the ACK via the link on which the DATA arrived
          self.flood2(p.pack(), 1 << linkno)
      elif p.kind == PacketKind.NL_ACK:
        if p.seqno == self.nltable.ackexpected(p.src):
          self.nltable.inc_ackexpected(p.src)
          enable_application(p.src)
    else:
      # this packet is for someone else
      p.hopcount = p.hopcount + 1
      if p.hopcount < MAXHOPS:
        # retransmit on all links *except* the one on which it arrived
        self.flood2(p.pack(), NLTable.ALL_LINKS ^ (1 << linkno))


  def down_to_datalink(self, linkno: int, packetbytes: bytes):
    frame = Frame(packetbytes)
    framebytes = frame.pack()
    write_physical_reliable(linkno, framebytes)


  def up_to_datalink(self, linkno: int, framebytes: bytes):
    frame = Frame(bytes())
    frame.unpack(framebytes)
    self.up_to_network(linkno, frame.packet)


  def reboot_node(self, args):
    if len(linkinfo) >= 32:
      print('flood2 flooding will not work here')
      exit(1)
    
    set_handler(Event.APPLICATIONREADY, self.down_to_network)
    set_handler(Event.PHYSICALREADY, self.up_to_datalink)
    enable_application()
