"""Pinned 31-way ownership and independently selectable codec recipes."""
import hashlib
import struct
import sys
import unittest
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'host'))
import z8_wlm_native_recipes as recipes
from z8_native_capsule import _recipe

class NativeRecipes(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  if not (ROOT/'inputs/z8-c311-main.bin').is_file() or not (ROOT/'vendor/NikonFirmwarePatch-features/features.py').is_file():
   raise unittest.SkipTest('requires local stock MAIN and the pinned feature toolkit')
  cls.stock=(ROOT/'inputs/z8-c311-main.bin').read_bytes()
 def test_masks(self):
  for value in (0,32,-1,True,1.0,'1'):
   with self.assertRaises(ValueError):recipes.selected(value)
 def test_all_31_ownership_and_legacy_exact_projection(self):
  unique={};shared={};legacy=0
  for mask in range(1,32):
   with self.subTest(mask=mask):
    result=recipes.compose_recipe(self.stock,mask)
    names=set(recipes.selected(mask))
    self.assertTrue(set(w.owner for w in result.windows)<=names|{'shared.locale','shared.menu','shared.quality','foundation.reserve-only'})
    end=0
    for w in result.windows:
     self.assertGreaterEqual(w.offset,end);end=w.offset+len(w.new)
     self.assertEqual(self.stock[w.offset:end],w.old)
    for owner in names:
     rows=recipes.component_windows(result,owner)
     digest=hashlib.sha256(b''.join(struct.pack('<QI',w.address,len(w.new))+w.old+w.new for w in rows)).hexdigest()
     if owner in unique:self.assertEqual(digest,unique[owner],owner+' changed when unrelated plugin installed')
     else:unique[owner]=digest
    for owner,selector in (('shared.menu',mask&15),('shared.quality',mask&6)):
     rows=recipes.component_windows(result,owner)
     if not rows:continue
     digest=hashlib.sha256(b''.join(struct.pack('<QI',w.address,len(w.new))+w.new for w in rows)).hexdigest()
     key=(owner,selector)
     if key in shared:self.assertEqual(digest,shared[key])
     else:shared[key]=digest
    for name,va in (('prores',0x40a00000),('h265',0x40a10000)):
     present=any(w.address==va for w in result.windows)
     self.assertEqual(present,name in names)
    if result.detail['menu']:
     self.assertEqual(result.detail['menu']['count'],44+int('h265'in names))
    # All original legal combinations remain byte-identical after reversing
    # only the explicitly reviewed five-bit shared-bank ABI adaptation.
    if bool(mask&2)==bool(mask&4):
     oldmask=(mask&1)|(2 if mask&6 else 0)|(4 if mask&8 else 0)|(8 if mask&16 else 0)
     old,_,_=_recipe(self.stock,oldmask)
     reverted=bytearray(result.image)
     if mask&15:
      reverted[0x4098005c-recipes.BASE:0x40980060-recipes.BASE]=bytes.fromhex('0c011036')
      reverted[0x40980070-recipes.BASE:0x40980074-recipes.BASE]=bytes.fromhex('6c000836')
      struct.pack_into('<I',reverted,0x40980f00-recipes.BASE,(mask&1)|(2 if mask&6 else 0)|(4 if mask&8 else 0))
     self.assertEqual(hashlib.sha256(reverted).digest(),hashlib.sha256(old).digest())
     legacy+=1
  self.assertEqual(legacy,15)
  self.assertEqual(set(unique),set(recipes.COMPONENTS))
  self.assertEqual(len([k for k in shared if k[0]=='shared.menu']),15)
  self.assertEqual(len([k for k in shared if k[0]=='shared.quality']),3)
 def test_stock_identity_guard(self):
  changed=bytearray(self.stock);changed[0]^=1
  with self.assertRaises(ValueError):recipes.compose_recipe(changed,2)

if __name__=='__main__':unittest.main()
