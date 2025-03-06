from random import random

CORRUPTION_RATE = 0.25

def crc16(data: bytes):
    xor_in = 0x0000  # initial value
    xor_out = 0x0000  # final XOR value
    poly = 0x8005  # generator polinom (normal form)

    reg = xor_in
    for octet in data:
        # reflect in
        for i in range(8):
            topbit = reg & 0x8000
            if octet & (0x80 >> i):
                topbit ^= 0x8000
            reg <<= 1
            if topbit:
                reg ^= poly
        reg &= 0xFFFF
        # reflect out
    return reg ^ xor_out


def corrupt_data(data : bytes):
    '''
    some random corruption of byte data
    modify as needed, mostly the CORRUPTION_RATE global constant
    ''' 
    temp = data[:]
    while True:
        location = int(len(temp) * random())
        data_list = list(temp)
        if random() < 0.5:
            data_list[location] = (data_list[location] + 1) % 256
        else: 
            data_list[location] = (data_list[location] - 1) % 256
        temp = bytes(data_list)
        if random() < CORRUPTION_RATE and temp != data:
            break
    return temp

##usecase for crc16 function
#data = b"helloworld"
#print(crc16(data))

##usecase for corrupt_data function
#corrupt_data(b"helloworld")