"""Composition guards and adversarial checks for the separate feature-suite layers."""
import os
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'host'))
from build_z8_feature_suite import merge_layers


class FeatureSuiteCompositionTests(unittest.TestCase):
    def test_composes_disjoint_layers_and_rejects_hidden_mutations(self):
        stock=b'0'*32
        core=bytearray(stock);core[4:8]=b'core'
        native=bytearray(stock);native[20:24]=b'feat'
        image=merge_layers(stock,core,native,[(4,8)],[(20,24)])
        self.assertEqual(image[4:8],b'core')
        self.assertEqual(image[20:24],b'feat')
        native[31]=1
        with self.assertRaisesRegex(ValueError,'unlisted'):
            merge_layers(stock,core,native,[(4,8)],[(20,24)])

    def test_shared_entry_requires_exact_reviewed_refinement(self):
        stock=b'0'*32
        core=bytearray(stock);core[4:8]=b'core'
        native=bytearray(stock);native[4:8]=b'orig'
        with self.assertRaisesRegex(ValueError,'overlap'):
            merge_layers(stock,core,native,[(4,8)],[(4,8)])
        with self.assertRaisesRegex(ValueError,'overlap'):
            merge_layers(stock,core,native,[(4,8)],[(4,8)],{(4,8):b'fake'})
        image=merge_layers(stock,core,native,[(4,8)],[(4,8)],{(4,8):b'orig'})
        self.assertEqual(image,bytes(core))

    def test_partial_overlap_is_rejected(self):
        stock=b'0'*32
        core=bytearray(stock);core[4:8]=b'core'
        native=bytearray(stock);native[6:10]=b'feat'
        with self.assertRaisesRegex(ValueError,'overlap'):
            merge_layers(stock,core,native,[(4,8)],[(6,10)],{(4,8):b'00fe'})

    def test_independent_recipe_rejects_native_or_unlisted_corruption(self):
        import json
        from verify_z8_feature_suite import verify_layers
        build=ROOT/Path(os.environ.get('FX_Z8_SUITE_BUILD','build/allfeatures-suite-20261106/candidate-2'))
        if not (build/'suite.json').is_file():
            self.skipTest('explicit complete feature-suite candidate is unavailable')
        stock=(build/'stock.main').read_bytes();core=(build/'core/z8-core.main').read_bytes()
        image=bytearray((build/'z8-suite.main').read_bytes())
        report=json.loads((build/'core/build.json').read_text())
        self.assertTrue(verify_layers(stock,core,image,report)['original_reconstructed'])
        image[0x8b0000]^=1
        with self.assertRaises(ValueError):
            verify_layers(stock,core,image,report)
        image[0x8b0000]^=1
        image[0x20000]^=1
        with self.assertRaisesRegex(ValueError,'unlisted'):
            verify_layers(stock,core,image,report)


if __name__ == '__main__':
    unittest.main()
