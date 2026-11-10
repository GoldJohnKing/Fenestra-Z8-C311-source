"""HTTP -> visible Tk -> real FXP2 client, using an explicit synthetic camera."""
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'host'))
from workbench_bridge import BridgeError, WorkbenchBridge, validate
from workbench_client import WorkbenchClient
from z8_debug_session import DebugSession, DebugWorker
from test_z8_debug_gui import Endpoint


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.bridge = WorkbenchBridge(self.directory.name)
        self.addCleanup(self.bridge.close)
        self.client = WorkbenchClient(self.bridge.discovery)

    def test_only_authenticated_local_non_browser_requests(self):
        url = self.bridge.url + '/v1/requests'
        body = json.dumps(dict(id='blocked', action='connect', arguments={})).encode()
        for headers in ({}, {'Authorization': 'Bearer ' + self.bridge.token, 'Origin': 'https://example.com'},
                        {'Authorization': 'Bearer ' + self.bridge.token, 'Host': 'untrusted.example'}):
            with self.subTest(headers=list(headers)):
                with self.assertRaises(HTTPError) as caught:
                    self.client.opener.open(Request(url, data=body, headers=headers), timeout=2)
                self.assertIn(caught.exception.code, (401, 403))
        self.assertIsNone(self.bridge.take())

    def test_duplicate_id_is_not_enqueued_or_executed_twice(self):
        first = self.client.submit('echo', identifier='once')
        second = self.client.submit('echo', identifier='once')
        self.assertEqual(first, second)
        self.assertEqual(self.bridge.take()['id'], 'once')
        self.bridge.observe('result', {'action': 'echo', 'value': {'ok': True}})
        self.bridge.observe('idle', 'echo')
        self.assertEqual(self.client.submit('echo', identifier='once')['status'], 'completed')
        self.assertIsNone(self.bridge.take())
        with self.assertRaises(HTTPError) as caught:
            self.client.submit('connect', identifier='once')
        self.assertEqual(caught.exception.code, 409)

    def test_bad_arguments_never_reach_dispatch_and_audit_has_no_token(self):
        for action, args in [('__getattribute__', {}), ('memory_read', {'address': True}),
                             ('memory_read', {'address': 0, 'count': 1009}),
                             ('execute', {'line': 'echo x', 'extra': 1})]:
            with self.subTest(action=action, args=args):
                with self.assertRaises(HTTPError):
                    self.client.submit(action, args)
        self.assertIsNone(self.bridge.take())
        self.client.submit('workbench_status', identifier='offline')
        audit = self.bridge.audit_path.read_text(encoding='utf-8')
        self.assertIn('offline', audit)
        self.assertNotIn(self.bridge.token, audit)

    def test_native_call_schema_rejects_non_integer_and_oversized_arguments(self):
        self.assertEqual(validate('native_call', {'address': 0x40183490}),
                         dict(address=0x40183490, args=[], timeout_ms=5000))
        for args in ([True], [-1], [1 << 64], [0] * 9, '0'):
            with self.subTest(args=args), self.assertRaises(HTTPError):
                self.client.submit('native_call', dict(address=0x40183490, args=args))
        self.assertIsNone(self.bridge.take())

    def test_camera_control_schema_contract_and_session(self):
        from ptp_contract import validate_control
        self.assertEqual(validate('camera_control', {'op': 'capture'}), dict(op='capture', value=0))
        for args in ({'op': 'capture', 'value': -1}, {'op': 'capture', 'value': True}, {'op': ''}):
            with self.subTest(args=args), self.assertRaises(HTTPError):
                self.client.submit('camera_control', args)
        self.assertIsNone(self.bridge.take())
        self.assertEqual(validate_control(0x9207, (0xFFFFFFFF, 0), None), (0xFFFFFFFF, 0))
        self.assertEqual(validate_control(0x1016, (0x5013,), b'\x02\x80'), (0x5013,))
        for bad in ((0x9207, (1,), None), (0x920C, (), None), (0x1016, (0x5013,), None),
                    (0x1016, (0x5012,), b'\0\0'), (0x1015, (0x5013, 0), None), (0x1014, (0x5012,), None), (0x9201, (), None),
                    (0x95e1, (), None), (0x9207, (True, 0), None)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_control(*bad)

        calls = []
        class Transport:
            mode = b'\x01\x00'
            def control(self, opcode, params, payload=None):
                validate_control(opcode, params, payload)
                calls.append((opcode, tuple(params), payload))
                if opcode == 0x1016:
                    self.mode = payload
                return self.mode if opcode == 0x1015 else b'P' if opcode == 0x1014 else b''
        session = DebugSession(lambda *args: None)
        session.client = type('Client', (), {'pending': None})()
        session.transport = Transport()
        self.assertEqual(session.camera_control('capture'), dict(op='capture', started=True))
        self.assertEqual(session.camera_control('terminate'), dict(op='terminate', terminated=True))
        self.assertEqual(session.camera_control('get_mode'), dict(op='get_mode', value=1, bytes=2))
        self.assertEqual(session.camera_control('set_mode', 0x8013),
                         dict(op='set_mode', before=1, value=0x8013, applied=True))
        with self.assertRaises(ValueError):
            session.camera_control('set_mode', 1 << 16)
        self.assertEqual(session.camera_control('mode_desc'), dict(op='mode_desc', hex='1350'))
        with self.assertRaises(ValueError):
            session.camera_control('shutdown')
        self.assertEqual(calls[:2], [(0x9207, (0xFFFFFFFF, 0), None), (0x920C, (0, 0), None)])
        self.assertIn((0x1016, (0x5013,), b'\x13\x80'), calls)

    def test_memory_write_schema_rejects_bool_and_oversized_hex(self):
        self.assertEqual(validate('memory_write', dict(address=0xa10000000, data_hex='00')),
                         dict(address=0xa10000000, data_hex='00'))
        for arguments in (dict(address=True, data_hex='00'),
                          dict(address=0, data_hex='00' * 1009),
                          dict(address=0, data_hex='00', extra=1)):
            with self.subTest(arguments=str(arguments)[:80]), self.assertRaises(HTTPError):
                self.client.submit('memory_write', arguments)
        self.assertIsNone(self.bridge.take())

    def test_audit_write_failure_does_not_enqueue_camera_action(self):
        self.bridge.audit_path = Path(self.directory.name) / 'missing' / 'audit.jsonl'
        with self.assertRaises(HTTPError) as caught:
            self.client.submit('connect')
        self.assertEqual(caught.exception.code, 500)
        self.assertIsNone(self.bridge.take())
        self.bridge.audit_path = Path(self.directory.name) / 'recovered.jsonl'

    def test_close_retires_discovery_and_queued_work(self):
        self.client.submit('connect', identifier='queued')
        self.bridge.close()
        self.assertFalse(self.bridge.discovery.exists())
        self.assertEqual(self.bridge.snapshot('queued')['status'], 'failed')

    def test_log_failure_between_enqueue_and_dispatch_rejects_operation(self):
        self.client.submit('connect', identifier='not-dispatched')
        self.bridge.audit_path = Path(self.directory.name) / 'missing' / 'audit.jsonl'
        with self.assertRaises(OSError):
            self.bridge.take()
        self.assertIsNone(self.bridge.active)
        self.assertEqual(self.bridge.snapshot('not-dispatched')['status'], 'failed')
        self.bridge.close()
        self.assertFalse(self.bridge.discovery.exists())


class VisibleWorkflowTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        try:
            self.window = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        from z8_debug_gui import DebugApp
        self.directory = tempfile.TemporaryDirectory()
        self.endpoint = Endpoint(output='workbench fixture output\n'.encode())
        self.worker = DebugWorker(lambda emit, cancel: DebugSession(emit, lambda: self.endpoint, cancel))
        self.app = DebugApp(self.window, self.worker, automation=True, bridge_directory=self.directory.name)
        self.window.withdraw()
        self.client = WorkbenchClient(self.app.bridge.discovery)
        self.addCleanup(self.cleanup)

    def cleanup(self):
        if not self.app.destroyed:
            self.app.close()
            end = time.monotonic() + 4
            while not self.app.destroyed and time.monotonic() < end:
                self.window.update()
                time.sleep(.01)
        self.worker.thread.join(3)
        self.directory.cleanup()

    def complete(self, identifier):
        end = time.monotonic() + 5
        while time.monotonic() < end:
            self.window.update()
            row = self.client.result(identifier)
            if row['status'] in ('completed', 'failed'):
                return row
            time.sleep(.01)
        self.fail('workbench request did not finish: ' + identifier)

    def test_offline_then_serial_usb_operations_are_visible_and_not_duplicated(self):
        self.client.submit('workbench_status', identifier='offline')
        offline = self.complete('offline')
        self.assertFalse(offline['result']['connected'])
        self.assertEqual(self.endpoint.opens, 0)
        self.client.submit('connect', identifier='connect')
        self.client.submit('execute', {'line': 'echo visible'}, identifier='command')
        self.client.submit('execute', {'line': 'echo visible'}, identifier='command')
        self.assertEqual(self.complete('connect')['status'], 'completed')
        result = self.complete('command')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['output'], 'workbench fixture output\n')
        self.assertEqual(self.endpoint.opens, 1)
        self.assertEqual(self.endpoint.submits(5), 1)
        self.assertEqual(self.app.current_page, 'calls')
        visible = self.app.calls_text.get('1.0', 'end')
        self.assertIn('echo visible', visible)
        self.assertIn('自动化 #command', visible)
        self.assertIn('workbench fixture output', visible)
        events = [json.loads(x) for x in self.app.bridge.audit_path.read_text(encoding='utf-8').splitlines()]
        self.assertEqual(sum(e['kind'] == 'dispatch' and e.get('request_id') == 'command' for e in events), 1)
        self.assertTrue(any(e['kind'] == 'result' and e.get('request_id') == 'command' for e in events))

    def test_native_call_is_visible_and_duplicate_id_executes_once(self):
        self.client.submit('connect', identifier='native-connect')
        self.assertEqual(self.complete('native-connect')['status'], 'completed')
        arguments = dict(address=0x40183490, args=[7])
        self.client.submit('native_call', arguments, identifier='native-once')
        self.client.submit('native_call', arguments, identifier='native-once')
        result = self.complete('native-once')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['result']['kind'], 1)
        self.assertEqual(result['result']['result'], self.endpoint.native_result)
        self.assertEqual(self.endpoint.submits(5), 1)
        visible = self.app.calls_text.get('1.0', 'end')
        self.assertIn('native_call', visible)
        self.assertIn(str(0x40183490), visible)
        self.assertIn('自动化 #native-once', visible)
        self.assertIn(str(self.endpoint.native_result), visible)

    def test_memory_write_is_visible_and_uses_existing_worker(self):
        self.client.submit('connect', identifier='write-connect')
        self.assertEqual(self.complete('write-connect')['status'], 'completed')
        self.client.submit('memory_write', dict(address=0xa10000000, data_hex='01020304'),
                           identifier='write-scratch')
        result = self.complete('write-scratch')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['result']['bytes'], 4)
        self.assertEqual(self.endpoint.memory_writes, [(0xa10000000, bytes.fromhex('01020304'))])
        self.assertEqual(self.endpoint.opens, 1)
        visible = self.app.calls_text.get('1.0', 'end')
        self.assertIn('memory_write', visible)
        self.assertIn('01020304', visible)
        self.assertIn('自动化 #write-scratch', visible)

    def test_failure_is_visible_and_does_not_implicitly_connect(self):
        self.client.submit('memory_read', {'address': 0x40000000}, identifier='no-camera')
        result = self.complete('no-camera')
        self.assertEqual(result['status'], 'failed')
        self.assertIn('请先连接', result['error']['error'])
        self.assertEqual(self.endpoint.opens, 0)
        self.assertIn('请先连接', self.app.calls_text.get('1.0', 'end'))


class CardUploadVisibleWorkflowTests(unittest.TestCase):
    """Real loopback/Tk/worker, explicitly synthetic RAM and card filesystem."""
    def setUp(self):
        import tkinter as tk
        try:
            self.window = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.window.withdraw()
        from z8_debug_gui import DebugApp
        from test_card_upload import SyntheticCardSession, install_synthetic_profiles, package, REMOTE, BACKUP
        self.directory = tempfile.TemporaryDirectory()
        self.folder = Path(self.directory.name)
        install_synthetic_profiles(self, self.folder)
        self.old = package(bytes((i*7) & 255 for i in range(100000)))
        payload = bytearray(self.old[152:])
        payload[:2000] = b'q'*2000
        self.new = package(payload)
        self.source, self.base = self.folder/'module.wlm', self.folder/'base.wlm'
        self.source.write_bytes(self.new)
        self.base.write_bytes(self.old)
        self.session = SyntheticCardSession()
        self.session.add(REMOTE, self.old)
        def factory(emit, cancel):
            self.session.emit, self.session.cancel = emit, cancel
            return self.session
        self.worker = DebugWorker(factory)
        self.app = DebugApp(self.window, self.worker, automation=True,
                            bridge_directory=self.folder/'bridge')
        self.client = WorkbenchClient(self.app.bridge.discovery)
        self.arguments = dict(source=str(self.source), remote=REMOTE, backup=BACKUP, base_source=str(self.base))
        self.addCleanup(self.cleanup)
        self.client.submit('connect', identifier='synthetic-card-connect')
        self.assertEqual(self.complete('synthetic-card-connect')['status'], 'completed')

    def cleanup(self):
        if not self.app.destroyed:
            self.app.close()
            end = time.monotonic()+4
            while not self.app.destroyed and time.monotonic() < end:
                self.window.update()
                time.sleep(.01)
        self.worker.thread.join(3)
        self.directory.cleanup()

    def complete(self, identifier):
        end = time.monotonic()+10
        while time.monotonic() < end:
            self.window.update()
            row = self.client.result(identifier)
            if row['status'] in ('completed', 'failed'):
                return row
            time.sleep(.01)
        self.fail('synthetic card request did not finish')

    def test_single_request_copy_verify_rename_stages_are_visible_and_audited(self):
        from test_card_upload import REMOTE, BACKUP
        first = self.client.submit('card_upload', self.arguments, identifier='card-install-once')
        self.client.submit('card_upload', self.arguments, identifier='card-install-once')
        row = self.complete('card-install-once')
        self.assertEqual(row['status'], 'completed')
        self.assertTrue(row['result']['complete'])
        self.assertEqual(row['result']['verification'], 'readback-chunk-sha256')
        self.assertEqual(self.session.content(REMOTE), self.new)
        self.assertEqual(self.session.content(BACKUP), self.old)
        self.assertEqual(sum(name == 'allocate' for name, _ in self.session.calls), 1)
        self.assertEqual(self.session.connected_count, 1)
        self.assertEqual(self.app.current_page, 'calls')
        visible = self.app.calls_text.get('1.0', 'end')
        for text in ('card_upload', 'card-install-once', 'upload-prefix', 'copy-suffix',
                     'verify-readback', 'rename-original-to-backup', 'rename-temp-to-target'):
            self.assertIn(text, visible)
        self.assertIn('verify-readback', row['output'])
        events = [json.loads(line) for line in self.app.bridge.audit_path.read_text(encoding='utf-8').splitlines()]
        own = [e for e in events if e.get('request_id') == 'card-install-once']
        self.assertEqual(sum(e['kind'] == 'dispatch' for e in own), 1)
        self.assertTrue(any(e['kind'] == 'output' and 'copy-suffix' in e['value']['text'] for e in own))
        self.assertTrue(any(e['kind'] == 'result' and e['value']['value']['complete'] for e in own))
        self.assertNotIn(self.app.bridge.token, self.app.bridge.audit_path.read_text(encoding='utf-8'))

    def test_uncertainty_snapshot_is_visible_and_same_id_never_replays(self):
        self.session.fault = 'write'
        self.client.submit('card_upload', self.arguments, identifier='card-timeout-once')
        row = self.complete('card-timeout-once')
        self.assertEqual(row['status'], 'failed')
        self.assertTrue(row['error']['card_upload']['retained'])
        self.assertEqual(row['error']['card_upload']['inflight']['function'], 'write')
        calls = list(self.session.calls)
        self.client.submit('card_upload', self.arguments, identifier='card-timeout-once')
        self.assertEqual(self.client.result('card-timeout-once')['status'], 'failed')
        self.window.update()
        self.assertEqual(self.session.calls, calls)
        self.assertIn('resources retained', self.app.calls_text.get('1.0', 'end'))
        self.assertFalse(any(name in ('close', 'release', 'rename') for name, _ in calls))


if __name__ == '__main__':
    unittest.main()
