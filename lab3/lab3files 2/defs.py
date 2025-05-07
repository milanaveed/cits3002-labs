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
  TIMER2 = 8
  TIMER3 = 9
  TIMER4 = 10
  TIMER5 = 11
  TIMER6 = 12

class LinkType(Enum):
  LOOPBACK = 0
  WAN = 1

class LinkInfo:
  def __init__(self, linktype, bandwidth, propagationdelay, probframeloss, probframecorrupt):
    self.linktype = linktype
    self.linkup = True
    self.bandwidth = bandwidth # in bits per second
    self.propagationdelay = propagationdelay # in usecs, for WAN
    self.probframeloss = probframeloss
    self.probframecorrupt = probframecorrupt
