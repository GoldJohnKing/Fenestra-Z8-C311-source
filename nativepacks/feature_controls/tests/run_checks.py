"""Build all 15 EL1 subsets; verify entry/leases/lifecycle on actual ARM code.
Original RTOS/GUI functions are synthetic return stubs in Unicorn. No camera.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3, UC_ARM64_REG_X4, UC_ARM64_REG_X5, UC_ARM64_REG_X6, UC_ARM64_REG_X7, UC_ARM64_REG_LR, UC_ARM64_REG_SP, UC_ARM64_REG_PC
ROOT = Path(__file__).resolve().parents[3]
PACK = ROOT / 'nativepacks/feature_controls'
LLVM = Path('C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Tools/Llvm/x64/bin')
REGS = [UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3, UC_ARM64_REG_X4, UC_ARM64_REG_X5, UC_ARM64_REG_X6, UC_ARM64_REG_X7]


def arm_check(metadata):
    m = json.loads(metadata.read_text(encoding='utf-8')); image = Path(m['elf']).read_bytes()
    u = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    for s in m['segments']:
        base, end = s['va'] & ~4095, (s['va'] + s['memory_bytes'] + 4095) & ~4095
        u.mem_map(base, end - base); u.mem_write(s['va'], image[s['file_offset']:s['file_offset'] + s['file_bytes']])
    STOP, ALLOC, RELEASE = 0x70000000, 0x70000100, 0x70000200
    API, OUT, COOKIE, REQUEST, REPLY = 0x71000000, 0x71000100, 0x71000200, 0x71000400, 0x71000800
    HEAP, STACK = 0x72000000, 0x73000000
    for a, n in [(STOP,4096),(API,4096),(HEAP,65536),(STACK,65536),
                 (0xa03d5c000,4096),(0xa0ffed000,12288),(0xa03203000,16384),
                 (0x410d5000,4096),(0x403ec000,4096),(0x4086e000,4096),(0x41013000,4096),(0xa03bd0000,0x50000)]: u.mem_map(a,n)
    stock=(ROOT/'inputs/z8-c311-main.bin').read_bytes();assert hashlib.sha256(stock).hexdigest()=='2b43a31c9de838f84b12416de4348a7004e65be07f853ec56ec2b10f3a8e3853'
    u.mem_write(0x4086e900,stock[0x4086e900-0x40160000:0x4086e970-0x40160000]);u.mem_write(0x41013ca0,stock[0x41013ca0-0x40160000:0x41013df0-0x40160000])
    slot=0xa03bddd20+7*0xf98;u.mem_write(slot+8,struct.pack('<Q',0x408703b4));u.mem_write(slot+0x14,struct.pack('<II',0x04320000,5))
    bitmap=bytearray(0xf80)
    for ident in (0x601,0x2000688,0x6000689,0x200172a,0x2000600):bitmap[((ident>>8)&255)*32+((ident>>3)&31)]|=1<<(ident&7)
    u.mem_write(slot+0x1c,bytes(bitmap))
    ret = bytes.fromhex('c0035fd6')
    for a in (STOP,ALLOC,RELEASE,0x410d5ec8,0x403ec398,0x403ec39c): u.mem_write(a,ret)
    stats = dict(allocations=0,releases=0,native_gets=0,native_sets=0,allocation_bytes=0)
    def hook(emu, address, size, data):
        if address == ALLOC:
            assert emu.reg_read(UC_ARM64_REG_X2) == 16
            stats['allocations'] += 1; stats['allocation_bytes'] = emu.reg_read(UC_ARM64_REG_X1)
            assert stats['allocation_bytes'] <= 4096
            emu.reg_write(UC_ARM64_REG_X0, HEAP)
        elif address == RELEASE: stats['releases'] += 1
        elif address in (0x410d5ec8,0x403ec398):
            stats['native_gets'] += 1; emu.reg_write(UC_ARM64_REG_X0,30)
        elif address == 0x403ec39c: stats['native_sets'] += 1; emu.reg_write(UC_ARM64_REG_X0,1)
    u.hook_add(UC_HOOK_CODE,hook)
    def call(fn,*args):
        for r in REGS: u.reg_write(r,0)
        for r,v in zip(REGS,args): u.reg_write(r,v)
        u.reg_write(UC_ARM64_REG_LR,STOP);u.reg_write(UC_ARM64_REG_SP,STACK+65520)
        u.emu_start(fn,STOP,count=4000000)
        assert u.reg_read(UC_ARM64_REG_PC)==STOP, 'ARM instruction budget exceeded'
        return u.reg_read(UC_ARM64_REG_X0)
    u.mem_write(API,struct.pack('<IIQQQQ',1,40,0,ALLOC,RELEASE,0))
    assert call(m['entry'],API,OUT)==0
    assert stats['allocations']==1 and stats['native_gets']==stats['native_sets']==0
    abi,size,count,ns,providers,symbols,context,event,pending=struct.unpack('<IIIIQQQQQ',bytes(u.mem_read(OUT,56)))
    expected=[]
    if m['features']&2: expected+=['camera.video.prores','camera.video.h265']
    if m['features']&4: expected+=['camera.video.log_colour']
    if m['features']&1: expected+=['camera.video.framing']
    if m['features']&8: expected+=['camera.photo.tools']
    assert (abi,size,count,ns)==(1,56,len(expected),5+len(m['dependencies']))
    locale_export=bytes(u.mem_read(symbols+(ns-1)*80,80))
    assert locale_export==bytes(u.mem_read(m['symbols']['fx_controls_locale_export'],80))
    assert locale_export[:64].split(b'\0')[0]==b'camera.locale.text'
    locale_version,locale_flags,locale_address=struct.unpack_from('<IIQ',locale_export,64)
    assert (locale_version,locale_flags,locale_address)==(1,2,m['symbols']['fx_controls_locale'])
    locale=struct.unpack('<4I2Q',bytes(u.mem_read(locale_address,32)))
    expected_locale=m['locale_descriptor']
    assert locale==(1,32,expected_locale['languages'],expected_locale['text_count'],expected_locale['offsets_directory'],expected_locale['pools_directory'])
    assert any(not(s['flags']&2) and s['va']<=locale_address and locale_address+32<=s['va']+s['file_bytes'] for s in m['segments'])
    assert bytes(u.mem_read(slot+0x18,4))==struct.pack('<I',5),'entry must not modify native DCF state'
    assert call(event,context,6)==0
    assert bytes(u.mem_read(slot+0x18,4))==struct.pack('<I',9 if m['features']&8 else 5)
    assert call(event,context,6)==0
    callbacks=[]
    for i,name in enumerate(expected):
        b=bytes(u.mem_read(providers+i*104,104));seen=b[:64].split(b'\0')[0].decode()
        version,kind,callabi,caps,where,flags,fn,ctx=struct.unpack_from('<IIIIIIQQ',b,64)
        assert seen==name and (version,kind,callabi,where)==(1,4,4,1)
        assert call(fn,ctx,1,7,101+i,COOKIE+i*8,0,0)==0
        callbacks.append((name,fn,ctx,101+i))
    assert stats['native_gets']==stats['native_sets']==0, 'ATTACH made original function call'
    for i,(name,fn,ctx,token) in enumerate(callbacks):
        u.mem_write(REQUEST,bytes(816));u.mem_write(REPLY,bytes(816))
        assert call(fn,ctx,3,7,token,COOKIE+i*8,REQUEST,REPLY)==0
        assert struct.unpack_from('<I',bytes(u.mem_read(REPLY,48)),8)[0]>0
    # Exact getters are only reached during short copied CALL, never staging/attach.
    assert stats['native_gets']==int(bool(m['features']&1))+3*int(bool(m['features']&8))
    assert call(pending,context)==0 and call(event,context,2)==0
    assert call(event,context,4)==5, 'resume must retain stale owner leases'
    before=stats['native_gets']
    for i,(_,fn,ctx,token) in enumerate(callbacks): assert call(fn,ctx,2,7,token,COOKIE+i*8,0,0)==0
    assert stats['native_gets']==before and call(event,context,4)==0
    assert call(event,context,5)==5 and stats['releases']==0, 'published storage cannot be aborted/freed'
    return dict(features=m['features'],providers=expected,**stats,
                entry=hex(m['entry']),elf_sha256=m['elf_sha256'],locale_descriptor_actual_export='passed',arm_entry_attach_query_stop_resume='passed')


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    builds=[]
    for mask in range(1,16):
        cmd=[sys.executable,str(PACK/'build.py'),'--features',str(mask),'--out',str(out/str(mask))]
        subprocess.run(cmd,cwd=ROOT,check=True,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
        builds.append(arm_check(out/str(mask)/'controls.json'))
        print(json.dumps(dict(mask=mask,arm='passed')),flush=True)
    exe=out/'test_backend.exe'
    hostcmd=[str(LLVM/'clang.exe'),'-std=c11','-O1','-Wall','-Wextra','-Werror','-Wconversion','-Wshadow',
             '-DFX_CONTROLS_TESTING=1','-DFX_CONTROL_FEATURES=15','-I'+str(ROOT/'include'),'-I'+str(PACK),'-I'+str(out/'15'),
             str(PACK/'tests/test_backend.c'),str(PACK/'backend.c'),str(PACK/'photo_backend.c'),str(PACK/'precapture_subscription.c'),
             str(ROOT/'src/suite_video.c'),str(ROOT/'src/framing.c'),str(ROOT/'src/photo_tools.c'),str(ROOT/'src/memory.c'),'-o',str(exe)]
    subprocess.run(hostcmd,cwd=ROOT,check=True,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
    hosttests=[]
    for a in ([],['fault']):
        p=subprocess.run([str(exe),*a],cwd=ROOT,check=True,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=10)
        hosttests.append(dict(arguments=a,stdout=p.stdout.strip(),exit_code=p.returncode))
    dcf_exe=out/'test_precapture_subscription.exe'
    dcf_cmd=[str(LLVM/'clang.exe'),'-std=c11','-O1','-Wall','-Wextra','-Werror','-Wconversion','-Wshadow','-DFX_CONTROLS_TESTING=1','-I'+str(ROOT/'include'),'-I'+str(PACK),str(PACK/'tests/test_precapture_subscription.c'),str(PACK/'precapture_subscription.c'),str(ROOT/'src/memory.c'),'-o',str(dcf_exe)]
    subprocess.run(dcf_cmd,cwd=ROOT,check=True,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
    dcf_run=subprocess.run([str(dcf_exe)],cwd=ROOT,check=True,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=10)
    hosttests.append(dict(arguments=['precapture-stage'],stdout=dcf_run.stdout.strip(),exit_code=dcf_run.returncode))
    result=dict(schema=1,passed=True,arm_subset_checks=builds,host_compile_command=hostcmd,host_tests=hosttests,
                no_camera=True,original_functions='synthetic stubs only',
                limitations=['No physical RTOS, actual original GUI scheduling, DMA/cache/SMP rendezvous, media IO or original worker execution qualification'],
                sources_sha256={str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in [ROOT/'include/fenestra_native_pack.h',*PACK.glob('*.c'),*PACK.glob('*.h'),*PACK.glob('*.S'),*PACK.glob('*.ld'),PACK/'build.py',Path(__file__),PACK/'tests/test_backend.c',PACK/'tests/test_precapture_subscription.c']})
    (out/'checks.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=True,arm_subsets=len(builds),host_tests=hosttests,report=str(out/'checks.json')),indent=2))


if __name__=='__main__':main()
