"""Strict ELF/input contracts for independently updateable native components."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'host'))
from build_wlm_native_components import read_component_elf,window_patch
from z8_wlm_native_recipes import OwnedWindow

class ComponentInputs(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.directory=ROOT/'build/native-wlm-controls-20261106/final/components/prores'
  if not (cls.directory/'controls.elf').is_file():
   raise unittest.SkipTest('local native components have not been built')
  cls.blob=(cls.directory/'controls.elf').read_bytes();cls.metadata=json.loads((cls.directory/'controls.json').read_text())
 def test_actual_seven_independent_elfs(self):
  for component in ('framing','prores','h265','log_colour','photo_tools','bridge','locale'):
   directory=self.directory.parent/component
   parsed=read_component_elf((directory/'controls.elf').read_bytes(),'shared.movie'if component=='bridge'else'shared.locale'if component=='locale'else component,json.loads((directory/'controls.json').read_text()))
   self.assertTrue(parsed['entry']);self.assertTrue(parsed['exports'])
 def test_metadata_digest_feature_symbol_and_exports_tampering(self):
  mutations=(lambda m:m.update(elf_sha256='0'*64),lambda m:m.update(features5=4),lambda m:m['symbols'].update(fx_native_pack_entry=0),lambda m:m['exports'][0].update(name='another.plugin'))
  for mutate in mutations:
   m=copy.deepcopy(self.metadata);mutate(m)
   with self.assertRaises(ValueError):read_component_elf(self.blob,'prores',m)
 def test_elf_wrong_slot_wx_and_relocations(self):
  with self.assertRaises(ValueError):read_component_elf(self.blob,'h265',self.metadata)
  phoff=struct.unpack_from('<Q',self.blob,32)[0];phnum=struct.unpack_from('<H',self.blob,56)[0]
  wx=bytearray(self.blob)
  for i in range(phnum):
   at=phoff+56*i
   if struct.unpack_from('<I',wx,at)[0]==1:struct.pack_into('<I',wx,at+4,7);break
  with self.assertRaises(ValueError):read_component_elf(wx,'prores',self.metadata)
  reloc=bytearray(self.blob);shoff=struct.unpack_from('<Q',reloc,40)[0];shnum=struct.unpack_from('<H',reloc,60)[0]
  for i in range(shnum):
   at=shoff+64*i
   if struct.unpack_from('<I',reloc,at+4)[0]==1 and struct.unpack_from('<Q',reloc,at+32)[0]:struct.pack_into('<I',reloc,at+4,4);break
  with self.assertRaises(ValueError):read_component_elf(reloc,'prores',self.metadata)
 def test_embedded_dependency_must_match_not_only_json_digest(self):
  m=copy.deepcopy(self.metadata);raw=bytearray(self.blob);address=m['symbols']['fx_wlm_dependency']
  for segment in m['segments']:
   if segment['va']<=address<segment['va']+segment['file_bytes']:
    at=segment['file_offset']+address-segment['va'];raw[at+72]^=4;break
  m['elf_sha256']=hashlib.sha256(raw).hexdigest()
  for segment in m['segments']:
   data=bytes(raw[segment['file_offset']:segment['file_offset']+segment['file_bytes']]);segment['sha']=hashlib.sha256(data).hexdigest();segment['memory_sha256']=hashlib.sha256(data+bytes(segment['memory_bytes']-len(data))).hexdigest()
  with self.assertRaisesRegex(ValueError,'embedded dependency differs'):read_component_elf(raw,'prores',m)
 def test_native_count_hook_is_forbidden(self):
  offset=0x4b13000+0xa0281cd5c-0xa02808000
  with self.assertRaisesRegex(ValueError,'accepted-count'):window_patch(OwnedWindow(offset,b'\xff\xff\0\0',b'\x99\x0c\0\0','shared.locale','forbidden count regression'))

if __name__=='__main__':unittest.main()
