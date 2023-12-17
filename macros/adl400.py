#!/usr/bin/python3
import struct
import pymodbus.client.serial
import pymodbus.exceptions
import binascii
import time
import sys
values = {}
     
def read_double_bulk (client, lregs ):
    bulklen=(lregs[len(lregs)-1][1]-lregs[0][1]+2)
    #print ("Bulklen: " +str(bulklen))
    try:
        resp = client.read_holding_registers(lregs[0][1],count=bulklen, unit=24)
        if (resp.function_code >= int('0x80',16)):
           print ("Received error code %",resp.function_code)
           return
        print(str(resp.registers))

        global values
        i=0
        regcounter=0
        increment=0

        while i < len(lregs):
           #print ("i: " + str(i) + " regcounter: " +str(regcounter) + " getRegister: " + str(resp.getRegister(regcounter)))
           print (f"i: %d, content: %s" %  ( i, str(resp.getRegister(regcounter))))
           print (f"i+1: %d, content: %s" %  ( i+1, str(resp.getRegister(regcounter+1))))
           value=struct.unpack('>i',struct.pack('>HH',resp.getRegister(regcounter),resp.getRegister(regcounter+1)))
           print (f" Struct: %d" % value)
           values[lregs[i][0]]=int(''.join(map(str, value)))#/(10**lregs[i][3])
           if i<len(lregs)-1:
               increment = lregs[i+1][1]-lregs[i][1]
               #print ("calculated increment: " + str(increment))
           else:
               increment=2
               #print ("static increment: " + str(increment))
           regcounter+=increment
           i=i+1
        print (values)
    except Exception as e:
        print(e)
        print ("Exception occured.Waiting 3 sec to stabilize")
        time.sleep(3)



        #print ("i: " +str(i) + "; " + "index: "+ str(increment) +"; " +str(resp.getRegister(increment)/(10**lregs[increment][3])))
        #values[lregs[i][0]]=resp.getRegister(i)/(10**lregs[i][3])
     #index = 0
     #for reg in lregs:
     #   values[reg[0]]=resp.getRegister(index + lregs[len(lregs)-1][1]-lregs[index][1])/reg[3]
     #   index += 1
     #print ("Myvalues" +str(values))
def read_float_reg(client, basereg, precission) :
    resp = client.read_holding_registers(basereg,count=1,slave=24, unit=24)
    if resp == None :
        return None
    # according to spec, each pair of registers returned
    # encodes a IEEE754 float where the first register carries
    # the most significant 16 bits, the second register carries the 
    # least significant 16 bits.
    #return None
    print (resp.registers)
    #print (resp.getRegister(0))
    #print (resp.getRegister(1))
    #print (resp.getRegister(2))
    #print (resp.getRegister(3))
    #print (resp.getRegister(4))
    #print (resp.getRegister(5))
    #print (resp.getRegister(6))
    #print (resp.getRegister(7))
    #print (resp.getRegister(8))
    #print (resp.getRegister(9))
    #print (resp.getRegister(20))
    #s_tmp = struct.pack('>HHHHHHHHHHHHHHHHHHHHHHH',*resp.registers )
    s_tmp = struct.pack('>H',*resp.registers )
    print (repr(s_tmp))
    #print ("size: "  + str(struct.calcsize (s_tmp)))
    #return struct.unpack('>f',struct.pack('>HH',*resp.registers )) #registers
    return struct.unpack('>h',s_tmp) #registers

def fmt_or_dummy(regfmt,val) :
    if val is None :
        return '.'*len(regfmt[2]%(0))
    return regfmt[2]%(val)

def main() :
    regs = [
        # Symbol    Reg#  Format
         ( 'Va'     ,0x61, '%6.1f',1 ), # Voltage Phase A [V]
         ( 'Vb'     ,0x62, '%6.1f',1 ), # Voltage Phase B [V]
         ( 'Vc'     ,0x63, '%6.1f',1 ), # Voltage Phase C [V]
         ( 'Ca'     ,0x64, '%6.2f',2), # Current Phase A[A]
         ( 'Cb'     ,0x65, '%6.2f',2 ), # Current Phase B[A]
         ( 'Cc'     ,0x66, '%6.2f',2 ), # Current Phase C[A]
         ( 'Pa[act]',0x67, '%6.3f',3 ), # Active Power ("Wirkleistung") Phase A [W]
         ( 'Pb[act]',0x68, '%6.3f',3 ), # Active Power ("Wirkleistung") Phase B [W]
         ( 'Pc[act]',0x69, '%6.3f',3 ), # Active Power ("Wirkleistung") Phase C [W]
         ( 'P[act]' ,0x6A, '%6.3f',3 ), # Active Power ("Wirkleistung") Total [W]
         ( 'Freq'   ,0x77, '%6.2f',2 )  # Line Frequency [Hz]         

    ]

    double_regs = [
        # Symbol    Reg#  Format
         ( 'Pa_compl'     ,0x164, '%6.1f',1 ), # Active Power with complement
         ( 'Pb_compl'     ,0x166, '%6.1f',1 ), # Active Power with complement
         ( 'Pc_compl'     ,0x168, '%6.1f',1 ), # Active Power with complement
         ( 'P_compl'     ,0x16A, '%6.1f',1 ), # Active Total Power with complement
    ] 
    # if client is set to odd or even parity, set stopbits to 1
    # if client is set to 'none' parity, set stopbits to 2
    
    cl = pymodbus.client.ModbusSerialClient(
        port='/dev/ttyUSB0', baudrate=1200, parity='N',stopbits=1,
        timeout=1)

    N=0
    while True :
        N += 1
        if N % 16 == 1 :
            print('#        '+(' '.join(['%-7s'%(x[0]) for x in double_regs])))
            print('#        '+(':'.join(['-------'        for x in double_regs])))


        read_double_bulk(cl,double_regs)
        #values = [ read_float_reg(cl, reg[1],  reg[2] ) for reg in regs ]
        #print ("Values"+str(values))
        tstr=time.strftime('%H:%M:%S ')
        #print(tstr+(' '.join([fmt_or_dummy(*t) for t in zip(regs, values)])))
        #print(tuple(zip(regs, values)))
        
        sys.stdout.flush()
        time.sleep(1)

if __name__ == '__main__' :
	main()

