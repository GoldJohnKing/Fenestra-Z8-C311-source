"""Instruction tests of the compiled Z8 diagnostic core with modeled native edges.

Only project-owned compiled A64 C/assembly runs in Unicorn. Native allocator,
task, original-dispatcher and PTP transfer boundaries are explicit fixtures.
This does not boot original firmware or qualify USB/RTOS/hardware behavior.
"""
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import unittest
import zlib

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import (UC_ARM64_REG_PC, UC_ARM64_REG_SP, UC_ARM64_REG_X0,
    UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3, UC_ARM64_REG_X4, UC_ARM64_REG_X30)

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT/Path(os.environ.get('Z8_DIAG_BUILD', 'build/z8-diag-compile-v2'))
REGS = (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3, UC_ARM64_REG_X4)
META_FIELDS = ('magic', 'version', 'state_bytes', 'magic_offset', 'phase_offset',
               'ready_offset', 'shutdown_offset', 'error_offset', 'worker_running_offset',
               'task_id_offset', 'task_stack_offset', 'ptp_offset', 'ptp_bytes',
               'ptp_enabled_offset', 'ptp_generation_offset', 'ptp_executions_offset', 'capabilities')


def number(value):
    return int(value, 0) if isinstance(value, str) else value


class Machine:
    def __init__(self, roots=True):
        self.report = json.loads((BUILD/'build.json').read_text(encoding='utf-8'))
        self.profile = json.loads((BUILD/'bindings.input.json').read_text(encoding='utf-8'))
        self.symbols = self.report['symbols']
        self.begin = number(self.report['code_begin'])
        self.code = (BUILD/'core.bin').read_bytes()
        if hashlib.sha256(self.code).hexdigest() != self.report['code_sha256']:
            raise AssertionError('test input differs from compiled build report')
        self.uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        self.pages = set()
        self.map(self.begin, len(self.code)); self.uc.mem_write(self.begin, self.code)
        meta = self.read(self.symbols['fx_z8_diag_metadata'], 4*len(META_FIELDS))
        self.metadata = dict(zip(META_FIELDS, struct.unpack('<'+'I'*len(META_FIELDS), meta)))
        if self.metadata['magic'] != 0x465a3844 or self.metadata['version'] != 1:
            raise AssertionError('unknown diagnostic metadata layout')
        ram_begin = number(self.profile['ram']['begin'])
        self.page_root = ram_begin+0x01000000
        anchor = self.profile['anchor']
        self.page = self.page_root+number(anchor['id'])*number(anchor['page_size'])
        self.write(self.page, struct.pack('<I', (number(anchor['id']) << 16)|2)+bytes(number(anchor['page_size'])-4))
        self.set_u64(self.page+number(anchor['descriptor_offset']), number(anchor['descriptor']))
        self.write(number(anchor['descriptor']), bytes.fromhex(anchor['descriptor_bytes']))
        self.page_before = self.read(self.page, number(anchor['page_size']))
        self.roots = number(self.profile['data']['page_roots'])
        self.write(self.roots, bytes(56))
        if roots:
            self.set_roots()
        self.session_address = number(self.profile['data']['ptp_session'])
        self.set_u32(self.session_address, 1)
        self.operations = number(self.profile['data']['ptp_operations'])
        self.write(self.operations, struct.pack('<IH', 1, 0x1001)+bytes(number(self.profile['data']['ptp_operations_capacity'])-6))
        self.stack = ram_begin+0x20000000
        self.map(self.stack, 0x20000)
        self.heap = ram_begin+0x10000000
        self.message = ram_begin+0x00300000
        self.request = ram_begin+0x00400000
        self.payload = ram_begin+0x00500000
        self.incoming = ram_begin+0x00600000
        self.output = ram_begin+0x00700000
        for at in (self.message, self.request, self.payload, self.incoming, self.output):
            self.map(at, 0x2000)
        self.stop = 0x70000000
        self.map(self.stop, 4096)
        self.allocations = []
        self.allocate_fail_at = None
        self.create_result = 17
        self.resume_result = 0
        self.create_calls = self.resume_calls = self.delay_calls = 0
        self.task = None
        self.worker_context = None
        self.original_events = []
        self.pause_original = False
        self.paused_original = None
        self.original_action = None
        self.responses = []
        self.sent = []
        self.boundaries = {}
        for name, value in self.profile['native'].items():
            self.boundaries[number(value)] = name
        self.boundaries[self.symbols['fx_z8_system_original']] = 'system_original'
        for name in ('lookup', 'session', 'operations'):
            self.boundaries[self.symbols['fx_z8_ptp_original_'+name]] = 'original_'+name
        for at in self.boundaries:
            self.map(at, 4)
        self.uc.hook_add(UC_HOOK_CODE, self.hook)

    def map(self, address, size):
        for page in range(address & ~4095, (address+size+4095) & ~4095, 4096):
            if page not in self.pages:
                self.uc.mem_map(page, 4096)
                self.pages.add(page)

    def write(self, address, data):
        self.map(address, len(data)); self.uc.mem_write(address, bytes(data))

    def read(self, address, size):
        return bytes(self.uc.mem_read(address, size))

    def u32(self, address):
        return struct.unpack('<I', self.read(address, 4))[0]

    def u64(self, address):
        return struct.unpack('<Q', self.read(address, 8))[0]

    def set_u32(self, address, value):
        self.write(address, struct.pack('<I', value & 0xffffffff))

    def set_u64(self, address, value):
        self.write(address, struct.pack('<Q', value))

    def set_roots(self):
        self.set_u64(self.roots+8*number(self.profile['anchor']['group']), self.page_root)

    def owner(self):
        pointer = self.u64(self.page+number(self.profile['anchor']['descriptor_offset']))
        return 0 if pointer == number(self.profile['anchor']['descriptor']) else pointer

    def field(self, key):
        owner = self.owner()
        if not owner:
            raise AssertionError('no published owner')
        return self.u32(owner+self.metadata[key+'_offset'])

    def ptp_field(self, key):
        return self.u32(self.owner()+self.metadata['ptp_offset']+self.metadata['ptp_'+key+'_offset'])

    def return_native(self, value=0):
        self.uc.reg_write(UC_ARM64_REG_X0, value & ((1 << 64)-1))
        self.uc.reg_write(UC_ARM64_REG_PC, self.uc.reg_read(UC_ARM64_REG_X30))

    def hook(self, uc, pc, size, context):
        del size, context
        name = self.boundaries.get(pc)
        if not name:
            return
        args = [uc.reg_read(reg) for reg in REGS]
        if name == 'allocate':
            self.allocations.append((args[0], args[1]))
            if self.allocate_fail_at == len(self.allocations):
                self.return_native(0); return
            address = (self.heap+15) & ~15
            self.heap = address+args[0]+16
            self.write(address, bytes(args[0]))
            self.return_native(address)
        elif name == 'task_create':
            self.create_calls += 1
            blob = self.read(args[0], 56)
            attrs, reserved, task_context, entry, priority, reserved2, stack_bytes, stack, processor, affinity = struct.unpack('<IIQQIIQQII', blob)
            self.task = {'attributes': attrs, 'reserved': reserved, 'context': task_context,
                         'entry': entry, 'priority': priority, 'reserved2': reserved2,
                         'stack_bytes': stack_bytes, 'stack': stack, 'processor': processor, 'affinity': affinity}
            self.return_native(self.create_result)
        elif name == 'task_resume':
            self.resume_calls += 1
            if args[0] != (self.create_result & 0xffffffff):
                raise AssertionError('resume did not use native creator result')
            self.return_native(self.resume_result)
        elif name == 'task_delay':
            self.delay_calls += 1
            if args[0] != number(self.profile['task']['delay_ticks']):
                raise AssertionError('delay did not use supplied native ticks')
            self.return_native(0)
            self.stop_reason = 'native_delay'
            uc.emu_stop()
        elif name == 'system_original':
            event = self.u32(args[0]+number(self.profile['events']['message_id_offset']))
            self.original_events.append(event)
            if self.original_action:
                self.original_action(event)
            if self.pause_original and event == number(self.profile['events']['startup_complete']):
                self.pause_original = False
                self.paused_original = uc.context_save()
                self.stop_reason = 'original_pause'
                uc.emu_stop()
            else:
                self.return_native(0x1234abcd)
        elif name == 'ptp_payload':
            self.return_native(self.payload)
        elif name == 'ptp_capacity':
            self.return_native(1056)
        elif name == 'ptp_incoming':
            self.return_native(self.incoming)
        elif name == 'ptp_response':
            self.responses.append({'code': args[1], 'mode': args[4]})
            self.return_native()
        elif name == 'ptp_send':
            self.sent.append(self.read(args[1], args[2]))
            self.return_native(1)
        elif name == 'original_lookup':
            self.return_native(0)
        elif name == 'original_session':
            self.set_u32(self.session_address, args[0])
            self.return_native()
        elif name == 'original_operations':
            count = self.u32(args[2]); length = 4+2*count
            if length > args[1]:
                self.return_native(0)
            else:
                self.write(args[0], self.read(args[2], length)); self.return_native(length)
        else:
            raise AssertionError('unmodeled native boundary '+name)

    def run(self, start):
        self.stop_reason = None
        self.uc.emu_start(start, self.stop, count=1000000)
        pc = self.uc.reg_read(UC_ARM64_REG_PC)
        if pc != self.stop and self.stop_reason is None:
            raise AssertionError('instruction allowance exhausted at '+hex(pc))

    def call(self, entry, *args):
        if isinstance(entry, str):
            entry = self.symbols[entry]
        self.uc.reg_write(UC_ARM64_REG_SP, self.stack+(0xf000 if self.paused_original is not None else 0x1f000))
        self.uc.reg_write(UC_ARM64_REG_X30, self.stop)
        for reg, value in zip(REGS, (*args, 0, 0, 0, 0, 0)):
            self.uc.reg_write(reg, value)
        self.run(entry)
        return self.uc.reg_read(UC_ARM64_REG_X0)

    def event(self, name):
        self.write(self.message, bytes(128))
        self.set_u32(self.message+number(self.profile['events']['message_id_offset']), number(self.profile['events'][name]))
        return self.call('fx_z8_system_dispatch', self.message, 1)

    def resume_startup_original(self):
        saved = self.paused_original
        self.paused_original = None
        self.uc.context_restore(saved)
        self.return_native(0x1234abcd)
        self.run(self.uc.reg_read(UC_ARM64_REG_PC))
        return self.uc.reg_read(UC_ARM64_REG_X0)

    def worker_once(self):
        if not self.task:
            raise AssertionError('no native task record')
        if self.worker_context is None:
            self.uc.reg_write(UC_ARM64_REG_SP, self.task['stack']+self.task['stack_bytes']-16)
            self.uc.reg_write(UC_ARM64_REG_X30, self.stop)
            self.uc.reg_write(UC_ARM64_REG_X0, self.task['context'])
            entry = self.task['entry']
        else:
            self.uc.context_restore(self.worker_context)
            entry = self.uc.reg_read(UC_ARM64_REG_PC)
        before = self.delay_calls
        self.run(entry)
        if self.delay_calls != before+1:
            raise AssertionError('worker did not reach one modeled native delay')
        self.worker_context = self.uc.context_save()

    def native_operation(self, opcode, transaction, parameters=b'', frame=None):
        query = struct.pack('<IHHI', 12+len(parameters), 1, opcode, transaction)+parameters
        self.write(self.request, query)
        if frame is not None:
            self.write(self.payload, frame)
            self.write(self.incoming, struct.pack('<IHHI', 12+len(frame), 2, opcode, transaction)+frame)
        descriptor = self.call('fx_z8_ptp_lookup', opcode)
        if not descriptor:
            raise AssertionError('no native vendor descriptor')
        # Native ABI execute callback is independently checked at descriptor+48.
        execute = self.u64(descriptor+48)
        return self.call(execute, descriptor, self.request)

    def request_frame(self, opcode, session, request_id, payload=b''):
        frame = bytearray(struct.pack('<4sBBHQIIII', b'FXP2', 2, 0, opcode, session, request_id, len(payload), 0, 0)+payload)
        struct.pack_into('<I', frame, 28, zlib.crc32(frame) & 0xffffffff)
        return bytes(frame)

    def job(self, opcode, session, request_id, payload=b''):
        self.native_operation(0x95e1, request_id*2, frame=self.request_frame(opcode, session, request_id, payload))
        if self.responses[-1]['code'] != 0x2001:
            raise AssertionError('submit rejected')
        self.worker_once()
        self.native_operation(0x95e2, request_id*2+1, struct.pack('<QIII', session, request_id, 0, 1056))
        if self.responses[-1]['code'] != 0x2001:
            raise AssertionError('fetch rejected')
        return self.sent[-1]


@unittest.skipUnless((BUILD / 'build.json').is_file(), 'requires a locally compiled diagnostic core')
class Z8DiagInstructionTests(unittest.TestCase):
    def test_prepare_clone_original_once_and_deferred_worker_enable(self):
        m = Machine(); result = m.event('startup_complete')
        self.assertEqual(result, 0x1234abcd)
        self.assertEqual(m.original_events, [number(m.profile['events']['startup_complete'])])
        self.assertEqual(m.read(m.owner(), 64), bytes.fromhex(m.profile['anchor']['descriptor_bytes']))
        page_after = bytearray(m.read(m.page, number(m.profile['anchor']['page_size'])))
        at = number(m.profile['anchor']['descriptor_offset'])
        page_after[at:at+8] = m.page_before[at:at+8]
        self.assertEqual(bytes(page_after), m.page_before)
        self.assertEqual((m.field('phase'), m.field('ready'), m.ptp_field('enabled')), (2, 0, 0))
        self.assertEqual(m.call('fx_z8_diag_active'), 0)
        self.assertEqual((m.create_calls, m.resume_calls), (1, 1))
        for key in ('attributes', 'priority', 'processor', 'affinity', 'stack_bytes'):
            self.assertEqual(m.task[key], number(m.profile['task'][key]))
        self.assertEqual(m.task['context'], m.owner())
        self.assertEqual(m.task['stack'] % 16, 0)
        m.worker_once()
        self.assertEqual((m.field('phase'), m.field('ready'), m.ptp_field('enabled')), (3, 1, 1))
        self.assertEqual(m.call('fx_z8_diag_active'), 1)

    def test_shutdown_inside_stock_startup_prevents_worker_creation(self):
        m = Machine(); m.pause_original = True; m.event('startup_complete')
        self.assertIsNotNone(m.paused_original)
        self.assertEqual((m.field('phase'), m.ptp_field('enabled'), m.create_calls), (1, 0, 0))
        m.event('shutdown')
        self.assertEqual(m.field('phase'), 4)
        self.assertEqual(m.resume_startup_original(), 0x1234abcd)
        self.assertEqual((m.create_calls, m.resume_calls, m.ptp_field('enabled')), (0, 0, 0))
        self.assertEqual(m.original_events, [19, 7])
        self.assertEqual(m.call('fx_z8_diag_active'), 0)

    def test_shutdown_before_first_worker_entry_cannot_enable_late(self):
        m = Machine(); m.event('startup_complete'); m.event('shutdown'); m.worker_once()
        self.assertEqual((m.field('phase'), m.field('ready'), m.ptp_field('enabled')), (4, 0, 0))
        self.assertEqual(m.call('fx_z8_diag_active'), 0)

    def test_shutdown_after_active_keeps_queue_closed(self):
        m = Machine(); m.event('startup_complete'); m.worker_once(); m.event('shutdown'); m.worker_once()
        self.assertEqual((m.field('phase'), m.field('worker_running'), m.ptp_field('enabled')), (4, 0, 0))
        m.native_operation(0x95e0, 1)
        self.assertEqual(m.responses[-1]['code'], 0x2005)

    def test_duplicate_startup_does_not_create_or_resume_twice(self):
        m = Machine(); m.event('startup_complete'); m.event('startup_complete'); m.worker_once(); m.event('startup_complete')
        self.assertEqual((m.create_calls, m.resume_calls), (1, 1))
        self.assertEqual(m.original_events, [19, 19, 19])
        self.assertEqual(m.field('phase'), 3)

    def test_task_creator_failure_is_closed_and_retained(self):
        m = Machine(); m.create_result = -9; m.event('startup_complete')
        self.assertEqual((m.field('phase'), m.field('shutdown'), m.field('error')), (5, 1, 0xfffffff7))
        self.assertEqual((m.create_calls, m.resume_calls, m.ptp_field('enabled')), (1, 0, 0))
        m.event('startup_complete')
        self.assertEqual(m.create_calls, 1)

    def test_resume_failure_and_late_entry_are_closed(self):
        m = Machine(); m.resume_result = -8; m.event('startup_complete'); m.worker_once()
        self.assertEqual((m.field('phase'), m.field('shutdown'), m.field('error'), m.ptp_field('enabled')), (5, 1, 0xfffffff8, 0))

    def test_stack_failure_is_closed_and_no_task_is_created(self):
        m = Machine(); m.allocate_fail_at = 2; m.event('startup_complete')
        self.assertEqual((m.field('phase'), m.field('error'), m.create_calls), (5, 0xf8000002, 0))

    def test_missing_entry_root_has_no_late_prepare_fallback(self):
        m = Machine(roots=False); m.original_action = lambda event: m.set_roots()
        m.event('startup_complete')
        self.assertEqual((m.owner(), m.create_calls, m.resume_calls), (0, 0, 0))
        m.native_operation(0x95e0, 1)
        self.assertEqual(m.responses[-1]['code'], 0x2005)

    def test_descriptor_mismatch_fails_before_allocation(self):
        m = Machine()
        address = number(m.profile['anchor']['descriptor'])
        changed = bytearray(m.read(address, 64)); changed[0] ^= 1
        m.write(address, changed)
        m.event('startup_complete')
        self.assertEqual((m.owner(), len(m.allocations), m.create_calls), (0, 0, 0))
        self.assertEqual(m.call('fx_z8_diag_active'), 0)

    def test_stock_replacing_prepared_anchor_prevents_worker_creation(self):
        m = Machine(); held = []
        def replace_anchor(event):
            held.append(m.owner())
            m.set_u64(m.page+number(m.profile['anchor']['descriptor_offset']), number(m.profile['anchor']['descriptor']))
        m.original_action = replace_anchor
        m.event('startup_complete')
        self.assertEqual((m.owner(), m.create_calls), (0, 0))
        self.assertEqual(m.u32(held[0]+m.metadata['phase_offset']), 5)
        self.assertEqual(m.u32(held[0]+m.metadata['error_offset']), 0xf8000003)

    def test_native_ptp_queue_status_echo_identity_and_unsupported(self):
        m = Machine(); m.event('startup_complete')
        # Inactive DeviceInfo retains only the stock operation array.
        size = m.call('fx_z8_ptp_operations', m.output, 512, m.operations)
        self.assertEqual((size, m.u32(m.output)), (6, 1))
        m.worker_once()
        size = m.call('fx_z8_ptp_operations', m.output, 512, m.operations)
        self.assertEqual((size, m.u32(m.output)), (14, 5))
        m.native_operation(0x95e0, 1)
        hello = m.sent[-1]
        self.assertEqual(hello[:4], b'FXP2')
        self.assertEqual(struct.unpack_from('<I', hello, 20)[0], 259)
        session = struct.unpack_from('<Q', hello, 8)[0]
        frame = m.request_frame(1, session, 1)
        m.native_operation(0x95e1, 2, frame=frame)
        self.assertEqual(m.ptp_field('executions'), 0, 'USB callback executed a backend')
        m.worker_once()
        m.native_operation(0x95e2, 3, struct.pack('<QIII', session, 1, 0, 1056))
        reply = m.sent[-1]
        self.assertEqual(struct.unpack_from('<III', reply, 32), (311, 1, 259))
        self.assertEqual(struct.unpack_from('<II', reply, 48), (3, 1))
        echo = b'\x00\xffZ8\x80\x00'
        self.assertEqual(m.job(2, session, 2, echo)[32:], echo)
        identity = m.job(9, session, 3)[32:]
        self.assertEqual(identity[:4], b'FXI1')
        self.assertEqual(identity[64:96], bytes.fromhex(m.profile['application']['sha256']))
        self.assertEqual(identity[128:160], bytes.fromhex(m.report['debug_build_identity']))
        unsupported = m.job(7, session, 4)
        self.assertEqual(struct.unpack_from('<II', unsupported, 20), (0, 0x80000005))
        old_generation = m.ptp_field('generation')
        m.call('fx_z8_ptp_session', 2)
        self.assertGreater(m.ptp_field('generation'), old_generation)


def main():
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Z8DiagInstructionTests))
    build = json.loads((BUILD/'build.json').read_text(encoding='utf-8'))
    evidence = {'schema': 'fenestra.z8-diagnostic-instruction-tests/v1', 'passed': result.wasSuccessful(),
        'tests_run': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
        'code_sha256': build['code_sha256'], 'debug_build_identity': build['debug_build_identity'],
        'test_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'executed': 'project-owned compiled A64 diagnostic core in Unicorn',
        'modeled_boundaries': ['native allocator', 'native task create/resume/delay',
            'original system dispatcher', 'original PTP lookup/session/operation-list helper',
            'native PTP payload/response/send'],
        'not_executed': ['original Nikon function bodies', 'full-system boot', 'physical camera', 'USB device'],
        'qemu_qualified': False, 'physical_qualified': False, 'flashable': False}
    (BUILD/'emulation.json').write_text(json.dumps(evidence, indent=2)+'\n', encoding='utf-8')
    return int(not result.wasSuccessful())


if __name__ == '__main__':
    raise SystemExit(main())
