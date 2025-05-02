from enum import IntEnum

class NLTableEntry:
  def __init__(self, address: int):
    self.address = address
    self.ackexpected = 0
    self.nextpackettosend = 0
    self.packetexpected = 0
    self.minhops = (2 ** 32) - 1 # minimum known hops to remote node
    self.minhop_link = 0 # link via which minhops path observed

class NLTable:
  ALL_LINKS = (2 ** 32) - 1

  def __init__(self):
    self.table = {} # address -> NLTableEntry
  
  def find_address(self, address: int):
    if address not in self.table:
      self.table[address] = NLTableEntry(address)
    return self.table[address]
  
  def ackexpected(self, address: int):
    entry = self.find_address(address)
    return entry.ackexpected

  def nextpackettosend(self, address: int):
    entry = self.find_address(address)
    return entry.nextpackettosend

  def packetexpected(self, address: int):
    entry = self.find_address(address)
    return entry.packetexpected

  def inc_ackexpected(self, address: int):
    entry = self.find_address(address)
    entry.ackexpected = entry.ackexpected + 1

  def inc_nextpackettosend(self, address: int):
    entry = self.find_address(address)
    entry.nextpackettosend = entry.nextpackettosend + 1

  def inc_packetexpected(self, address: int):
    entry = self.find_address(address)
    entry.packetexpected = entry.packetexpected + 1

  def linksofminhops(self, address: int):
    entry = self.find_address(address)
    if entry.minhop_link:
      return 1 << entry.minhop_link
    else:
      return NLTable.ALL_LINKS

  def savehopcount(self, address: int, hops: int, link: int):
    entry = self.find_address(address)
    if hops < entry.minhops:
      entry.minhops = hops
      entry.minhop_link = link
