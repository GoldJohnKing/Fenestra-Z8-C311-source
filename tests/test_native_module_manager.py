"""Actual native_modules.c IO/manager C tests with explicit synthetic Nikon FS."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
class NativeModuleManagerTests(unittest.TestCase):
    def test_actual_manager_reader_and_v4_contract(self):
        cc=shutil.which('clang') or 'C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Tools/Llvm/x64/bin/clang.exe'
        for native in (False,True):
            with self.subTest(native=native), tempfile.TemporaryDirectory(prefix='native-manager-',dir=ROOT/'build') as folder:
                exe=Path(folder)/('manager.exe' if os.name=='nt' else 'manager')
                flags=['-std=c11','-O1','-Wall','-Wextra','-Werror','-Wconversion','-Wshadow','-DFX_Z8_C311_FULL=1','-ffunction-sections','-fdata-sections','-I'+str(ROOT/'include')]
                if native:flags+=['-DFX_NATIVE_CAPSULES=1']
                flags+=['-fuse-ld=lld','-Wl,/OPT:REF'] if os.name=='nt' else ['-Wl,--gc-sections']
                sources=['tests/test_native_module_manager.c','src/module_manager.c','src/wlm_bundle.c','src/module.c','src/services.c','src/sha256.c','src/memory.c']
                made=subprocess.run([cc,*flags,*[str(ROOT/x) for x in sources],'-o',str(exe)],capture_output=True,text=True,timeout=60)
                self.assertEqual(made.returncode,0,made.stdout+made.stderr)
                ran=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30)
                self.assertEqual(ran.returncode,0,ran.stdout+ran.stderr)
                self.assertIn('PASS:',ran.stdout)
if __name__=='__main__':unittest.main()
