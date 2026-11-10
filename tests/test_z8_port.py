"""Synthetic Z8 admission regressions; no firmware distribution or camera access."""
import binascii
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'host'))
import z8_container as container
import z8_port


def digest(data):
    return hashlib.sha256(data).hexdigest()


class Z8TargetTests(unittest.TestCase):
    def test_exact_original_identities_are_distinct(self):
        rows = container.TARGET['identities']
        self.assertEqual(rows['package'], dict(bytes=99051117, sha256='d67413c2ede6b9ce8887175f20700bd9fbad2a973a4820968c45503d15d80d96'))
        self.assertEqual(rows['component'], dict(bytes=81807711, sha256='f85e0138e2f5e660ece8560de62e0d12cb795e0e14983e50f20b61dce906c46c'))
        self.assertEqual(rows['application'], dict(bytes=81807709, sha256='2b43a31c9de838f84b12416de4348a7004e65be07f853ec56ec2b10f3a8e3853'))
        self.assertEqual(container.TARGET['module_name'], 'eg2070_0311b0.bi')

    def test_profile_does_not_claim_missing_abi(self):
        profile = z8_port.research_profile()
        self.assertFalse(profile['runtime_ready'])
        self.assertNotIn('camera.card.seek64', profile['functions'])
        self.assertNotIn('rtos.task.create', profile['functions'])
        self.assertNotIn('camera.card.directory.open', profile['functions'])
        self.assertEqual(profile['functions']['camera.card.seek32'], 0x402dac24)
        self.assertGreater(len(profile['blockers']), 0)

    def test_observed_fingerprints_have_provenance(self):
        for row in container.TARGET['bindings']:
            self.assertEqual(row['fingerprint_bytes'], 16)
            self.assertEqual(len(bytes.fromhex(row['fingerprint_sha256'])), 32)
            self.assertFalse(row['runtime_qualified'])
            self.assertTrue(row['source'].startswith('z8pixelshift/'))

    def test_profile_registration_is_explicit_and_idempotent(self):
        registry = {}
        first = z8_port.register_profile(registry)
        self.assertEqual(first, z8_port.register_profile(registry))
        self.assertFalse(registry['z8-c311']['runtime_ready'])
        with self.assertRaises(ValueError):
            z8_port.register_profile({'z8-c311': {'different': True}})


class Z8AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.application = bytes(range(128))
        self.component = self.application + binascii.crc_hqx(self.application, 0).to_bytes(2, 'big')
        self.package = b'P' * 257
        self.identities = {name: dict(bytes=len(data), sha256=digest(data)) for name, data in (
            ('package', self.package), ('component', self.component), ('application', self.application))}
        self.modules = [dict(name='eg2070_0311b0.bi', start=64, bytes=len(self.component), sha256=digest(self.component))]
        self.target_patch = mock.patch.dict(container.TARGET, {
            'identities': self.identities, 'modules': self.modules,
            'external_reader': dict(relative_path='z8prores/package.py', sha256='0' * 64,
                                    license='synthetic external dependency')})
        self.target_patch.start()
        self.addCleanup(self.target_patch.stop)
        patch = mock.patch.object(container, 'IDENTITIES', self.identities)
        patch.start()
        self.addCleanup(patch.stop)
        self.input = self.root / 'input.bin'
        self.output = self.root / 'application.bin'

    def write_input(self, data):
        self.input.write_bytes(data)
        return self.input

    def external(self, *, component=None, modules=None):
        project = self.root / 'external'
        source = project / 'z8prores' / 'package.py'
        source.parent.mkdir(parents=True, exist_ok=True)
        component = self.component if component is None else component
        modules = self.modules if modules is None else modules
        text = 'class Package:\n    def __init__(self, raw):\n        self.eg = bytes.fromhex(' + repr(component.hex()) + ')\n        self.modules = ' + repr(modules) + '\n'
        source.write_text(text, encoding='utf-8')
        container.TARGET['external_reader']['sha256'] = digest(source.read_bytes())
        return project

    def test_application_extract_is_exact_and_input_preserved(self):
        self.write_input(self.application)
        receipt = container.extract(self.input, self.output)
        self.assertEqual(self.output.read_bytes(), self.application)
        self.assertEqual(self.input.read_bytes(), self.application)
        self.assertFalse(receipt['runtime_ready'])
        self.assertFalse(receipt['flashable_package_produced'])
        self.assertTrue(receipt['embedded_main_verified'])

    def test_component_strips_only_verified_crc(self):
        self.write_input(self.component)
        receipt = container.extract(self.input, self.output)
        self.assertEqual(receipt['input_kind'], 'component')
        self.assertEqual(self.output.read_bytes(), self.application)

    def test_component_output_is_rechecked(self):
        self.write_input(self.application)
        container.extract(self.input, self.output, output_kind='component')
        self.assertEqual(self.output.read_bytes(), self.component)
        self.assertEqual(binascii.crc_hqx(self.output.read_bytes(), 0), 0)

    def test_package_inspect_needs_no_decoder_and_creates_no_files(self):
        self.write_input(self.package)
        with mock.patch.object(container, '_load_external_reader', side_effect=AssertionError('must not load')):
            receipt = container.inspect(self.input)
        self.assertFalse(receipt['embedded_main_verified'])
        self.assertFalse(receipt['runtime_ready'])
        self.assertEqual(list(self.root.iterdir()), [self.input])

    def test_package_extract_requires_explicit_decoder(self):
        self.write_input(self.package)
        with self.assertRaisesRegex(ValueError, 'external-project'):
            container.extract(self.input, self.output)
        self.assertFalse(self.output.exists())

    def test_external_decode_is_pinned_and_returned_component_verified(self):
        project = self.external()
        self.write_input(self.package)
        receipt = container.extract(self.input, self.output, external_project=project)
        self.assertEqual(self.output.read_bytes(), self.application)
        self.assertEqual(receipt['components'], self.modules)
        self.assertIn('source_sha256', receipt['external_reader'])
        self.assertTrue(receipt['embedded_main_verified'])
        self.assertFalse((project / 'z8prores' / '__pycache__').exists())

    def test_external_inspection_reports_actual_components(self):
        project = self.external()
        self.write_input(self.package)
        receipt = container.inspect(self.input, external_project=project)
        self.assertEqual(receipt['components'], self.modules)
        self.assertFalse(self.output.exists())

    def test_bad_reader_digest_is_rejected_before_execution(self):
        project = self.external()
        source = project / 'z8prores' / 'package.py'
        sentinel = self.root / 'executed'
        source.write_text('from pathlib import Path\nPath(' + repr(str(sentinel)) + ').touch()\n', encoding='utf-8')
        self.write_input(self.package)
        with self.assertRaisesRegex(ValueError, 'reader source SHA-256'):
            container.extract(self.input, self.output, external_project=project)
        self.assertFalse(sentinel.exists())
        self.assertFalse(self.output.exists())

    def test_modified_input_rejected_before_decoder_loading(self):
        self.write_input(b'Q' + self.package[1:])
        with mock.patch.object(container, '_load_external_reader', side_effect=AssertionError('must not load')):
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                container.extract(self.input, self.output, external_project=self.root)
        self.assertFalse(self.output.exists())

    def test_truncated_input_rejected_without_output(self):
        self.write_input(self.component[:-3])
        with self.assertRaises(ValueError):
            container.extract(self.input, self.output)
        self.assertFalse(self.output.exists())

    def test_wrong_extracted_main_rejected_without_output(self):
        project = self.external(component=b'X' + self.component[1:])
        self.write_input(self.package)
        with self.assertRaisesRegex(ValueError, 'extracted MAIN component'):
            container.extract(self.input, self.output, external_project=project)
        self.assertFalse(self.output.exists())

    def test_wrong_module_name_rejected(self):
        rows = copy.deepcopy(self.modules)
        rows[0]['name'] = 'eg1990_053200.bi'
        project = self.external(modules=rows)
        self.write_input(self.package)
        with self.assertRaisesRegex(ValueError, 'component directory'):
            container.extract(self.input, self.output, external_project=project)
        self.assertFalse(self.output.exists())

    def test_duplicate_or_missing_module_rejected(self):
        for rows in ([], self.modules * 2):
            project = self.external(modules=rows)
            self.write_input(self.package)
            with self.assertRaisesRegex(ValueError, 'component directory'):
                container.extract(self.input, self.output, external_project=project)
            self.assertFalse(self.output.exists())

    def test_crc_is_independently_checked_after_identity(self):
        changed = self.component[:-1] + bytes([self.component[-1] ^ 1])
        self.identities['component']['sha256'] = digest(changed)
        with self.assertRaisesRegex(ValueError, 'CRC16'):
            container.identify(changed)

    def test_existing_output_and_input_are_preserved(self):
        self.write_input(self.application)
        self.output.write_bytes(b'keep')
        with self.assertRaises(FileExistsError):
            container.extract(self.input, self.output)
        self.assertEqual(self.output.read_bytes(), b'keep')
        with self.assertRaises(FileExistsError):
            container.extract(self.input, self.input)
        self.assertEqual(self.input.read_bytes(), self.application)

    def test_update_package_output_is_not_supported(self):
        self.write_input(self.application)
        with self.assertRaisesRegex(ValueError, 'only application'):
            container.extract(self.input, self.output, output_kind='package')
        self.assertFalse(self.output.exists())

    def test_verified_profile_rejects_wrong_full_image_first(self):
        with mock.patch.object(z8_port, 'verify_binding_fingerprints', side_effect=AssertionError('must not run')):
            with self.assertRaisesRegex(ValueError, 'application'):
                z8_port.verified_profile(b'X' + self.application[1:])

    def test_fingerprint_mutation_and_bounds_rejected(self):
        row = dict(name='synthetic.card.read', address=hex(z8_port.BASE + 32),
                   original=self.application[32:48].hex())
        self.assertEqual(z8_port.verify_binding_fingerprints(self.application, [row]), [row])
        changed = self.application[:33] + b'X' + self.application[34:]
        with self.assertRaisesRegex(ValueError, 'binding bytes'):
            z8_port.verify_binding_fingerprints(changed, [row])
        for address in (z8_port.BASE - 1, z8_port.BASE + len(self.application) - 8):
            row['address'] = hex(address)
            with self.assertRaisesRegex(ValueError, 'fingerprint range'):
                z8_port.verify_binding_fingerprints(self.application, [row])


if __name__ == '__main__':
    unittest.main()
