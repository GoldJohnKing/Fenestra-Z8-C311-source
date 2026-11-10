"""Synthetic offline native-profile protocol fixtures; no camera transport."""
from pathlib import Path
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'host'))
import z8_native_profile as profile

class NativeProfileTests(unittest.TestCase):
    def setUp(self):
        self.image=bytes((i%251)+1 for i in range(512))
        self.patch=mock.patch.multiple(profile,STOCK_BYTES=len(self.image),STOCK_SHA256=hashlib.sha256(self.image).hexdigest())
        self.patch.start();self.addCleanup(self.patch.stop)
        self.functions=[dict(name='probe.c311.get',address=profile.BASE+64),
                        dict(name='probe.c311.frame',address=profile.BASE+128,abi=5,flags=4)]
    def build(self):return profile.build_profile(self.image,self.functions)
    def test_explicit_preimages_are_deterministic_and_input_is_unchanged(self):
        before=bytes(self.image);doc=self.build()
        self.assertEqual(doc,profile.build_profile(self.image,list(reversed(self.functions))))
        self.assertEqual(self.image,before)
        self.assertEqual(profile.verify_profile(self.image,doc)['functions'],2)
        self.assertFalse(doc['semantic_qualified'])
        self.assertTrue(doc['runtime_preimage_verification_required'])
        self.assertEqual(doc['native_begin'],hex(profile.BASE))
        self.assertEqual(doc['native_end'],hex(profile.BASE+512))
        get=next(row for row in doc['functions'] if row['name']=='probe.c311.get')
        self.assertEqual(get['original'],self.image[64:80].hex())
        self.assertEqual((get['kind'],get['abi'],get['capabilities'],get['bytes']),(1,1,1<<19,0))
    def test_wrong_whole_image_is_rejected_even_when_entry_windows_match(self):
        altered=bytearray(self.image);altered[400]^=1
        for data in (bytes(altered),self.image[:-1],self.image+b'\0'):
            with self.subTest(length=len(data)),self.assertRaises(ValueError):profile.build_profile(data,self.functions)
    def test_explicit_entry_must_fit_align_and_be_nonzero(self):
        for address in (profile.BASE-4,profile.BASE+1,profile.BASE+500,profile.BASE+512,True):
            with self.subTest(address=address),self.assertRaises(ValueError):profile.build_profile(self.image,[dict(name='probe.bad',address=address)])
        doc=profile.build_profile(self.image,[dict(name='probe.last',address=profile.BASE+496)])
        self.assertEqual(doc['functions'][0]['original'],self.image[-16:].hex())
        image=bytearray(self.image);image[64:80]=bytes(16)
        with mock.patch.object(profile,'STOCK_SHA256',hashlib.sha256(image).hexdigest()),self.assertRaises(ValueError):
            profile.build_profile(bytes(image),[self.functions[0]])
    def test_unknown_metadata_and_ambiguous_types_are_rejected(self):
        cases=[dict(name='A',address=profile.BASE),dict(name='probe.'+'x'*64,address=profile.BASE),
               dict(name='probe.good',address=profile.BASE,kind=2),dict(name='probe.good',address=profile.BASE,abi=2),
               dict(name='probe.good',address=profile.BASE,abi=1.0),dict(name='probe.good',address=profile.BASE,version=0),
               dict(name='probe.good',address=profile.BASE,flags=1),dict(name='probe.good',address=profile.BASE,address2=profile.BASE)]
        for row in cases:
            with self.subTest(row=row),self.assertRaises(ValueError):profile.build_profile(self.image,[row])
        for rows in ([],[self.functions[0],self.functions[0]],self.functions*33):
            with self.assertRaises(ValueError):profile.build_profile(self.image,rows)
    def test_profile_verifier_rederives_all_fields_from_stock(self):
        for key,value in [('profile_sha256','0'*64),('semantic_qualified',True),('semantic_qualified',0),('stock_main_sha256','0'*64),
                          ('native_end',hex(profile.BASE+511)),('extra','ignored')]:
            doc=self.build();doc[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):profile.verify_profile(self.image,doc)
        for key,value in [('original','ff'*16),('capabilities',0),('bytes',16),('kind',2),('kind',True),('address',hex(profile.BASE+160))]:
            doc=self.build();doc['functions'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):profile.verify_profile(self.image,doc)
        doc=self.build();del doc['functions'][0]['abi']
        with self.assertRaises(ValueError):profile.verify_profile(self.image,doc)
    def test_output_paths_are_new_owned_and_main_is_not_overwritten(self):
        with tempfile.TemporaryDirectory(prefix='native-profile-fixture-',dir=ROOT/'build') as name:
            work=Path(name).resolve();self.assertTrue(work.is_relative_to(ROOT/'build'))
            original=work/'synthetic.main';original.write_bytes(self.image)
            with mock.patch.object(profile,'application_from_bytes',return_value=(self.image,{'input_kind':'application'})) as reader:
                out=work/'generated';doc=profile.create(original,out,self.functions,'fixture_profile');reader.assert_called_once_with(self.image)
            self.assertEqual(original.read_bytes(),self.image)
            self.assertEqual(json.loads((out/'native-profile.json').read_text()),doc)
            self.assertIn('fixture_profile_bindings',(out/'native-profile.h').read_text())
            with mock.patch.object(profile,'application_from_bytes',return_value=(self.image,{'input_kind':'application'})),self.assertRaises(ValueError):
                profile.create(original,out,self.functions)
            with mock.patch.object(profile,'application_from_bytes',return_value=(self.image,{'input_kind':'application'})),self.assertRaises(ValueError):
                profile.create(original,ROOT/'dist/not-a-profile-output',self.functions)
    def test_generated_c_arrays_compile_against_the_real_helper(self):
        cc=shutil.which('clang') or shutil.which('gcc')
        if not cc:
            candidate=Path('C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Tools/Llvm/x64/bin/clang.exe')
            if candidate.is_file():cc=str(candidate)
        if not cc:raise RuntimeError('Clang or GCC required')
        with tempfile.TemporaryDirectory(prefix='native-profile-c-',dir=ROOT/'build') as name:
            work=Path(name).resolve();self.assertTrue(work.is_relative_to(ROOT/'build'))
            doc=self.build();(work/'profile.h').write_text(profile.render_c(doc,'fixture_profile'))
            source=work/'fixture.c'
            source.write_text('#include "profile.h"\n_Static_assert(FIXTURE_PROFILE_COUNT==2u,"profile count");\n'
                '_Static_assert(FIXTURE_PROFILE_NATIVE_BEGIN < FIXTURE_PROFILE_NATIVE_END,"image interval");\n'
                'int main(void){return fixture_profile_bindings[0].kind!=FX_BIND_FUNCTION || '
                'fixture_profile_stock_main_sha256[0]!='+str(int(doc['stock_main_sha256'][:2],16))+'u || '+
                'fixture_profile_sha256[0]!='+str(int(doc['profile_sha256'][:2],16))+'u;}\n')
            executable=work/('fixture.exe' if os.name=='nt' else 'fixture')
            result=subprocess.run([cc,'-std=c11','-Wall','-Wextra','-Werror','-I'+str(ROOT/'include'),str(source),'-o',str(executable)],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result=subprocess.run([str(executable)],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
    def test_invalid_c_symbol_is_rejected_before_publication(self):
        for symbol in ('bad-name','1bad','x'*65,'a;void bad(void)'):
            with self.subTest(symbol=symbol),self.assertRaises(ValueError):profile.render_c(self.build(),symbol)

class RealStockProfileIntegration(unittest.TestCase):
    def test_real_local_stock_getter_profile_when_input_is_present(self):
        source=ROOT/'inputs/z8-c311-main.bin'
        if not source.is_file():self.skipTest('optional exact local stock MAIN is absent')
        original=profile.read_main(source)
        doc=profile.build_profile(original,[dict(name='probe.c311.get',address=0x410d5ec8)])
        self.assertTrue(profile.verify_profile(original,doc)['passed'])
        self.assertEqual(doc['stock_main_sha256'],'2b43a31c9de838f84b12416de4348a7004e65be07f853ec56ec2b10f3a8e3853')
        self.assertEqual(doc['functions'][0]['original'],'f37bbfa9f303002aecffff9720010036')

if __name__=='__main__':unittest.main()
