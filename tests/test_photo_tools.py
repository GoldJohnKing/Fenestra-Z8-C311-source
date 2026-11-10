"""Synthetic tests of the actual photo-tools provider/native bridge and WLM."""
from pathlib import Path
import os, shutil, subprocess, tempfile, unittest
ROOT=Path(__file__).resolve().parents[1]
class PhotoToolsTests(unittest.TestCase):
    def probe(self,name):
        cc=shutil.which("clang") or shutil.which("gcc")
        if not cc:
            p=Path("C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Tools/Llvm/x64/bin/clang.exe")
            if p.is_file():cc=str(p)
        if not cc:raise RuntimeError("Clang/GCC required")
        with tempfile.TemporaryDirectory(prefix="fenestra-photo-") as folder:
            out=Path(folder);exe=out/("probe.exe" if os.name=="nt" else "probe")
            (out/"z8_feature_suite_symbols.h").write_text("#define FX_Z8_PSM_WORKER UINT64_C(0x409a44cc)\n#define FX_Z8_PSM_CAMERA_JOB UINT64_C(0x40995818)\n")
            result=subprocess.run([cc,"-std=c11","-O1","-Wall","-Wextra","-Werror","-I"+str(ROOT/"include"),"-I"+str(out),str(ROOT/"tests"/name),str(ROOT/"src/photo_tools.c"),str(ROOT/"src/memory.c"),"-o",str(exe)],capture_output=True,text=True,timeout=45)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn("PASS:",result.stdout)
    def test_native_gui_claim_lifetime(self):self.probe("test_photo_tools.c")
    def test_actual_module_async_ui(self):self.probe("test_photo_tools_module.c")
if __name__=="__main__":unittest.main()
