"""Explicit synthetic card/DebugSession fixtures. Never opens USB, PTP or WPD."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'host'))
import card_upload
from card_upload import ALLOCATION, CHUNK, COLD_RETRY3_ID, MISSING, UploadError, UploadUncertain, card_paths, load_profile
from z8_debug_session import DebugSession
from workbench_bridge import validate

TARGET = hashlib.sha256(b'synthetic card target').digest()
REMOTE = r'B:\FENESTRA\module.wlm'
BACKUP = r'B:\FENESTRA\module.backup'
TEMP = r'B:\FENESTRA\module.uploading'


def package(payload):
    """A real, independently preflighted service WLM; not a firmware blob."""
    raw = bytearray(152 + len(payload))
    raw[:8] = b'FENESTRA'
    struct.pack_into('<4I', raw, 8, 2, 128, 1, 1)
    raw[24:56] = TARGET
    struct.pack_into('<5IQI', raw, 88, len(raw), len(payload), 0, 1, 0, 0x310000, 1)
    struct.pack_into('<6I', raw, 128, 0, 152, len(payload), len(payload), 5, 4)
    raw[152:] = payload
    raw[56:88] = hashlib.sha256(raw[128:]).digest()
    return bytes(raw)


def install_synthetic_profiles(test, folder):
    profile_path = folder / 'card-native-c311.json'
    for cold, path in ((False, profile_path),
                       (True, profile_path.with_name('card-native-c311-cold-retry3.json'))):
        base = 0x100000 if cold else 0x200000
        functions = {
            name: dict(address=base + 0x40 * index,
                       hex32=hashlib.sha256(name.encode('ascii')).hexdigest())
            for index, name in enumerate(('open', 'close', 'write', 'rename', 'read',
                                          'allocate', 'release', 'sha256', 'cache'))
        }
        data = dict(schema='fenestra.workbench-card-native-c311/v1',
                    build_identity=COLD_RETRY3_ID if cold else 'a1' * 32,
                    application_sha256=TARGET.hex(), code_sha256='c1' * 32,
                    functions=functions,
                    native_ram=dict(begin=0xa00000000, end=0xa40000000, alignment=8),
                    write_cache=dict(function='cache', context=0, operation=4))
        path.write_text(json.dumps(data), encoding='utf-8')
    patcher = patch.object(card_upload, 'PROFILE', profile_path)
    patcher.start()
    test.addCleanup(patcher.stop)


class SyntheticCardSession(DebugSession):
    """Only in-memory RAM and FS, exercising the production upload helper."""
    def __init__(self, emit=None, cancel=None, build_identity=None, retained_path=None, client_session=0x500000002):
        self.events = []
        super().__init__(emit or (lambda k, v: self.events.append((k, v))),
                         factory=lambda: (_ for _ in ()).throw(AssertionError('no physical transport')), cancel=cancel,
                         retained_path=retained_path)
        self.profile = load_profile(build_identity)
        self.client = SimpleNamespace(pending=None, session=client_session)
        self.report = dict(model='Nikon Z8', firmware='C 3.11', fenestra_active=True,
            usb_debug_connected=True, capabilities=0x1ff, build_identity=self.profile['build_identity'],
            application_sha256=self.profile['application_sha256'])
        self.names = {v['address']: k for k, v in self.profile['functions'].items()}
        self.code = {v['address']: bytes.fromhex(v['hex32']) for v in self.profile['functions'].values()}
        self.ram = bytearray(ALLOCATION)
        self.dma = bytearray(ALLOCATION)
        self.base_address = 0xa10020000
        self.files, self.handles = {}, {}
        self.calls, self.writes, self.reads, self.io_sizes = [], [], [], []
        self.fault = None
        self.fault_when = None
        self.last_value = None
        self.echoes = 0
        self.short = None
        self.corrupt_hash = False
        self.corrupt_ram_hash = False
        self.clean_error = False
        self.clean_effective = True
        self.sign_missing = False
        self.next_fd = 0
        self.recovered_calls = 0
        self.connected_count = 0
        self.ram_fault = False

    def connect(self):
        self.connected_count += 1
        return self.report

    def disconnect(self):
        # No transport, and deliberately no native cleanup in this fixture.
        self.client = None
        return dict(disconnected=True)

    def echo(self):
        self._require()
        self.echoes += 1
        return dict(echo_verified=True)

    def share_camera(self, other):
        """A second window on the same synthetic camera boot: card, handles and RAM."""
        for name in ('files', 'handles', 'ram', 'dma', 'next_fd', 'base_address'):
            setattr(self, name, getattr(other, name))

    def add(self, name, value):
        self.files[name.casefold()] = bytes(value)

    def content(self, name):
        return self.files.get(name.casefold())

    def ram_offset(self, address, count):
        offset = address-self.base_address
        if not 0 <= offset <= len(self.ram)-count:
            raise AssertionError('out-of-allocation RAM access')
        return offset

    def memory_write(self, address, data_hex):
        self._require()
        data = bytes.fromhex(data_hex)
        if len(data) > 1008:
            raise AssertionError('oversized memory write')
        at = self.ram_offset(address, len(data))
        self.ram[at:at+len(data)] = data
        self.writes.append((address, len(data)))
        if self.ram_fault:
            self.ram_fault = False
            self.client.pending = (17, 7, b'explicit synthetic pending frame')
            raise TimeoutError('synthetic lost RAM-write response')
        return dict(bytes=len(data))

    def memory_read(self, address, count=256):
        self._require()
        self.reads.append((address, count))
        data = self.code[address] if address in self.code else self.ram[self.ram_offset(address, count):self.ram_offset(address, count)+count]
        return dict(bytes=len(data), hex=bytes(data).hex())

    def string(self, pointer):
        at = self.ram_offset(pointer, 1)
        return bytes(self.ram[at:]).split(b'\0', 1)[0].decode('ascii')

    def native_call(self, address, args=(), timeout_ms=5000):
        self._require()
        name = self.names[address]
        self.calls.append((name, tuple(args)))
        value = 0
        if name == 'allocate':
            if tuple(args) != (ALLOCATION, 0):
                raise AssertionError('allocation must remain 64 KiB')
            value = self.base_address
        elif name == 'release':
            if args != [self.base_address]:
                raise AssertionError('foreign release')
        elif name == 'open':
            path, mode, zero = self.string(args[0]).casefold(), args[1], args[2]
            if mode == 0 and path not in self.files:
                value = (0xffffffff00000000 | MISSING) if self.sign_missing else MISSING
            else:
                if mode == 0x101:
                    if path in self.files:
                        raise AssertionError('create must not overwrite an existing file')
                    self.files[path] = b''
                elif mode != 0:
                    raise AssertionError('unexpected open mode')
                value = self.next_fd
                self.next_fd += 1
                self.handles[value] = [path, 0, mode]
        elif name in ('read', 'write'):
            fd, buffer, n, done = args[:4]
            if not 1 <= n <= CHUNK:
                raise AssertionError('I/O exceeds cache-safe adapter bounds')
            if name == 'write' and args[4] != 0:
                raise AssertionError('write ABI')
            self.io_sizes.append((name, n))
            path, cursor, mode = self.handles[fd]
            at = self.ram_offset(buffer, n)
            count = n
            if self.short == name:
                self.short = None
                count -= 1
            if name == 'read':
                piece = self.files[path][cursor:cursor+count]
                count = len(piece)
                self.ram[at:at+count] = piece
            else:
                # Explicit noncoherent DMA model: a CPU write is invisible
                # until the target cache-clean operation reaches PoC.
                piece = bytes(self.dma[at:at+count])
                original = self.files[path]
                self.files[path] = original[:cursor]+piece+original[cursor+count:]
            self.handles[fd][1] += count
            struct.pack_into('<I', self.ram, self.ram_offset(done, 4), count)
        elif name == 'cache':
            context, pointer, n, operation = args
            if context != 0 or operation != 4 or not 1 <= n <= CHUNK:
                raise AssertionError('cache ABI/range must be CLEAN of owned source')
            at = self.ram_offset(pointer, n)
            if self.clean_error:
                value = 2
            elif self.clean_effective:
                self.dma[at:at+n] = self.ram[at:at+n]
        elif name == 'sha256':
            pointer, n, out = args
            at = self.ram_offset(pointer, n)
            digest = bytearray(hashlib.sha256(self.ram[at:at+n]).digest())
            stage = self.card_transfer.stage if self.card_transfer else ''
            if ((self.corrupt_hash and stage == 'verify-readback') or
                    (self.corrupt_ram_hash and stage == 'verify-host-prefix-ram')):
                digest[0] ^= 1
            start = self.ram_offset(out, 32)
            self.ram[start:start+32] = digest
        elif name == 'close':
            if args[0] not in self.handles:
                raise AssertionError('close of a handle that is not open')
            del self.handles[args[0]]
        elif name == 'rename':
            source, dest = map(lambda v: self.string(v).casefold(), args)
            if dest in self.files:
                raise AssertionError('rename destination already exists')
            self.files[dest] = self.files.pop(source)
        else:
            raise AssertionError(name)
        self.last_value = value
        if self.fault == name or (self.fault_when and self.fault_when(name, tuple(args))):
            self.fault = self.fault_when = None
            self.job = 71
            raise TimeoutError('synthetic native result timeout after side effect: '+name)
        return dict(phase=3, kind=1, result=value)

    def _recover(self):
        self.recovered_calls += 1
        self.job = None
        self.client.pending = None
        return dict(phase=3, kind=1, result=self.last_value or 0, job=71, session=self.client.session)


class CardUploadTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.folder = Path(self.directory.name)
        install_synthetic_profiles(self, self.folder)
        self.old = package(bytes((i*13+7) & 255 for i in range(190000)))
        changed = bytearray(self.old[152:])
        changed[:6144] = bytes((x^0x37) for x in changed[:6144])
        self.new = package(changed)
        self.source = self.folder/'module.wlm'
        self.source.write_bytes(self.new)
        self.base = self.folder/'base.wlm'
        self.base.write_bytes(self.old)
        self.session = SyntheticCardSession()
        self.session.add(REMOTE, self.old)

    def upload(self, **values):
        return self.session.card_upload(str(self.source), REMOTE, BACKUP, **values)

    def test_second_volume_preserves_full_descriptors_through_upload_and_verify(self):
        self.session.next_fd = 0x10000
        self.session.sign_missing = True
        receipt = self.upload(base_source=str(self.base))
        self.assertTrue(receipt['complete'])
        self.assertEqual(receipt['verified_bytes'], len(self.new))
        self.assertEqual(self.session.content(REMOTE), self.new)
        self.assertEqual(self.session.content(BACKUP), self.old)
        self.assertEqual(self.session.handles, {})
        for operation in ('read', 'write', 'close'):
            descriptors = [args[0] for name, args in self.session.calls if name == operation]
            self.assertTrue(descriptors)
            self.assertTrue(all(fd >> 16 == 1 for fd in descriptors))

    def test_open_rejects_invalid_native_volume_and_file_index(self):
        for descriptor in (0x20000, 0x1001e):
            with self.subTest(descriptor=descriptor):
                self.session = SyntheticCardSession()
                self.session.add(REMOTE, self.old)
                self.session.next_fd = descriptor
                with self.assertRaisesRegex(UploadError, 'open failed'):
                    self.upload()
                self.assertEqual(self.session.content(REMOTE), self.old)
                self.assertIsNone(self.session.content(BACKUP))
                self.assertFalse(any(name in ('write', 'close', 'rename') for name, _ in self.session.calls))

    def test_copy_suffix_upload_new_prefix_readback_and_preserve_original(self):
        self.session.sign_missing = True
        receipt = self.upload(base_source=str(self.base))
        self.assertEqual(self.session.content(REMOTE), self.new)
        self.assertEqual(self.session.content(BACKUP), self.old)
        self.assertIsNone(self.session.content(TEMP))
        self.assertTrue(receipt['complete'])
        self.assertFalse(receipt['blocking'])
        self.assertEqual(receipt['verification'], 'readback-chunk-sha256')
        self.assertEqual(receipt['newhostSHA'], hashlib.sha256(self.new).hexdigest())
        self.assertEqual(receipt['verified_bytes'], len(self.new))
        self.assertEqual(receipt['host_prefix_ram_verified_bytes'], receipt['uploaded_bytes'])
        operations = [name for name, _ in self.session.calls]
        for i, name in enumerate(operations):
            if name == 'write':
                self.assertEqual(operations[i-1], 'cache')

        self.assertGreater(receipt['reused_bytes'], 180000)
        self.assertLess(receipt['uploaded_bytes'], 6500)
        self.assertLess(sum(n for _, n in self.session.writes), 10000)
        self.assertEqual(sum(n == 'release' for n, _ in self.session.calls), 1)
        self.assertFalse(self.session.handles)
        self.assertEqual(self.source.read_bytes(), self.new)
        self.assertEqual(self.base.read_bytes(), self.old)
        self.assertEqual(len([x for x in self.session.reads if x[0] in self.session.code]), 9)
        self.assertTrue(all(n <= 32768 for _, n in self.session.io_sizes))
        self.assertEqual([x for x in self.session.io_sizes if x == ('read', 1)], [('read', 1)])
        output = ''.join(v['text'] for k, v in self.session.events if k == 'output')
        self.assertIn('verify-readback', output)
        self.assertIn('rename-original-to-backup', output)

    def test_direct_upload_and_absent_target(self):
        self.session.files.clear()
        result = self.upload()
        self.assertEqual(self.session.content(REMOTE), self.new)
        self.assertIsNone(self.session.content(BACKUP))
        self.assertFalse(result['target_existed'])
        self.assertFalse(result['original_in_backup'])
        self.assertEqual(result['uploaded_bytes'], len(self.new))
        self.assertEqual(result['reused_bytes'], 0)

    def test_suffix_at_or_below_64k_falls_back_to_plain_upload(self):
        old = package(b'a'*40000)
        self.base.write_bytes(old)
        self.session.add(REMOTE, old)
        result = self.upload(base_source=str(self.base))
        self.assertEqual(result['shared_suffix_bytes'], 0)
        self.assertEqual(result['uploaded_bytes'], len(self.new))

    def test_hash_mismatch_never_renames_and_keeps_ignored_temp(self):
        self.session.corrupt_hash = True
        with self.assertRaisesRegex(UploadError, 'SHA256 differs'):
            self.upload(base_source=str(self.base))
        self.assertEqual(self.session.content(REMOTE), self.old)
        self.assertIsNone(self.session.content(BACKUP))
        self.assertEqual(self.session.content(TEMP), self.new)
        self.assertFalse(any(n == 'rename' for n, _ in self.session.calls))
        self.assertEqual(sum(n == 'release' for n, _ in self.session.calls), 1)
        self.assertFalse(self.session.handles)
        self.assertFalse(self.session.card_transfer.blocking)

    def test_short_io_is_not_retried_or_committed(self):
        for operation in ('write', 'read'):
            with self.subTest(operation=operation):
                self.session = SyntheticCardSession()
                self.session.add(REMOTE, self.old)
                self.session.short = operation
                with self.assertRaisesRegex(UploadError, 'short'):
                    self.upload(base_source=str(self.base))
                self.assertFalse(any(n == 'rename' for n, _ in self.session.calls))
                self.assertEqual(self.session.content(REMOTE), self.old)
                self.assertFalse(self.session.handles)
                self.assertEqual(sum(n == 'release' for n, _ in self.session.calls), 1)

    def test_existing_backup_is_never_overwritten(self):
        self.session.add(BACKUP, b'keep original side file')
        with self.assertRaisesRegex(UploadError, 'existing temp/backup'):
            self.upload()
        self.assertEqual(self.session.content(BACKUP), b'keep original side file')
        self.assertEqual(self.session.content(REMOTE), self.old)
        self.assertFalse(any(n in ('write', 'rename') for n, _ in self.session.calls))
        self.assertFalse(self.session.handles)

    def test_leftover_temp_is_kept_under_a_new_name_and_upload_proceeds(self):
        self.session.add(TEMP, b'earlier attempt')
        self.session.add(TEMP + '-old1', b'older attempt')
        result = self.upload()
        self.assertTrue(result['complete'])
        self.assertEqual(self.session.content(REMOTE), self.new)
        self.assertEqual(self.session.content(TEMP + '-old1'), b'older attempt')
        self.assertEqual(self.session.content(TEMP + '-old2'), b'earlier attempt')
        self.assertEqual(result['set_aside'], [dict(source=TEMP, target=TEMP + '-old2')])
        self.assertFalse(self.session.handles)

    def create_fault(self, session):
        session.fault_when = lambda name, args: name == 'open' and args[1] == 0x101

    def test_resolve_closes_recovered_fd_releases_and_sets_temp_aside(self):
        retained = self.folder / 'card-retained.json'
        self.session = SyntheticCardSession(retained_path=retained)
        self.session.add(REMOTE, self.old)
        self.create_fault(self.session)
        with self.assertRaises(UploadUncertain):
            self.upload()
        self.assertTrue(retained.is_file())
        self.assertEqual(len(self.session.handles), 1)
        with self.assertRaisesRegex(RuntimeError, '保留状态'):
            self.session.memory_read(0xa10020000, 4)
        result = self.session.card_resolve()
        self.assertTrue(result['resolved'])
        self.assertFalse(result['blocking'])
        self.assertFalse(result['complete'])
        self.assertEqual(self.session.recovered_calls, 1)
        self.assertEqual(self.session.echoes, 1)
        self.assertFalse(self.session.handles)
        self.assertEqual(self.session.content(REMOTE), self.old)
        self.assertIsNone(self.session.content(TEMP))
        self.assertEqual(self.session.content(TEMP + '-old1'), b'')
        self.assertEqual(sum(n == 'release' for n, _ in self.session.calls), 1)
        self.assertEqual(sum(n == 'allocate' for n, _ in self.session.calls), 1)
        self.assertFalse(any(n == 'write' for n, _ in self.session.calls))
        self.assertFalse(retained.exists())
        self.assertEqual(self.session.memory_read(0xa10020000, 4)['bytes'], 4)
        with self.assertRaisesRegex(RuntimeError, '没有需要收尾'):
            self.session.card_resolve()

    def test_resolve_restores_original_moved_to_backup(self):
        self.session.fault_when = lambda name, args: name == 'rename'
        with self.assertRaises(UploadUncertain):
            self.upload()
        self.assertIsNone(self.session.content(REMOTE))
        self.session.recover()
        result = self.session.card_resolve()
        self.assertFalse(result['original_in_backup'])
        self.assertEqual(self.session.content(REMOTE), self.old)
        self.assertIsNone(self.session.content(BACKUP))
        self.assertEqual(self.session.content(TEMP + '-old1'), self.new)
        self.assertFalse(self.session.handles)

    def retained_window(self, retained):
        first = SyntheticCardSession(retained_path=retained, client_session=0x700000003)
        first.add(REMOTE, self.old)
        self.create_fault(first)
        self.session = first
        with self.assertRaises(UploadUncertain):
            self.upload()
        first.recover()
        return first

    def test_new_window_claims_retained_upload_on_the_same_boot(self):
        retained = self.folder / 'card-retained.json'
        first = self.retained_window(retained)
        second = SyntheticCardSession(retained_path=retained, client_session=0x800000001)
        second.share_camera(first)
        self.assertTrue(second.state()['card_orphan'])
        second.memory_read(0xa10020000, 4)  # an orphan no longer blocks other work
        result = second.card_resolve()
        self.assertTrue(result['resolved'])
        self.assertFalse(second.handles)
        self.assertEqual([n for n, _ in second.calls].count('close'), 2)  # owned fd + one set-aside probe
        self.assertFalse(any(n == 'allocate' for n, _ in second.calls))
        self.assertEqual(sum(n == 'release' for n, _ in second.calls), 1)
        self.assertEqual(second.content(TEMP + '-old1'), b'')
        self.assertFalse(retained.exists())
        self.assertIsNone(second.state()['card_orphan'])

    def test_after_camera_restart_native_handles_are_dropped_not_closed(self):
        retained = self.folder / 'card-retained.json'
        first = self.retained_window(retained)
        second = SyntheticCardSession(retained_path=retained, client_session=0x100000001)
        second.share_camera(first)
        second.handles.clear()  # a restart closes every native handle
        second.ram[:] = bytes(len(second.ram))
        result = second.card_resolve()
        self.assertTrue(result['resolved'])
        names = [n for n, _ in second.calls]
        self.assertEqual(names.count('allocate'), 1)
        self.assertEqual(names.count('release'), 1)
        self.assertEqual(second.content(TEMP + '-old1'), b'')
        self.assertEqual(second.content(REMOTE), self.old)
        output = ''.join(v['text'] for k, v in second.events if k == 'output')
        self.assertIn('orphan-native-state', output)

    def test_probe_reports_missing_match_and_mismatch_without_changing_the_card(self):
        before = dict(self.session.files)
        missing = self.session.card_probe(r'B:\FENESTRA\absent.wlm')
        self.assertEqual(missing, dict(path=r'B:\FENESTRA\absent.wlm', exists=False))
        self.source.write_bytes(self.old)
        same = self.session.card_probe(REMOTE, str(self.source))
        self.assertTrue(same['exists'])
        self.assertEqual(same['bytes'], len(self.old))
        self.assertTrue(same['matches_expected'])
        self.source.write_bytes(self.new)
        other = self.session.card_probe(REMOTE, str(self.source))
        self.assertFalse(other['matches_expected'])
        self.assertEqual(other['chunk_digest'], same['chunk_digest'])
        self.assertEqual(self.session.files, before)
        names = [n for n, _ in self.session.calls]
        self.assertFalse(any(n in ('write', 'rename', 'cache') for n in names))
        self.assertEqual(names.count('allocate'), names.count('release'))
        self.assertFalse(self.session.handles)
        self.assertFalse(self.session.card_transfer.blocking)
        with self.assertRaises(ValueError):
            self.session.card_probe(r'B:\FENESTRA\..\MAIN.bin')
        self.assertEqual(validate('card_probe', {'remote': REMOTE}), {'remote': REMOTE, 'expect': None})
        with self.assertRaises(ValueError):
            validate('card_probe', {'remote': r'C:\FENESTRA\x.wlm'})

    def test_reconnect_turns_retained_upload_into_a_persisted_record(self):
        retained = self.folder / 'card-retained.json'
        first = self.retained_window(retained)
        first.client = None
        first.factory = lambda: (_ for _ in ()).throw(ConnectionError('synthetic camera absent'))
        with self.assertRaises(ConnectionError):
            DebugSession.connect(first)
        self.assertIsNone(first.card_transfer)
        self.assertIsNone(first.job)
        self.assertEqual(first.card_orphan['inflight']['function'], 'open')
        self.assertEqual(json.loads(retained.read_text(encoding='utf-8'))['card_upload'], first.card_orphan)

    def test_timeout_retains_job_fd_allocation_and_recover_does_not_continue(self):
        self.session.fault = 'write'
        with self.assertRaises(UploadUncertain) as caught:
            self.upload(base_source=str(self.base))
        before = list(self.session.calls)
        state = self.session.state()['card_upload']
        self.assertTrue(state['retained'])
        self.assertEqual(state['allocation'], self.session.base_address)
        self.assertEqual(self.session.job, 71)
        self.assertEqual(len(state['fds']), 2)
        self.assertEqual(state['inflight']['function'], 'write')
        self.assertIn('card_upload', vars(caught.exception))
        with self.assertRaisesRegex(RuntimeError, '保留状态'):
            self.upload()
        self.assertEqual(self.session.calls, before)
        result = self.session.recover()
        self.assertEqual(self.session.recovered_calls, 1)
        self.assertTrue(result['card_upload']['blocking'])
        self.assertEqual(self.session.calls, before)
        self.assertFalse(any(n in ('close', 'release', 'rename') for n, _ in self.session.calls))

    def test_uncertain_memory_write_keeps_original_ptp_identity(self):
        self.session.ram_fault = True
        with self.assertRaises(UploadUncertain):
            self.upload()
        state = self.session.state()['card_upload']
        self.assertEqual(state['pending']['ptp_request'], 17)
        self.assertEqual(self.session.client.pending[0], 17)
        self.assertEqual(state['allocation'], self.session.base_address)
        self.assertFalse(any(n in ('release', 'close') for n, _ in self.session.calls))

    def test_close_timeout_is_not_closed_twice_or_freed(self):
        self.session.fault = 'close'
        with self.assertRaises(UploadUncertain):
            self.upload()
        self.assertEqual(sum(n == 'close' for n, _ in self.session.calls), 1)
        self.assertFalse(any(n == 'release' for n, _ in self.session.calls))
        self.assertTrue(self.session.card_transfer.blocking)

    def test_identity_and_all_nine_preimages_before_allocate(self):
        self.session.report['build_identity'] = '00'*32
        with self.assertRaisesRegex(UploadError, 'exact pinned'):
            self.upload()
        self.assertFalse(self.session.calls)
        self.assertFalse(self.session.reads)
        self.session = SyntheticCardSession()
        self.session.code[self.session.profile['functions']['sha256']['address']] = bytes(32)
        with self.assertRaisesRegex(UploadError, 'preimage differs: sha256'):
            self.upload()
        self.assertFalse(self.session.calls)
        self.assertEqual(len(self.session.reads), 8)  # sha256 is eighth; cache is the ninth check

    def test_cold_retry3_uses_its_own_relocated_file_read_hash_and_cache(self):
        previous = load_profile()
        self.session = SyntheticCardSession(build_identity=COLD_RETRY3_ID)
        self.assertEqual(self.session.report['build_identity'], COLD_RETRY3_ID)
        for name in ('read', 'sha256', 'cache'):
            self.assertNotEqual(self.session.profile['functions'][name]['address'], previous['functions'][name]['address'])
        result = self.upload()
        self.assertTrue(result['complete'])
        self.assertEqual(self.session.content(REMOTE), self.source.read_bytes())

    def test_path_escape_firmware_and_wrong_target_rejected_before_device_work(self):
        invalid = [r'C:\FENESTRA\module.wlm', r'B:\FENESTRA\..\module.wlm',
                   r'B:\FENESTRA\MAIN.bin', r'B:\FENESTRA\BOOT.FNC',
                   r'B:\FENESTRA\folder\module.wlm', r'B:\fenestra\module.wlm',
                   r'B:\FENESTRA\中文.wlm']
        for remote in invalid:
            with self.subTest(remote=remote), self.assertRaises(ValueError):
                self.session.card_upload(str(self.source), remote, BACKUP)
        for backup in (REMOTE, TEMP, r'A:\FENESTRA\safe.bak', r'B:\FENESTRA\x..bak',
                       r'B:\FENESTRA\other.wlm', r'B:\FENESTRA\..\safe.bak'):
            with self.subTest(backup=backup), self.assertRaises(ValueError):
                self.session.card_upload(str(self.source), REMOTE, backup)
        self.source.write_bytes(b'firmware'*100)
        with self.assertRaisesRegex(ValueError, 'WLM package'):
            self.upload()
        bad = bytearray(self.new)
        bad[24] ^= 1
        self.source.write_bytes(bad)
        with self.assertRaisesRegex(ValueError, 'target'):
            self.upload()
        self.assertFalse(self.session.calls)
        self.assertFalse(self.session.reads)


    def test_invalid_allocator_pointer_never_writes_or_releases_unknown_address(self):
        invalid = (0x80000010, 0xffffffff80000010, 0x40d00000, 0xa00000000-8,
                   0xa40000000-ALLOCATION+8, 0xa10020001)
        for pointer in invalid:
            with self.subTest(pointer=hex(pointer)):
                self.session = SyntheticCardSession()
                real_call = self.session.native_call
                def invalid_allocate(address, args=(), timeout_ms=5000):
                    if address == self.session.profile['functions']['allocate']['address']:
                        self.session.calls.append(('allocate', tuple(args)))
                        return dict(phase=3, kind=1, result=pointer)
                    return real_call(address, args, timeout_ms)
                self.session.native_call = invalid_allocate
                with self.assertRaisesRegex(UploadUncertain, 'outside pinned native RAM'):
                    self.upload()
                self.assertFalse(self.session.writes)
                self.assertEqual([name for name, _ in self.session.calls], ['allocate'])
                self.assertEqual(self.session.card_transfer.pointer, pointer)
                self.assertTrue(self.session.card_transfer.retained)

    def test_eof_check_rejects_extra_bytes_after_all_correct_chunks(self):
        real_call = self.session.native_call
        appended = False
        def with_extra_tail(address, args=(), timeout_ms=5000):
            nonlocal appended
            add_tail = (self.session.names[address] == 'close' and not appended and
                        self.session.handles[args[0]][0] == TEMP.casefold() and
                        self.session.handles[args[0]][2] == 0x101)
            value = real_call(address, args, timeout_ms)
            if add_tail:
                appended = True
                self.session.files[TEMP.casefold()] += b'x'
            return value
        self.session.native_call = with_extra_tail
        with self.assertRaisesRegex(UploadError, 'extra bytes'):
            self.upload(base_source=str(self.base))
        self.assertEqual(self.session.card_transfer.verified, len(self.new))
        self.assertEqual(self.session.content(REMOTE), self.old)
        self.assertFalse(any(name == 'rename' for name, _ in self.session.calls))

    def test_incorrect_installed_suffix_is_caught_by_temp_readback(self):
        corrupted = bytearray(self.old)
        corrupted[-3] ^= 1
        self.session.add(REMOTE, corrupted)
        with self.assertRaisesRegex(UploadError, 'SHA256 differs'):
            self.upload(base_source=str(self.base))
        self.assertEqual(self.session.content(REMOTE), bytes(corrupted))
        self.assertFalse(any(name == 'rename' for name, _ in self.session.calls))

    def test_failed_second_rename_preserves_original_in_backup(self):
        real_call = self.session.native_call
        def fail_second_rename(address, args=(), timeout_ms=5000):
            if self.session.names[address] == 'rename' and self.session.string(args[0]) == TEMP:
                self.session.calls.append(('rename', tuple(args)))
                return dict(phase=3, kind=1, result=0x80000001)
            return real_call(address, args, timeout_ms)
        self.session.native_call = fail_second_rename
        with self.assertRaisesRegex(UploadError, 'target rename failed') as caught:
            self.upload(base_source=str(self.base))
        self.assertIsNone(self.session.content(REMOTE))
        self.assertEqual(self.session.content(BACKUP), self.old)
        self.assertEqual(self.session.content(TEMP), self.new)
        self.assertTrue(caught.exception.card_upload['original_in_backup'])
        self.assertFalse(caught.exception.card_upload['committed'])
        self.assertEqual(sum(name == 'release' for name, _ in self.session.calls), 1)


    def test_dirty_cpu_dma_model_fails_without_clean_and_passes_after_clean(self):
        self.session.clean_effective = False
        with self.assertRaisesRegex(UploadError, 'readback chunk SHA256 differs'):
            self.upload(base_source=str(self.base))
        self.assertEqual(self.session.card_transfer.ram_verified, self.session.card_transfer.uploaded)
        self.assertFalse(any(name == 'rename' for name, _ in self.session.calls))
        self.assertEqual(self.session.content(REMOTE), self.old)
        self.assertNotEqual(self.session.content(TEMP), self.new)
        self.session = SyntheticCardSession()
        self.session.add(REMOTE, self.old)
        result = self.upload(base_source=str(self.base))
        self.assertTrue(result['complete'])
        self.assertEqual(self.session.content(REMOTE), self.new)
        self.assertEqual(self.session.content(BACKUP), self.old)
        self.assertGreater(result['reused_bytes'], 180000)

    def test_cache_clean_error_aborts_before_write_and_safely_cleans_up(self):
        self.session.clean_error = True
        with self.assertRaisesRegex(UploadError, 'cache CLEAN failed') as caught:
            self.upload(base_source=str(self.base))
        self.assertFalse(any(name in ('write', 'rename') for name, _ in self.session.calls))
        self.assertEqual(sum(name == 'release' for name, _ in self.session.calls), 1)
        self.assertFalse(self.session.handles)
        self.assertFalse(caught.exception.card_upload['blocking'])
        self.assertEqual(self.session.content(REMOTE), self.old)

    def test_cache_clean_timeout_retains_resources_and_never_writes_or_replays(self):
        self.session.fault = 'cache'
        with self.assertRaises(UploadUncertain) as caught:
            self.upload(base_source=str(self.base))
        state = caught.exception.card_upload
        self.assertTrue(state['retained'])
        self.assertEqual(state['inflight']['function'], 'cache')
        self.assertEqual(state['allocation'], self.session.base_address)
        self.assertEqual(len(state['fds']), 2)
        self.assertFalse(any(name in ('write', 'close', 'release', 'rename') for name, _ in self.session.calls))
        before = list(self.session.calls)
        self.session.recover()
        self.assertEqual(self.session.calls, before)
        self.assertTrue(self.session.card_transfer.blocking)

    def test_host_prefix_ram_hash_failure_aborts_before_clean_or_file_write(self):
        self.session.corrupt_ram_hash = True
        with self.assertRaisesRegex(UploadError, 'host prefix RAM chunk SHA256 differs'):
            self.upload(base_source=str(self.base))
        self.assertFalse(any(name in ('write', 'rename', 'cache') for name, _ in self.session.calls))
        self.assertEqual(self.session.content(TEMP), b'')
        self.assertEqual(self.session.content(REMOTE), self.old)
        self.assertFalse(self.session.handles)
        self.assertEqual(sum(name == 'release' for name, _ in self.session.calls), 1)

    def test_ninth_cache_preimage_is_required_before_allocate(self):
        self.session.code[self.session.profile['functions']['cache']['address']] = bytes(32)
        with self.assertRaisesRegex(UploadError, 'preimage differs: cache'):
            self.upload()
        self.assertEqual(len(self.session.reads), 9)
        self.assertFalse(self.session.calls)

    def test_bridge_schema_defaults_and_path_policy(self):
        expected = dict(source=str(self.source), remote=REMOTE, backup=BACKUP, base_source=None)
        self.assertEqual(validate('card_upload', dict(source=str(self.source), remote=REMOTE, backup=BACKUP)), expected)
        for extra in (dict(base_source=True), dict(base_source=''), dict(source=True), dict(remote='B:\\MAIN.bin'), dict(extra=1)):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                validate('card_upload', {**expected, **extra})


if __name__ == '__main__':
    unittest.main()
