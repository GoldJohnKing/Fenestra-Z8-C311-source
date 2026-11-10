"""Run the actual Linux agent dispatcher over its local stdio fixture."""
import errno
import os
from pathlib import Path
import select
import shutil
import string
import struct
import subprocess
import sys
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'host'))
from linux_debug import LinuxDebug,LinuxError


@unittest.skipUnless(sys.platform.startswith('linux'),'Linux agent uses POSIX syscalls')
class LinuxAgentPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler=shutil.which('gcc') or shutil.which('clang')
        if not compiler:raise RuntimeError('GCC or Clang required for Linux agent regression')
        (ROOT/'build').mkdir(exist_ok=True)
        cls.build=tempfile.TemporaryDirectory(prefix='agent-path-tests-',dir=ROOT/'build')
        cls.addClassCleanup(cls.build.cleanup)
        cls.binary=Path(cls.build.name)/'agent-stdio'
        command=[compiler,'-std=c11','-O2','-Wall','-Wextra','-Werror',
                 '-DFX_LINUX_STDIO_FIXTURE',str(ROOT/'linux/fenestra_agent.c'),'-o',str(cls.binary)]
        result=subprocess.run(command,capture_output=True,text=True,timeout=30)
        if result.returncode:raise AssertionError(result.stdout+result.stderr)

    def setUp(self):
        self.process=subprocess.Popen([str(self.binary)],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
        self.addCleanup(self.stop_agent)
        self.debug=LinuxDebug(self.exchange)

    def stop_agent(self):
        process=self.process
        try:
            process.stdin.close()
            process.wait(timeout=5)
        except (BrokenPipeError,subprocess.TimeoutExpired):
            process.kill();process.wait(timeout=5)
        finally:
            process.stdout.close()

    def exact(self,count):
        output=bytearray();deadline=time.monotonic()+5
        while len(output)<count:
            left=deadline-time.monotonic()
            if left<=0 or not select.select([self.process.stdout],[],[],left)[0]:
                raise TimeoutError('Linux fixture response deadline')
            data=os.read(self.process.stdout.fileno(),count-len(output))
            if not data:raise EOFError('Linux fixture ended')
            output.extend(data)
        return bytes(output)

    def exchange(self,packet):
        self.process.stdin.write(struct.pack('<I',len(packet))+packet)
        self.process.stdin.flush()
        count=struct.unpack('<I',self.exact(4))[0]
        if not 8<=count<=1024:raise ValueError('Linux fixture response bounds')
        return self.exact(count)

    def test_short_absolute_paths_reach_filesystem(self):
        # Choose absent paths so the test only attempts read-only open, never
        # creates entries in the system root or depends on root privileges.
        for length in (1,2,3):
            name=next('/'+c*length for c in string.ascii_lowercase if not os.path.lexists('/'+c*length))
            with self.subTest(path=name):
                with self.assertRaises(LinuxError) as caught:self.debug.file_open(name)
                self.assertEqual(caught.exception.errno,errno.ENOENT)
        with self.assertRaises(LinuxError) as caught:self.debug.file_open('/')
        self.assertEqual(caught.exception.errno,errno.ENOTSUP)

    def test_empty_truncated_and_invalid_paths_are_still_rejected(self):
        packets=[b'',b'\0',b'\0'*2,b'\0'*3,struct.pack('<I',0),
                 struct.pack('<I',0)+b'a',struct.pack('<I',0)+b'/a\0',
                 struct.pack('<I',3)+b'/abc']
        for packet in packets:
            with self.subTest(packet=packet):
                with self.assertRaises(LinuxError) as caught:self.debug.request(10,packet)
                self.assertEqual(caught.exception.errno,errno.EINVAL)

    def test_regular_file_roundtrip_and_exclusive_create(self):
        with tempfile.TemporaryDirectory(prefix='fenestra-agent-files-') as folder:
            destination=Path(folder)/'new'
            handle,size=self.debug.file_open(str(destination),2)
            try:
                self.assertEqual(size,0)
                self.assertEqual(self.debug.file_write(handle,0,b'payload'),7)
                self.debug.file_sync(handle)
                self.assertEqual(self.debug.file_read(handle,0,7),b'payload')
            finally:self.debug.file_close(handle)
            self.assertEqual(destination.read_bytes(),b'payload')
            with self.assertRaises(LinuxError) as caught:self.debug.file_open(str(destination),2)
            self.assertEqual(caught.exception.errno,errno.EEXIST)
            handle,size=self.debug.file_open(str(destination))
            try:
                self.assertEqual(size,7)
                self.assertEqual(self.debug.file_read(handle,0,7),b'payload')
            finally:self.debug.file_close(handle)


if __name__=='__main__':unittest.main()
