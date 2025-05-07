# Simple network simulator (v0.1)
#   matt.heinsenegan@uwa.edu.au
# Released under the GNU General Public License (GPL) version 2.
#
# Significant portions of this code derived from the cnet network simulator
# (v3.4.1), Copyright (C) 1992-onwards, Chris.McDonald@uwa.edu.au
# Released under the GNU General Public License (GPL) version 2.
# Portions that have been directly translated are marked by comments.
#
import sys
import importlib
import inspect
import secrets
import heapq
import random
import math
import traceback
import csv
import argparse
import json
import re
from enum import IntEnum

from defs import Event, NodeType, LinkType, LinkInfo


parser = argparse.ArgumentParser(prog='Network Simulator')

parser.add_argument('-e', '--execution-duration', nargs='?')

parser.add_argument('--node-output', nargs='?', type=argparse.FileType('w'),
  default=sys.stdout)

parser.add_argument('--silent-nodes', action='store_true')

parser.add_argument('--stats-period', nargs='?')

parser.add_argument('--stats-csv', nargs='?')

parser.add_argument('-S', '--seed', nargs='?', type=int)

parser.add_argument('topology')

parser.add_argument('nodeargs', nargs='*')

args = parser.parse_args()


# try to parse the topology file and load the user's module

with open(args.topology, 'r') as fin:
  topology = json.load(fin)

try:
  node_module = importlib.import_module(topology['module'])
except ImportError:
  print('failed to import module {}'.format(topology['module']))
  exit(1)

def is_node_class(what):
  if inspect.isclass(what) and what.__name__ == 'Node':
    return True
  return False

mod_classes = inspect.getmembers(node_module, is_node_class)

if (len(mod_classes) < 1):
  print('module {} does not define a Node class'.format(topology['module']))
  exit(1)


probframecorrupt = 0
if 'probframecorrupt' in topology:
  probframecorrupt = 1 << int(topology['probframecorrupt'])

probframeloss = 0
if 'probframeloss' in topology:
  probframeloss = 1 << int(topology['probframeloss'])

class WLANResult(IntEnum):
  TOOWEAK = 0
  TOONOISY = 1
  RECEIVED = 2

# The following code adapted from
# The cnet network simulator (v3.4.1)
# Copyright (C) 1992-onwards,  Chris.McDonald@uwa.edu.au
# Released under the GNU General Public License (GPL) version 2.

def poisson(mean):
  L = math.exp(-mean)
  p = 1.0
  k = 0

  while True:
    k = k + 1
    p *= random.random()
    if p <= L:
      break

  return k - 1

def poisson_usecs(mean_usecs):
  lam = mean_usecs
  mult = 1.0

  while (lam > 64.0):
    lam  = lam  / 2.0
    mult = mult * 2.0

  return math.floor(poisson(lam) * mult)

def default_WLAN_model(tx_info, rx_info, tx_node, rx_node):
  # CALCULATE THE TOTAL OUTPUT POWER LEAVING TRANSMITTER
  tx_total = tx_info.tx_power_dBm - tx_info.tx_cable_loss_dBm + tx_info.tx_antenna_gain_dBi

  # CALCULATE THE DISTANCE TO THE DESTINATION NODE
  dx = tx_node.x - rx_node.x
  dy = tx_node.y - rx_node.y
  metres = math.sqrt(dx*dx + dy*dy) + 0.1

  # CALCULATE THE FREE-SPACE-LOSS OVER THIS DISTANCE
  free_space_loss = (92.467 + 20.0*math.log10(tx_info.frequency_GHz)) + 20.0*math.log10(metres/1000.0)

  # CALCULATE THE SIGNAL STRENGTH ARRIVING AT RECEIVER
  rx_strength_dBm = tx_total - free_space_loss + rx_info.rx_antenna_gain_dBi - rx_info.rx_cable_loss_dBm

  # CAN THE RECEIVER DETECT THIS SIGNAL AT ALL?
  budget = rx_strength_dBm - rx_info.rx_sensitivity_dBm
  if budget < 0.0:
    return WLANResult.TOOWEAK

  # CAN THE RECEIVER DECODE THIS SIGNAL?
  if budget < rx_info.rx_signal_to_noise_dBm:
    return WLANResult.TOONOISY
  else:
    return WLANResult.RECEIVED


LAN_ENCODE_TIME = 0 # microseconds >= 0
LAN_DECODE_TIME = 1 # microseconds >= 0

WLAN_PROPAGATION = 5 # 5usec
WLAN_BANDWIDTH = 11000000 # 11Mbps
WLAN_FREQUENCY_GHz = 2.45

WLAN_TX_POWER_dBm = 14.771
WLAN_TX_CABLE_LOSS_dBm = 0.0
WLAN_TX_ANTENNA_GAIN_dBi = 2.14

WLAN_RX_ANTENNA_GAIN_dBi = 2.14
WLAN_RX_CABLE_LOSS_dBm = 0.0
WLAN_RX_SENSITIVITY_dBm = (-82.0)
WLAN_RX_SIGNAL_TO_NOISE_dBm = 16.0

WLAN_SLEEP_mA = 9.0
WLAN_IDLE_mA = 156.0
WLAN_TX_mA = 285.0
WLAN_RX_mA = 185.0

WLAN_ENCODE_TIME = 0 # microseconds >= 0
WLAN_DECODE_TIME = 1 # microseconds > 0


# back to non-cnet code

TIME_SUFFIX_TO_USEC = {
  'us':                1,
  'ms':             1000,
  's':           1000000,
  'm':      60 * 1000000,
  'h': 60 * 60 * 1000000
}

BANDWIDTH_SUFFIX_TO_BITS_PER_SEC = {
   'bps': 1,
  'Kbps': 1<<10,
  'Mbps': 1<<20,
  'Gbps': 1<<30
}


def usecs_from_time_str(s):
  s = s.strip()
  
  match = re.match(r'(\d+)\s*(.*)', s)
  
  if match:
    digits, suffix = match.group(1, 2)
    
    digits = int(digits)

    if suffix:
      if suffix in TIME_SUFFIX_TO_USEC:
        digits = digits * TIME_SUFFIX_TO_USEC[suffix]
      else:
        raise RuntimeError('unknown time suffix {}'.format(suffix))
    
    return digits
  
  raise RuntimeError('invalid time string {}'.format(s))


def bps_from_bandwidth_str(s):
  s = s.strip()
  
  match = re.match(r'(\d+)\s*(.*)', s)
  
  if match:
    digits, suffix = match.group(1, 2)
    
    digits = int(digits)

    if suffix:
      if suffix in BANDWIDTH_SUFFIX_TO_BITS_PER_SEC:
        digits = digits * BANDWIDTH_SUFFIX_TO_BITS_PER_SEC[suffix]
      else:
        raise RuntimeError('unknown bandwidth suffix {}'.format(suffix))
    
    return digits
  
  raise RuntimeError('invalid bandwidth string {}'.format(s))


class PrivateLinkInfo:
  def __init__(self, linktype, bandwidth, propagationdelay, probframeloss, probframecorrupt, link):
    self.linktype = linktype
    self.linkup = True
    self.bandwidth = bandwidth # in bits per second
    self.propagationdelay = propagationdelay # in usecs, for WAN
    self.probframeloss = probframeloss
    self.probframecorrupt = probframecorrupt

    self.tx_until = 0

    self.rx_from = 0
    self.rx_until = 0

    if isinstance(link, LinkWLAN):
      self.frequency_GHz = link.frequency_GHz

      self.tx_power_dBm = link.tx_power_dBm
      self.tx_cable_loss_dBm = link.tx_cable_loss_dBm
      self.tx_antenna_gain_dBi = link.tx_antenna_gain_dBi

      self.rx_antenna_gain_dBi = link.rx_antenna_gain_dBi
      self.rx_cable_loss_dBm = link.rx_cable_loss_dBm
      self.rx_sensitivity_dBm = link.rx_sensitivity_dBm
      self.rx_signal_to_noise_dBm = link.rx_signal_to_noise_dBm
    
    self.public = LinkInfo(self.linktype, self.bandwidth, self.propagationdelay,
      self.probframeloss, self.probframecorrupt)
  
  def set_tx_until(self, value):
    self.tx_until = value
    self.public.tx_until = value
  
  def set_rx_period(self, rx_from, rx_until, overwrite=False):
    # if the new receiving period is after our current receiving period (there
    # is some gap clear of signal), then update to the new period exactly.
    if overwrite or rx_from > self.rx_until + 1:
      self.rx_from  = self.public.rx_from  = rx_from
      self.rx_until = self.public.rx_until = rx_until
    else:
      # otherwise merge the periods
      self.rx_until = self.public.rx_until = max(self.rx_until, rx_until)


class LinkLoopback:
  def __init__(self):
    self.node = None

  def node_added(self, node):
    if self.node != None:
      raise RuntimeError('loopback shared by multiple nodes?')
    self.node = node
  
  def get_destination_nodes(self, sender):
    return [self.node]


class LinkWAN:
  def __init__(self):
    self.nodes = []
  
  def node_added(self, node):
    self.nodes.append(node)
  
  def get_destination_nodes(self, sender):
    return [x for x in self.nodes if x != sender]


class LinkLAN:
  def __init__(self, name):
    self.nodes = []
    self.name = name
    self.bandwidth = bps_from_bandwidth_str('10Mbps')
    self.slottime = 52 # microseconds

    self.tx_from = 0
    self.tx_until = 0

    self.events_scheduled = []
  
  def set_tx_period(self, tx_from, tx_until):
    # if the new receiving period is after our current receiving period (there
    # is some gap clear of signal), then update to the new period exactly.
    if tx_from > self.tx_until + 1:
      self.tx_from  = tx_from
      self.tx_until = tx_until
    else:
      # otherwise merge the periods
      self.tx_until = max(self.tx_until, tx_until)
  
  def node_added(self, node):
    self.nodes.append(node)
  
  def get_destination_nodes(self, sender):
    return [x for x in self.nodes if x != sender]
  
  def add_scheduled(self, event):
    heapq.heappush(self.events_scheduled, event)

  def cancel_all_scheduled(self):
    for ev in self.events_scheduled:
      ev.cancelled = True
    self.events_scheduled = []
  
  def discard_past_events(self, current_time_usec):
    while self.events_scheduled:
      if self.events_scheduled[0].timeout < current_time_usec:
        heapq.heappop(self.events_scheduled)
      else:
        break


class LinkWLAN:
  def __init__(self, name):
    self.nodes = []
    self.name = name

    self.propagation = WLAN_PROPAGATION
    self.bandwidth = WLAN_BANDWIDTH

    self.frequency_GHz = WLAN_FREQUENCY_GHz

    self.tx_power_dBm = WLAN_TX_POWER_dBm
    self.tx_cable_loss_dBm = WLAN_TX_CABLE_LOSS_dBm
    self.tx_antenna_gain_dBi = WLAN_TX_ANTENNA_GAIN_dBi

    self.rx_antenna_gain_dBi = WLAN_RX_ANTENNA_GAIN_dBi
    self.rx_cable_loss_dBm = WLAN_RX_CABLE_LOSS_dBm
    self.rx_sensitivity_dBm = WLAN_RX_SENSITIVITY_dBm
    self.rx_signal_to_noise_dBm = WLAN_RX_SIGNAL_TO_NOISE_dBm

    # self.slottime = 52 # microseconds
    self.events_scheduled = []
  
  def node_added(self, node):
    self.nodes.append(node)
  
  def get_destination_nodes(self, sender):
    return [x for x in self.nodes if x != sender]
  
  def add_scheduled(self, event):
    heapq.heappush(self.events_scheduled, event)

  def cancel_scheduled_for(self, receiver):
    for ev in self.events_scheduled:
      if isinstance(ev, WLANFrameDelivery):
        if ev.receiver == receiver:
          ev.cancelled = True
  
  def discard_past_events(self, current_time_usec):
    while self.events_scheduled:
      if self.events_scheduled[0].timeout < current_time_usec:
        heapq.heappop(self.events_scheduled)
      else:
        break


class NodeInfo:
  def __init__(self, nodenumber, name, nodetype: NodeType):
    self.nodenumber = nodenumber
    self.name = name
    self.nodetype = nodetype
    self.linkinfo = []


class NodeState:
  def __init__(self, nodeinfo, hostinfo):
    self.nodenumber = nodeinfo.nodenumber
    self.nodeinfo = nodeinfo
    self.nodetype = nodeinfo.nodetype

    self.x = random.randrange(10, 1001)
    self.y = random.randrange(10, 701)

    self.impl = None
    
    self.handlers = {}
    self.handler_num_args = {}
    
    self.links = []
    self.linkinfos = []
    
    self.messagerate = TIME_SUFFIX_TO_USEC['s']
    self.application_enabled = False
    self.application_destinations = []
    self.application_waiting = {}
    self.next_message_usec = -1

    if 'messagerate' in hostinfo and hostinfo['messagerate']:
      try:
        self.messagerate = usecs_from_time_str(hostinfo['messagerate'])
      except:
        print('failed to set messagerate={}'.format(hostinfo['messagerate']))
        exit(1)
    elif 'messagerate' in topology and topology['messagerate']:
      try:
        self.messagerate = usecs_from_time_str(topology['messagerate'])
      except:
        print('failed to set messagerate={}'.format(topology['messagerate']))
        exit(1)
    
    if 'x' in hostinfo and hostinfo['x']:
      self.x = float(hostinfo['x'])
    
    if 'y' in hostinfo and hostinfo['y']:
      self.y = float(hostinfo['y'])
  
  def add_link(self, link, linkinfo: PrivateLinkInfo):
    self.links.append(link)
    self.linkinfos.append(linkinfo)
    self.nodeinfo.linkinfo.append(linkinfo.public)
    link.node_added(self)


class TimedEvent:
  def __init__(self, timeout, event):
    self.timeout = timeout
    self.event = event
    self.cancelled = False
  
  def __eq__(self, other):
    return self.timeout == other.timeout

  def __ne__(self, other):
    return self.timeout != other.timeout

  def __lt__(self, other):
    return self.timeout < other.timeout

  def __le__(self, other):
    return self.timeout <= other.timeout

  def __gt__(self, other):
    return self.timeout > other.timeout

  def __ge__(self, other):
    return self.timeout >= other.timeout


class FrameDelivery:
  def __init__(self, frame, link, receivers):
    self.frame = frame
    self.link = link
    self.receivers = receivers


class WLANFrameDelivery:
  def __init__(self, frame, link, sender, receiver):
    self.frame = frame
    self.link = link
    self.receiver = receiver
    self.tx_pos = (sender.x, sender.y)
    self.rx_pos = (receiver.x, receiver.y)


class CollisionDelivery:
  def __init__(self, link, receiver):
    self.link = link
    self.receiver = receiver


class WLANCollisionDelivery:
  def __init__(self, link, sender, receiver):
    self.link = link
    self.receiver = receiver
    self.tx_pos = (sender.x, sender.y)
    self.rx_pos = (receiver.x, receiver.y)


class Timer:
  def __init__(self, timeout, timerid, nodenumber, event, data):
    self.timeout = timeout
    self.timerid = timerid
    self.nodenumber = nodenumber
    self.event = event
    self.data = data
    self.cancelled = False

  def __eq__(self, other):
    return self.timeout == other.timeout

  def __ne__(self, other):
    return self.timeout != other.timeout

  def __lt__(self, other):
    return self.timeout < other.timeout

  def __le__(self, other):
    return self.timeout <= other.timeout

  def __gt__(self, other):
    return self.timeout > other.timeout

  def __ge__(self, other):
    return self.timeout >= other.timeout


def earliest(times):
  earliest = None
  for t in times:
    if earliest == None or (t != None and t < earliest):
      earliest = t
  return earliest


class Simulator:
  def __init__(self):
    self.nodes = []

    self.nodes_with_application_enabled = []

    self.current_index = None

    self.current_time_usec = 1 # simulation time in usec
    self.duration_usec = None

    if args.execution_duration:
      try:
        self.duration_usec = usecs_from_time_str(args.execution_duration)
      except:
        print('invalid execution duration {}'.format(args.execution_duration))
        exit(1)

    self.event_queue = [] # waiting frame arrivals, in order

    self.timers_created = 0
    self.timer_queue = [] # current timers, in order
    self.timer_map = {} # lookup from timerID to timer queue entry

    if args.stats_csv:
      fout = open(args.stats_csv, 'w', newline='')

      self.stats_csv_write = csv.writer(fout, quoting=csv.QUOTE_MINIMAL)

      self.stats_csv_write.writerow(['Time (usec)', 'Events Raised',
        'Messages Generated', 'Messages Delivered',
        'Average Delivery Time (usec)',
        'Frames Transmitted', 'Frames Received', 'Frame Collisions',
        'Bytes Received (Physical)', 'Bytes Received (Application)',
        'Efficiency (AL/PL)'])
    else:
      self.stats_csv_write = None

    self.stats_period = 10000000
    self.next_stats_print_usec = 10000000
    
    if args.stats_period:
      try:
        self.stats_period = usecs_from_time_str(args.stats_period)
        self.next_stats_print_usec = self.stats_period
      except:
        print('invalid stats period {}'.format(args.stats_period))
        exit(1)

    self.events_raised = 0
    self.messages_generated = 0
    self.messages_delivered = 0
    self.total_delivery_time = 0
    self.frames_transmitted = 0
    self.frames_received = 0
    self.frame_collisions = 0
    self.bytes_received_physical = 0
    self.bytes_received_application = 0

    node_module.print = self.intercepted_print
    node_module.current_time_usec = self.get_current_time_usec
    node_module.enable_application = self.enable_application
    node_module.disable_application = self.disable_application
    node_module.start_timer = self.start_timer
    node_module.stop_timer = self.stop_timer
    node_module.timer_data = self.timer_data
    node_module.set_handler = self.set_handler
    node_module.write_physical = self.write_physical
    node_module.write_physical_reliable = self.write_physical_reliable
    node_module.write_application = self.write_application
    node_module.carrier_sense = self.carrier_sense
    node_module.wlan_arrival = self.wlan_arrival
    node_module.set_position = self.set_position
    node_module.get_position = self.get_position

  def add_node(self, hostinfo, nodetype: NodeType):
    name = hostinfo['name']
    info = NodeInfo(len(self.nodes), name, nodetype)
    state = NodeState(info, hostinfo)
    state.add_link(LinkLoopback(), PrivateLinkInfo(LinkType.LOOPBACK, 0, 0, 0, 0, None))
    self.nodes.append(state)

    self.current_index = info.nodenumber
    node_module.nodeinfo = info
    node_module.linkinfo = info.linkinfo
    state.impl = node_module.Node()

    return state

  def boot_nodes(self):
    for node in self.nodes:
      sig = inspect.signature(node.impl.reboot_node)
      numargs = len(sig.parameters)
      nodeargs = [args.nodeargs][:numargs]

      self.current_index = node.nodenumber
      node_module.nodeinfo = node.nodeinfo
      node_module.linkinfo = node.nodeinfo.linkinfo

      try:
        node.impl.reboot_node(*nodeargs)
      except:
        etype, value, tb =  sys.exc_info()
        print("Error in node {} reboot_node:")
        traceback.print_exception(etype, value, tb)
        exit(1)

    self.current_index = None

  def call_node_handler(self, node_index, event, *args):
    if self.current_index != None:
      raise RuntimeError('recursive call_node_handler')
    
    node = self.nodes[node_index]
    handlers = node.handlers

    if event in handlers:
      self.current_index = node_index
      node_module.nodeinfo = node.nodeinfo
      node_module.linkinfo = node.nodeinfo.linkinfo

      try:
        # sig = inspect.signature(handlers[event])
        # args = args[:len(sig.parameters)]
        passedargs = args[:node.handler_num_args[event]]
        handlers[event](*passedargs)
      except:
        etype, value, tb = sys.exc_info()
        print("Error in node {} handler {}:")
        traceback.print_exception(etype, value, tb)
        exit(1)
      
      self.current_index = None

  def next_application_message(self):
    earliest = None

    for node in self.nodes_with_application_enabled:
      if (node.next_message_usec < self.current_time_usec):
        node.next_message_usec = self.current_time_usec + poisson_usecs(node.messagerate)
      if (earliest == None or node.next_message_usec < earliest.next_message_usec):
        earliest = node

    if earliest != None:
      return (earliest.next_message_usec, earliest)
    else:
      return (None, None)

  def generate_application_message(self, sender):
    dests = sender.application_destinations
    
    if dests:
      destnum = random.choice(dests)
      
      messagebytes = secrets.token_bytes(50)
      
      self.events_raised = self.events_raised + 1
      simulator.call_node_handler(sender.nodenumber, Event.APPLICATIONREADY,
        destnum, messagebytes)
      
      self.messages_generated = self.messages_generated + 1

      dest = self.nodes[destnum]

      dest.application_waiting[messagebytes] = self.current_time_usec

      sender.next_message_usec = 0 # will be regenerated by next_application_message

  def process_next_event(self):
    app_time, app_node = self.next_application_message()

    event_time = None
    while self.event_queue:
      if self.event_queue[0].cancelled:
        heapq.heappop(self.event_queue)
      else:
        event_time = self.event_queue[0].timeout
        break

    timer_time = None
    if self.timer_queue:
      timer_time = self.timer_queue[0].timeout

    earliest_time = earliest([app_time, event_time, timer_time,
      self.next_stats_print_usec])

    if earliest_time == None:
      return False

    if self.duration_usec and earliest_time > self.duration_usec:
      self.current_time_usec = self.duration_usec
      return False

    if earliest_time < self.current_time_usec:
      raise RuntimeError('time is running backwards?')

    self.current_time_usec = earliest_time

    if earliest_time == app_time:
      self.generate_application_message(app_node)
      return True

    if earliest_time == event_time:
      event = self.event_queue[0].event
      heapq.heappop(self.event_queue)

      if (isinstance(event, FrameDelivery)):
        for receiver in event.receivers:
          try:
            linkno = receiver.links.index(event.link)
          except:
            raise RuntimeError('receiving node does not have link?')

          self.events_raised = self.events_raised + 1
          self.frames_received = self.frames_received + 1
          self.bytes_received_physical = self.bytes_received_physical + len(event.frame)
          self.call_node_handler(receiver.nodenumber, Event.PHYSICALREADY, linkno, event.frame)
        
        if isinstance(event.link, LinkLAN):
          event.link.discard_past_events(self.current_time_usec)
      
      elif isinstance(event, WLANFrameDelivery):
        receiver = event.receiver

        try:
          linkno = receiver.links.index(event.link)
        except:
          raise RuntimeError('receiving node does not have link?')

        self.events_raised = self.events_raised + 1
        self.frames_received = self.frames_received + 1
        self.bytes_received_physical = self.bytes_received_physical + len(event.frame)
        self.call_node_handler(receiver.nodenumber, Event.PHYSICALREADY, linkno, event.frame)

        event.link.discard_past_events(self.current_time_usec)
      
      elif isinstance(event, CollisionDelivery) or isinstance(event, WLANCollisionDelivery):
        receiver = event.receiver

        try:
          linkno = event.receiver.links.index(event.link)
        except:
          raise RuntimeError('receiving node does not have link?')

        self.events_raised = self.events_raised + 1
        self.call_node_handler(receiver.nodenumber, Event.FRAMECOLLISION, linkno)
        
        if isinstance(event.link, LinkLAN) or isinstance(event.link, LinkWLAN):
          event.link.discard_past_events(self.current_time_usec)
      
      else:
        raise RuntimeError('unexpected event type {}'.format(event))

      return True
    
    if earliest_time == timer_time:
      timer = heapq.heappop(self.timer_queue)
      if not timer.cancelled:
        self.events_raised = self.events_raised + 1
        self.call_node_handler(timer.nodenumber, timer.event, timer.timerid)
        try:
          self.timer_map.pop(timer.timerid)
        except:
          pass
      return True
    
    if earliest_time == self.next_stats_print_usec:
      if self.stats_csv_write:
        average_delivery_time = 0

        if self.messages_delivered:
          average_delivery_time = self.total_delivery_time // self.messages_delivered

        efficiency = 1
        if self.bytes_received_physical:
          efficiency = self.bytes_received_application / self.bytes_received_physical

        self.stats_csv_write.writerow([self.current_time_usec,
          self.events_raised,
          self.messages_generated, self.messages_delivered,
          average_delivery_time,
          self.frames_transmitted, self.frames_received, self.frame_collisions,
          self.bytes_received_physical, self.bytes_received_application,
          efficiency])
        
        self.next_stats_print_usec = self.next_stats_print_usec + self.stats_period
      else:
        self.next_stats_print_usec = None
      
      # raise periodic event to give nodes a chance to do things (e.g. print their own stats)
      for node_index in range(len(self.nodes)):
        self.call_node_handler(node_index, Event.PERIODIC, self.next_stats_print_usec)

      return True
    
    return False

  # this function also adapted from the cnet network simulator (see copyright
  # notice above)
  def corrupt_frame(self, linkinfo, frame):
    prob = probframecorrupt
    if linkinfo.probframecorrupt != None:
      prob = linkinfo.probframecorrupt

    if (prob > 0 and random.randrange(0, prob) == 0):
      # CORRUPT FRAME BY COMPLEMENTING TWO OF ITS BYTES
      offset = random.randrange(0, len(frame) - 2)
      frame = bytearray(frame)
      frame[offset] = (~frame[offset] & 0xFF) # detectable by all checksums
      frame[offset + 1] = (~frame[offset + 1] & 0xFF)
      frame = bytes(frame)

    return frame
  
  # this function also adapted from the cnet network simulator (see copyright
  # notice above)
  def generate_lan_collision(self, sender, link, linkinfo):
    # remove all existing frames and collisions scheduled on this LAN
    link.cancel_all_scheduled()

    # record that this segment is now busy due to jamming
    link.tx_from = self.current_time_usec + 1
    link.tx_until = self.current_time_usec + link.slottime

    nhear = 0

    # deliver a collision frame to all nodes on this LAN (incl. ourselves)
    for dest in link.nodes:
      destlinkno = dest.links.index(link)
      destlinkinfo = dest.linkinfos[destlinkno]

      # each destination nic cannot transmit while collision is being received
      destlinkinfo.set_tx_until(link.tx_until)

      # propagation delay comes from distance of (src -> dest) at 200m/usec
      proptime = max(1, abs(dest.x - sender.x) // 200)

      # print('-> collision at {} from {} until {}'.format(dest, self.current_time_usec + proptime, link.tx_until + proptime))
      destlinkinfo.set_rx_period(self.current_time_usec + proptime, link.tx_until + proptime, overwrite=True)

      arrivaltime = destlinkinfo.rx_until + LAN_DECODE_TIME
      collisionev = TimedEvent(arrivaltime, CollisionDelivery(link, dest))

      heapq.heappush(self.event_queue, collisionev)
      link.add_scheduled(collisionev)

      nhear = nhear + 1
    
    return nhear
  
  def write_physical_lan(self, reliable, sender, receivers, link, linkinfo, frame, time_to_write):
    # first check for collision
    self_receiving = self.current_time_usec >= linkinfo.rx_from and self.current_time_usec <= linkinfo.rx_until

    if not reliable and (self.current_time_usec <= link.tx_until or self_receiving):
      if self.generate_lan_collision(sender, link, linkinfo) > 0:
        self.frame_collisions = self.frame_collisions + 1
    else:
      time_to_write = time_to_write

      write_begins = linkinfo.tx_until if self.current_time_usec <= linkinfo.tx_until else self.current_time_usec
      write_begins = write_begins + LAN_ENCODE_TIME

      linkinfo.set_tx_until(write_begins + time_to_write)
      linkinfo.set_rx_period(self.current_time_usec, linkinfo.tx_until) # our nic

      link.set_tx_period(write_begins, linkinfo.tx_until) # entire lan segment

      for receiver in receivers:
        if receiver != sender:
          destlinkno = receiver.links.index(link)
          destlinkinfo = receiver.linkinfos[destlinkno]

          proptime = max(1, abs(receiver.x - sender.x) // 200)
          destlinkinfo.set_rx_period(self.current_time_usec + proptime, linkinfo.rx_until + proptime)

          received_frame = self.corrupt_frame(linkinfo, frame) if not reliable else frame

          arrival_event = TimedEvent(destlinkinfo.rx_until + LAN_DECODE_TIME,
            FrameDelivery(received_frame, link, [receiver]))
          
          heapq.heappush(self.event_queue, arrival_event)
          link.add_scheduled(arrival_event)

  def write_physical_wlan(self, reliable, sender, receivers, link, linkinfo, frame, time_to_write):
    # first check for collision
    start_transmitting = self.current_time_usec if self.current_time_usec <= linkinfo.tx_until else linkinfo.tx_until
    start_transmitting = start_transmitting + WLAN_ENCODE_TIME
    
    linkinfo.set_tx_until(start_transmitting + time_to_write)

    for receiver in receivers:
      if receiver != sender:
        destlinkno = receiver.links.index(link)
        destlinkinfo = receiver.linkinfos[destlinkno]

        # TRANSMITTING AND RECEIVING WLANs MUST BE OPERATING AT THE SAME FREQUENCY
        if linkinfo.frequency_GHz != destlinkinfo.frequency_GHz:
          continue

        # CALCULATE THE DISTANCE TO THE DESTINATION NODE
        dx = receiver.x - sender.x
        dy = receiver.y - sender.y

        metres = math.sqrt(dx*dx + dy*dy) + 0.1
        proptime = max(1, metres // 299)

        Tarrive_start = start_transmitting + proptime
        Tarrive_end = Tarrive_start + time_to_write

        wlan_result = default_WLAN_model(linkinfo, destlinkinfo, sender, receiver)

        if wlan_result == WLANResult.TOOWEAK:
          continue
        
        # if destination is either transmitting or receiving ==> collision
        if not reliable and (Tarrive_end >= destlinkinfo.rx_from or Tarrive_start <= destlinkinfo.rx_until):
          link.cancel_scheduled_for(receiver)
          
          destlinkinfo.set_rx_period(Tarrive_start, Tarrive_end)

          arrivaltime = Tarrive_end + WLAN_DECODE_TIME
          collisionev = TimedEvent(arrivaltime, CollisionDelivery(link, receiver))

          heapq.heappush(self.event_queue, collisionev)

          self.frame_collisions = self.frame_collisions + 1
        elif wlan_result != WLANResult.RECEIVED:
          # can't decode the data from the background noise, but it will interfere with other signals
          destlinkinfo.set_rx_period(Tarrive_start, Tarrive_end)
        else:
          # frame decoded and will arrive
          destlinkinfo.set_rx_period(Tarrive_start, Tarrive_end)
          
          received_frame = self.corrupt_frame(linkinfo, frame) if not reliable else frame

          arrival_event = TimedEvent(Tarrive_end + LAN_DECODE_TIME,
            WLANFrameDelivery(received_frame, link, sender, receiver))
          
          heapq.heappush(self.event_queue, arrival_event)

          link.add_scheduled(arrival_event)

  def write_physical_internal(self, linkno, frame, reliable):
    sender = self.nodes[self.current_index]

    if (linkno < 0 or linkno >= len(sender.links)):
      return False
    
    if not isinstance(frame, bytes):
      raise TypeError('frame *must* be a bytes object')
    
    link = sender.links[linkno]
    linkinfo = sender.linkinfos[linkno]
    # print('{} transmit {} bytes on link {}'.format(self.current_index, len(frame), link))

    if (not linkinfo.linkup):
      return False

    self.frames_transmitted = self.frames_transmitted + 1

    # lose frame
    if not reliable:
      probloss = probframeloss
      if linkinfo.probframeloss != None:
        probloss = linkinfo.probframeloss
      if probloss and random.randrange(0, probloss) == 0:
        return True

    time = self.current_time_usec

    time_to_write = 0
    bandwidth = linkinfo.bandwidth
    if bandwidth > 0:
      time_to_write = len(frame) * 8 * TIME_SUFFIX_TO_USEC['s'] // bandwidth
    
    receivers = link.get_destination_nodes(sender)

    if isinstance(link, LinkLoopback) or isinstance(link, LinkWAN):
      if self.current_time_usec <= linkinfo.tx_until:
        linkinfo.set_tx_until(linkinfo.tx_until + time_to_write)
      else:
        linkinfo.set_tx_until(self.current_time_usec + time_to_write)
      
      if (len(receivers) > 0):
        time = self.current_time_usec + time_to_write
        if (linkinfo.propagationdelay > 0):
          time = time + linkinfo.propagationdelay
        received_frame = self.corrupt_frame(linkinfo, frame) if not reliable else frame
        heapq.heappush(self.event_queue, TimedEvent(time, FrameDelivery(received_frame, link, receivers)))
    
    elif isinstance(link, LinkLAN):
      self.write_physical_lan(reliable, sender, receivers, link, linkinfo, frame, time_to_write)
    
    elif isinstance(link, LinkWLAN):
      self.write_physical_wlan(reliable, sender, receivers, link, linkinfo, frame, time_to_write)

    return True

  # standard functions that are redirected from the node perspective

  def intercepted_print(self, *userargs):
    if not args.silent_nodes:
      print('[{}]: '.format(self.current_index), *userargs,
        file=args.node_output)
  
  # below here is node-facing functionality

  def get_current_time_usec(self):
    return self.current_time_usec

  def enable_application(self, nodenumber = None):
    if (nodenumber == None):
      for nn in range(len(self.nodes)):
        self.enable_application(nn)
      return True
    else:
      if nodenumber < 0 or nodenumber >= len(self.nodes):
        return False
      
      if self.current_index != nodenumber:
        current_node = self.nodes[self.current_index]
        if not (nodenumber in current_node.application_destinations):
          current_node.application_destinations.append(nodenumber)
          current_node.application_enabled = True
          self.nodes_with_application_enabled = [x for x in self.nodes if x.application_enabled]
  
  def disable_application(self, nodenumber = None):
    if (nodenumber == None):
      for nn in range(len(self.nodes)):
        self.disable_application(nn)
      return True
    else:
      if nodenumber < 0 or nodenumber >= len(self.nodes):
        return False
      
      if self.current_index != nodenumber:
        current_node = self.nodes[self.current_index]
        current_node.application_destinations.remove(nodenumber)
        if not current_node.application_destinations:
          current_node.application_enabled = False
          self.nodes_with_application_enabled = [x for x in self.nodes if x.application_enabled]

  def start_timer(self, event, usecs, data = None):
    if usecs < 0:
      raise RuntimeError('timer with negative usecs')

    if not isinstance(event, Event):
      raise TypeError('event should be an Event enumeration value')

    self.timers_created = self.timers_created + 1
    timeout = self.current_time_usec + usecs
    timer = Timer(timeout, self.timers_created, self.current_index, event, data)
    heapq.heappush(self.timer_queue, timer)
    self.timer_map[self.timers_created] = timer
    return self.timers_created

  def stop_timer(self, timerid):
    try:
      timer = self.timer_map.pop(timerid)
      timer.cancelled = True
      return True
    except:
      return False

  def timer_data(self, timerid):
    try:
      timer = self.timer_map[timerid]
      return timer.data
    except:
      raise RuntimeError('timer no longer exists')

  def set_handler(self, event, callback):
    # print('{}: {} -> {}'.format(self.current_index, event, callback))
    sig = inspect.signature(callback)
    numargs = len(sig.parameters)
    node = self.nodes[self.current_index]
    node.handlers[event] = callback
    node.handler_num_args[event] = numargs
  
  def write_physical(self, linkno, frame):
    return self.write_physical_internal(linkno, frame, False)
  
  def write_physical_reliable(self, linkno, frame):
    return self.write_physical_internal(linkno, frame, True)

  def write_application(self, message):
    node = self.nodes[self.current_index]

    if not isinstance(message, bytes):
      raise TypeError('write_application must receive a bytes() object')

    try:
      sent_time = node.application_waiting.pop(message)
    except:
      return False
    
    elapsed = self.current_time_usec - sent_time

    self.total_delivery_time = self.total_delivery_time + elapsed
    self.messages_delivered = self.messages_delivered + 1
    self.bytes_received_application = self.bytes_received_application + len(message)

    return True
  
  def carrier_sense(self, linkno):
    node = self.nodes[self.current_index]
    
    if linkno < 0 or linkno > len(node.links):
      return False # invalid link
    
    link = node.links[linkno]
    
    if isinstance(link, LinkLAN) or isinstance(link, LinkWLAN):
      linkinfo = node.linkinfos[linkno]
      if linkinfo.rx_from <= self.current_time_usec and self.current_time_usec <= linkinfo.rx_until:
        return True
      
    # if isinstance(link, LinkLAN):
    #   if link.tx_from <= self.current_time_usec and self.current_time_usec <= link.tx_until:
    #     return True
    
    return False
  
  def wlan_arrival(self, link):
    return 0, 0 # rx_signal_dBm, rx_angle (radians)
  
  def set_position(self, x: float, y: float):
    node = self.nodes[self.current_index]
    node.x = x
    node.y = y

  def get_position(self):
    node = self.nodes[self.current_index]
    return node.x, node.y


if args.seed:
  random.seed(args.seed)

simulator = Simulator()

bandwidth = 56 * 1024

if 'bandwidth' in topology and topology['bandwidth']:
  try:
    bandwidth = bps_from_bandwidth_str(topology['bandwidth'])
  except:
    print('failed to set bandwidth={}'.format(topology['bandwidth']))
    exit(1)

propagationdelay = 2500 * 1000

if 'propagationdelay' in topology and topology['propagationdelay']:
  try:
    propagationdelay = usecs_from_time_str(topology['propagationdelay'])
  except:
    print('failed to set propagationdelay={}'.format(topology['propagationdelay']))
    exit(1)

if 'hosts' in topology or 'mobiles' in topology:
  hostlookup = {}
  hostnum = 0

  mobilelookup = {}
  mobilenum = 0

  lanlookup = {}
  lannum = 0

  linklookup = {}

  # first just create the nodes
  if 'hosts' in topology:
    for host in topology['hosts']:
      hostnum = hostnum + 1
      
      if not 'name' in host:
        host['name'] = 'Host {}'.format(hostnum)
      
      if host['name'] in hostlookup:
        print('Host "{}" is multiply defined'.format(host['name']))
        exit(1)
      
      hostlookup[host['name']] = simulator.add_node(host, NodeType.HOST)
  
  # just one WLAN for now
  wlan = LinkWLAN('WLAN')

  if 'mobiles' in topology:
    for mobile in topology['mobiles']:
      mobilenum = mobilenum + 1

      if not 'name' in mobile:
        mobile['name'] = 'Mobile {}'.format(mobilenum)
      
      if mobile['name'] in mobilelookup:
        print('Mobile "{}" is multiply defined'.format(mobile['name']))
        exit(1)
      
      node = simulator.add_node(mobile, NodeType.MOBILE)
      mobilelookup[mobile['name']] = node

      linkinfo = PrivateLinkInfo(LinkType.WLAN, wlan.bandwidth, 0, probframeloss, probframecorrupt, wlan)
      node.add_link(wlan, linkinfo)

  # now create the LAN segments
  if 'lansegments' in topology:
    for lan in topology['lansegments']:
      lannum = lannum + 1

      if not 'name' in lan:
        lan['name'] = 'LAN {}'.format(lannum)
      
      lanname = lan['name']

      if lanname in lanlookup:
        print('LAN "{}" is multiply defined'.format(lanname))
        exit(1)
      
      lanimpl = LinkLAN(lanname)
      lanlookup[lanname] = lanimpl

      if 'bandwidth' in lan and lan['bandwidth']:
        try:
          lanimpl.bandwidth = bps_from_bandwidth_str(lan['bandwidth'])
        except:
          print('failed to set bandwidth={}'.format(lan['bandwidth']))
          exit(1)

  # now go back through and create the links
  if 'hosts' in topology:
    for host in topology['hosts']:
      if 'links' in host:
        node1 = hostlookup[host['name']]

        for link in host['links']:
          linkinfo = None

          if 'to' in link:
            if link['to'] in hostlookup:
              linkid = [host['name'], link['to']].sort()
              
              if linkid in linklookup:
                wan, linkinfo2, linkinfo = linklookup[linkid]
              else:
                node2 = hostlookup[link['to']]
                wan = LinkWAN()
                linkinfo = PrivateLinkInfo(LinkType.WAN, bandwidth, propagationdelay, probframeloss, probframecorrupt, wan)
                linkinfo2 = PrivateLinkInfo(LinkType.WAN, bandwidth, propagationdelay, probframeloss, probframecorrupt, wan)
                node1.add_link(wan, linkinfo)
                node2.add_link(wan, linkinfo2)
                linklookup[linkid] = (wan, linkinfo, linkinfo2)
            else:
              print('unknown node {}'.format(link['to']))
              exit(1)
          
          elif 'lan to' in link:
            lanname = link['lan to']
            if lanname in lanlookup:
              lan = lanlookup[lanname]
              linkinfo = PrivateLinkInfo(LinkType.LAN, lan.bandwidth, 0, probframeloss, probframecorrupt, lan)
              node1.add_link(lan, linkinfo)
            else:
              print('unknown LAN segment {}'.format(lanname))
              exit(1)

          # adjust properties for this node's linkinfo, only
          if linkinfo != None:
            if 'bandwidth' in link and link['bandwidth']:
              try:
                linkinfo.bandwidth = bps_from_bandwidth_str(link['bandwidth'])
              except:
                print('failed to set bandwidth={}'.format(link['bandwidth']))
                exit(1)
            if 'propagationdelay' in link and link['propagationdelay']:
              try:
                linkinfo.propagationdelay = usecs_from_time_str(link['propagationdelay'])
              except:
                print('failed to set propagationdelay={}'.format(link['propagationdelay']))
                exit(1)
            if 'probframecorrupt' in link:
              linkinfo.probframecorrupt = 1 << int(link['probframecorrupt'])
            if 'probframeloss' in link:
              linkinfo.probframeloss = 1 << int(link['probframeloss'])

simulator.boot_nodes()

while True:
  if not simulator.process_next_event():
    break
