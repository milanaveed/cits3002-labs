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

from defs import Event, LinkType, LinkInfo


parser = argparse.ArgumentParser(prog='Network Simulator')

parser.add_argument('-e', '--execution-duration', nargs='?')

parser.add_argument('--node-output', nargs='?', type=argparse.FileType('w'),
  default=sys.stdout)

parser.add_argument('--silent-nodes', action='store_true')

parser.add_argument('--stats-period', nargs='?')

parser.add_argument('--stats-csv', nargs='?')

parser.add_argument('-S', '--seed', nargs='?', type=int)

parser.add_argument('topology')

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


# back to non-cnet code

MAY_CORRUPT_FRAMES = False

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


class LinkLoopback:
  def __init__(self):
    self.linkinfo = LinkInfo(LinkType.LOOPBACK, 0, 0)
    self.node = None

  def node_added(self, node):
    if self.node != None:
      raise RuntimeError('loopback shared by multiple nodes?')
    self.node = node
  
  def get_destination_nodes(self, sender):
    return [self.node]


class LinkWAN:
  def __init__(self, linkinfo):
    self.linkinfo = linkinfo
    self.nodes = []
  
  def node_added(self, node):
    self.nodes.append(node)
  
  def get_destination_nodes(self, sender):
    return [x for x in self.nodes if x != sender]


class NodeInfo:
  def __init__(self, nodenumber, name):
    self.nodenumber = nodenumber
    self.name = name
    self.linkinfo = []


class NodeState:
  def __init__(self, nodeinfo):
    self.nodenumber = nodeinfo.nodenumber
    self.nodeinfo = nodeinfo
    self.impl = None
    self.handlers = {}
    self.links = []
    self.messagerate = TIME_SUFFIX_TO_USEC['s']
    self.application_enabled = False
    self.application_destinations = []
    self.application_waiting = {}
    self.next_message_usec = -1

    if 'messagerate' in topology and topology['messagerate']:
      try:
        self.messagerate = usecs_from_time_str(topology['messagerate'])
      except:
        print('failed to set messagerate={}'.format(topology['messagerate']))
  
  def add_link(self, link):
    self.links.append(link)
    self.nodeinfo.linkinfo.append(link.linkinfo)
    link.node_added(self)


class FrameDelivery:
  def __init__(self, frame, link, receivers):
    self.frame = frame
    self.link = link
    self.receivers = receivers


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

    self.current_time_usec = 0 # simulation time in usec
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
        'Frames Transmitted', 'Frames Received',
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
    self.bytes_received_physical = 0
    self.bytes_received_application = 0

    node_module.print = self.intercepted_print
    node_module.enable_application = self.enable_application
    node_module.disable_application = self.disable_application
    node_module.start_timer = self.start_timer
    node_module.stop_timer = self.stop_timer
    node_module.timer_data = self.timer_data
    node_module.set_handler = self.set_handler
    node_module.write_physical = self.write_physical
    node_module.write_application = self.write_application

  def add_node(self, name):
    info = NodeInfo(len(self.nodes), name)
    state = NodeState(info)
    state.add_link(LinkLoopback())
    self.nodes.append(state)

    self.current_index = info.nodenumber
    node_module.nodeinfo = info
    node_module.linkinfo = info.linkinfo
    state.impl = node_module.Node()

    return state

  def boot_nodes(self):
    for node in self.nodes:
      self.current_index = node.nodenumber
      node_module.nodeinfo = node.nodeinfo
      node_module.linkinfo = node.nodeinfo.linkinfo

      try:
        node.impl.reboot_node()
      except:
        etype, value, tb =  sys.exc_info()
        print("Error in node {} reboot_node:")
        traceback.print_exception(etype, value, tb)

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
        handlers[event](*args)
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
    if self.event_queue:
      event_time, event = self.event_queue[0]

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
      event_time, event = heapq.heappop(self.event_queue)
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
      else:
        raise RuntimeError('unexpected event type {}'.format(event))
      return True
    
    if earliest_time == timer_time:
      timer = heapq.heappop(self.timer_queue)
      if not timer.cancelled:
        self.events_raised = self.events_raised + 1
        self.call_node_handler(timer.nodenumber, timer.event)
        self.timer_map.pop(timer.timerid)
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
          self.frames_transmitted, self.frames_received,
          self.bytes_received_physical, self.bytes_received_application,
          efficiency])
        
        self.next_stats_print_usec = self.next_stats_print_usec + self.stats_period
      else:
        self.next_stats_print_usec = None

      return True
    
    return False

  # this function also adapted from the cnet network simulator (see copyright
  # notice above)
  def corrupt_frame(self, link, frame):
    prob = probframecorrupt

    if (prob > 0 and random.randrange(0, prob) == 0):
      # CORRUPT FRAME BY COMPLEMENTING TWO OF ITS BYTES
      offset = random.randrange(0, len(frame) - 2)
      frame = bytearray(frame)
      frame[offset] = (~frame[offset] & 0xFF) # detectable by all checksums
      frame[offset + 1] = (~frame[offset + 1] & 0xFF)
      frame = bytes(frame)

    return frame

  # standard functions that are redirected from the node perspective

  def intercepted_print(self, *userargs):
    if not args.silent_nodes:
      print('[{}]: '.format(self.current_index), *userargs,
        file=args.node_output)
  
  # below here is node-facing functionality

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
    self.nodes[self.current_index].handlers[event] = callback
  
  def write_physical(self, linkno, frame):
    sender = self.nodes[self.current_index]

    if (linkno < 0 or linkno >= len(sender.links)):
      return False
    
    if not isinstance(frame, bytes):
      raise TypeError('frame *must* be a bytes object')
    
    link = sender.links[linkno]
    # print('{} transmit {} bytes on link {}'.format(self.current_index, len(frame), link))

    if (not link.linkinfo.linkup):
      return False

    self.frames_transmitted = self.frames_transmitted + 1

    # lose frame (with global probability, not per-link yet)
    probloss = probframeloss
    if probloss and random.randrange(0, probloss) == 0:
      return True

    frame = self.corrupt_frame(link, frame)

    receivers = link.get_destination_nodes(sender)

    if (len(receivers) > 0):
      time = self.current_time_usec

      bandwidth = link.linkinfo.bandwidth
      if (bandwidth > 0):
        time = time + (len(frame) * 8 * TIME_SUFFIX_TO_USEC['s'] // bandwidth)
      
      if (link.linkinfo.propagationdelay > 0):
        time = time + link.linkinfo.propagationdelay

      heapq.heappush(self.event_queue, (time, FrameDelivery(frame, link, receivers)))

    return True
  
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


if args.seed:
  random.seed(args.seed)

simulator = Simulator()

bandwidth = 56 * 1024

if 'bandwidth' in topology and topology['bandwidth']:
  try:
    bandwidth = bps_from_bandwidth_str(topology['bandwidth'])
  except:
    print('failed to set bandwidth={}'.format(topology['bandwidth']))

propagationdelay = 2500 * 1000

if 'propagationdelay' in topology and topology['propagationdelay']:
  try:
    propagationdelay = usecs_from_time_str(topology['propagationdelay'])
  except:
    print('failed to set propagationdelay={}'.format(topology['propagationdelay']))

if 'hosts' in topology:
  hostlookup = {}
  linklookup = {}
  hostnum = 0

  # first just create the nodes
  for host in topology['hosts']:
    hostnum = hostnum + 1
    
    if not 'name' in host:
      host['name'] = 'Host {}'.format(hostnum)
    
    hostlookup[host['name']] = simulator.add_node(host['name'])

  # now go back through and create the links
  for host in topology['hosts']:
    if 'links' in host:
      for link in host['links']:
        if 'to' in link:
          if link['to'] in hostlookup:
            linkid = [host['name'], link['to']].sort()
            if not linkid in linklookup:
              node1 = hostlookup[host['name']]
              node2 = hostlookup[link['to']]
              wan = LinkWAN(LinkInfo(LinkType.WAN, bandwidth, propagationdelay))
              node1.add_link(wan)
              node2.add_link(wan)
              linklookup[linkid] = wan
          else:
            print('unknown node {}'.format(link['to']))

simulator.boot_nodes()

while True:
  if not simulator.process_next_event():
    break
