"""Compile and exercise the real ProRes provider and async module on the host."""
from pathlib import Path
import os,shutil,subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
class ProResTests(unittest.TestCase):
    def probe(self,name):
        cc=shutil.which('clang') or shutil.which('gcc')
        if not cc:
            candidate=Path('C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Tools/Llvm/x64/bin/clang.exe')
            if candidate.is_file():cc=str(candidate)
        if not cc:raise RuntimeError('Clang or GCC required')
        with tempfile.TemporaryDirectory(prefix='fenestra-prores-') as folder:
            exe=Path(folder)/('probe.exe' if os.name=='nt' else 'probe')
            result=subprocess.run([cc,'-std=c11','-O1','-Wall','-Wextra','-Werror','-I'+str(ROOT/'include'),
                str(ROOT/'tests'/name),str(ROOT/'src/prores.c'),str(ROOT/'src/memory.c'),'-o',str(exe)],capture_output=True,text=True,timeout=45)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('PASS:',result.stdout)
    def test_native_provider_lifetime(self):self.probe('test_prores.c')
    def test_actual_module_async_ui(self):self.probe('test_prores_module.c')
if __name__=='__main__':unittest.main()
