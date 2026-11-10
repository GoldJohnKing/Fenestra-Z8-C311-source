"""GUI/session regression fixtures. These tests never open a physical USB device."""
from pathlib import Path
import struct
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'host'))
from ptp_client import HEADER, HELLO
from test_z8_status import Endpoint as StatusEndpoint
from z8_debug_session import DebugSession, DebugWorker


class Endpoint(StatusEndpoint):
    """Explicit synthetic transport exercising the real FXP2 client and job API."""
    def __init__(self, output='测试输出\n'.encode()):
        super().__init__()
        self.output = output
        self.opens = self.closes = self.hellos = 0
        self.job = 41
        self.phase = 3
        self.levels = []
        self.operations = []
        self.failure = None
        self.failed = False
        self.threads = []
        self.block = self.release = None
        self.memory_writes = []
        self.job_kind = 0
        self.native_result = 0x123456789abcdef

    def __enter__(self):
        self.opens += 1
        self.threads.append(threading.get_ident())
        return self

    def __exit__(self, *args):
        self.closes += 1
        self.threads.append(threading.get_ident())

    def read(self, operation, params, maximum):
        if operation == HELLO:
            self.hellos += 1
            return super().read(operation, params, maximum)
        request = HEADER.unpack_from(self.pending)
        op, payload = request[2], self.pending[32:]
        if op in (1, 9):
            return super().read(operation, params, maximum)
        subop = struct.unpack_from('<I', payload)[0] if op == 7 else None
        if self.block == (op, subop):
            self.release.wait(4)
        if self.failure == (op, subop) and not self.failed:
            self.failed = True
            raise OSError('fixture: lost response, original request retained')
        self.operations.append((op, subop, payload[4:]))
        if op == 2:
            result = payload
        elif op == 7:
            if subop == 0:
                result = b'FXT1\x01\0\0\0' + bytes(8) + struct.pack('<10Q', *range(10))
            elif subop == 2:
                address, count = struct.unpack('<QI', payload[4:])
                result = bytes((address + i) & 255 for i in range(count))
            elif subop == 3:
                address, count = struct.unpack_from('<QI', payload, 4)
                data = payload[16:]
                if len(data) != count:
                    raise AssertionError('fixture write length mismatch')
                self.memory_writes.append((address, data))
                result = struct.pack('<I', count)
            elif subop == 4:
                produced = self.levels.pop(0) if self.levels else len(self.output)
                result = bytearray(64)
                struct.pack_into('<4s5I', result, 0, b'FXS1', 1, 3, self.phase, self.job, 307)
                struct.pack_into('<QIIQ4I', result, 24, self.native_result if self.job_kind else 0,
                                 produced, 0, 123, 1, 0, 5000, self.job_kind)
            elif subop == 5:
                self.job_kind = struct.unpack_from('<I', payload, 4)[0]
                result = struct.pack('<I', 41)
            elif subop == 6:
                job, offset, count = struct.unpack('<III', payload[4:])
                if job != self.job:
                    raise AssertionError('foreign output read')
                result = self.output[offset:offset + count]
            elif subop in (7, 8):
                if subop == 8:
                    self.phase = 5
                result = b''
            else:
                raise AssertionError(subop)
        else:
            raise AssertionError(op)
        raw = HEADER.pack(b'FXP2', 2, op, request[3], request[4], len(result), 0x80000000, 0) + result
        import zlib
        return raw[:28] + struct.pack('<I', zlib.crc32(raw)) + raw[32:]

    def submits(self, subop):
        return sum(HEADER.unpack_from(raw)[2] == 7 and
                   struct.unpack_from('<I', raw, 32)[0] == subop for _, _, raw in self.writes)


class SessionTests(unittest.TestCase):
    def make(self, endpoint=None):
        endpoint = endpoint or Endpoint()
        events = []
        session = DebugSession(lambda k, v: events.append((k, v)), lambda: endpoint)
        self.addCleanup(session.disconnect)
        return session, endpoint, events

    @staticmethod
    def output(events):
        return ''.join(v['text'] for k, v in events if k == 'output')

    def test_inert_session_does_not_open_transport(self):
        session, endpoint, _ = self.make()
        self.assertFalse(session.state()['connected'])
        self.assertEqual(endpoint.opens, 0)

    def test_connect_verifies_identity_and_refresh_preserves_handshake(self):
        session, endpoint, _ = self.make()
        report = session.connect()
        self.assertTrue(report['usb_debug_connected'])
        session.refresh()
        session.echo()
        self.assertEqual(endpoint.hellos, 1)
        self.assertTrue(session.state()['connected'])

    def test_wrong_identity_closes_transport_without_connected_state(self):
        session, endpoint, _ = self.make()
        identity = bytearray(endpoint.identity)
        identity[64] ^= 1
        endpoint.identity = bytes(identity)
        with self.assertRaisesRegex(ValueError, 'exact Z8'):
            session.connect()
        self.assertFalse(session.state()['connected'])
        self.assertEqual(endpoint.closes, 1)

    def test_segmented_utf8_output_is_decoded_once_and_completed_job_acknowledged(self):
        session, endpoint, events = self.make()
        endpoint.phase, endpoint.levels = 2, [1]
        original_read = endpoint.read
        def complete_after_first(*args):
            result = original_read(*args)
            if endpoint.operations and endpoint.operations[-1][1] == 6:
                endpoint.phase = 3
            return result
        endpoint.read = complete_after_first
        session.connect()
        result = session.execute('echo 测试')
        self.assertEqual(self.output(events), endpoint.output.decode())
        self.assertEqual(result['dropped'], 0)
        self.assertIsNone(session.job)
        self.assertEqual(endpoint.submits(5), 1)
        self.assertEqual(endpoint.submits(7), 1)

    def test_native_call_uses_integer_call_job_and_returns_result(self):
        session, endpoint, events = self.make(Endpoint(output=b''))
        session.connect()
        result = session.native_call(0x40183490, [0, 0xffffffffffffffff])
        submitted = next(data for op, subop, data in endpoint.operations if op == 7 and subop == 5)
        self.assertEqual(struct.unpack('<II9Q', submitted),
                         (1, 5000, 0x40183490, 0, 0xffffffffffffffff, 0, 0, 0, 0, 0, 0))
        self.assertEqual(result['kind'], 1)
        self.assertEqual(result['result'], endpoint.native_result)
        self.assertIsNone(session.job)
        self.assertEqual(endpoint.submits(5), 1)
        self.assertEqual(endpoint.submits(7), 1)
        self.assertTrue(any(k == 'notice' and '40183490' in v for k, v in events))

    def test_invalid_native_call_never_reaches_transport(self):
        session, endpoint, _ = self.make()
        session.connect()
        before = len(endpoint.writes)
        cases = [dict(address=0), dict(address=1), dict(address=True),
                 dict(address=0x40183490, args=[True]),
                 dict(address=0x40183490, args=[-1]),
                 dict(address=0x40183490, args=[1 << 64]),
                 dict(address=0x40183490, args=[0] * 9),
                 dict(address=0x40183490, timeout_ms=True)]
        for arguments in cases:
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                session.native_call(**arguments)
        self.assertEqual(len(endpoint.writes), before)

    def test_lost_native_submit_response_recovers_same_call_once(self):
        session, endpoint, _ = self.make(Endpoint(output=b''))
        endpoint.failure = (7, 5)
        session.connect()
        with self.assertRaises(OSError):
            session.native_call(0x40183490)
        with self.assertRaisesRegex(RuntimeError, '不会自动重发'):
            session.native_call(0x40183490)
        result = session.recover()
        self.assertEqual(result['kind'], 1)
        self.assertEqual(result['result'], endpoint.native_result)
        self.assertEqual(endpoint.submits(5), 1)
        self.assertEqual(endpoint.submits(7), 1)
        self.assertIsNone(session.job)

    def test_foreign_job_is_rejected_before_output_read(self):
        session, endpoint, events = self.make()
        endpoint.job = 99
        session.connect()
        with self.assertRaisesRegex(ValueError, 'job identity changed'):
            session.execute('echo own')
        self.assertEqual(endpoint.submits(6), 0)
        self.assertEqual(self.output(events), '')

    def test_lost_submit_response_recovers_without_reexecuting_command(self):
        session, endpoint, events = self.make()
        endpoint.failure = (7, 5)
        session.connect()
        with self.assertRaises(OSError):
            session.execute('echo once')
        self.assertTrue(session.state()['pending'])
        with self.assertRaisesRegex(RuntimeError, '不会自动重发'):
            session.execute('echo duplicate')
        session.recover()
        self.assertEqual(endpoint.submits(5), 1)
        self.assertEqual(self.output(events), endpoint.output.decode())
        self.assertIsNone(session.job)

    def test_lost_output_response_recovers_same_chunk_without_duplicate_output(self):
        session, endpoint, events = self.make()
        endpoint.failure = (7, 6)
        session.connect()
        with self.assertRaises(OSError):
            session.execute('echo once')
        session.recover()
        self.assertEqual(endpoint.submits(5), 1)
        self.assertEqual(endpoint.submits(6), 1)
        self.assertEqual(self.output(events), endpoint.output.decode())

    def test_lost_acknowledge_response_does_not_repeat_command_or_output(self):
        session, endpoint, events = self.make()
        endpoint.failure = (7, 7)
        session.connect()
        with self.assertRaises(OSError):
            session.execute('echo once')
        session.recover()
        self.assertEqual(endpoint.submits(5), 1)
        self.assertEqual(endpoint.submits(7), 1)
        self.assertEqual(self.output(events), endpoint.output.decode())
        self.assertIsNone(session.job)

    def test_cancel_is_cooperative_and_preserves_terminal_job(self):
        session, endpoint, _ = self.make()
        endpoint.phase = 2
        session.connect()
        session.cancel.set()
        result = session.execute('echo cancel')
        self.assertEqual(endpoint.submits(8), 1)
        self.assertEqual(result['phase'], 5)
        self.assertEqual(session.job, 41)

    def test_registers_and_bounded_memory_read(self):
        session, endpoint, _ = self.make()
        session.connect()
        self.assertEqual(session.registers()['CNTFRQ_EL0'], '0x9')
        memory = session.memory_read(0x40000000, 32)
        self.assertEqual(bytes.fromhex(memory['hex']), bytes(range(32)))
        with self.assertRaises(ValueError):
            session.memory_read(0, 1009)

    def test_bounded_memory_write_uses_existing_transport_and_reports_digest(self):
        import hashlib
        session, endpoint, _ = self.make()
        session.connect()
        result = session.memory_write(0xa10000000, '001122ff')
        self.assertEqual(endpoint.memory_writes, [(0xa10000000, bytes.fromhex('001122ff'))])
        self.assertEqual(result['bytes'], 4)
        self.assertEqual(result['sha256'], hashlib.sha256(bytes.fromhex('001122ff')).hexdigest())
        self.assertEqual(endpoint.opens, 1)

    def test_invalid_memory_write_never_reaches_transport(self):
        session, endpoint, _ = self.make()
        session.connect()
        before = len(endpoint.writes)
        for address, data in [(True, '00'), (-1, '00'), (1 << 64, '00'),
                              ((1 << 64) - 1, '0000'), (0, ''), (0, 'x0'),
                              (0, '00' * 1009), (0, True)]:
            with self.subTest(address=address, data=str(data)[:16]), self.assertRaises(ValueError):
                session.memory_write(address, data)
        self.assertEqual(len(endpoint.writes), before)

    def test_existing_memory_dump_output_is_preserved_before_device_read(self):
        session, endpoint, _ = self.make()
        session.connect()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'keep.bin'
            output.write_bytes(b'keep')
            before = len(endpoint.writes)
            with self.assertRaises(FileExistsError):
                session.memory_dump(0x40000000, 32, output)
            self.assertEqual(output.read_bytes(), b'keep')
            self.assertEqual(len(endpoint.writes), before)

    def test_disconnect_reports_unconfirmed_agent_and_still_closes_transport(self):
        session, endpoint, events = self.make()
        session.connect()
        def failed_stop():
            raise OSError('fixture agent stop unconfirmed')
        session.bridge = SimpleNamespace(owns_allocation=True, pending=None, call_pending=None, stop=failed_stop)
        result = session.disconnect()
        self.assertIn('停止未确认', result['notes'][0])
        self.assertEqual(endpoint.closes, 1)
        self.assertFalse(session.state()['connected'])
        self.assertTrue(any(k == 'notice' for k, _ in events))

    def test_worker_serializes_transport_on_one_background_thread(self):
        endpoint = Endpoint()
        worker = DebugWorker(lambda emit, cancel: DebugSession(emit, lambda: endpoint, cancel))
        try:
            worker.submit('connect')
            worker.submit('refresh')
            idle, deadline = [], time.monotonic() + 3
            while len(idle) < 2 and time.monotonic() < deadline:
                kind, value = worker.events.get(timeout=1)
                if kind == 'error':
                    self.fail(value)
                if kind == 'idle':
                    idle.append(value)
            self.assertEqual(idle, ['connect', 'refresh'])
        finally:
            worker.stop()
            worker.thread.join(3)
        self.assertFalse(worker.thread.is_alive())
        self.assertEqual(len(set(endpoint.threads)), 1)
        self.assertNotEqual(endpoint.threads[0], threading.get_ident())


class GuiTests(unittest.TestCase):
    def setUp(self):
        try:
            import tkinter as tk
            from z8_debug_gui import DebugApp
            self.window = tk.Tk()
        except Exception as exc:
            self.skipTest('desktop Tk unavailable: ' + str(exc))
        self.window.withdraw()
        self.endpoint = Endpoint()
        self.worker = DebugWorker(lambda emit, cancel: DebugSession(emit, lambda: self.endpoint, cancel))
        self.app = DebugApp(self.window, self.worker)
        self.window.update()

    def tearDown(self):
        if not hasattr(self, 'app'):
            return
        if self.endpoint.release:
            self.endpoint.release.set()
        if not self.app.destroyed:
            self.app.close()
            self.wait(lambda: self.app.destroyed)
        self.worker.thread.join(3)
        self.assertFalse(self.worker.thread.is_alive())

    def wait(self, predicate, timeout=4):
        end = time.monotonic() + timeout
        while not predicate() and time.monotonic() < end:
            self.window.update()
            time.sleep(.01)
        self.assertTrue(predicate(), 'GUI event deadline expired')

    def connect(self):
        self.app.connect_button.invoke()
        self.wait(lambda: self.app.state['connected'] and not self.app.busy)

    def test_connect_execute_export_and_disconnect_through_ui(self):
        self.connect()
        self.assertEqual(self.app.card_values['model'].cget('text'), 'Nikon Z8')
        self.app.command.set('echo 测试')
        self.app._execute()
        self.wait(lambda: not self.app.busy)
        self.assertIn('测试输出', self.app.terminal.get('1.0', 'end'))
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory) / 'debug.txt'
            self.app.export_log(dest)
            self.assertIn('测试输出', dest.read_text(encoding='utf-8'))
        self.app.connect_button.invoke()
        self.wait(lambda: not self.app.busy)
        self.assertFalse(self.app.state['connected'])
        self.assertEqual(self.endpoint.closes, 1)

    def test_native_call_can_request_cooperative_cancel(self):
        self.connect()
        self.endpoint.phase = 2
        self.app._submit('native_call', address=0x40183490)
        self.wait(lambda: self.endpoint.submits(5) == 1)
        self.assertEqual(self.app.cancel_button.cget('state'), 'normal')
        self.app.cancel_button.invoke()
        self.wait(lambda: not self.app.busy)
        self.assertEqual(self.endpoint.submits(8), 1)
        self.assertEqual(self.endpoint.submits(7), 0)
        self.assertEqual(self.app.state['rtos_job'], 41)

    def test_connection_failure_stays_offline_and_logs_error(self):
        identity = bytearray(self.endpoint.identity)
        identity[64] ^= 1
        self.endpoint.identity = bytes(identity)
        self.app.connect_button.invoke()
        self.wait(lambda: not self.app.busy)
        self.assertFalse(self.app.state['connected'])
        self.assertIn('未连接', self.app.connection_badge.cget('text'))
        self.assertIn('exact Z8', self.app.terminal.get('1.0', 'end'))

    def test_close_waits_for_inflight_task_and_queued_disconnect(self):
        self.connect()
        self.endpoint.block = (7, 5)
        self.endpoint.release = threading.Event()
        self.app._execute()
        self.app.close()
        self.window.update()
        self.assertFalse(self.app.destroyed)
        self.endpoint.release.set()
        self.wait(lambda: self.app.destroyed)
        self.assertEqual(self.endpoint.closes, 1)


if __name__ == '__main__':
    unittest.main()
