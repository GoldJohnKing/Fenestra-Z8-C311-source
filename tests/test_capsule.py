"""Compile/run the actual capsule C suites; all native I/O is synthetic.
No firmware files, native toolchain downloads, WSL or physical camera needed.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]

class CapsuleTests(unittest.TestCase):
    def compile_and_run(self, name, sources, flags=()):
        compiler = shutil.which('clang') or shutil.which('cc')
        if not compiler and os.name == 'nt':
            fallback = Path('C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Tools/Llvm/x64/bin/clang.exe')
            if fallback.is_file():
                compiler = str(fallback)
        if not compiler:
            self.skipTest('native C compiler unavailable')
        (ROOT/'build').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='capsule-ci-', dir=ROOT/'build') as folder:
            executable = Path(folder)/(name+'.exe' if os.name == 'nt' else name)
            # Existing compact C suites intentionally place independent
            # statements on one line; GCC's indentation heuristic adds no
            # semantic check here. Keep all other strict warnings enabled.
            command = [compiler, '-std=c11', '-O1', '-Wall', '-Wextra', '-Werror',
                       '-Wconversion', '-Wshadow', '-Wno-misleading-indentation',
                       '-I'+str(ROOT/'include'),
                       '-I'+str(ROOT/'src/platform/z8_c311_full'), *flags,
                       *[str(ROOT/source) for source in sources], '-o', str(executable)]
            built = subprocess.run(command, capture_output=True, text=True, timeout=45)
            self.assertEqual(built.returncode, 0, built.stdout+built.stderr)
            ran = subprocess.run([str(executable)], capture_output=True, text=True, timeout=15)
            self.assertEqual(ran.returncode, 0, ran.stdout+ran.stderr)
            self.assertIn('PASS', ran.stdout)
            self.assertIn('checks', ran.stdout)

    def test_manager_package_preflight_commit_and_rollback(self):
        self.compile_and_run('manager', ['tests/test_capsule.c', 'src/capsule.c',
                                        'src/memory.c', 'src/sha256.c'])

    def test_power_off_revocation_record(self):
        self.compile_and_run('revocation', ['tests/test_z8_revocation.c', 'src/memory.c', 'src/sha256.c'])

    def test_three_cpu_rendezvous_protocol(self):
        flags = ['-DFX_Z8_CAPSULE_RENDEZVOUS_TEST=1']
        if os.name != 'nt':
            flags.append('-pthread')
        self.compile_and_run('rendezvous', ['tests/test_capsule_rendezvous.c',
                                           'src/platform/z8_c311_full/capsule_rendezvous.c'], flags)

if __name__ == '__main__':
    unittest.main()
