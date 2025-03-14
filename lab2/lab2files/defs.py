from enum import Enum

class Event(Enum):
  NULL = 0
  REBOOT = 1
  SHUTDOWN = 2
  PHYSICALREADY = 3
  APPLICATIONREADY = 4
  DEBUG0 = 5
  TIMER0 = 6
  TIMER1 = 7

class LinkType(Enum):
  LOOPBACK = 0
  WAN = 1

class LinkInfo:
  def __init__(self, linktype, bandwidth, propagationdelay):
    self.linktype = linktype
    self.linkup = True
    self.bandwidth = bandwidth # in bits per second
    self.propagationdelay = propagationdelay # in usecs, for WAN
