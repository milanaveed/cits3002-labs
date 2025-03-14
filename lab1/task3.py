from random import random

CORRUPTION_RATE = 0.25

def crc16(data: bytes):
    '''CRC is an error-detecting code used to check the integrity of data. It processes a sequence of bytes and computes a checksum, which can be compared to a received checksum to detect errors.'''
    xor_in = 0x0000  # initial value
    xor_out = 0x0000  # final XOR value
    poly = 0x8005  # generator polinom (normal form)

    reg = xor_in # reg is the 16-bit register that will store the CRC result. It is initialized with the value of xor_in.
    for octet in data: # iterate over each byte (8 bit chunk) in the input data
        # reflect in
        for i in range(8): # iterate over each bit in the current byte
            topbit = reg & 0x8000 # extract the leftmost bit
            if octet & (0x80 >> i): # 0x80 >> i creates a mask where only the i-th bit is set.
                # octet & (0x80 >> i) checks if the i-th bit of octet is 1
                topbit ^= 0x8000 # Each hex digit corresponds to 4 binary bits. 0x80 is 10000000 in binary. The >> operator shifts the bits to the right by the specified number of positions. If the bit at position i is 1, the topbit is XORed with 0x8000.
            reg <<= 1 # Shifts reg left by 1 bit (equivalent to multiplying by 2).
            if topbit:
                reg ^= poly # If the most significant bit (MSB) was 1, perform a XOR with the polynomial (0x8005).
        reg &= 0xFFFF # Keep only the lowest 16 bits (ensures 16-bit CRC)
        # reflect out
    return reg ^ xor_out


def corrupt_data(data : bytes):
    '''
    some random corruption of byte data
    modify as needed, mostly the CORRUPTION_RATE global constant
    ''' 
    temp = data[:] #creates a shallow copy of data to avoid modifying the original input directly.
    while True: #keeps modifying the data until the corruption rate condition is met
        location = int(len(temp) * random()) # random() generates a float between 0 and 1 
        # len(temp) * random() selects a random index within the byte data
        #int() ensures we get a valid integer index
        data_list = list(temp) #bytes in Python are immutable, so we convert them into a mutable list before modifying them
        if random() < 0.5:
            data_list[location] = (data_list[location] + 1) % 256
        else: 
            data_list[location] = (data_list[location] - 1) % 256
        temp = bytes(data_list)
        if random() < CORRUPTION_RATE and temp != data: #Ensures at least one byte is changed before stopping
            break
    return temp #Returns the modified (corrupted) byte data

##usecase for crc16 function
#data = b"helloworld"
#print(crc16(data))

##usecase for corrupt_data function
#corrupt_data(b"helloworld")