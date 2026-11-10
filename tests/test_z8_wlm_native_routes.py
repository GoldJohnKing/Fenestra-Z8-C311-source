"""Execute actual split shared-bank and quality route instructions, no QEMU."""
import binascii
import struct
import sys
import unittest
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'host'))
from z8_feature_suite import checked_upstream
from z8_wlm_native_recipes import shared_video_code,quality_part,_unit,BASE
from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm64_const import *

class NativeRoutes(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  if not (ROOT/'inputs/z8-c311-main.bin').is_file() or not (ROOT/'vendor/NikonFirmwarePatch-features/features.py').is_file():
   raise unittest.SkipTest('requires local stock MAIN and the pinned feature toolkit')
  checked_upstream();cls.bank,_=shared_video_code()
  cls.stock=(ROOT/'inputs/z8-c311-main.bin').read_bytes()
  cls.eg=cls.stock+binascii.crc_hqx(cls.stock,0).to_bytes(2,'big')
  cls.original,cls.entries=_unit('quality')
 def test_all_31_bank_masks_execute_exact_extra_bytes(self):
  for mask in range(1,32):
   for item in (0x120b,0x122c,0x1238,0x1257,0x9999):
    with self.subTest(mask=mask,item=hex(item)):
     uc=Uc(UC_ARCH_ARM64,UC_MODE_ARM)
     for at,n in ((0x40980000,4096),(0x41016000,4096),(0x100000,16384)):uc.mem_map(at,n)
     uc.mem_write(0x40980000,self.bank);uc.mem_write(0x40980f00,struct.pack('<I',mask))
     source=bytes(range(0x30,0x40));before=bytes([0xa5])*16
     uc.mem_write(0x100000,source);uc.mem_write(0x100100,before)
     uc.reg_write(UC_ARM64_REG_SP,0x103000);uc.mem_write(0x103000,struct.pack('<QQ',0x100100,0x100000))
     uc.reg_write(UC_ARM64_REG_X20,0xfeed0000|item)
     uc.reg_write(UC_ARM64_REG_X12,0x123456789abcdef0);uc.reg_write(UC_ARM64_REG_X13,0x1fedcba987654321)
     def stop(m,a,n,user):
      if a==0x410162f0:m.emu_stop()
     uc.hook_add(UC_HOOK_CODE,stop);uc.emu_start(0x40980000,0,count=100)
     expected=bytearray(before)
     if item==0x120b:
      if mask&2:expected[1]=source[1]
      if mask&1:expected[3]=source[3]
     elif item==0x122c and mask&1:expected[1]=source[1]
     elif item==0x1238 and mask&8:expected[1]=source[1]
     elif item==0x1257 and mask&4:expected[1]=source[1]
     self.assertEqual(uc.reg_read(UC_ARM64_REG_PC),0x410162f0)
     self.assertEqual(bytes(uc.mem_read(0x100100,16)),bytes(expected))
     self.assertEqual(uc.reg_read(UC_ARM64_REG_SP),0x103000)
     self.assertEqual(uc.reg_read(UC_ARM64_REG_X12),0x123456789abcdef0)
     self.assertEqual(uc.reg_read(UC_ARM64_REG_X13),0x1fedcba987654321)
 def test_quality_routes_keep_absent_codec_stock_even_with_spare_ds(self):
  filetype,tier,grade=struct.unpack_from('<3Q',self.original,0x3a0)
  # Native map tables from the pinned compiled unit, not invented icon IDs.
  pair_h=struct.unpack_from('<HH',self.original,self.entries['tier_star_pairs']-0x40a41000)
  pair_p=struct.unpack_from('<HH',self.original,self.entries['tier_hq_pairs']-0x40a41000)
  for p,h in ((True,False),(False,True),(True,True)):
   edits,_=quality_part(self.eg,p,h,0,0)
   code=next(e['new']for e in edits if e['offset']==0x40a41000-BASE)
   for codec,pair,enabled in ((2,pair_h,h),(3,pair_h,h),(4,pair_p,p)):
    for route,start,stop in ((0,0x40a41000,0x40325d4c),(1,0x40a41090,0x4032dc68),(2,0x40a41150,0x4032dd38)):
     with self.subTest(prores=p,h265=h,codec=codec,route=route):
      uc=Uc(UC_ARCH_ARM64,UC_MODE_ARM);pages={0x40a41000,0x40325000,0x4032d000,0x100000,0x101000,0x102000}
      pages.update(a&~4095 for a in (filetype,tier,grade))
      for a in pages:uc.mem_map(a,4096)
      uc.mem_write(0x40a41000,code);uc.mem_write(filetype,struct.pack('<I',codec));uc.mem_write(tier,b'\x01');uc.mem_write(grade,b'\x04')
      # grade 4 has zero low two bits: HQ is eligible even with nonzero state.
      uc.reg_write(UC_ARM64_REG_SP,0x102800);uc.reg_write(UC_ARM64_REG_LR,0x101000)
      uc.mem_write(0x100000,struct.pack('<I',pair[0]));uc.reg_write(UC_ARM64_REG_X1,0x100100);uc.reg_write(UC_ARM64_REG_X2,0x100200)
      if route==0:uc.reg_write(UC_ARM64_REG_W1,1);uc.reg_write(UC_ARM64_REG_W2,pair[0])
      elif route==1:uc.reg_write(UC_ARM64_REG_X0,0x100000)
      else:uc.reg_write(UC_ARM64_REG_W0,pair[0])
      def halt(m,a,n,user):
       if a in (stop,0x101000):m.emu_stop()
      uc.hook_add(UC_HOOK_CODE,halt);uc.emu_start(start,0,count=1000)
      if route==0:actual=uc.reg_read(UC_ARM64_REG_W2)
      elif route==1:actual=struct.unpack('<I',uc.mem_read(0x100000,4))[0]
      else:actual=uc.reg_read(UC_ARM64_REG_W0)
      self.assertEqual(actual,pair[1]if enabled else pair[0])

if __name__=='__main__':unittest.main()
