"""Build and run the actual native-pack registry with synthetic providers."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
class PackRegistryTests(unittest.TestCase):
    def compile_run(self, source):
        cc=shutil.which('clang') or str(Path('C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Tools/Llvm/x64/bin/clang.exe'))
        with tempfile.TemporaryDirectory(prefix='pack-registry-',dir=ROOT/'build') as folder:
            exe=Path(folder)/('probe.exe' if os.name=='nt' else 'probe')
            built=subprocess.run([cc,'-std=c11','-O1','-Wall','-Wextra','-Werror','-Wconversion','-Wshadow','-I'+str(ROOT/'include'),
                str(ROOT/'tests'/source),str(ROOT/'src/pack_registry.c'),str(ROOT/'src/memory.c'),'-o',str(exe)],capture_output=True,text=True,timeout=45)
            self.assertEqual(built.returncode,0,built.stdout+built.stderr)
            ran=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
            self.assertEqual(ran.returncode,0,ran.stdout+ran.stderr);self.assertIn('PASS:',ran.stdout)
    def test_registry_stage_deferred_and_lifecycle(self):
        self.compile_run('test_pack_registry.c')
    def test_multiple_resident_owners(self):
        self.compile_run('test_pack_registry_many.c')
if __name__=='__main__':unittest.main()
