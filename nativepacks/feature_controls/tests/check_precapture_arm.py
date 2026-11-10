"""Actual original constructor versus late P capsule compensation on AArch64.
Only native mutex boundaries and host staging allocation are modeled. No camera.
The table has a 4-byte global prefix; each real slot starts at base+4+slot*f98.
"""
import argparse,hashlib,json,struct,sys
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_MEM_WRITE
import unicorn.arm64_const as a
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'host'))
import z8_native_capsule as c
BANK=0xa03bddd20;STRIDE=0xf98;TABLE=48*STRIDE+4;STOP=0x70000000;ALLOC=STOP+0x100;RELEASE=STOP+0x200;API=0x71000000;OUT=API+0x100;HEAP=0x72000000;STACK=0xa30000000
REGS=[getattr(a,'UC_ARM64_REG_X'+str(i))for i in range(31)]
class Machine:
 def __init__(self,image):
  self.u=Uc(UC_ARCH_ARM64,UC_MODE_ARM);self.u.mem_map(c.BASE,(len(image)+4095)&~4095);self.u.mem_write(c.BASE,image)
  for p,n in [(STOP,4096),(API,4096),(HEAP,0x20000),(STACK,65536),(0xa03bd0000,0x70000),(0xa04841000,4096)]:self.u.mem_map(p,n)
  for p in (ALLOC,RELEASE):self.u.mem_write(p,bytes.fromhex('c0035fd6'))
  self.u.hook_add(UC_HOOK_CODE,self.hook);self.phase='construction';self.external_writes=[];self.cache=[];self.dsb=0;self.mutex=[];self.allocations=0;self.releases=0;self.u.hook_add(UC_HOOK_MEM_WRITE,self.write,begin=BANK,end=BANK+TABLE-1)
 def ret(self,n=0):self.u.reg_write(a.UC_ARM64_REG_X0,n);self.u.reg_write(a.UC_ARM64_REG_PC,self.u.reg_read(a.UC_ARM64_REG_X30))
 def hook(self,u,pc,n,_):
  if pc in (0x40d2c674,0x40d2c660):self.mutex.append(pc);self.ret(1 if pc==0x40d2c674 else 0);return
  if pc==ALLOC:self.allocations+=1;self.allocation_bytes=u.reg_read(a.UC_ARM64_REG_X1);assert self.allocation_bytes<0x20000;self.ret(HEAP);return
  if pc==RELEASE:self.releases+=1;self.ret();return
  word=struct.unpack('<I',bytes(u.mem_read(pc,4)))[0]
  if word&0xffffffe0==0xd53b0020:
   u.reg_write(REGS[word&31],4<<16);u.reg_write(a.UC_ARM64_REG_PC,pc+4);return
  if word&0xffffffe0==0xd50b7a20:self.cache.append(u.reg_read(REGS[word&31]));assert self.phase=='publish'
  if word==0xd5033f9f and self.phase=='publish':self.dsb+=1
 def write(self,u,access,address,size,value,_):
  if self.phase=='construction':return
  assert self.phase=='publish','stage/abort wrote external native state';self.external_writes.append((address,size,value))
 def call(self,fn,*args):
  for reg in REGS:self.u.reg_write(reg,0)
  for reg,value in zip(REGS,args):self.u.reg_write(reg,value)
  self.u.reg_write(a.UC_ARM64_REG_SP,STACK+0x8000);self.u.reg_write(a.UC_ARM64_REG_X30,STOP);self.u.emu_start(fn,STOP,count=4000000);assert self.u.reg_read(a.UC_ARM64_REG_PC)==STOP,'bounded ARM return';return self.u.reg_read(a.UC_ARM64_REG_X0)
 def read(self,p,n):return bytes(self.u.mem_read(p,n))
 def constructor(self,slot):
  for index in range(slot):self.u.mem_write(BANK+index*STRIDE+0x18,struct.pack('<I',1))
  self.call(0x4086e900,0x408643d4);assert self.mutex==[0x40d2c674,0x40d2c660];self.mutex=[]
 def pack(self,metadata):
  self.m=json.loads(metadata.read_text());elf=Path(self.m['elf']).read_bytes()
  for s in self.m['segments']:self.u.mem_write(s['va'],elf[s['file_offset']:s['file_offset']+s['file_bytes']])
  self.u.mem_write(API,struct.pack('<IIQQQQ',1,40,0,ALLOC,RELEASE,0));self.phase='stage'
 def stage(self):
  result=self.call(self.m['entry'],API,OUT);assert not self.mutex and not self.external_writes
  if result==0:self.exports=struct.unpack('<IIIIQQQQQ',self.read(OUT,56))
  else:assert self.read(OUT,56)==bytes(56) and self.releases==1,'failed entry never exposes descriptors'
  return result
 def event(self,op):
  self.phase='publish' if op==6 else 'abort';r=self.call(self.exports[7],self.exports[6],op);self.phase='idle';return r

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--controls',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args();stock=c.read_main(ROOT/'inputs/z8-c311-main.bin');early,_,_=c._recipe(stock,15);cases=[]
 for slot in (0,7,47):
  old=Machine(stock);old.constructor(slot);expected=Machine(early);expected.constructor(slot);before=old.read(BANK,TABLE);target=expected.read(BANK+slot*STRIDE,STRIDE+4);old.pack(args.controls);assert old.stage()==0 and old.read(BANK,TABLE)==before
  assert old.event(6)==0;after=old.read(BANK,TABLE);assert after[slot*STRIDE:slot*STRIDE+STRIDE+4]==target
  diff=[i for i,(x,y)in enumerate(zip(before,after))if x!=y];assert diff==[slot*STRIDE+0x18,slot*STRIDE+0xdc,slot*STRIDE+0xdd]
  assert old.external_writes==[(BANK+slot*STRIDE+0xdc,1,0x73),(BANK+slot*STRIDE+0xdd,1,1),(BANK+slot*STRIDE+0x18,4,9)]
  assert set(old.cache)=={(BANK+slot*STRIDE+0x18)&~63,(BANK+slot*STRIDE+0xdc)&~63} and len(old.cache)==2 and old.dsb==1
  writes=list(old.external_writes);cache=list(old.cache);assert old.event(6)==0 and writes==old.external_writes and cache==old.cache
  cases.append(dict(slot=slot,original_constructor_vs_late_publish_exact=True,changed_bytes=[hex(i-slot*STRIDE)for i in diff],stores=[dict(offset=hex(address-BANK-slot*STRIDE),bytes=n,value=v)for address,n,v in writes],dc_cvac_lines=[hex(x)for x in cache],DSB_SY=1,allocation_bytes=old.allocation_bytes))
 # An exact early-initialized 9-event state is accepted without any write/clean.
 already=Machine(stock);expected=Machine(early);expected.constructor(7);already.u.mem_write(BANK,expected.read(BANK,TABLE));already.pack(args.controls);assert already.stage()==0;before=already.read(BANK,TABLE);assert already.event(6)==0 and already.read(BANK,TABLE)==before and not already.external_writes and not already.cache
 abort=Machine(stock);abort.constructor(7);abort.pack(args.controls);before=abort.read(BANK,TABLE);assert abort.stage()==0 and abort.event(5)==0 and abort.read(BANK,TABLE)==before and not abort.external_writes and abort.releases==1
 bad=[]
 for kind in ('none','duplicate','bitmap','old_bitmap_count9','partial_count','header','constructor','registration'):
  v=Machine(stock)
  if kind!='none':v.constructor(7)
  slot=BANK+7*STRIDE
  if kind=='duplicate':v.u.mem_write(BANK+12*STRIDE+4,v.read(slot+4,STRIDE))
  if kind=='bitmap':v.u.mem_write(slot+0x1c+800,b'\x01')
  if kind=='old_bitmap_count9':v.u.mem_write(slot+0x18,struct.pack('<I',9))
  if kind=='partial_count':v.u.mem_write(slot+0x18,bytes(4))
  if kind=='header':v.u.mem_write(slot+4,b'\x01')
  if kind in ('constructor','registration'):
   at=0x4086e900 if kind=='constructor' else 0x41013ca0;v.u.mem_write(at,bytes([v.read(at,1)[0]^1]))
  v.pack(args.controls);before=v.read(BANK,TABLE);assert v.stage()!=0 and v.read(BANK,TABLE)==before and not v.external_writes and not v.cache;bad.append(kind)
 # Non-atomic read-only physical sample: preserve every unrelated byte/slot.
 physical=ROOT/'build/native-capsules-20261106/root/physical-dcf-registry.bin';physical_case=None
 if physical.is_file():
  blob=physical.read_bytes();assert len(blob)==48*STRIDE;v=Machine(stock);v.u.mem_write(BANK,blob);v.pack(args.controls);assert v.stage()==0;assert v.event(6)==0;after=v.read(BANK,len(blob));differences=[i for i,(x,y)in enumerate(zip(blob,after))if x!=y];assert differences==[12*STRIDE+0x18,12*STRIDE+0xdc,12*STRIDE+0xdd];physical_case=dict(file=str(physical.relative_to(ROOT)),sha256=c.sha(blob),slot=12,changed_offsets=[hex(x)for x in differences],non_atomic_read_only_capture=True)
 report=dict(schema='fenestra.precapture-subscription-arm/v1',passed=True,controls_elf_sha256=json.loads(args.controls.read_text())['elf_sha256'],cases=cases,rejected=bad,abort_no_external_write=True,exact_new9_idempotent=True,physical_case=physical_case,native_mutex_boundary_model=True,production_publish_before_cpu_release='independently covered by adapter/rendezvous fixture',no_camera=True)
 args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
