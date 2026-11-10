"""Execute the independent component AArch64 code in Unicorn, never a camera.
The original GUI/RTOS functions, heap, named registry and MOV body are synthetic.
This verifies actual pack callbacks and exact hook assembly, not physical media.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm64_const import *
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'nativepacks/wlm_controls'))
import build
REGS=[UC_ARM64_REG_X0,UC_ARM64_REG_X1,UC_ARM64_REG_X2,UC_ARM64_REG_X3,UC_ARM64_REG_X4,UC_ARM64_REG_X5,UC_ARM64_REG_X6,UC_ARM64_REG_X7]
ALLREGS=[UC_ARM64_REG_X0,UC_ARM64_REG_X1,UC_ARM64_REG_X2,UC_ARM64_REG_X3,UC_ARM64_REG_X4,UC_ARM64_REG_X5,UC_ARM64_REG_X6,UC_ARM64_REG_X7,UC_ARM64_REG_X8,UC_ARM64_REG_X9,UC_ARM64_REG_X10,UC_ARM64_REG_X11,UC_ARM64_REG_X12,UC_ARM64_REG_X13,UC_ARM64_REG_X14,UC_ARM64_REG_X15,UC_ARM64_REG_X16,UC_ARM64_REG_X17,UC_ARM64_REG_X18]
STOP,ALLOC,RELEASE,LOOKUP=0x70000000,0x70000100,0x70000200,0x70000300
API,OUT,COOKIE,REQUEST,REPLY=0x71000000,0x71000100,0x71000200,0x71000400,0x71000800
HEAP,STACK=0x72000000,0x73000000
RET=bytes.fromhex('c0035fd6')
PROVIDERS={'framing':'camera.video.framing','prores':'camera.video.prores','h265':'camera.video.h265','log_colour':'camera.video.log_colour','photo_tools':'camera.photo.tools'}

class Harness:
 def __init__(self,metas,mask):
  self.mask=mask;self.metas=metas;self.u=Uc(UC_ARCH_ARM64,UC_MODE_ARM);self.exports={};self.symbols={};self.next_heap=HEAP
  self.stats=dict(allocations=0,releases=0,lookup=0,gets=0,sets=0,republishes=0,upstream_closes=0,stock_closes=0)
  self.callbacks={};self.calls={};self.close_result=0;self.lookup_error=None;self.stop_at_open_resume=False;self.fail_allocate=False;self.misaligned_allocate=False
  self.u.mem_map(0x408d0000,0x70000)
  self.chosen=[name for name,bit in build.FEATURES.items() if mask&bit]+['locale','bridge']
  for name in self.chosen:
   m=metas[name];elf=Path(m['elf']).read_bytes();assert hashlib.sha256(elf).hexdigest()==m['elf_sha256']
   for s in m['segments']: self.u.mem_write(s['va'],elf[s['file_offset']:s['file_offset']+s['file_bytes']])
   if name in build.FEATURES:
    self.callbacks[m['symbols']['fx_wlm_movie_open']]=name+'.open';self.callbacks[m['symbols']['fx_wlm_movie_close']]=name+'.close'
  for a,n in [(STOP,4096),(API,4096),(HEAP,1048576),(STACK,65536),(0xa03d5c000,4096),(0xa0ffed000,12288),
              (0xa03203000,16384),(0x410d5000,4096),(0x403ec000,4096),(0x4086e000,4096),(0x41013000,4096),
              (0xa03bd0000,0x50000),(0x40a41000,4096),(0x40960000,4096),(0x40cee000,4096),(0x40ceb000,4096)]:self.u.mem_map(a,n)
  stock=(ROOT/'inputs/z8-c311-main.bin').read_bytes();assert hashlib.sha256(stock).hexdigest()=='2b43a31c9de838f84b12416de4348a7004e65be07f853ec56ec2b10f3a8e3853'
  for a,n in [(0x4086e900,0x70),(0x41013ca0,0x150)]:self.u.mem_write(a,stock[a-0x40160000:a-0x40160000+n])
  self.slot=0xa03bddd20+7*0xf98;self.u.mem_write(self.slot+8,struct.pack('<Q',0x408703b4));self.u.mem_write(self.slot+0x14,struct.pack('<II',0x04320000,5))
  bitmap=bytearray(0xf80)
  for ident in (0x601,0x2000688,0x6000689,0x200172a,0x2000600):bitmap[((ident>>8)&255)*32+((ident>>3)&31)]|=1<<(ident&7)
  self.u.mem_write(self.slot+0x1c,bytes(bitmap))
  for a in (STOP,ALLOC,RELEASE,LOOKUP,0x410d5ec8,0x403ec398,0x403ec39c,0x40a41250,0x40960870):self.u.mem_write(a,RET)
  self.u.hook_add(UC_HOOK_CODE,self.hook)
  self.u.mem_write(API,struct.pack('<IIQQQQ',1,40,0,ALLOC,RELEASE,LOOKUP))
 def read(self,a,n):return bytes(self.u.mem_read(a,n))
 def cstring(self,a):return self.read(a,64).split(b'\0')[0].decode('ascii')
 def hook(self,u,address,size,data):
  if address in self.callbacks:
   name=self.callbacks[address];self.calls[name]=self.calls.get(name,0)+1
  if address==ALLOC:
   count=u.reg_read(UC_ARM64_REG_X1);assert u.reg_read(UC_ARM64_REG_X2)==16 and count<=4096
   self.stats['allocations']+=1;p=self.next_heap;self.next_heap=(p+count+15)&~15;u.reg_write(UC_ARM64_REG_X0,0 if self.fail_allocate else p+int(self.misaligned_allocate))
  elif address==RELEASE:self.stats['releases']+=1
  elif address==LOOKUP:
   name=self.cstring(u.reg_read(UC_ARM64_REG_X1));version=u.reg_read(UC_ARM64_REG_X2);target=u.reg_read(UC_ARM64_REG_X3)
   self.stats['lookup']+=1;assert version==1
   value=self.symbols.get(name,0);u.mem_write(target,struct.pack('<Q',value));u.reg_write(UC_ARM64_REG_X0,self.lookup_error if self.lookup_error is not None else 0 if value else 3)
  elif address in (0x410d5ec8,0x403ec398):self.stats['gets']+=1;u.reg_write(UC_ARM64_REG_X0,30)
  elif address==0x403ec39c:
   self.stats['sets']+=1
   if u.reg_read(UC_ARM64_REG_X0)==0x05001261:u.mem_write(0xa03d5c290,struct.pack('<I',u.reg_read(UC_ARM64_REG_X1)))
   u.reg_write(UC_ARM64_REG_X0,1)
  elif address==0x40a41250:self.stats['republishes']+=1
  elif address==0x40960870:self.stats['upstream_closes']+=1;u.reg_write(UC_ARM64_REG_X0,self.close_result)
  elif address==0x40ceef14:
   # Synthetic remainder of the original MOV close after its displaced STR.
   # Only models stack restoration and result; original function is not tested.
   self.stats['stock_closes']+=1;sp=u.reg_read(UC_ARM64_REG_SP);u.reg_write(UC_ARM64_REG_X20,struct.unpack('<Q',self.read(sp,8))[0]);u.reg_write(UC_ARM64_REG_SP,sp+32)
   u.reg_write(UC_ARM64_REG_X0,self.close_result);u.reg_write(UC_ARM64_REG_PC,u.reg_read(UC_ARM64_REG_LR))
  elif address==0x40cebe40 and self.stop_at_open_resume:u.emu_stop()
 def call(self,fn,*args):
  for r in REGS:self.u.reg_write(r,0)
  for r,v in zip(REGS,args):self.u.reg_write(r,v)
  self.u.reg_write(UC_ARM64_REG_LR,STOP);self.u.reg_write(UC_ARM64_REG_SP,STACK+65520)
  self.u.emu_start(fn,STOP,count=4000000)
  assert self.u.reg_read(UC_ARM64_REG_PC)==STOP,'instruction budget exceeded'
  return self.u.reg_read(UC_ARM64_REG_X0)
 def stage(self,name,expected=0):
  result=self.call(self.metas[name]['entry'],API,OUT);assert result==expected,(name,result,expected)
  if result:return None
  abi,size,np,ns,providers,symbols,context,event,pending=struct.unpack('<IIIIQQQQQ',self.read(OUT,56));assert (abi,size)==(1,56)
  seen=[]
  for i in range(ns):
   b=self.read(symbols+i*80,80);key=b[:64].split(b'\0')[0].decode();version,flags,address=struct.unpack_from('<IIQ',b,64)
   assert version==1 and key not in self.symbols;self.symbols[key]=address;seen.append(key)
  state=dict(context=context,event=event,pending=pending,symbols=seen,providers=[])
  for i in range(np):
   b=self.read(providers+i*104,104);key=b[:64].split(b'\0')[0].decode();version,kind,abi,caps,where,flags,fn,ctx=struct.unpack_from('<IIIIIIQQ',b,64)
   assert (version,kind,abi,where,flags)==(1,4,4,1,0);state['providers'].append(dict(name=key,fn=fn,context=ctx,cookie=COOKIE+8*list(build.FEATURES).index(name),token=100+build.FEATURES[name]))
  assert np==int(name in build.FEATURES)
  if np:assert state['providers'][0]['name']==PROVIDERS[name]
  self.exports[name]=state;return state
 def stage_all(self):
  for name in self.chosen:self.stage(name)
  assert self.stats['gets']==self.stats['sets']==0 and self.stats['lookup']==11
 def event(self,name,op):
  e=self.exports[name];return self.call(e['event'],e['context'],op)
 def pending(self,name):
  e=self.exports[name];return self.call(e['pending'],e['context'])
 def op(self,name,op,command=0,data=b'',owner=7,token=None):
  p=self.exports[name]['providers'][0];self.u.mem_write(REQUEST,struct.pack('<4I4Q',1,22,1,len(data),0,0,command,0)+data+bytes(768-len(data)));self.u.mem_write(REPLY,bytes(816))
  return self.call(p['fn'],p['context'],op,owner,p['token'] if token is None else token,p['cookie'],REQUEST if op==3 else 0,REPLY if op==3 else 0)
 def publish(self):
  before=self.stats['allocations']
  for name in self.chosen:assert self.event(name,6)==0
  assert self.stats['allocations']==before
  assert struct.unpack('<I',self.read(self.slot+0x18,4))[0]==(9 if self.mask&16 else 5)
 def open_hook(self,context):
  vals=[0x1000+i for i in range(19)];vals[8]=context
  for r,v in zip(ALLREGS,vals):self.u.reg_write(r,v)
  self.u.reg_write(UC_ARM64_REG_X19,HEAP+0xf0000);self.u.reg_write(UC_ARM64_REG_LR,STOP);self.u.reg_write(UC_ARM64_REG_SP,STACK+65520);self.u.reg_write(UC_ARM64_REG_NZCV,0xa0000000)
  self.stop_at_open_resume=True;self.u.emu_start(self.metas['bridge']['symbols']['fx_wlm_video_open_hook'],STOP,count=4000000);self.stop_at_open_resume=False
  assert self.u.reg_read(UC_ARM64_REG_PC)==0x40cebe40
  assert [self.u.reg_read(r) for r in ALLREGS]==vals
  assert self.u.reg_read(UC_ARM64_REG_LR)==STOP and self.u.reg_read(UC_ARM64_REG_SP)==STACK+65520 and self.u.reg_read(UC_ARM64_REG_NZCV)==0xa0000000
  assert struct.unpack('<Q',self.read(HEAP+0xf0000,8))[0]==context
 def close_hook(self,context,result):
  self.close_result=result;self.u.reg_write(UC_ARM64_REG_X19,0x19191919);self.u.reg_write(UC_ARM64_REG_X20,0x20202020)
  seen=self.call(self.metas['bridge']['symbols']['fx_wlm_video_close_hook'],context)
  assert seen==result and self.u.reg_read(UC_ARM64_REG_X19)==0x19191919 and self.u.reg_read(UC_ARM64_REG_SP)==STACK+65520
  assert self.u.reg_read(UC_ARM64_REG_X20)==0x20202020

def check_metadata(metas):
 for name,m in metas.items():
  assert m['fixed_base']==build.BASES[name] and m['limit']==build.BASES[name]+65536
  symbols=m['symbols']
  if name!='framing':assert not any(n.startswith('fx_framing_') for n in symbols)
  if name!='photo_tools':assert not any(n.startswith(('fx_photo_tools_','fx_controls_photo_','fx_controls_precapture_')) for n in symbols)
  if name not in ('prores','h265','log_colour'):assert 'fx_suite_video_resource' not in symbols
  if name in ('bridge','locale'):assert not any(n.startswith(('fx_suite_video_','fx_framing_','fx_photo_tools_')) for n in symbols)
 return True

def check_mask(metas,mask):
 h=Harness(metas,mask);h.stage_all()
 for name in h.chosen:
  if name in build.FEATURES:assert h.op(name,1)==2
 h.publish()
 for name in h.chosen:
  if name not in build.FEATURES:continue
  assert h.op(name,1)==0;assert h.op(name,3)==0
  assert struct.unpack_from('<I',h.read(REPLY,48),8)[0]>0
  if name in ('prores','h265','log_colour'):
   value={'prores':3,'h265':4,'log_colour':2}[name];assert h.op(name,3,1,struct.pack('<4I',1,16,value,0))==0
   assert h.op(name,3,1,struct.pack('<4I',1,16,value+1,0))==1
  elif name=='framing':assert h.op(name,3,1,struct.pack('<4I',1,16,0,1))==0
 assert h.stats['republishes']==int(bool(mask&2))+int(bool(mask&4))
 assert h.stats['gets']==int(bool(mask&1))*3+int(bool(mask&16))*3
 h.open_hook(0x12345678)
 for name in h.chosen:
  if name not in build.FEATURES:continue
  assert h.pending(name)
  if name in ('prores','h265','log_colour'):assert h.op(name,3,1,struct.pack('<4I',1,16,0,0))==5
  elif name=='framing':assert h.op(name,3,1,struct.pack('<4I',1,16,0,0))==5
  else:assert h.op(name,3,1,struct.pack('<4I',1,16,0,0x4d455247))==5
  assert h.event(name,2)==5
 # Failed original close must not dispatch any close callback.
 h.close_hook(0x12345678,1)
 for name in h.chosen:
  if name in build.FEATURES:assert h.calls.get(name+'.close',0)==0 and h.pending(name)
 h.close_hook(0x12345678,0)
 expected_original='upstream_closes' if mask&1 else 'stock_closes'
 assert h.stats[expected_original]==2 and h.stats['stock_closes' if mask&1 else 'upstream_closes']==0
 for name in h.chosen:
  if name in build.FEATURES:
   assert h.calls[name+'.open']==h.calls[name+'.close']==1 and not h.pending(name)
   assert h.event(name,2)==0 and h.event(name,4)==5
   assert h.op(name,2)==0 and h.event(name,4)==0 and h.event(name,4)==0
  assert h.event(name,5)==5 if name!='locale' else h.event(name,5)==0
 if mask&16:
  assert h.op('photo_tools',1)==0
  assert h.op('photo_tools',3,1,struct.pack('<4I',1,16,0,0x4d455247))==0 and h.pending('photo_tools')
  assert h.event('photo_tools',2)==0 and not h.pending('photo_tools')
  assert h.op('photo_tools',2)==0 and h.event('photo_tools',4)==0
 return dict(mask=mask,components=h.chosen,providers=[PROVIDERS[n] for n in h.chosen if n in PROVIDERS],stats=h.stats,
             passed=True,exact_hook_register_preservation=True,original_close_exactly_once_per_call=True)

def check_negatives(metas):
 results=[]
 for name in ('one_open_missing','one_close_missing','framing_original_missing','orphan_framing_original','lookup_argument','empty'):
  mask=1 if name in ('framing_original_missing','one_open_missing','one_close_missing') else 2
  h=Harness(metas,mask)
  for feature in h.chosen:
   if feature!='bridge':h.stage(feature)
  if name=='one_open_missing':del h.symbols['controls.movie_open.framing']
  elif name=='one_close_missing':del h.symbols['controls.movie_close.framing']
  elif name=='framing_original_missing':del h.symbols['controls.movie_close_original.framing']
  elif name=='orphan_framing_original':h.symbols['controls.movie_close_original.framing']=0x40960870
  elif name=='lookup_argument':h.lookup_error=1
  else:h.symbols.clear()
  before=h.stats['allocations'];h.stage('bridge',3 if name=='empty' else 10);assert h.stats['allocations']==before
  results.append(dict(case=name,passed=True,no_allocation=True))
 # An unpublished component can be aborted and staged again; published cannot.
 h=Harness(metas,31)
 for name in h.chosen:
  before=h.stats['releases'];h.stage(name);assert h.event(name,5)==0
  assert h.stats['releases']==before+int(name!='locale')
  for symbol in h.exports[name]['symbols']:del h.symbols[symbol]
  del h.exports[name];h.stage(name)
 # Re-staging has intentionally separate synthetic registry descriptors.
 results.append(dict(case='unpublished_abort_reclaims_state',passed=True))
 for feature,bit in build.FEATURES.items():
  h=Harness(metas,bit);h.stage_all();h.publish();assert h.op(feature,1)==0
  assert h.op(feature,3,owner=8)==6 and h.op(feature,3,token=999)==6
  h.open_hook(0x123);h.open_hook(0x123);h.close_hook(0x123,0)
  assert h.pending(feature) and h.event(feature,2)==5 and h.event(feature,4)==5 and h.event(feature,5)==5
  results.append(dict(case=feature+'_stale_lease_and_ambiguous_movie_fail_closed',passed=True))
 for feature,bit in build.FEATURES.items():
  h=Harness(metas,bit);h.fail_allocate=True;h.stage(feature,4);assert h.stats['releases']==0
  h.fail_allocate=False;h.misaligned_allocate=True;h.stage(feature,10);assert h.stats['releases']==1
  h.misaligned_allocate=False;h.stage(feature);assert h.event(feature,5)==0
  results.append(dict(case=feature+'_allocation_and_alignment_fail_closed',passed=True))
 h=Harness(metas,31)
 for feature in h.chosen:
  if feature!='bridge':h.stage(feature)
 h.fail_allocate=True;h.stage('bridge',4);h.fail_allocate=False;h.misaligned_allocate=True;h.stage('bridge',10)
 assert h.stats['releases']==1
 h.misaligned_allocate=False;h.stage('bridge');assert h.event('bridge',5)==0
 results.append(dict(case='bridge_allocation_and_alignment_fail_closed',passed=True))
 return results

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--skip-build',action='store_true');args=ap.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
 if not args.skip_build:subprocess.run([sys.executable,str(ROOT/'nativepacks/wlm_controls/build.py'),'--component','all','--out',str(out/'components')],cwd=ROOT,check=True,capture_output=True,text=True,timeout=90)
 sys.path.insert(0,str(ROOT/'host'));from z8_native_capsule import pinned_native_text_layout
 locale=pinned_native_text_layout(15)
 if not args.skip_build:subprocess.run([sys.executable,str(ROOT/'nativepacks/wlm_controls/build.py'),'--component','locale','--out',str(out/'components/locale'),'--text-count',str(locale['text_count']),'--languages',str(locale['languages']),'--offsets-directory',hex(locale['offsets_directory']),'--pools-directory',hex(locale['pools_directory'])],cwd=ROOT,check=True,capture_output=True,text=True,timeout=60)
 metas={name:json.loads((out/'components'/name/'controls.json').read_text(encoding='utf-8')) for name in build.BASES};assert check_metadata(metas)
 masks=[]
 for mask in range(1,32):masks.append(check_mask(metas,mask));print(json.dumps(dict(mask=mask,passed=True)),flush=True)
 negatives=check_negatives(metas)
 sources={str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in [*ROOT.glob('nativepacks/wlm_controls/*.c'),*ROOT.glob('nativepacks/wlm_controls/*.h'),*ROOT.glob('nativepacks/wlm_controls/*.S'),*ROOT.glob('nativepacks/wlm_controls/*.ld'),ROOT/'nativepacks/wlm_controls/build.py',Path(__file__)]}
 result=dict(schema=1,passed=True,arm_masks=masks,negative_cases=negatives,source_sha256=sources,components={n:dict(elf_sha256=m['elf_sha256'],entry=m['entry'],features5=m['features5']) for n,m in metas.items()},
             no_camera=True,original_functions='synthetic GUI/RTOS/native MOV body; actual independent pack callbacks and hook assembly',
             limitations=['Unicorn is not full-system QEMU or a physical camera','No original recording, codec, media, DMA/cache/SMP or sensor qualification'])
 (out/'checks.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(dict(passed=True,masks=len(masks),negative_cases=len(negatives),report=str(out/'checks.json'))))

if __name__=='__main__':main()
