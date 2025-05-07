from enum import IntEnum
import struct
import random
import defs
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

USECS_PER_SEC = 1000000
ROUTE_UPDATE_INTERVAL = 30 * USECS_PER_SEC

class Frame:
  def __init__(self, packet: bytes):
    self.packet = packet

  def pack(self):
    result = struct.pack('!{}s'.format(len(self.packet)), self.packet)
    return result

  @classmethod
  def unpack(cls, data: bytes):
    packetlen = len(data)
    packet, = struct.unpack_from('!{}s'.format(packetlen), data)
    return Frame(packet)

class RoutingTable:
  def __init__(self):
    self.routes = {} # address -> (link, hops)
  
  def pack(self):
    """pack to send to a neighbour, note that the neighbour doesn't care about
    which of our links we use, so we only pack the destination and distance.
    """

    packed = bytearray()

    # start with our own address
    packed.extend(struct.pack('!L', nodeinfo.nodenumber))

    # add all of the routes that we know about (only)
    for dest, path in self.routes.items():
      _, hops = path
      packed.extend(struct.pack('!LH', dest, hops))
    
    return bytes(packed)
  
  @classmethod
  def unpack(cls, packed: bytes):
    """unpack route information received from a neighbour."""

    source, = struct.unpack_from('!L', packed, 0)
    routes = {}

    for offset in range(struct.calcsize('!L'), len(packed), struct.calcsize('!LH')):
      dest, hops = struct.unpack_from('!LH', packed, offset)
      routes[dest] = hops
    
    return source, routes
  
  def update_from_neighbour(self, link, neighbour, routes):
    for dest, hops in routes.items():
      if dest == nodeinfo.nodenumber:
        continue # we already know how to deliver messages to ourselves

      # TODO: update our own table if the new link is shorter

      pass
    
    # TODO: also record the path to the neighbour themselves!



# The Node class, which must be provided to make the simulator happy. Each node
# (i.e. computer) in the network topology is represented by an instance of Node.
#
class Node:
  def __init__(self):
    self.routes = RoutingTable()
    self.route_update_timer = None


  def send_routing_table(self):
    # TODO: send to all of our direct neighbours

    # start timer for the next route update
    self.route_update_timer = start_timer(Event.TIMER1, ROUTE_UPDATE_INTERVAL)


  def up_to_network(self, linkno: int, packetbytes: bytes):
    """called from the data link layer to accept a packet for this node"""

    # we only deal with routing table packets, so interpret this one as such
    # source, routes = RoutingTable.unpack(packetbytes)

    # print out our updated routing table
    pass


  def down_to_datalink(self, linkno: int, packetbytes: bytes):
    frame = Frame(packetbytes)
    framebytes = frame.pack()
    write_physical_reliable(linkno, framebytes)


  def up_to_datalink(self, linkno: int, framebytes: bytes):
    frame = Frame.unpack(framebytes)
    self.up_to_network(linkno, frame.packet)


  def reboot_node(self, args):
    set_handler(Event.PHYSICALREADY, self.up_to_datalink)
    set_handler(Event.TIMER1, self.send_routing_table)
    self.route_update_timer = start_timer(Event.TIMER1, ROUTE_UPDATE_INTERVAL)
