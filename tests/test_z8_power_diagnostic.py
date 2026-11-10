"""Diagnostic policy/backend tests; synthetic native boundaries, no camera access."""
from pathlib import Path
import os,shutil,subprocess,unittest
ROOT=Path(__file__).resolve().parents[1]
class PowerDiagnosticTests(unittest.TestCase):
    def test_actual_c311_backend_and_portable_protocol(self):
        headers = ROOT / os.environ.get('FX_Z8_BUILD', 'build/local-native-core')
        if not (headers / 'z8_full_bindings.h').is_file():
            self.skipTest('requires headers from a locally compiled Z8 core')
        compiler=shutil.which('clang') or shutil.which('gcc')
        if not compiler:
            candidate=Path('C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Tools/Llvm/x64/bin/clang.exe')
            if candidate.is_file():compiler=str(candidate)
        if not compiler:raise RuntimeError('Clang or GCC required')
        folder=Path(os.environ.get('FX_Z8_DIAGNOSTIC_TEST_OUTPUT', str(ROOT/'build/resume-progress-20261107/unittest')))
        folder.mkdir(parents=True,exist_ok=True)
        output=folder/('diagnostic.exe' if os.name=='nt' else 'diagnostic')
        command=[compiler,'-std=c11','-O1','-Wall','-Wextra','-Werror','-Wconversion','-Wshadow',
                 '-I'+str(ROOT/'include'),'-I'+str(ROOT/'src/platform/z8_c311_full'),
                 '-I'+str(headers),
                 str(ROOT/'tests/test_z8_power_diagnostic.c'),str(ROOT/'src/ptp.c'),
                 str(ROOT/'src/memory.c'),'-o',str(output)]
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=45)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        result=subprocess.run([str(output)],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=10)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('112 immutable labels',result.stdout)
        self.assertIn('168 immutable resume labels',result.stdout)
    def test_real_host_session_connects_to_inactive_explicit_synthetic_endpoint(self):
        from test_z8_debug_gui import Endpoint
        from z8_debug_session import DebugSession
        endpoint=Endpoint(output=b'');endpoint.active=0
        session=DebugSession(lambda *_:None,lambda:endpoint)
        try:
            report=session.connect()
            self.assertFalse(report['fenestra_active'])
            self.assertTrue(report['usb_debug_connected'])
            self.assertTrue(session.state()['connected'])
            self.assertEqual(session.memory_read(0x1000,16)['hex'],bytes(range(16)).hex())
            self.assertEqual(session.echo()['bytes'],13)
            self.assertEqual(session.rtos_status()['phase'],3)
            self.assertEqual(endpoint.memory_writes,[])
            self.assertEqual(endpoint.submits(5),0)
        finally:session.disconnect()
if __name__=='__main__':unittest.main()
