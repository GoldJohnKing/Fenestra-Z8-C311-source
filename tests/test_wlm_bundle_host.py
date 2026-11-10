"""Host WLM4 corruption and capacity checks; no device or native invocation."""
import hashlib
from pathlib import Path
import struct
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'host'))
from wlm_bundle import encode_bundle,decode_bundle,summary,HEADER,COMPONENT,LIMIT,MAX_COMPONENTS
from wlm_native import encode_component
from z8_native_capsule import encode,Patch,IMAGE,EXEC
from z8_native_profile import STOCK_SHA256
TARGET=bytes.fromhex(STOCK_SHA256)

def frontend(version=3,extra=0):
 data=bytearray(156+extra);data[:8]=b'FENESTRA';struct.pack_into('<4I',data,8,version,128,1,1);data[24:56]=TARGET
 struct.pack_into('<5IQ',data,88,len(data),4096,0,1,0,0);struct.pack_into('<I',data,116,1)
 if version==3:struct.pack_into('<2I',data,120,32768,4096)
 struct.pack_into('<6I',data,128,0,152,4,4096,5,4096);data[152:156]=bytes.fromhex('c0035fd6');data[56:88]=hashlib.sha256(data[128:]).digest()
 return bytes(data)

def component(name='prores',bit=2,version=1):
 capsule=encode([Patch(IMAGE,EXEC,0x408e0000,bytes(4),bytes.fromhex('c0035fd6'))],1,7,0x408e0000)
 return encode_component(name,version,bit,11,[dict(mask=0,value=0,capsule=capsule)],target=TARGET,requires_id=7)

def body_hash(data):
 data[56:88]=hashlib.sha256(data[HEADER:]).digest();return bytes(data)

def changed(blob,offset,value,fmt='<I',rehash=False):
 data=bytearray(blob);struct.pack_into(fmt,data,offset,value);return body_hash(data) if rehash else bytes(data)

class BundleHostTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.front=frontend();cls.native=component();cls.shared=component('shared.movie',0);cls.blob=encode_bundle(cls.front,'prores',[cls.native,cls.shared],TARGET)
 def assertBad(self,blob,**kwargs):
  with self.assertRaises(ValueError):decode_bundle(blob,**kwargs)
 def test_roundtrip_v2_and_v3(self):
  for version in (2,3):
   with self.subTest(version=version):
    front=frontend(version);blob=encode_bundle(front,'prores',[self.native,self.shared],TARGET);parsed=decode_bundle(blob,module_id='prores',target=TARGET)
    self.assertEqual(parsed['frontend'],front);self.assertEqual([x['data'] for x in parsed['components']],[self.native,self.shared]);self.assertEqual([x['flags'] for x in parsed['components']],[0,1])
    self.assertEqual(parsed['frontend_offset'],HEADER+2*COMPONENT);self.assertEqual(parsed['components'][0]['offset'],HEADER+2*COMPONENT+len(front));self.assertEqual(parsed['components'][-1]['offset']+parsed['components'][-1]['bytes'],len(blob))
    self.assertEqual(summary(parsed)['component_count'],2)
 def test_empty_component_directory(self):
  parsed=decode_bundle(encode_bundle(self.front,'demo',[],TARGET));self.assertEqual(parsed['components'],[]);self.assertEqual(parsed['frontend_offset'],HEADER)
 def test_metadata_and_raw_component_agree(self):
  parsed=decode_bundle(self.blob);self.assertEqual(parsed['module_id'],'prores');self.assertEqual(parsed['target'],TARGET)
  for row in parsed['components']:self.assertEqual(row['sha256'],hashlib.sha256(row['data']).hexdigest())
 def test_wrong_expected_target_or_filename(self):
  self.assertBad(self.blob,target=bytes(32));self.assertBad(self.blob,module_id='h265');self.assertBad(self.blob,target=b'x')
 def test_encoder_requires_canonical_module_id(self):
  for name in ('','A','shared.movie','a/b','a b','a'*16):
   with self.subTest(name=name),self.assertRaises(ValueError):encode_bundle(self.front,name,[],TARGET)
 def test_directory_component_ids_can_include_dot_and_uppercase(self):
  parsed=decode_bundle(encode_bundle(self.front,'demo',[component('Shared.movie',0)],TARGET));self.assertEqual(parsed['components'][0]['id'],'Shared.movie')
 def test_header_identity_padding_and_reserved(self):
  for offset in (92,168,191):
   data=bytearray(self.blob);data[offset]=1;self.assertBad(bytes(data))
  data=bytearray(self.blob);data[159]=0;data[160]=ord('x');self.assertBad(bytes(data))
 def test_header_version_abi_isa_size_and_native_abi(self):
  for at,value in [(8,3),(12,128),(16,2),(20,2),(88,len(self.blob)+1),(148,2)]:
   with self.subTest(at=at):self.assertBad(changed(self.blob,at,value))
 def test_complete_body_and_inner_frontend_hashes(self):
  bad=bytearray(self.blob);bad[-1]^=1;self.assertBad(bytes(bad))
  bad=bytearray(self.blob);bad[104]^=1;self.assertBad(bytes(bad))
  bad=bytearray(self.blob);off=struct.unpack_from('<I',bad,96)[0];bad[off+56]^=1;bad[104:136]=hashlib.sha256(bad[off:off+len(self.front)]).digest();self.assertBad(body_hash(bad))
 def test_frontend_target_and_service_entry(self):
  for offset in (24,116):
   bad=bytearray(self.front);bad[offset]^=1
   with self.subTest(offset=offset),self.assertRaises(ValueError):encode_bundle(bytes(bad),'demo',[],TARGET)
 def test_frontend_rejects_v1_and_recursive_v4(self):
  with self.assertRaises(ValueError):encode_bundle(frontend(1),'demo',[],TARGET)
  with self.assertRaises(ValueError):encode_bundle(self.blob,'demo',[],TARGET)
 def test_frontend_capacity_exact_one_mib_and_oversize(self):
  maximum=frontend(extra=1024*1024-156);parsed=decode_bundle(encode_bundle(maximum,'demo',[],TARGET));self.assertEqual(parsed['frontend_bytes'],1024*1024)
  with self.assertRaises(ValueError):encode_bundle(frontend(extra=1024*1024-155),'demo',[],TARGET)
 def test_stack_and_segment_validation(self):
  bad=bytearray(self.front);struct.pack_into('<I',bad,120,32769)
  with self.assertRaises(ValueError):encode_bundle(bytes(bad),'demo',[],TARGET)
  bad=bytearray(self.front);struct.pack_into('<I',bad,144,7);bad[56:88]=hashlib.sha256(bad[128:]).digest()
  with self.assertRaises(ValueError):encode_bundle(bytes(bad),'demo',[],TARGET)
 def test_directory_stride_table_count_and_front_extent(self):
  for at,value in [(136,200),(140,33),(144,80),(96,HEADER),(100,128),(100,1024*1024+1),(100,len(self.blob))]:
   with self.subTest(at=at,value=value):self.assertBad(changed(self.blob,at,value))
 def test_directory_version_unknown_flags_and_extent(self):
  for at,value in [(HEADER+16,0),(HEADER+20,2),(HEADER+24,0),(HEADER+28,0),(HEADER+24,len(self.blob)),(HEADER+28,len(self.blob))]:
   with self.subTest(at=at,value=value):self.assertBad(changed(self.blob,at,value,rehash=True))
 def test_directory_cannot_disagree_with_inner_id_version_or_shared_flag(self):
  for at,value in [(HEADER+16,2),(HEADER+20,1),(HEADER+COMPONENT+20,0)]:
   with self.subTest(at=at):self.assertBad(changed(self.blob,at,value,rehash=True))
  bad=bytearray(self.blob);bad[HEADER:HEADER+16]=b'h265'.ljust(16,b'\0');self.assertBad(body_hash(bad))
 def test_component_target_and_payload_validation(self):
  for inner_offset in (72,104,148):
   bad=bytearray(self.blob);off,n=struct.unpack_from('<2I',bad,HEADER+24);bad[off+inner_offset]^=1;bad[HEADER+32:HEADER+64]=hashlib.sha256(bad[off:off+n]).digest();self.assertBad(body_hash(bad))
 def test_duplicate_component_ids_rejected_even_if_equal(self):
  with self.assertRaises(ValueError):encode_bundle(self.front,'prores',[self.native,self.native],TARGET)
  bad=bytearray(self.blob);bad[HEADER+COMPONENT:HEADER+COMPONENT+16]=bad[HEADER:HEADER+16];self.assertBad(body_hash(bad))
 def test_component_checksum_is_independent_from_outer_hash(self):
  bad=bytearray(self.blob);bad[-1]^=1;self.assertBad(body_hash(bad))
  bad=bytearray(self.blob);bad[HEADER+32]^=1;self.assertBad(body_hash(bad))
 def test_hidden_tail_is_rejected_even_with_valid_hash_and_size(self):
  bad=bytearray(self.blob+b'\0');struct.pack_into('<I',bad,88,len(bad));self.assertBad(body_hash(bad))
 def test_hidden_gap_between_frontend_and_components_is_rejected(self):
  off=struct.unpack_from('<I',self.blob,HEADER+24)[0];bad=bytearray(self.blob[:off]+b'\0'+self.blob[off:]);struct.pack_into('<I',bad,88,len(bad))
  for row in range(2):
   at=HEADER+row*COMPONENT+24;struct.pack_into('<I',bad,at,struct.unpack_from('<I',bad,at)[0]+1)
  self.assertBad(body_hash(bad))
 def test_components_cannot_overlap_frontend_or_each_other(self):
  front=struct.unpack_from('<I',self.blob,96)[0];self.assertBad(changed(self.blob,HEADER+24,front,rehash=True))
  first=struct.unpack_from('<I',self.blob,HEADER+24)[0];self.assertBad(changed(self.blob,HEADER+COMPONENT+24,first,rehash=True))
 def test_truncation_and_outer_limit(self):
  for n in (0,8,127,191,len(self.blob)-1):self.assertBad(self.blob[:n])
  self.assertBad(bytes(LIMIT+1))
 def test_component_count_capacity(self):
  values=[component('lib'+str(i),0) for i in range(MAX_COMPONENTS)];parsed=decode_bundle(encode_bundle(self.front,'demo',values,TARGET));self.assertEqual(parsed['component_count'],32)
  with self.assertRaises(ValueError):encode_bundle(self.front,'demo',values+[component('overflow',0)],TARGET)
 def test_byte_input_and_target_width(self):
  for value in ('not bytes',None):
   with self.assertRaises(ValueError):decode_bundle(value)
  with self.assertRaises(ValueError):encode_bundle(self.front,'demo',[],bytes(31))
  with self.assertRaises(ValueError):encode_bundle(self.front,'demo',[b'broken'],TARGET)

if __name__=='__main__':unittest.main()
