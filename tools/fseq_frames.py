"""Read zstd FSEQ v2 frames, including sparse ranges and extended headers."""
from pathlib import Path
import ctypes,ctypes.util,struct
ZSTD=ctypes.CDLL(ctypes.util.find_library('zstd'))
ZSTD.ZSTD_decompress.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t]
ZSTD.ZSTD_decompress.restype=ctypes.c_size_t

def read_frames(path,total_channels=None):
    data=Path(path).read_bytes()
    assert data[:4]==b'PSEQ' and data[7]==2
    channels,frames=struct.unpack_from('<II',data,10)
    count=data[21]+((data[20]>>4)<<8)
    offset=struct.unpack_from('<H',data,4)[0]
    assert data[20]&15==1,('Expected zstd compression',path)
    blocks=[struct.unpack_from('<II',data,32+8*i) for i in range(count)]
    blocks=[block for block in blocks if block[1]]
    ranges=[]
    for i in range(data[22]):
        pos=32+8*count+6*i
        ranges.append((int.from_bytes(data[pos:pos+3],'little'),int.from_bytes(data[pos+3:pos+6],'little')))
    if not ranges:ranges=[(0,channels)]
    assert sum(length for _,length in ranges)==channels
    size=total_channels or max(start+length for start,length in ranges)
    contiguous=ranges==[(0,size)]
    yielded=0
    for i,(first,length) in enumerate(blocks):
        assert first==yielded
        last=blocks[i+1][0] if i+1<len(blocks) else frames
        capacity=(last-first)*channels
        out=ctypes.create_string_buffer(capacity)
        assert ZSTD.ZSTD_decompress(out,capacity,data[offset:offset+length],length)==capacity
        offset+=length
        raw=out.raw
        for j in range(last-first):
            packed=raw[j*channels:(j+1)*channels]
            if contiguous:yield packed
            else:
                expanded=bytearray(size);pos=0
                for start,length in ranges:
                    expanded[start:start+length]=packed[pos:pos+length];pos+=length
                yield bytes(expanded)
            yielded+=1
    assert yielded==frames
    # FSEQ 2.2 can append metadata after the compressed channel data.
    pos=struct.unpack_from('<H',data,8)[0];extended=[]
    data_offset=struct.unpack_from('<H',data,4)[0]
    while pos+4<=data_offset:
        length=struct.unpack_from('<H',data,pos)[0]
        if not length:break
        assert length>=4 and pos+length<=data_offset
        if data[pos+2:pos+4]==b'ED':
            start,length_ext=struct.unpack_from('<QI',data,pos+6)
            assert start>=offset and start+length_ext<=len(data)
            extended.append((start,length_ext))
        pos+=length
    assert offset==len(data) or (extended and max(a+b for a,b in extended)==len(data))
