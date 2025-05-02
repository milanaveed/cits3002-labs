from enum import IntEnum

class Event(IntEnum):
  NULL = 0
  REBOOT = 1
  SHUTDOWN = 2
  PHYSICALREADY = 3
  APPLICATIONREADY = 4
  FRAMECOLLISION = 5
  DEBUG0 = 6
  TIMER0 = 7
  TIMER1 = 8
  TIMER2 = 9
  TIMER3 = 10
  TIMER4 = 11
  TIMER5 = 12
  TIMER6 = 13
  PERIODIC = 14

class NodeType(IntEnum):
  HOST = 0
  MOBILE = 1

class LinkType(IntEnum):
  LOOPBACK = 0
  WAN = 1
  LAN = 2
  WLAN = 3

class LinkInfo:
  def __init__(self, linktype, bandwidth, propagationdelay, probframeloss, probframecorrupt):
    self.linktype = linktype
    self.linkup = True
    self.bandwidth = bandwidth # in bits per second
    self.propagationdelay = propagationdelay # in usecs, for WAN
    self.probframeloss = probframeloss
    self.probframecorrupt = probframecorrupt
    self.rx_from = 0 # simulator usecs
    self.rx_until = 0 # simulator usecs
    self.tx_until = 0 # simulator usecs
