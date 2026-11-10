"""Compile actual WLM compound parser, module parser and cold inventory code."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
class WlmBundleTests(unittest.TestCase):
    def test_production_bundle_and_frozen_frontend(self):
        cc=shutil.which('clang') or 'C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Tools/Llvm/x64/bin/clang.exe'
        with tempfile.TemporaryDirectory(prefix='wlm-bundle-',dir=ROOT/'build') as folder:
            exe=Path(folder)/('probe.exe' if os.name=='nt' else 'probe')
            sources=['tests/test_wlm_bundle.c','src/wlm_bundle.c','src/module.c','src/services.c','src/sha256.c','src/memory.c']
            flags=['-std=c11','-O1','-Wall','-Wextra','-Werror','-Wconversion','-Wshadow','-ffunction-sections','-fdata-sections','-I'+str(ROOT/'include')]
            flags+=['-fuse-ld=lld','-Wl,/OPT:REF'] if os.name=='nt' else ['-Wl,--gc-sections']
            made=subprocess.run([cc,*flags,*[str(ROOT/x) for x in sources],'-o',str(exe)],capture_output=True,text=True,timeout=60)
            self.assertEqual(made.returncode,0,made.stdout+made.stderr)
            ran=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
            self.assertEqual(ran.returncode,0,ran.stdout+ran.stderr)
            self.assertIn('PASS:',ran.stdout)
    def test_actual_z8_frozen_stage_does_not_reopen_card(self):
        cc=shutil.which('clang') or 'C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Tools/Llvm/x64/bin/clang.exe'
        with tempfile.TemporaryDirectory(prefix='wlm-stage-',dir=ROOT/'build') as folder:
            folder=Path(folder)
            # Exact stock MAIN identity; no physical IO/address stubs are used as
            # successful transports. Native card functions assert unreachable.
            sha=bytes.fromhex('2b43a31c9de838f84b12416de4348a7004e65be07f853ec56ec2b10f3a8e3853')
            (folder/'z8_full_bindings.h').write_text('#define FX_Z8_APPLICATION_IDENTITY {'+','.join(str(x) for x in sha)+'}\n')
            exe=folder/('stage.exe' if os.name=='nt' else 'stage')
            sources=['tests/test_z8_frozen_stage.c','src/platform/z8_c311_full/module_stage.c','src/file_card.c','src/exec.c','src/loader.c','src/runtime.c','src/card.c','src/module.c','src/services.c','src/sha256.c','src/memory.c']
            flags=['-std=c11','-O1','-Wall','-Wextra','-Werror','-Wconversion','-Wshadow','-ffunction-sections','-fdata-sections','-I'+str(folder),'-I'+str(ROOT/'include'),'-I'+str(ROOT/'src/platform/z8_c311_full')]
            flags+=['-fuse-ld=lld','-Wl,/OPT:REF'] if os.name=='nt' else ['-Wl,--gc-sections']
            made=subprocess.run([cc,*flags,*[str(ROOT/x) for x in sources],'-o',str(exe)],capture_output=True,text=True,timeout=60)
            self.assertEqual(made.returncode,0,made.stdout+made.stderr)
            ran=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
            self.assertEqual(ran.returncode,0,ran.stdout+ran.stderr)
            self.assertIn('PASS: actual frozen Z8 stage',ran.stdout)
    def test_manager_warm_resume_keeps_frozen_current(self):
        cc=shutil.which('clang') or 'C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Tools/Llvm/x64/bin/clang.exe'
        with tempfile.TemporaryDirectory(prefix='wlm-manager-',dir=ROOT/'build') as folder:
            exe=Path(folder)/('manager.exe' if os.name=='nt' else 'manager')
            sources=['tests/test_wlm_manager_resume.c','src/module_manager.c','src/wlm_bundle.c','src/module.c','src/services.c','src/sha256.c','src/memory.c']
            flags=['-std=c11','-O1','-Wall','-Wextra','-Werror','-Wconversion','-Wshadow','-DFX_NATIVE_CAPSULES=1','-ffunction-sections','-fdata-sections','-I'+str(ROOT/'include')]
            flags+=['-fuse-ld=lld','-Wl,/OPT:REF'] if os.name=='nt' else ['-Wl,--gc-sections']
            made=subprocess.run([cc,*flags,*[str(ROOT/x) for x in sources],'-o',str(exe)],capture_output=True,text=True,timeout=60)
            self.assertEqual(made.returncode,0,made.stdout+made.stderr)
            ran=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
            self.assertEqual(ran.returncode,0,ran.stdout+ran.stderr)
            self.assertIn('PASS: actual manager warm Resume',ran.stdout)
    def test_exact_production_module_read_full_capacity(self):
        cc=shutil.which('clang') or 'C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Tools/Llvm/x64/bin/clang.exe'
        production=(ROOT/'src/platform/z8_c311_full/menu.c').read_text()
        end=production.index('} Directory;')+len('} Directory;')
        directory=production[production.rfind('typedef struct {',0,end):end]
        start=production.index('#ifdef FX_NATIVE_CAPSULES\n#define FX_Z8_DISCOVERY_LIMIT')
        finish=production.index('static void *index_allocate',start)
        fragment=directory+'\n'+production[start:finish]
        for native in (False,True):
            with self.subTest(native=native), tempfile.TemporaryDirectory(prefix='wlm-read-',dir=ROOT/'build') as folder:
                folder=Path(folder);(folder/'production_module_read.inc').write_text(fragment)
                exe=folder/('read.exe' if os.name=='nt' else 'read')
                flags=['-std=c11','-O1','-Wall','-Wextra','-Werror','-Wconversion','-Wshadow','-ffunction-sections','-fdata-sections','-I'+str(folder),'-I'+str(ROOT/'include')]
                if native:flags+=['-DFX_NATIVE_CAPSULES=1']
                flags+=['-fuse-ld=lld','-Wl,/OPT:REF'] if os.name=='nt' else ['-Wl,--gc-sections']
                sources=['tests/test_z8_wlm_module_read.c','src/wlm_bundle.c','src/module.c','src/services.c','src/sha256.c','src/memory.c']
                made=subprocess.run([cc,*flags,*[str(ROOT/x) for x in sources],'-o',str(exe)],capture_output=True,text=True,timeout=60)
                self.assertEqual(made.returncode,0,made.stdout+made.stderr)
                ran=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
                self.assertEqual(ran.returncode,0,ran.stdout+ran.stderr)
                self.assertIn('PASS: exact production module_read',ran.stdout)
if __name__=='__main__':unittest.main()
