"""Execute production suite video provider and both asynchronous WLM UIs."""
from pathlib import Path
import os,shutil,subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
class SuiteVideoTests(unittest.TestCase):
    def probe(self,name,*defines):
        cc=shutil.which('clang') or shutil.which('gcc')
        if not cc:
            candidate=Path('C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Tools/Llvm/x64/bin/clang.exe')
            if candidate.is_file():cc=str(candidate)
        if not cc:raise RuntimeError('Clang or GCC required')
        with tempfile.TemporaryDirectory(prefix='fenestra-suite-video-') as folder:
            exe=Path(folder)/('probe.exe' if os.name=='nt' else 'probe')
            result=subprocess.run([cc,'-std=c11','-O1','-Wall','-Wextra','-Werror',*defines,'-I'+str(ROOT/'include'),
                str(ROOT/'tests'/name),str(ROOT/'src/suite_video.c'),str(ROOT/'src/memory.c'),'-o',str(exe)],capture_output=True,text=True,timeout=45)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('PASS:',result.stdout)
    def test_shared_native_provider_lifetime(self):self.probe('test_suite_video.c')
    def test_existing_prores_module_wire_compatibility(self):self.probe('test_suite_video_module.c','-DSUITE_TEST_PRORES=1')
    def test_actual_h265_module_async_ui(self):self.probe('test_suite_video_module.c')
    def test_actual_log_colour_module_async_ui(self):self.probe('test_suite_video_module.c','-DSUITE_TEST_LOG=1')
if __name__=='__main__':unittest.main()
