import struct
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from ttarch_patch import pack


class PatchArchiveTests(unittest.TestCase):
    def test_native_header_sorted_table_and_payload_bounds(self):
        entries={"z.lenc":b"cipher-z", "_system.lenc":b"cipher-bootstrap", "a.lenc":b"cipher-a"}
        data=pack(entries)
        version,encrypted,kind,mode,chunks,size,index_size=struct.unpack_from("<7I",data)
        self.assertEqual((version,encrypted,kind,mode,chunks),(3,0,2,1,0))
        self.assertEqual(size,len(data)-28-index_size)
        dirs,length=struct.unpack_from("<II",data,28)
        self.assertEqual((dirs,length,data[36:37]),(1,1,b"."))
        count=struct.unpack_from("<I",data,37)[0]; cursor=41; names=[]
        for _ in range(count):
            length=struct.unpack_from("<I",data,cursor)[0]; cursor+=4
            name=data[cursor:cursor+length].decode();cursor+=length
            zero,offset,size=struct.unpack_from("<III",data,cursor);cursor+=12
            self.assertEqual(zero,0)
            self.assertEqual(data[28+index_size+offset:28+index_size+offset+size],entries[name])
            names.append(name)
        self.assertEqual(names,sorted(entries,key=str.lower))
        self.assertEqual(cursor,28+index_size)

    def test_rejects_nested_paths(self):
        with self.assertRaises(ValueError): pack({"../_system.lenc":b"invalid"})
