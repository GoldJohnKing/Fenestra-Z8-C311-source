"""Original file-wrapper integration; local pinned application inputs are optional."""
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'host'))
import verify_z8_file_abi as file_abi

INPUTS_READY=all((ROOT/'inputs'/name).is_file() for name in ('z8-c311-main.bin','z9-c532-main.bin')) and (ROOT/'build/z8-full-port/correspondence/address-map.json').is_file()


@unittest.skipUnless(INPUTS_READY,'requires operator-provided exact original applications and correspondence')
class Z8FileAbiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.z8=(ROOT/'inputs/z8-c311-main.bin').read_bytes()
        cls.z9=(ROOT/'inputs/z9-c532-main.bin').read_bytes()
        cls.mapping=json.loads((ROOT/'build/z8-full-port/correspondence/address-map.json').read_text())['mappings']
        cls.report=file_abi.verify(cls.z8,cls.z9,cls.mapping)
        cls.cases={row['case']:row for row in cls.report['checks'] if row['model']=='z8'}

    def test_all_nine_interfaces_run_both_originals(self):
        self.assertEqual(len(self.report['interfaces']),9)
        self.assertEqual(self.report['models_checked'],2)
        self.assertEqual(self.report['executed_cases'],80)
        self.assertEqual(self.report['cases_per_model'],40)
        self.assertFalse(self.report['runtime_ready'])
        self.assertFalse(self.report['abi_validated'])
        self.assertTrue(all(row['original_instructions_executed']>0 for row in self.report['checks']))

    def test_read_accumulates_and_preserves_error_progress(self):
        case=self.cases['read.partial_then_error']
        self.assertEqual(case['return_u32'],0x80000002)
        self.assertEqual(case['details']['final_actual'],4)
        self.assertEqual([row['request'] for row in case['details']['calls']],[7,4])
        self.assertEqual([row['buffer_delta'] for row in case['details']['calls']],[0,3])
        self.assertEqual(self.cases['read.zero_progress']['details']['final_actual'],0)

    def test_write_backpressure_is_not_generic_error_passthrough(self):
        self.assertEqual(self.cases['write.backpressure_then_success']['return_u32'],0)
        self.assertEqual(self.cases['write.repeated_backpressure']['return_u32'],0x80005010)
        self.assertEqual(len(self.cases['write.repeated_backpressure']['details']['calls']),2)
        self.assertEqual(self.cases['write.full_with_backpressure']['return_u32'],0)
        self.assertEqual(self.cases['write.full_with_backpressure']['details']['final_actual'],7)

    def test_seek_preserves_64bit_values_with_native_bool_results(self):
        for origin in (0,1,2):
            success=self.cases['seek64.'+str(origin)+'.0x1']
            failure=self.cases['seek64.'+str(origin)+'.0x0']
            self.assertEqual(success['details']['offset'],'0x123456789abcdef0')
            self.assertEqual(success['details']['output_position'],'0xfedcba9876543210')
            self.assertEqual(success['return_u32'],1)
            self.assertEqual(failure['return_u32'],0)
            self.assertEqual(failure['details']['output_position'],'0x1111111111111111')
            self.assertEqual(success['details']['fixture_kind'],'native-bool')
            self.assertEqual(failure['details']['fixture_kind'],'native-bool')
            self.assertEqual(success['details']['backend_argument_order'],['fd','offset64','position64_pointer','origin'])

    def test_seek_noncanonical_value_only_checks_wrapper_normalization(self):
        for origin in (0,1,2):
            case=self.cases['seek64.'+str(origin)+'.0x80000002']
            self.assertEqual(case['return_u32'],1)
            self.assertEqual(case['details']['output_position'],'0x1111111111111111')
            self.assertEqual(case['details']['fixture_kind'],'noncanonical-normalization-only')

    def test_directory_end_is_preserved_and_locks_balance(self):
        self.assertEqual(self.cases['directory.next.0x80000030']['return_u32'],0x80000030)
        self.assertTrue(all(row['mutex_acquire_release_balanced'] for row in self.report['checks']))
        self.assertEqual({row['mutex'] for row in self.report['checks'] if row['model']=='z8'},{'0xa02e81dd8'})

    def test_wrong_whole_image_rejected_before_emulation(self):
        changed=bytearray(self.z8);changed[0]^=1
        with mock.patch.object(file_abi,'platform_wrappers',side_effect=AssertionError('must not run')):
            with self.assertRaisesRegex(ValueError,'SHA-256'):
                file_abi.verify(changed,self.z9,self.mapping)


if __name__=='__main__':unittest.main()
