"""Independent production-header/storage regression; no physical or QEMU IO."""
from pathlib import Path
import os,shutil,subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
class ColdBootstrapReviewTests(unittest.TestCase):
 def test_production_retry_cancel_ownership_and_idempotence(self):
  compiler=shutil.which('clang') or shutil.which('gcc')
  if not compiler:
   candidate=Path('C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Tools/Llvm/x64/bin/clang.exe')
   if candidate.is_file():compiler=str(candidate)
  if not compiler:raise RuntimeError('Clang or GCC required')
  with tempfile.TemporaryDirectory(prefix='fenestra-cold-review-') as d:
   output=Path(d)/('review.exe' if os.name=='nt' else 'review')
   command=[compiler,'-std=c11','-O1','-Wall','-Wextra','-Werror','-Wconversion','-Wshadow','-I'+str(ROOT/'include'),'-I'+str(ROOT/'src/platform/z8_c311_full'),str(ROOT/'tests/test_z8_cold_bootstrap_review.c'),str(ROOT/'src/platform/z8_c311_full/storage.c'),str(ROOT/'src/startup_service.c'),str(ROOT/'src/startup.c'),str(ROOT/'src/memory.c'),'-o',str(output)]
   build=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=45);self.assertEqual(build.returncode,0,build.stdout+build.stderr)
   run=subprocess.run([str(output)],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=10);self.assertEqual(run.returncode,0,run.stdout+run.stderr);self.assertIn('production bootstrap schedules, bounded retries, ownership, generation and duplicate events',run.stdout)
if __name__=='__main__':unittest.main()
