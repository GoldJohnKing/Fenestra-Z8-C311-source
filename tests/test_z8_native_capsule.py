"""Native capsule format, fixed ELF, exact subset and de-layering regression tests."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'host'))
import z8_native_capsule as c


def repaired(blob):
    blob=bytearray(blob)
    blob[64:96]=hashlib.sha256(blob[128:]).digest()
    return bytes(blob)


def controls_fixture(mask=15):
    blob=bytearray(0x3800)
    blob[:16]=b'\x7fELF\x02\x01\x01'+bytes(9)
    struct.pack_into('<HHIQQQIHHHHHH',blob,16,2,183,1,c.CONTROLS_BEGIN,64,0x3500,0,64,56,2,64,4,0)
    struct.pack_into('<II6Q',blob,64,1,5,0x1000,c.CONTROLS_BEGIN,c.CONTROLS_BEGIN,0x400,0x400,4096)
    struct.pack_into('<II6Q',blob,120,1,6,0x2000,c.CONTROLS_BEGIN+0x1000,c.CONTROLS_BEGIN+0x1000,0,16,4096)
    blob[0x1000:0x1010]=bytes.fromhex('c0035fd6')*4
    names=('fx_native_pack_entry','fx_controls_video_open_hook','fx_controls_video_close_hook','fx_native_pack_feature_mask',
           'fx_controls_metadata','fx_controls_dependency_digest','fx_controls_dependency_count','fx_controls_dependency_table',
           'fx_controls_locale','fx_controls_locale_export')
    values=(c.CONTROLS_BEGIN,c.CONTROLS_BEGIN+4,c.CONTROLS_BEGIN+8,mask,
            c.CONTROLS_BEGIN+0x40,c.CONTROLS_BEGIN+0x80,c.CONTROLS_BEGIN+0xa0,c.CONTROLS_BEGIN+0x100,
            c.CONTROLS_BEGIN+0x300,c.CONTROLS_BEGIN+0x320)
    exports=[('framing.opengate.writer_close_hook',0x40960870)] if mask&1 else []
    if mask&2:exports.append(('quality.tier_star_republish',0x40a41250))
    if mask&8:exports.append(('pixelshift.psm_worker',0x409a44cc))
    sizes=(4,4,4,0,28,32,4,max(80,len(exports)*80),32,80)
    text=c.pinned_native_text_layout(mask)
    struct.pack_into('<4I2Q',blob,0x1300,1,32,text['languages'],text['text_count'],text['offsets_directory'],text['pools_directory'])
    struct.pack_into('<64sIIQ',blob,0x1320,b'camera.locale.text',1,2,c.CONTROLS_BEGIN+0x300)
    struct.pack_into('<7I',blob,0x1040,0x46584e50,1,mask,40,56,104,80)
    blob[0x1080:0x10a0]=bytes.fromhex(c.COMPILED_SHA256)
    struct.pack_into('<I',blob,0x10a0,len(exports))
    for i,(name,address) in enumerate(exports):struct.pack_into('<64sIIQ',blob,0x1100+i*80,name.encode(),1,1,address)
    strings=b'\0';positions=[]
    for name in names:positions.append(len(strings));strings+=name.encode()+b'\0'
    blob[0x3000:0x3000+len(strings)]=strings
    for i,name in enumerate(names):
        struct.pack_into('<IBBHQQ',blob,0x3200+(i+1)*24,positions[i],0x12 if i<3 else 0x10,0,0xfff1 if i==3 else 1,values[i],sizes[i])
    struct.pack_into('<II4QII2Q',blob,0x3540,0,1,6,c.CONTROLS_BEGIN,0x1000,0x400,0,0,4,0)
    struct.pack_into('<II4QII2Q',blob,0x3580,0,3,0,0,0x3000,len(strings),0,0,1,0)
    struct.pack_into('<II4QII2Q',blob,0x35c0,0,2,0,0,0x3200,(len(names)+1)*24,2,0,8,24)
    return bytes(blob)


class CapsuleWireTests(unittest.TestCase):
    def sample(self):
        return c.encode([c.Patch(c.IMAGE,c.EXEC,0x408d0000,bytes(4),bytes.fromhex('c0035fd6')),
                         c.Patch(c.HOOK,c.INSTRUCTION,0x40cebe3c,bytes.fromhex('680200f9'),bytes.fromhex('01000014'),0)],1,2,0x408d0000)

    def test_wire_offsets_and_round_trip(self):
        blob=self.sample();got=c.decode(blob)
        self.assertEqual(len(blob),128+112*2+16)
        self.assertEqual(blob[:8],b'FXCAPS1\0')
        self.assertEqual(struct.unpack_from('<4Q',blob,96),(1,2,8,0x408d0000))
        self.assertEqual(got['patches'][1].depends,0)
        self.assertEqual(got['patches'][0].new,bytes.fromhex('c0035fd6'))

    def test_full_file_index_exact_wire_and_stale_file_rejected(self):
        blob=self.sample();index=c.make_index(blob)
        self.assertEqual(len(index),56)
        self.assertEqual(struct.unpack('<8sIIQ32s',index),(b'FNCIDX01',1,56,len(blob),bytes.fromhex(c.sha(blob))))
        self.assertTrue(c.verify_index(index,blob))
        for wrong in (index+b'0',index[:-1],bytes(56)):
            with self.assertRaises(ValueError):c.verify_index(wrong,blob)
        other=bytearray(blob);other[96]^=1
        with self.assertRaisesRegex(ValueError,'complete package SHA'):c.verify_index(index,bytes(other))

    def test_body_and_payload_hashes_are_independently_checked(self):
        blob=bytearray(self.sample());blob[-1]^=1
        with self.assertRaisesRegex(ValueError,'body SHA'):c.decode(bytes(blob))
        with self.assertRaisesRegex(ValueError,'payload SHA'):c.decode(repaired(blob))

    def test_payload_alias_and_destination_overlap_rejected(self):
        blob=bytearray(self.sample())
        struct.pack_into('<I',blob,128+24,struct.unpack_from('<I',blob,128+20)[0])
        # Equal old/new hashes ensure the overlap check itself is reached.
        blob[128+32:128+64]=blob[128+64:128+96]
        with self.assertRaisesRegex(ValueError,'payload windows overlap'):c.decode(repaired(blob))
        blob=bytearray(self.sample());struct.pack_into('<Q',blob,128+112+8,0x408d0000)
        with self.assertRaisesRegex(ValueError,'destination windows overlap'):c.decode(repaired(blob))

    def test_bad_order_dependency_permission_entry_and_boot_kind_rejected(self):
        alterations=((128,3,'unsupported record kind'),(128+4,3,'permissions'),
                     (128+28,0,'dependency'),(128+112+28,1,'dependency'))
        for at,value,message in alterations:
            blob=bytearray(self.sample());struct.pack_into('<I',blob,at,value)
            with self.subTest(at=at),self.assertRaisesRegex(ValueError,message):c.decode(repaired(blob))
        blob=bytearray(self.sample());struct.pack_into('<Q',blob,120,0x408d1000)
        with self.assertRaisesRegex(ValueError,'entry'):c.decode(bytes(blob))
        with self.assertRaisesRegex(ValueError,'IMAGE prefix'):
            c.encode([c.Patch(c.HOOK,c.DATA,0x43000000,b'a',b'b'),c.Patch(c.IMAGE,0,0x408d0000,b'a',b'b')],1,2)

    @unittest.skipUnless((c.VENDOR/'features.py').is_file(), 'requires the pinned feature toolkit')
    def test_fixed_elf_segment_and_mask_guards(self):
        elf=controls_fixture(15);got=c.read_controls_elf(elf,15)
        self.assertEqual(got['entry'],c.CONTROLS_BEGIN)
        self.assertEqual(got['segments'][1]['data'],bytes(16))
        with self.assertRaisesRegex(ValueError,'selection differs'):c.read_controls_elf(elf,1)
        bad=bytearray(elf);struct.pack_into('<I',bad,64+4,7)
        with self.assertRaisesRegex(ValueError,r'W\+X'):c.read_controls_elf(bytes(bad),15)
        bad=bytearray(elf);struct.pack_into('<Q',bad,64+16,0x408c0000)
        with self.assertRaisesRegex(ValueError,'outside'):c.read_controls_elf(bytes(bad),15)
        bad=bytearray(elf);struct.pack_into('<I',bad,0x35c0+4,4)
        with self.assertRaisesRegex(ValueError,'relocation'):c.read_controls_elf(bytes(bad),15)
        bad=bytearray(elf);struct.pack_into('<H',bad,0x3200+24+6,0)
        with self.assertRaisesRegex(ValueError,'undefined imports'):c.read_controls_elf(bytes(bad),15)

    def test_controls_native_dependency_bytes_are_independently_checked(self):
        if not (c.VENDOR/'features.py').is_file():
            self.skipTest('requires the pinned feature toolkit')
        c.checked_upstream()
        good=controls_fixture(15)
        self.assertTrue(c.verify_controls_dependencies(c.read_controls_elf(good,15),15))
        for at,message in ((0x1080,'digest differs'),(0x1040,'ABI'),(0x10a0,'count differs'),(0x1100+72,'addresses differ')):
            bad=bytearray(good);bad[at]^=1
            with self.subTest(at=at),self.assertRaisesRegex(ValueError,message):
                c.verify_controls_dependencies(c.read_controls_elf(bytes(bad),15),15)
        self.assertTrue(c.verify_controls_dependencies(c.read_controls_elf(controls_fixture(4),4),4))
        hidden=c.read_controls_elf(controls_fixture(4),4);hidden['symbols']['fx_controls_precapture_stage']=c.CONTROLS_BEGIN+16
        with self.assertRaisesRegex(ValueError,'disabled feature code'):c.verify_controls_dependencies(hidden,4)

    @unittest.skipUnless((c.VENDOR/'features.py').is_file(), 'requires the pinned feature toolkit')
    def test_locale_descriptor_and_export_are_exact_immutable_data(self):
        good=controls_fixture(15);control=c.read_controls_elf(good,15);info=c.pinned_native_text_layout(15)
        row=c.verify_controls_locale(control,info)
        self.assertEqual((row['name'],row['version'],row['flags']),('camera.locale.text',1,2))
        for at,message in ((0x1300+12,'text bounds'),(0x1300+16,'text bounds'),(0x1320,'DATA export'),(0x1320+64,'DATA export'),(0x1320+68,'DATA export'),(0x1320+72,'DATA export')):
            changed=bytearray(good);changed[at]^=1
            with self.subTest(at=at),self.assertRaisesRegex(ValueError,message):c.verify_controls_locale(c.read_controls_elf(bytes(changed),15),info)
        mutable=copy.deepcopy(control);mutable['segments'][0]['flags']=6
        with self.assertRaisesRegex(ValueError,'immutable RO'):c.verify_controls_locale(mutable,info)

    def test_output_guard_runs_before_input_read(self):
        for output in (ROOT/'dist/native-capsule-test',ROOT/'host',ROOT/'build'):
            with self.subTest(output=output),mock.patch.object(c,'read_main') as read:
                with self.assertRaisesRegex(ValueError,'new owned'):c.create('absent',output,1,upstream_only=True)
                read.assert_not_called()

    def test_all_empty_and_unknown_selections_rejected(self):
        for mask in (0,16,True,-1,'1'):
            with self.subTest(mask=mask),self.assertRaises(ValueError):c.selected(mask)
        self.assertEqual(c.feature_mask('framing,photo-tools'),9)
        self.assertEqual(c.feature_mask('0xf'),15)
        self.assertEqual(c.arena_profile()['requires_id'],0x81947c592af69a37)
        self.assertIs(c.arena_profile()['locale_contract']['count_hook_permitted'],False)


class ExactNativeProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source=ROOT/'inputs/z8-c311-main.bin'
        if not source.exists() or not (c.VENDOR/'features.py').is_file():
            raise unittest.SkipTest('requires local stock MAIN and the pinned feature toolkit')
        cls.stock=c.read_main(source)
        cls.products={mask:c.build(cls.stock,mask) for mask in range(1,16)}

    def test_all_fifteen_complete_recipe_reconstruction_and_no_boot_runtime(self):
        upstreams={}
        for mask,(blob,manifest) in self.products.items():
            with self.subTest(mask=mask):
                report=c.verify_projection(self.stock,blob,manifest)
                self.assertTrue(report['passed'])
                self.assertEqual(len(manifest['boot_only']),1)
                self.assertEqual(manifest['features'],c.selected(mask))
                self.assertFalse(manifest['deployable'])
                self.assertFalse(manifest['physical_qualified'])
                self.assertTrue(all(p.address!=c.COPY_END_SITE for p in c.decode(blob)['patches']))
                self.assertTrue(all(not c.CONTROLS_BEGIN<=p.address<c.CONTROLS_END for p in c.decode(blob)['patches']))
                upstreams[mask]=manifest['upstream_main_sha256']
        self.assertEqual(len(set(upstreams.values())),15)

    def test_text_count_is_derived_from_actual_locales_and_keeps_stock_preimage(self):
        for mask,(blob,manifest) in self.products.items():
            with self.subTest(mask=mask):
                text=manifest['native_text']
                self.assertEqual(text['original_count'],65535)
                self.assertEqual(text['stock_text_count'],3136)
                self.assertEqual(text['loaded_count'],text['entries_per_language']-1)
                self.assertEqual(text['table_bytes'],text['entries_per_language']*36*4)
                records=c.decode(blob)['patches']
                metadata=[r for r in manifest['records'] if r['source']=='text-count-supplement']
                self.assertEqual(metadata,[])
                self.assertTrue(all(not(p.address<0xa0281cd60 and 0xa0281cd5c<p.address+len(p.new)) for p in records))
                self.assertTrue(text['native_acceptance_managed_by_core'])
                self.assertEqual(text['runtime_count_source'],'published-font-bank-capacity')
                self.assertEqual(c.pinned_native_text_layout(mask)['text_count'],text['loaded_count'])

    def test_text_table_stride_utf16_pool_bounds_and_count_tamper_rejected(self):
        upstream,rows,_=c._recipe(self.stock,15)
        table=next(r for r in rows if r['purpose']=='shared 36 language offset tables')
        table_at=int(table['offset'],0)
        for at,value,message in ((0x311c5a0+8,0,'directory stride'),(table_at,0x7fffffff,'offset prefix'),(table_at+3137*4,0x7fffffff,'endpoint escapes')):
            bad=bytearray(upstream)
            struct.pack_into('<Q' if at==0x311c5a0+8 else '<I',bad,at,value)
            with self.subTest(at=at),self.assertRaisesRegex(ValueError,message):c.derive_native_text(self.stock,bytes(bad),rows)
        blob,manifest=self.products[15]
        bad=copy.deepcopy(manifest);bad['native_text']['loaded_count']+=1
        with self.assertRaisesRegex(ValueError,'text bounds'):c.verify_projection(self.stock,blob,bad)

    def test_old_and_new_arena_dependencies_fail_closed_in_both_directions(self):
        blob,manifest=self.products[15];old_id=0x385ac573803622df
        old=bytearray(blob);struct.pack_into('<Q',old,104,old_id);old=bytes(old)
        altered=copy.deepcopy(manifest);altered.update(package_sha256=c.sha(old),package_bytes=len(old),index_sha256=c.sha(c.make_index(old)),requires_id=old_id)
        with self.assertRaisesRegex(ValueError,'foundation prerequisite'):c.verify_projection(self.stock,old,altered)
        old_profile=copy.deepcopy(c.arena_profile());old_profile['requires_id']=old_id;old_profile['profile_sha256']='df22368073c55a386838460ac06c3b707b7fbe1506f2694e18c1dba7a6073e5f';old_profile.pop('locale_contract')
        with mock.patch.object(c,'arena_profile',return_value=old_profile),self.assertRaisesRegex(ValueError,'foundation prerequisite'):c.verify_projection(self.stock,blob,manifest)

    def test_new_dependency_cannot_hide_a_native_id_limit_write(self):
        blob,manifest=self.products[15];patches=c.decode(blob)['patches'];address=0xa0281cd5c
        patch=c.Patch(c.HOOK,c.DATA,address,bytes.fromhex('ffff0000'),struct.pack('<I',3225));patches.append(patch)
        changed=c.encode(patches,manifest['package_id'],manifest['requires_id'])
        altered=copy.deepcopy(manifest);altered.update(package_sha256=c.sha(changed),package_bytes=len(changed),index_sha256=c.sha(c.make_index(changed)))
        altered['records'].append(dict(index=len(patches)-1,kind=patch.kind,flags=patch.flags,address=hex(address),bytes=4,depends_on=c.NONE,old_sha256=c.sha(patch.old),new_sha256=c.sha(patch.new),source='controls',file_offset=c.INIT_FILE_BEGIN+address-c.INIT_RAM_BEGIN,mapping='init-ram',purpose='malicious accepted-ID count write'))
        with self.assertRaisesRegex(ValueError,'acceptance limit'):c.verify_projection(self.stock,changed,altered)

    def test_runtime_icon_root_is_explicit_and_only_in_log_selections(self):
        for mask,(blob,manifest) in self.products.items():
            with self.subTest(mask=mask):
                rows=[r for r in manifest['records'] if r['source']=='runtime-resource-root-supplement']
                self.assertEqual(len(rows),bool(mask&4))
                self.assertEqual(len(manifest['native_resources']),bool(mask&4))
                if not rows:continue
                row=rows[0];p=c.decode(blob)['patches'][row['index']]
                self.assertEqual((p.kind,p.flags,p.address),(c.HOOK,c.POINTER,0xa02f2ab80))
                self.assertEqual((p.old,p.new),(struct.pack('<Q',0x431d96d0),struct.pack('<Q',0x40b20000)))
                self.assertIsNone(row['file_offset'])
                self.assertEqual(row['mapping'],'runtime-resource-root')
                self.assertNotEqual(p.depends,c.NONE)
                self.assertEqual(manifest['native_resources'][0]['stock_entries'],6242)

    def test_runtime_icon_root_setter_initializer_and_png_bounds_are_checked(self):
        upstream,rows,_=c._recipe(self.stock,15)
        c.native_resource_supplements(self.stock,upstream,rows,15)
        for address,value,message in ((0x403ee56c,0,'MOV sequence'),(0x403ee57c,0,'initializer call'),
                                      (0x40b20000,0,'prefix/end'),(0x40b20000+6242*24+16,0,'escapes actual PNG')):
            bad=bytearray(upstream);struct.pack_into('<I',bad,address-c.BASE,value)
            with self.subTest(address=address),self.assertRaisesRegex(ValueError,message):
                c.native_resource_supplements(self.stock,bytes(bad),rows,15)
        bad=bytearray(self.stock);bad[0x4032dc44-c.BASE]^=1
        with self.assertRaisesRegex(ValueError,'store/return'):
            c.native_resource_supplements(bytes(bad),upstream,rows,15)
        with mock.patch.object(c,'arena_profile',return_value=dict(resource_roots=[])):
            with self.assertRaisesRegex(ValueError,'capability'):c.native_resource_supplements(self.stock,upstream,rows,15)

    def test_runtime_icon_root_cannot_claim_file_origin_or_change_derived_pointer(self):
        blob,manifest=self.products[15]
        row=next(r for r in manifest['records'] if r['source']=='runtime-resource-root-supplement')
        bad=copy.deepcopy(manifest);bad['records'][row['index']]['file_offset']=0
        with self.assertRaisesRegex(ValueError,'must not claim'):c.verify_projection(self.stock,blob,bad)
        bad=copy.deepcopy(manifest);bad['native_resources'][0]['original_root']='0x0'
        with self.assertRaisesRegex(ValueError,'resource-root supplement'):c.verify_projection(self.stock,blob,bad)
        parsed=c.decode(blob);patches=parsed['patches'];p=patches[row['index']]
        patches[row['index']]=c.Patch(p.kind,p.flags,p.address,bytes(8),p.new,p.depends)
        changed=c.encode(patches,parsed['package_id'],parsed['requires_id'],parsed['entry'])
        bad=copy.deepcopy(manifest);bad.update(package_sha256=c.sha(changed),package_bytes=len(changed),index_sha256=c.sha(c.make_index(changed)))
        bad['records'][row['index']]['old_sha256']=c.sha(bytes(8))
        with self.assertRaisesRegex(ValueError,'resource-root supplement'):c.verify_projection(self.stock,changed,bad)

    def test_selected_native_exports_and_disabled_payloads(self):
        for mask,(blob,manifest) in self.products.items():
            with self.subTest(mask=mask):
                names={row['name'] for row in manifest['native_exports']}
                self.assertEqual('framing.opengate.writer_close_hook' in names,bool(mask&1))
                self.assertEqual('quality.tier_star_republish' in names,bool(mask&2))
                self.assertEqual('pixelshift.psm_worker' in names,bool(mask&8))
                for row in manifest['records']:
                    purpose=row['purpose']
                    if not mask&1:self.assertFalse(purpose.startswith(('opengate-nraw:','anamorphic:')))
                    if not mask&2:self.assertFalse(purpose.startswith(('prores:','h265:','stars:')))
                    if not mask&4:self.assertFalse(purpose.startswith('log:'))
                    if not mask&8:self.assertFalse(purpose.startswith(('pixelshift:','pre-capture')))

    def test_controls_are_native_image_records_and_exact_close_refinement(self):
        for mask in (2,15):
            with self.subTest(mask=mask):
                blob,manifest=c.build(self.stock,mask,controls_fixture(mask))
                self.assertTrue(manifest['deployable'])
                self.assertEqual(c.decode(blob)['entry'],c.CONTROLS_BEGIN)
                self.assertEqual(len(manifest['refinements']),2)
                close=next(r for r in manifest['refinements'] if int(r['site'],0)==0x40ceef10)
                self.assertEqual(close['upstream'],c._word_branch(0x40ceef10,0x40960870).hex() if mask&1 else 'f40f1ef8')
                self.assertTrue(c.verify_projection(self.stock,blob,manifest)['passed'])
                bad=copy.deepcopy(manifest);bad['refinements'][1]['upstream']='00000000'
                with self.assertRaisesRegex(ValueError,'reconstruct'):c.verify_projection(self.stock,blob,bad)

    def test_manifest_mapping_or_unaccounted_source_is_rejected(self):
        blob,manifest=self.products[15]
        bad=copy.deepcopy(manifest);bad['records'][0]['mapping']='init-ram'
        with self.assertRaisesRegex(ValueError,'mapping differs'):c.verify_projection(self.stock,blob,bad)
        bad=copy.deepcopy(manifest);bad['records'][0]['source']='other'
        with self.assertRaisesRegex(ValueError,'unknown projection'):c.verify_projection(self.stock,blob,bad)

    def test_install_readback_existing_file_guard_and_tamper_preserve_target(self):
        with tempfile.TemporaryDirectory(prefix='fenestra-capsule-') as work:
            base=Path(work);source=base/'package';(source/'FENESTRA').mkdir(parents=True)
            control=controls_fixture(2);blob,manifest=c.build(self.stock,2,control)
            (source/'FENESTRA/BOOT.FNC').write_bytes(blob)
            (source/'FENESTRA/BOOT.IDX').write_bytes(c.make_index(blob))
            (source/'controls.elf').write_bytes(control)
            (source/'capsule.json').write_text(json.dumps(manifest),encoding='utf-8')
            card=base/'card';card.mkdir()
            result=c.install(ROOT/'inputs/z8-c311-main.bin',source,card)
            self.assertEqual(result['package_sha256'],c.sha(blob))
            self.assertEqual((card/'FENESTRA/BOOT.FNC').read_bytes(),blob)
            with self.assertRaisesRegex(ValueError,'exists'):c.install(ROOT/'inputs/z8-c311-main.bin',source,card)
            changed=bytearray(control);changed[0x1080]^=1;(source/'controls.elf').write_bytes(changed)
            with self.assertRaisesRegex(ValueError,'digest differs'):c.install(ROOT/'inputs/z8-c311-main.bin',source,card,replace=True)
            self.assertEqual((card/'FENESTRA/BOOT.FNC').read_bytes(),blob)
            self.assertFalse(list((card/'FENESTRA').glob('*.tmp-*')))

    def test_stock_candidate_and_modified_preimages_rejected(self):
        bad=bytearray(self.stock);bad[c.CONTROLS_BEGIN-c.BASE]=1
        with self.assertRaisesRegex(ValueError,'exact original'):c.build(bytes(bad),1)
        with self.assertRaisesRegex(ValueError,'original'):c.build(self.stock+b'\0',1)


if __name__=='__main__':unittest.main()
