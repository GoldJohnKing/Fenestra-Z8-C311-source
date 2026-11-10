"""Compiled complete-core instruction tests with explicit native boundary fixtures.

No Nikon function body is executed. Actual original initialized UI data is used;
locale style roots, allocation, RTOS task edges and missing card files are modeled.
This is neither a full-system boot nor physical USB/display/storage qualification.
"""
import hashlib
import json
import os
import re
from pathlib import Path
import struct
import sys
import unittest

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE, UcError
from unicorn.arm64_const import UC_ARM64_REG_PC, UC_ARM64_REG_X0, UC_ARM64_REG_X30
from test_z8_diag_emulation import Machine as BaseMachine, number

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'host'))
from z8_ui_profile import get_profile, INIT_FILE, INIT_RAM, INIT_BYTES, read_original

BUILD = ROOT/Path(os.environ.get('FX_Z8_BUILD', os.environ.get('Z8_FULL_BUILD', 'build/z8-full-compile-4')))
ORIGINAL = ROOT/Path(os.environ.get('Z8_ORIGINAL_MAIN', 'inputs/z8-c311-main.bin'))


class FullMachine(BaseMachine):
    def map(self,address,size):
        begin=address & ~4095;end=(address+size+4095)&~4095;run=None
        for page in range(begin,end,4096):
            if page not in self.pages:
                if run is None:run=page
                self.pages.add(page)
            elif run is not None:
                self.uc.mem_map(run,page-run);run=None
        if run is not None:self.uc.mem_map(run,end-run)

    def run(self,start):
        self.stop_reason=None
        self.uc.emu_start(start,self.stop,count=20000000)
        pc=self.uc.reg_read(UC_ARM64_REG_PC)
        if pc!=self.stop and self.stop_reason is None:raise AssertionError('full-core instruction allowance exhausted at '+hex(pc))

    def __init__(self, roots=True, directories=None, writable=False):
        self.report = json.loads((BUILD/'build.json').read_text())
        self.ui = get_profile(); self.symbols = self.report['symbols']; self.begin = 0x401a0000
        self.native_capsules=bool(self.report.get('native_capsules_backend'))
        if self.native_capsules:
            # Derive the native ID domain from this build's pinned input, never
            # from the unrelated stock offset-table length or an assumed suite.
            header_name='include/fenestra_native_locale.h'
            header=(ROOT/header_name).read_bytes()
            if self.report['source_sha256'].get(header_name)!=hashlib.sha256(header).hexdigest():
                raise AssertionError('native locale fixture differs from compiled build input')
            contract=self.report['native_capsules_backend']['arena']['locale_contract']
            match=re.search(rb'^#define FX_NATIVE_LOCALE_CORE_TEXT_BASE ([0-9]+)u$',header,re.MULTILINE)
            if not match or contract.get('abi')!=1 or contract.get('symbol')!='camera.locale.text':
                raise AssertionError('unknown native locale contract for full-core model')
            self.extension_text_base=int(match.group(1))
        else:
            self.extension_text_base=3225 if self.report.get('feature_suite_backend') else self.ui['text']['base']
        self.code = (BUILD/'core.bin').read_bytes(); original = ORIGINAL.read_bytes()
        if hashlib.sha256(original).hexdigest() != self.report['base_sha256']:
            raise AssertionError('wrong original UI data fixture')
        if hashlib.sha256(self.code).hexdigest() != self.report['code_sha256']:
            raise AssertionError('compiled core input changed')
        self.original = original
        self.uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM); self.pages = set()
        base = 0x40160000
        self.map(base, len(original)); self.uc.mem_write(base, original)
        self.uc.mem_write(self.begin, self.code)
        self.map(INIT_RAM, INIT_BYTES); self.uc.mem_write(INIT_RAM, original[INIT_FILE:INIT_FILE+INIT_BYTES])
        menu = struct.unpack('<14I', self.read(self.symbols['fx_z8_menu_metadata'], 56))
        installation = struct.unpack('<12I', self.read(self.symbols['fx_z8_install_metadata'], 48))
        startup = struct.unpack('<9I', self.read(self.symbols['fx_z8_startup_metadata'], 36))
        ptp = struct.unpack('<7I', self.read(self.symbols['fx_z8_ptp_metadata'], 28))
        step = struct.unpack('<3I', self.read(self.symbols['fx_z8_install_step_metadata'], 12))
        if menu[0] != 0x465a384d or menu[1] != 4 or installation[:3] != (menu[0], 1, menu[2]):
            raise AssertionError('unknown full-core metadata schema')
        self.metadata = {'magic': menu[0], 'state_bytes': menu[2], 'magic_offset': menu[3],
            'phase_offset': menu[4], 'activation_offset': menu[5], 'error_offset': menu[6], 'modules_offset': menu[7],
            'installation_step_offset': step[2], 'anchor_offset': installation[3], 'setup_offset': installation[4], 'installed_offset': installation[5],
            'installation_offset': installation[6], 'shutdown_offset': installation[7],
            'startup_shutdown_offset': installation[9], 'task_offset': installation[10], 'task_stack_offset': installation[11],
            'startup_offset': startup[2], 'startup_phase_offset': startup[2]+startup[3],
            'shutdown_done_offset': startup[2]+startup[6], 'ptp_offset': ptp[2], 'ptp_bytes': ptp[3],
            'ptp_enabled_offset': ptp[4], 'ptp_generation_offset': ptp[5], 'ptp_executions_offset': ptp[6]}
        def mapped(old):
            return number(self.report['native_binding_evidence'][hex(old)]['address'])
        self.mapped = mapped
        native_keys = {'allocate':0x40d30458,'release':0x40d30498,'task_create':0x40185064,'task_resume':0x401855e0,'task_delay':0x40187b00,
            'ptp_payload':0x407e337c,'ptp_capacity':0x407e33b8,'ptp_incoming':0x407e3460,'ptp_response':0x407e346c,'ptp_send':0x407e375c}
        self.profile = {'native': {key:mapped(old) for key,old in native_keys.items()},
            'anchor': {'group':2,'id':self.ui['setup']['id'],'descriptor':self.ui['setup']['descriptor'],
                'descriptor_bytes':read_original(original,self.ui['setup']['descriptor'],64).hex(), 'page_size':96,'descriptor_offset':80},
            'events': {'message_id_offset':self.report['system_events']['message_id_offset'],
                'startup_complete':self.report['system_events']['startup'],'shutdown':self.report['system_events']['shutdown']},
            'task': {'delay_ticks':10}, 'data': {'ptp_operations_capacity':512}}
        for record in self.report['native_binding_evidence'].values():
            address = number(record['address'])
            if 0xa00000000 <= address < 0xa40000000:
                self.map(address, 4096)
        ram_begin = 0xa00000000
        self.page_root = self.ui['native_pages']['page_zero']; self.page = self.page_root+self.ui['setup']['id']*96
        self.page_before = self.read(self.page,96)
        self.current_page=self.page;self.navigation=[];self.navigate_target=0
        self.roots = self.ui['native_pages']['page_roots']; self.write(self.roots,bytes(56))
        if roots:self.set_roots()
        self.session_address = mapped(0xa04a756c4); self.set_u32(self.session_address,1)
        self.operations = mapped(0xa04a75f48); self.write(self.operations,struct.pack('<IH',1,0x1001)+bytes(506))
        # Explicitly modeled initialized font/style roots; no font engine is run.
        text = self.ui['text']; font_data=ram_begin+0x02000000; attrs=font_data+0x10000
        self.write(font_data,bytes(text['base']+1))
        for language in range(text['languages']):
            table=attrs+0x1000+language*(text['base']+16)
            self.write(table,bytes(text['base']+1));self.set_u64(attrs+language*8,table)
        self.set_u64(text['font_root'],font_data);self.set_u64(text['attribute_root'],attrs)
        self.set_u64(text['offset_root'],base+text['table_directory_file'])
        self.set_u64(text['pool_root'],base+text['blob_directory_file'])
        self.set_u32(text['count_address'],text['base'])
        self.stack=ram_begin+0x20000000;self.map(self.stack,0x20000);self.heap=ram_begin+0x10000000
        self.message=ram_begin+0x00300000;self.request=ram_begin+0x00400000;self.payload=ram_begin+0x00500000
        self.incoming=ram_begin+0x00600000;self.output=ram_begin+0x00700000
        for at in (self.message,self.request,self.payload,self.incoming,self.output):self.map(at,0x2000)
        self.stop=0x70000000;self.map(self.stop,4096)
        self.live_allocations={};self.releases=[]
        self.allocations=[];self.allocate_fail_at=None;self.create_result=17;self.resume_result=0
        self.create_calls=self.resume_calls=self.delay_calls=0;self.task=None;self.worker_context=None
        self.original_events=[];self.pause_original=False;self.paused_original=None;self.original_action=None
        self.responses=[];self.sent=[];self.file_opens=[];self.worker_mode=False;self.gui_locked=False;self.gui_lock_action=None
        self.directories=set(directories if directories is not None else ('A:\\FENESTRA',))
        self.directory_opens=[];self.directory_closes=[];self.writable=writable
        self.records={};self.file_handles={};self.next_file_handle=100
        self.boundaries={number(value):key for key,value in self.profile['native'].items()}
        self.boundaries[self.symbols['fx_z8_system_original']]='system_original'
        for name in ('lookup','session','operations'):self.boundaries[self.symbols['fx_z8_ptp_original_'+name]]='original_'+name
        for old,name in ((0x402dc960,'file_open'),(0x402dcb30,'file_read'),(0x402dcbf4,'file_write'),(0x402dc9c0,'file_close'),(0x402dceb4,'file_remove')):
            self.boundaries[mapped(old)]=name
        for old,name in ((0x402dd0d4,'dir_open'),(0x402dd184,'dir_read'),(0x402dd1d4,'dir_close')):
            self.boundaries[mapped(old)]=name
        for old,name in ((0x40d30004,'gui_lock'),(0x40d2ffb0,'gui_unlock'),(0x403d6d38,'gui_current_page'),(0x403adbac,'gui_navigate'),(0x403d6908,'gui_event_group'),(0x403d69d4,'gui_event_set')):self.boundaries[mapped(old)]=name
        for at in self.boundaries:self.map(at,4)
        self.uc.hook_add(UC_HOOK_CODE,self.hook)

    def owner(self):
        pointer=self.u64(self.page+80)
        if pointer==self.ui['setup']['descriptor']:return 0
        for offset in (self.metadata['anchor_offset'],self.metadata['setup_offset']):
            candidate=pointer-offset
            try:
                if self.u32(candidate+self.metadata['magic_offset'])==self.metadata['magic']:return candidate
            except UcError:pass
        return 0

    def hook(self,uc,pc,size,context):
        name=self.boundaries.get(pc)
        if not self.begin<=pc<self.begin+len(self.code) and name is None:
            raise AssertionError('unmodeled Nikon body excluded at '+hex(pc))
        if name=='allocate':
            bytes=uc.reg_read(UC_ARM64_REG_X0)
            super().hook(uc,pc,size,context)
            address=uc.reg_read(UC_ARM64_REG_X0)
            if address:self.live_allocations[address]=bytes
            return
        if name=='release':
            address=uc.reg_read(UC_ARM64_REG_X0)
            if address not in self.live_allocations:raise AssertionError('unowned or duplicate fixture release')
            self.releases.append((address,self.live_allocations.pop(address)))
            self.return_native();return
        if name=='gui_lock':
            if self.gui_lock_action:self.gui_lock_action()
            if self.gui_locked:raise AssertionError('recursive fixture GUI lock')
            self.gui_locked=True;self.return_native()
        elif name=='gui_unlock':
            if not self.gui_locked:raise AssertionError('unpaired fixture GUI unlock')
            self.gui_locked=False;self.return_native()
        elif name in ('gui_event_group','gui_event_set'):self.return_native(0)
        elif name=='gui_current_page':self.return_native(self.current_page)
        elif name=='gui_navigate':
            self.navigation.append((uc.reg_read(UC_ARM64_REG_X0),uc.reg_read(UC_ARM64_REG_X0+1)))
            if self.navigate_target:self.current_page=self.navigate_target
            self.return_native(1)
        elif name=='task_delay':
            self.delay_calls+=1;tick=uc.reg_read(UC_ARM64_REG_X0)
            if tick not in (10,33):raise AssertionError('unexpected native delay unit '+str(tick))
            self.return_native(0)
            if self.worker_mode:self.stop_reason='native_delay';uc.emu_stop()
        elif name=='dir_open':
            pointer=uc.reg_read(UC_ARM64_REG_X0)
            path=self.read(pointer,96).split(b'\0',1)[0].decode('ascii')
            self.directory_opens.append(path)
            if path in self.directories:
                self.set_u32(uc.reg_read(UC_ARM64_REG_X0+1),901)
                self.return_native(0)
            else:self.return_native(0x80000010)
        elif name=='dir_close':
            self.directory_closes.append(uc.reg_read(UC_ARM64_REG_X0));self.return_native(0)
        elif name=='dir_read':self.return_native(0x80000030)
        elif name=='file_open':
            pointer=uc.reg_read(UC_ARM64_REG_X0)
            path=self.read(pointer,96).split(b'\0',1)[0].decode('ascii')
            self.file_opens.append(path)
            mode=uc.reg_read(UC_ARM64_REG_X0+1)
            if self.writable and mode==0x101:
                if path in self.records:raise AssertionError('fixture refuses existing record create')
                self.records[path]=b''
            if path in self.records:
                fd=self.next_file_handle;self.next_file_handle+=1
                self.file_handles[fd]=[path,0];self.return_native(fd)
            else:self.return_native(0x80000010)
        elif name in ('file_read','file_write'):
            fd=uc.reg_read(UC_ARM64_REG_X0);pointer=uc.reg_read(UC_ARM64_REG_X0+1)
            count=uc.reg_read(UC_ARM64_REG_X0+2);done=uc.reg_read(UC_ARM64_REG_X0+3)
            path,offset=self.file_handles[fd]
            if name=='file_read':
                data=self.records[path][offset:offset+count];self.write(pointer,data);count=len(data)
            else:
                if not self.writable:raise AssertionError('unexpected write with Auto Off')
                data=self.read(pointer,count)
                self.records[path]=self.records[path][:offset]+data+self.records[path][offset+count:]
            self.file_handles[fd][1]+=count;self.set_u32(done,count);self.return_native(0)
        elif name=='file_close':
            del self.file_handles[uc.reg_read(UC_ARM64_REG_X0)];self.return_native(0)
        elif name=='file_remove':
            if not self.writable:raise AssertionError('unexpected record removal with Auto Off')
            path=self.read(uc.reg_read(UC_ARM64_REG_X0),96).split(b'\0',1)[0].decode('ascii')
            del self.records[path];self.return_native(0)
        else:super().hook(uc,pc,size,context)

    def worker_once(self):
        self.worker_mode=True
        try:super().worker_once()
        finally:self.worker_mode=False


class FullLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (BUILD/'build.json').is_file() or not ORIGINAL.is_file():
            raise unittest.SkipTest('complete Z8 compiled core and original UI data fixtures are required')

    def test_split_worker_stack_requires_separate_page_aligned_storage(self):
        m = FullMachine()
        metadata = m.symbols['fx_native_load_owner_metadata']
        if m.u32(metadata+4) != 2:
            self.skipTest('requires the split worker stack ABI')

        package_bytes, image_bytes = 5836, 18132
        native_bytes, user_bytes = 65536, 65536
        stacks = native_bytes | (user_bytes << 32)
        layout = m.output
        self.assertEqual(m.call('fx_z8_session_layout_stacks', package_bytes, image_bytes, stacks, layout), 0)
        allocation_bytes = m.u32(layout)+4096
        allocation, stack = 0xa10800010, 0xa10bff000
        out, buffers = m.output+128, m.output+256
        m.map(allocation, allocation_bytes)
        m.map(stack, native_bytes)

        def initialize(stack_address):
            m.uc.reg_write(UC_ARM64_REG_X0+5, stack_address)
            m.uc.reg_write(UC_ARM64_REG_X0+6, out)
            m.uc.reg_write(UC_ARM64_REG_X0+7, buffers)
            return m.call('fx_z8_session_init_stacks', allocation, allocation_bytes,
                          package_bytes, image_bytes, stacks)

        self.assertEqual(initialize(0xa10801000), 1)
        self.assertEqual(initialize(stack+16), 1)
        self.assertEqual(m.u64(out), 0)
        self.assertEqual(initialize(stack), 0)
        self.assertEqual(m.u64(out), 0xa10801000)
        self.assertEqual(m.u64(buffers+16), stack)
        self.assertEqual(m.u32(buffers+28), native_bytes)

    def test_prepared_clone_is_original_and_shutdown_blocks_late_install(self):
        m=FullMachine();m.pause_original=True;m.event('startup_complete')
        self.assertNotEqual(m.owner(),0)
        self.assertEqual(m.read(m.owner()+m.metadata['anchor_offset'],64),bytes.fromhex(m.profile['anchor']['descriptor_bytes']))
        self.assertEqual((m.field('installed'),m.field('installation'),m.create_calls),(0,0,0))
        m.event('shutdown');m.resume_startup_original()
        self.assertEqual((m.field('installed'),m.field('installation'),m.create_calls),(0,4,0))
        self.assertEqual(m.original_events,[19,7])

    def test_complete_install_builds_menu_without_starting_modules(self):
        m=FullMachine();self.assertEqual(m.event('startup_complete'),0x1234abcd)
        self.assertEqual((m.field('installed'),m.field('installation'),m.field('activation'),m.field('modules')),(1,2,0,0))
        self.assertEqual((m.create_calls,m.resume_calls),(1,1))
        self.assertEqual(m.field('installation_step'),13)
        self.assertEqual(m.read(m.owner(),64),bytes.fromhex(m.profile['anchor']['descriptor_bytes']))
        pointer=m.u64(m.page+80)
        self.assertEqual(pointer,m.owner()+m.metadata['setup_offset'])
        self.assertEqual(struct.unpack('<H',m.read(pointer+32,2))[0],m.ui['setup']['count']+2)
        custom=m.call('fx_z8_menu_page',2,0x7000)
        self.assertNotEqual(custom,0)
        self.assertEqual(m.u32(custom),(0x7000<<16)|2)
        self.assertEqual(m.call('fx_z8_menu_page',2,m.ui['setup']['id']),m.page)
        m.call('fx_z8_menu_text',1,m.extension_text_base,m.output,m.output+8)
        self.assertEqual(m.read(m.u64(m.output),m.u32(m.output+8)).decode('utf-16le'),'Fenestra')
        self.assertEqual(m.ptp_field('enabled'),0)

    def test_auto_off_worker_inspects_missing_records_without_writes(self):
        m=FullMachine();m.event('startup_complete');m.worker_once()
        self.assertEqual(m.field('activation'),0)
        self.assertEqual(m.field('installation_step'),14)
        self.assertEqual(m.field('modules'),0)
        self.assertEqual(m.ptp_field('enabled'),0)
        self.assertTrue(m.file_opens)
        self.assertTrue(all(path.startswith('A:\\FENESTRA\\') for path in m.file_opens))
        self.assertTrue(all('z8' in path for path in m.file_opens))
        self.assertEqual(m.original_events,[19])

    def test_shutdown_worker_quiesces_and_does_not_reactivate(self):
        m=FullMachine();m.event('startup_complete');m.worker_once();m.event('shutdown');m.worker_once()
        self.assertEqual((m.field('shutdown'),m.field('startup_shutdown'),m.field('installation')),(1,1,4))
        self.assertEqual(m.field('shutdown_done'),1)
        self.assertEqual(m.field('activation'),0)
        self.assertEqual(m.ptp_field('enabled'),0)
        self.assertEqual(m.original_events,[19,7])

    def test_duplicate_startup_does_not_spawn_second_loader(self):
        m=FullMachine();m.event('startup_complete');m.event('startup_complete')
        self.assertEqual((m.create_calls,m.resume_calls),(1,1))
        self.assertEqual(m.original_events,[19,19])

    def test_missing_root_does_not_late_prepare(self):
        m=FullMachine(roots=False);m.original_action=lambda event:m.set_roots();m.event('startup_complete')
        self.assertEqual((m.owner(),m.create_calls),(0,0))
        self.assertEqual(m.call('fx_z8_menu_page',2,0x7000),0)

    def test_text_bank_allocation_failure_preserves_budget_result_and_step(self):
        m=FullMachine();m.allocate_fail_at=3 if m.report.get('feature_suite_backend') else 2;m.event('startup_complete')
        self.assertEqual((m.field('installed'),m.field('installation'),m.field('installation_step')),(0,3,7))
        self.assertEqual(m.field('error'),4) # Public FxResult: FX_BUDGET.
        self.assertEqual(m.create_calls,0)

    def test_task_creator_failure_latches_runtime_fault(self):
        m=FullMachine();m.create_result=-9;m.event('startup_complete')
        self.assertEqual((m.create_calls,m.resume_calls,m.field('activation'),m.field('phase')),(1,0,0,5))
        self.assertNotEqual(m.field('error'),0)
        self.assertEqual(m.ptp_field('enabled'),0)


    def storage_machine(self, **options):
        m=FullMachine(**options)
        if 'fx_z8_storage_select' not in m.symbols:
            self.skipTest('storage selection requires the new SD/CF core')
        m.event('startup_complete')
        return m

    def test_sd_only_empty_directory_activates_usb_and_cleans_its_own_flag(self):
        m=self.storage_machine(directories={'B:\\FENESTRA'},writable=True)
        m.worker_once()
        expected=['A:\\FENESTRA','B:\\FENESTRA']
        # Selection probes A/B, then the cold native scan enumerates the one
        # selected directory. No second volume may supply this boot's modules.
        if m.native_capsules:expected.append('B:\\FENESTRA')
        self.assertEqual(m.directory_opens,expected)
        self.assertEqual(m.call('fx_z8_card_drive'),ord('B'))
        self.assertTrue(all(p.startswith('B:\\FENESTRA\\') for p in m.file_opens))
        m.call('fx_startup_service_request',m.owner()+m.metadata['startup_offset'],1);m.worker_once()
        self.assertEqual((m.field('activation'),m.field('phase')),(1,2))
        self.assertEqual(set(m.records),{'B:\\FENESTRA\\boot-z8.flag'})
        m.call('usb_toggle',0)
        self.assertEqual(m.ptp_field('enabled'),1)
        m.event('shutdown')
        # No concurrent scheduler runs inside this modeled event callback.
        # Supply the explicit original cleanup-window state for the loader.
        cleanup=m.owner()+m.metadata['shutdown_done_offset']-4
        m.set_u32(cleanup,1);m.worker_once();m.set_u32(cleanup,0)
        self.assertEqual(m.records,{})
        self.assertFalse(m.file_handles)
        self.assertEqual(m.ptp_field('enabled'),0)
        self.assertTrue(all(p.startswith('B:\\FENESTRA\\') for p in m.file_opens))

    def test_both_directories_prefer_a_without_probing_b(self):
        m=self.storage_machine(directories={'A:\\FENESTRA','B:\\FENESTRA'})
        m.worker_once()
        expected=['A:\\FENESTRA']*(2 if m.native_capsules else 1)
        self.assertEqual(m.directory_opens,expected)
        self.assertNotIn('B:\\FENESTRA',m.directory_opens)
        self.assertEqual(m.call('fx_z8_card_drive'),ord('A'))
        opened=list(m.directory_opens);m.worker_once()
        self.assertEqual(m.directory_opens,opened)
        self.assertEqual(m.call('fx_z8_card_drive'),ord('A'))

    def test_no_directory_then_inserted_sd_can_retry_activation(self):
        m=self.storage_machine(directories=set(),writable=True);m.worker_once()
        self.assertEqual(m.call('fx_z8_card_drive'),0)
        self.assertFalse(m.file_opens)
        m.directories.add('B:\\FENESTRA')
        m.call('fx_startup_service_request',m.owner()+m.metadata['startup_offset'],1);m.worker_once()
        self.assertEqual(m.call('fx_z8_card_drive'),ord('B'))
        self.assertEqual((m.field('activation'),m.field('phase')),(1,2))
        self.assertEqual(set(m.records),{'B:\\FENESTRA\\boot-z8.flag'})

    def test_selected_sd_is_not_changed_when_cf_directory_appears(self):
        m=self.storage_machine(directories={'B:\\FENESTRA'});m.worker_once()
        opened=list(m.directory_opens)
        m.directories={'A:\\FENESTRA'};m.worker_once()
        self.assertEqual(m.call('fx_z8_card_drive'),ord('B'))
        self.assertEqual(m.directory_opens,opened)

    def test_sd_abnormal_flag_is_retained_and_activation_is_blocked(self):
        import zlib
        m=self.storage_machine(directories={'B:\\FENESTRA'})
        flag=bytearray(64);flag[:8]=b'FXBOOT1\0'
        struct.pack_into('<6I',flag,8,0x00080311,0,1,0,123,0)
        struct.pack_into('<I',flag,60,zlib.crc32(flag[:60]))
        m.records['B:\\FENESTRA\\boot-z8.flag']=bytes(flag)
        m.worker_once();m.call('fx_startup_service_request',m.owner()+m.metadata['startup_offset'],1);m.worker_once()
        self.assertEqual(m.call('fx_z8_card_drive'),ord('B'))
        self.assertEqual(m.field('activation'),0)
        self.assertEqual(m.records['B:\\FENESTRA\\boot-z8.flag'],bytes(flag))


    def test_resume_auto_off_returns_ready_and_manual_activation_works(self):
        m=self.storage_machine(directories={'B:\\FENESTRA'},writable=True);m.worker_once()
        request,count,last,generation=self.resume_layout(m)
        startup=m.owner()+m.metadata['startup_offset']
        m.call('fx_startup_service_request',startup,1);m.worker_once()
        self.clean_stop(m)
        m.call('fx_z8_menu_text',1,m.extension_text_base+10,m.output,m.output+8)
        self.assertEqual(m.read(m.u64(m.output),m.u32(m.output+8)).decode('utf-16le'),'Stopped')
        self.raw_event(m,m.report['system_events']['shutdown_cancel']);m.worker_once()
        self.assertEqual((m.field('activation'),m.field('phase'),m.field('startup_phase')),(0,0,1))
        self.assertEqual((m.field('shutdown'),m.field('startup_shutdown'),m.field('installation')),(0,0,2))
        self.assertEqual((m.u32(request),m.u32(count),m.u32(generation)),(0,1,2))
        self.assertEqual(m.create_calls,1)
        self.assertEqual(m.call('fx_startup_service_request',startup,1),0);m.worker_once()
        self.assertEqual((m.field('activation'),m.field('phase')),(1,2))
        m.call('usb_toggle',0);self.assertEqual(m.ptp_field('enabled'),1)

    def test_power_on_reinspects_card_even_when_never_activated(self):
        m=self.storage_machine(directories={'A:\\FENESTRA'},writable=True);m.worker_once()
        self.resume_layout(m);self.clean_stop(m)
        m.directories={'B:\\FENESTRA'}
        self.raw_event(m,m.report['system_events']['power_on']);m.worker_once()
        self.assertEqual((m.field('activation'),m.field('startup_phase')),(0,1))
        self.assertEqual(m.call('fx_z8_card_drive'),ord('B'))
        self.assertEqual(m.create_calls,1)

    def test_auto_on_resume_activates_once_in_new_generation(self):
        m=self.storage_machine(directories={'B:\\FENESTRA'},writable=True);m.worker_once()
        request,count,last,generation=self.resume_layout(m)
        startup=m.owner()+m.metadata['startup_offset']
        m.call('fx_startup_service_request',startup,2);m.worker_once()
        self.assertEqual(m.field('activation'),0) # setting On is next boot only
        m.call('fx_startup_service_request',startup,1);m.worker_once();self.clean_stop(m)
        self.raw_event(m,m.report['system_events']['shutdown_cancel']);m.worker_once()
        self.assertEqual((m.field('activation'),m.field('phase'),m.field('startup_phase')),(1,2,5))
        for event in (8,20,19,8):self.raw_event(m,event);m.worker_once()
        self.assertEqual((m.create_calls,m.u32(count),m.u32(generation)),(1,1,2))

    def test_resume_retains_unclean_flag_and_blocks_activation(self):
        m=self.storage_machine(directories={'B:\\FENESTRA'},writable=True);m.worker_once()
        self.resume_layout(m);startup=m.owner()+m.metadata['startup_offset']
        m.call('fx_startup_service_request',startup,1);m.worker_once()
        flag=dict(m.records);m.event('shutdown');m.worker_once() # cleanup window already closed
        self.raw_event(m,8);m.worker_once()
        self.assertEqual((m.field('activation'),m.field('startup_phase')),(0,2))
        m.call('fx_startup_service_request',startup,1);m.worker_once()
        self.assertEqual(m.field('activation'),0);self.assertEqual(m.records,flag)

    def test_resume_waits_for_stop_ack_and_never_reopens_fault(self):
        m=self.storage_machine(writable=True);m.worker_once();self.resume_layout(m)
        m.event('shutdown');self.raw_event(m,8)
        m.worker_once()
        self.assertEqual(m.field('shutdown'),1)
        self.assertEqual(m.field('shutdown_done'),1)
        m.set_u32(m.owner()+m.metadata['phase_offset'],5)
        m.worker_once()
        self.assertEqual(m.field('shutdown'),1)

    def test_new_shutdown_during_resume_publication_wins(self):
        m=self.storage_machine(writable=True);m.worker_once()
        request,count,last,generation=self.resume_layout(m);self.clean_stop(m);self.raw_event(m,8)
        def interrupt():
            # Competing system task stop stores at the native GUI boundary.
            m.set_u32(request,0);m.set_u32(m.owner()+m.metadata['shutdown_offset'],3)
            m.set_u32(m.owner()+m.metadata['startup_shutdown_offset'],1)
            m.set_u32(m.owner()+m.metadata['installation_offset'],4)
        m.gui_lock_action=interrupt
        m.worker_once()
        self.assertNotEqual(m.field('shutdown'),0)
        self.assertEqual((m.field('startup_shutdown'),m.field('installation'),m.u32(count)),(1,4,0))

    def test_repeated_resume_preserves_loader_and_unique_generations(self):
        m=self.storage_machine(writable=True);m.worker_once()
        request,count,last,generation=self.resume_layout(m);startup=m.owner()+m.metadata['startup_offset']
        for i in range(16):
            m.call('fx_startup_service_request',startup,1);m.worker_once()
            self.clean_stop(m);self.raw_event(m,8);m.worker_once()
            self.assertEqual((m.field('activation'),m.field('startup_phase')),(0,1))
            self.assertEqual((m.u32(count),m.u32(generation)),(i+1,i+2))
        self.assertEqual(m.create_calls,1);self.assertFalse(m.file_handles)

    def test_manual_resume_remains_available_without_native_resume_event(self):
        m=self.storage_machine(writable=True);m.worker_once()
        request,count,last,generation=self.resume_layout(m);self.clean_stop(m)
        m.call('fx_z8_menu_text',1,m.extension_text_base+2,m.output,m.output+8)
        self.assertEqual(m.read(m.u64(m.output),m.u32(m.output+8)).decode('utf-16le'),'Resume')
        m.call('activate',0);m.worker_once()
        self.assertEqual((m.field('activation'),m.field('startup_phase'),m.field('shutdown')),(0,1,0))
        m.call('activate',0);m.worker_once()
        self.assertEqual((m.field('activation'),m.field('phase')),(1,2))

    def test_new_shutdown_inside_native_resume_handler_is_not_overridden(self):
        m=self.storage_machine(writable=True);m.worker_once()
        request,count,last,generation=self.resume_layout(m);self.clean_stop(m)
        layout=struct.unpack('<7I',m.read(m.symbols['fx_z8_resume_metadata'],28))
        def nested_stop(event):
            if event!=8:return
            m.set_u32(request,0)
            address=m.owner()+layout[6];m.set_u32(address,m.u32(address)+1)
            m.set_u32(m.owner()+m.metadata['shutdown_offset'],1)
            m.set_u32(m.owner()+m.metadata['startup_shutdown_offset'],1)
        m.original_action=nested_stop
        self.raw_event(m,8);m.worker_once()
        self.assertEqual((m.field('shutdown'),m.u32(request),m.u32(count)),(1,0,0))

    def test_retained_manager_resume_rejects_contention_and_uncertain_io(self):
        m=self.storage_machine(writable=True);m.worker_once();self.resume_layout(m)
        layout=struct.unpack('<22I',m.read(m.symbols['fx_native_modules_metadata'],88))
        manager=0xa30000000;m.map(manager,layout[2]);m.write(manager,bytes(layout[2]))
        # Consecutive uint32 fields are independently anchored by linked metadata.
        activated,loading,scanned=layout[7],layout[8],layout[5]
        uncertain,lock,scan,shutdown=activated+4,loading+4,loading+8,loading+12
        for off in (activated,loading,scanned,shutdown):m.set_u32(manager+off,1)
        m.set_u32(manager+lock,1)
        self.assertEqual(m.call('fx_module_manager_resume',manager),5) # BUSY
        self.assertEqual(m.u32(manager+shutdown),1)
        m.set_u32(manager+lock,0);m.set_u32(manager+uncertain,1)
        self.assertEqual(m.call('fx_module_manager_resume',manager),11) # CLOSE
        self.assertEqual(m.u32(manager+shutdown),1)
        m.set_u32(manager+uncertain,0)
        self.assertEqual(m.call('fx_module_manager_resume',manager),0)
        self.assertEqual([m.u32(manager+off) for off in (activated,loading,scanned,shutdown,scan)], [int(m.native_capsules),0,0,0,1])
        self.assertEqual(m.call('fx_module_manager_resume',manager),2) # already live

    def test_resume_leaves_retired_plugin_page_via_original_gui_navigation(self):
        m=self.storage_machine(writable=True);m.worker_once();self.resume_layout(m)
        self.clean_stop(m)
        fake=0xa30000000;m.map(fake,4096);m.write(fake,bytes(4096))
        m.set_u32(fake,(0x7100<<16)|2);m.current_page=fake
        # Observe the original navigation call; native redraw bodies remain excluded.
        m.navigate_target=m.page
        self.raw_event(m,8);m.worker_once()
        self.assertEqual(m.navigation,[]) # loader must not navigate
        m.call('resume_gui',m.owner()) # explicitly modeled captured GUI poll
        self.assertEqual(m.navigation,[(2,0x7000)])
        self.assertEqual(m.current_page,m.navigate_target)
        self.assertEqual((m.field('shutdown'),m.field('startup_phase')),(0,1))


    def resume_diagnostic_layout(self,m):
        if 'fx_z8_resume_diagnostic_metadata' not in m.symbols:
            self.skipTest('resume progress diagnostic candidate required')
        layout=struct.unpack('<6I',m.read(m.symbols['fx_z8_resume_diagnostic_metadata'],24))
        self.assertEqual(layout[:3],(0x46585244,1,m.metadata['state_bytes']))
        self.assertEqual(layout[4:],(8,11))
        self.assertEqual(layout[3]%8,0)
        # Embedded 16-byte aligned native objects give State tail padding.
        self.assertGreaterEqual(layout[2],layout[3]+8)
        self.assertLess(layout[2]-(layout[3]+8),16)
        generation=self.resume_layout(m)[3]-m.owner()
        self.assertGreaterEqual(layout[3],generation+4)
        return m.owner()+layout[3]

    def resume_diagnostic(self,m):
        value=m.u64(self.resume_diagnostic_layout(m))
        return value>>32,value&0xffffffff

    def core_status_text(self,m,offset=10):
        m.call('fx_z8_menu_text',1,m.extension_text_base+offset,m.output,m.output+8)
        return m.read(m.u64(m.output),m.u32(m.output+8)).decode('utf-16le')

    def test_wonder_title_is_requested_z8mouldes(self):
        m=self.storage_machine(writable=True);m.worker_once()
        self.resume_diagnostic_layout(m)
        self.assertEqual(self.core_status_text(m,1),'Z8Mouldes')

    def test_resume_diagnostic_tracks_real_queued_wait_and_completed_rearm(self):
        m=self.storage_machine(writable=True);m.worker_once()
        request,count,last,generation=self.resume_layout(m);self.resume_diagnostic_layout(m)
        m.event('shutdown');self.raw_event(m,8)
        self.assertEqual(self.resume_diagnostic(m),(0,0))
        self.assertEqual(self.core_status_text(m),'Resuming R0 E00')
        m.worker_once() # actual loader observes missing stop_done, then STOP ACK is polled
        self.assertEqual(self.resume_diagnostic(m),(1,5))
        self.assertEqual(self.core_status_text(m),'Resuming R1 E05')
        self.assertEqual((m.field('shutdown'),m.u32(count),m.u32(generation)),(1,0,1))
        m.worker_once()
        self.assertEqual(self.resume_diagnostic(m),(10,0))
        self.assertEqual((m.field('shutdown'),m.u32(request),m.u32(count),m.u32(generation)),(0,0,1,2))
        self.assertEqual(self.core_status_text(m),'Ready')

    def test_resume_diagnostic_stop_busy_preserves_closed_debug_owner(self):
        m=self.storage_machine(writable=True);m.worker_once();self.clean_stop(m)
        request,count,last,generation=self.resume_layout(m);self.resume_diagnostic_layout(m)
        rtos=m.call('fx_z8_menu_rtos')
        layout=struct.unpack('<12I',m.read(m.symbols['fx_native_rtos_metadata'],48))
        self.assertEqual(layout[:2],(0x46585254,1))
        # Explicit synthetic fixture for a revoked native job. Production must
        # retain this closed owner; the test never clears it to permit resume.
        m.set_u32(rtos+layout[4],1)
        self.raw_event(m,8);m.worker_once()
        self.assertEqual(self.resume_diagnostic(m),(2,5))
        self.assertEqual(self.core_status_text(m),'Resuming R2 E05')
        self.assertEqual((m.field('shutdown'),m.u32(count),m.u32(generation)),(1,0,1))
        self.assertNotEqual(m.u32(request),0)
        m.worker_once()
        self.assertEqual(self.resume_diagnostic(m),(2,5))
        self.assertEqual(m.u32(rtos+layout[4]),1)

    def test_resume_diagnostic_records_manager_contention_and_uncertain_io(self):
        for busy in (True,False):
            with self.subTest(busy=busy):
                m=self.storage_machine(writable=True);m.worker_once();self.clean_stop(m)
                request,count,last,generation=self.resume_layout(m);self.resume_diagnostic_layout(m)
                layout=struct.unpack('<22I',m.read(m.symbols['fx_native_modules_metadata'],88))
                manager=0xa30000000;m.map(manager,layout[2]);m.write(manager,bytes(layout[2]))
                menu=struct.unpack('<14I',m.read(m.symbols['fx_z8_menu_metadata'],56))
                m.set_u64(m.owner()+menu[10],manager)
                activated,loading=layout[7],layout[8]
                uncertain,lock=activated+4,loading+4
                # Lock and uncertain-I/O are fixture states; actual production
                # startup_stop/manager_resume and its return code are executed.
                m.set_u32(manager+lock,int(busy));m.set_u32(manager+uncertain,int(not busy))
                self.raw_event(m,8);m.worker_once()
                error=5 if busy else 11
                self.assertEqual(self.resume_diagnostic(m),(6,error))
                self.assertEqual(self.core_status_text(m),'Resuming R6 E'+format(error,'02X'))
                self.assertEqual((m.field('shutdown'),m.u32(count),m.u32(generation)),(1,0,1))
                self.assertNotEqual(m.u32(request),0)

    def test_resume_diagnostic_observes_gui_boundary_and_new_stop_wins(self):
        m=self.storage_machine(writable=True);m.worker_once();self.clean_stop(m)
        request,count,last,generation=self.resume_layout(m);record=self.resume_diagnostic_layout(m)
        self.raw_event(m,8);observed=[]
        def interrupt():
            value=m.u64(record);observed.append((value>>32,value&0xffffffff))
            m.set_u32(request,0);m.set_u32(m.owner()+m.metadata['shutdown_offset'],3)
            m.set_u32(m.owner()+m.metadata['startup_shutdown_offset'],1)
            m.set_u32(m.owner()+m.metadata['installation_offset'],4)
        m.gui_lock_action=interrupt;m.worker_once()
        self.assertEqual(observed,[(5,5)])
        self.assertEqual(self.resume_diagnostic(m),(9,13))
        self.assertEqual((m.field('shutdown'),m.field('startup_shutdown'),m.field('installation'),m.u32(count)),(3,1,4,0))

    def test_resume_diagnostic_generation_overflow_remains_blocked(self):
        m=self.storage_machine(writable=True);m.worker_once();self.clean_stop(m)
        request,count,last,generation=self.resume_layout(m);self.resume_diagnostic_layout(m)
        m.set_u32(generation,0xffffffff);self.raw_event(m,8);m.worker_once()
        self.assertEqual(self.resume_diagnostic(m),(11,9))
        self.assertEqual(self.core_status_text(m),'Resuming RB E09')
        self.assertEqual((m.field('shutdown'),m.u32(count),m.u32(generation)),(1,0,0xffffffff))

    def cold_layout(self,m):
        if not m.native_capsules:self.skipTest('native cold loader required')
        cold=struct.unpack('<14I',m.read(m.symbols['fx_z8_cold_bootstrap_metadata'],56))
        self.assertEqual(cold[:2],(0x46584342,1))
        base=m.owner()+cold[2]
        return base+cold[4],base+cold[5],base+cold[6],base+cold[13]

    def cancel_first_cold_step(self,m):
        m.event('shutdown');m.worker_once() # actual first cold step cancels before any IO

    def test_cold_cancel_restarts_after_power_on(self):
        m=self.storage_machine(writable=True)
        request,count,last,generation=self.resume_layout(m);self.resume_diagnostic_layout(m)
        phase,error,cold_generation,retries=self.cold_layout(m)
        self.cancel_first_cold_step(m)
        self.assertEqual((m.u32(phase),m.u32(error),m.u32(retries),m.field('shutdown_done')),(7,13,0,1))
        self.assertEqual(self.core_status_text(m),'Card error E0D B7')
        self.assertEqual(self.core_status_text(m,2),'Resume')
        self.raw_event(m,m.report['system_events']['shutdown_cancel'])
        self.assertNotEqual(m.u32(request),0)
        self.assertEqual(self.core_status_text(m),'Resuming R0 E00')
        m.worker_once() # loader discards, restarts in generation 2 and completes
        self.assertEqual((m.u32(phase),m.u32(error),m.u32(retries),m.u32(cold_generation)),(5,0,1,2))
        self.assertEqual((m.u32(request),m.u32(count),m.u32(generation)),(0,0,2))
        self.assertEqual((m.field('shutdown'),m.field('startup_shutdown'),m.field('installation')),(0,0,2))
        self.assertEqual(self.resume_diagnostic(m),(10,0))
        self.assertNotIn('Card error',self.core_status_text(m))
        startup=m.owner()+m.metadata['startup_offset']
        self.assertEqual(m.call('fx_startup_service_request',startup,1),0);m.worker_once()
        self.assertEqual((m.field('activation'),m.field('phase')),(1,2))
        self.assertEqual(m.create_calls,1);self.assertFalse(m.file_handles)

    def test_manual_resume_restarts_cancelled_cold_attempt(self):
        m=self.storage_machine(writable=True)
        request,count,last,generation=self.resume_layout(m);self.resume_diagnostic_layout(m)
        phase,error,cold_generation,retries=self.cold_layout(m)
        self.cancel_first_cold_step(m)
        m.call('activate',0);self.assertNotEqual(m.u32(request),0);m.worker_once()
        self.assertEqual((m.u32(phase),m.u32(retries),m.u32(generation),m.field('shutdown')),(5,1,2,0))
        self.assertEqual(m.create_calls,1)

    def test_new_shutdown_during_cold_retry_wins_and_budget_is_bounded(self):
        m=self.storage_machine(writable=True)
        request,count,last,generation=self.resume_layout(m);self.resume_diagnostic_layout(m)
        phase,error,cold_generation,retries=self.cold_layout(m)
        self.cancel_first_cold_step(m)
        def interrupt():
            # Competing system task stop stores at the native GUI boundary.
            m.set_u32(request,0);m.set_u32(m.owner()+m.metadata['shutdown_offset'],3)
            m.set_u32(m.owner()+m.metadata['startup_shutdown_offset'],1)
            m.set_u32(m.owner()+m.metadata['installation_offset'],4)
        m.gui_lock_action=interrupt
        for i in range(4):
            self.raw_event(m,8);self.assertNotEqual(m.u32(request),0)
            m.worker_once() # the WAITING attempt cancels at its first step
            self.assertEqual((m.u32(phase),m.u32(error),m.u32(retries),m.u32(cold_generation)),(7,13,i+1,i+2))
            self.assertEqual((m.field('shutdown'),m.field('startup_shutdown'),m.field('installation')),(3,1,4))
            self.assertEqual((self.resume_diagnostic(m),m.field('shutdown_done')),((9,13),1))
        m.gui_lock_action=None
        self.assertNotEqual(self.core_status_text(m,2),'Resume')
        self.raw_event(m,8);self.assertEqual(m.u32(request),0)
        m.call('activate',0);self.assertEqual(m.u32(request),0);m.worker_once()
        self.assertEqual((m.u32(phase),m.u32(retries),m.field('shutdown')),(7,4,3))
        self.assertEqual(self.core_status_text(m),'Card error E0D B7')
        self.assertEqual(m.create_calls,1)

def main():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(FullLifecycleTests))
    report=json.loads((BUILD/'build.json').read_text())
    evidence={'schema':'fenestra.z8-full-lifecycle-instruction-tests/v1','passed':result.wasSuccessful(),
        'tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'code_sha256':report['code_sha256'],
        'candidate_sha256':report['candidate_sha256'],'test_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'executed':'project-owned compiled complete A64 core','original_data':'pinned Z8 initialized UI image data',
        'modeled_boundaries':['font/style root initialization','native heap','GUI mutex/current-page read','task create/resume/delay','original event dispatcher','A/B directory presence and empty enumeration','startup record read/write/remove and explicit cleanup window'],
        'not_executed':['Nikon function bodies','module EL0 execution','full-system QEMU boot','physical USB/display/storage'],
        'qemu_qualified':False,'physical_qualified':False,'flashable':False}
    (BUILD/'lifecycle-instructions.json').write_text(json.dumps(evidence,indent=2)+'\n')
    return int(not result.wasSuccessful())


if __name__=='__main__':raise SystemExit(main())
