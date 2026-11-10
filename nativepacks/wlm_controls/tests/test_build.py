"""Focused host validation for independent component bounds and descriptors."""
import importlib.util
from pathlib import Path
import struct
import unittest
MODULE=Path(__file__).resolve().parents[1]/'build.py'
spec=importlib.util.spec_from_file_location('wlm_controls_build',MODULE);build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)

def fixture(*,perm=5,va=0x408d0000,memsz=16,entry=None):
 raw=bytearray(144);raw[:7]=b'\x7fELF\x02\x01\x01'
 struct.pack_into('<HHIQQQIHHHHHH',raw,16,2,183,1,va if entry is None else entry,64,0,0,64,56,1,64,0,0)
 struct.pack_into('<IIQQQQQQ',raw,64,1,perm,128,va,va,16,memsz,16)
 return bytes(raw)

class BuildValidation(unittest.TestCase):
 def test_five_independent_bits_and_disjoint_slots(self):
  self.assertEqual(sorted(build.FEATURES.values()),[1,2,4,8,16]);self.assertEqual(len(set(build.BASES.values())),7)
  for base in build.BASES.values():self.assertGreaterEqual(base,0x408d0000);self.assertLessEqual(base+65536,0x40950000)
 def test_dependency_exports_are_unique(self):
  self.assertEqual(len({v[0] for v in build.DEPENDENCIES.values()}),4)
  self.assertEqual(build.DEPENDENCIES['prores'][1],build.DEPENDENCIES['h265'][1])
 def test_own_slot_exec_segment(self):
  entry,segments=build.load_segments(fixture(),0x408d0000);self.assertEqual(entry,0x408d0000);self.assertEqual(segments[0]['memory_bytes'],16)
 def test_reject_writable_executable(self):
  with self.assertRaises(ValueError):build.load_segments(fixture(perm=7),0x408d0000)
 def test_reject_adjacent_slot(self):
  with self.assertRaises(ValueError):build.load_segments(fixture(va=0x408e0000),0x408d0000)
 def test_reject_crossing_slot(self):
  with self.assertRaises(ValueError):build.load_segments(fixture(memsz=65537),0x408d0000)
 def test_reject_nonexec_entry(self):
  with self.assertRaises(ValueError):build.load_segments(fixture(entry=0x408d1000),0x408d0000)
 def test_exact_locale_dimensions_and_pointers(self):
  valid=dict(languages=36,text_count=3225,offsets_directory=0x40e00000,pools_directory=0x40e00120);build.validate_locale(valid)
  for key,value in [('languages',35),('text_count',0),('text_count',8193),('offsets_directory',0),('offsets_directory',0x1001),('pools_directory',2**64),('text_count',True)]:
   with self.subTest(key=key,value=value),self.assertRaises(ValueError):build.validate_locale(dict(valid,**{key:value}))
  with self.assertRaises(ValueError):build.validate_locale(dict(valid,extra=1))

if __name__=='__main__':unittest.main()
