"""Z8 host/SDK identity checks using synthetic transports only; no camera opened."""
import hashlib
import importlib
from pathlib import Path
import struct
import subprocess
import sys
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'host'))
import build_sdk_module
from module_header import validate_package
import platform_profiles
from ptp_contract import check_profile, identify
from ptp_identity import parse_identity
from ptp_client import Client, HEADER, HELLO, FETCH, request_frame
from z8_port import research_profile

IDENTITY = bytes.fromhex('2b43a31c9de838f84b12416de4348a7004e65be07f853ec56ec2b10f3a8e3853')
COMPONENT = bytes.fromhex('f85e0138e2f5e660ece8560de62e0d12cb795e0e14983e50f20b61dce906c46c')
CAPS = 1 << 8


def endpoint_identity(firmware=311):
    data = bytearray(256)
    data[:4] = b'FXI1'
    struct.pack_into('<10I', data, 4, 1, 256, 2, 1, 1, 1, CAPS, firmware, 1, 0)
    data[64:96] = IDENTITY
    data[96:128] = IDENTITY
    data[128:160] = bytes.fromhex('ab' * 32)
    data[160:168] = b'Nikon Z8'
    data[208:214] = b'C 3.11'
    return bytes(data)


def synthetic_module():
    header = bytearray(128)
    header[:8] = b'FENESTRA'
    struct.pack_into('<4I', header, 8, 2, 128, 1, 1)
    header[24:56] = IDENTITY
    body = struct.pack('<6I', 0, 152, 4, 4, 5, 4) + bytes.fromhex('c0035fd6')
    header[56:88] = hashlib.sha256(body).digest()
    struct.pack_into('<5IQ', header, 88, 128 + len(body), 4, 0, 1, 0, 0x3f0000)
    struct.pack_into('<I', header, 116, 1)
    return bytes(header) + body


class SyntheticEndpoint:
    def __init__(self, firmware=311):
        self.identity = endpoint_identity(firmware)
        self.pending = None
        self.writes = []

    def read(self, operation, params, maximum):
        if operation == HELLO:
            return struct.pack('<4sIQ4I', b'FXP2', 2, 123, 1024, CAPS, 311, 1) + bytes(32)
        if operation != FETCH or self.pending is None:
            raise AssertionError('unexpected synthetic transfer')
        request = HEADER.unpack_from(self.pending)
        raw = HEADER.pack(b'FXP2', 2, request[2], request[3], request[4], len(self.identity), 0x80000000, 0) + self.identity
        return raw[:28] + struct.pack('<I', zlib.crc32(raw)) + raw[32:]

    def write(self, operation, params, payload):
        self.writes.append((operation, params, payload))
        self.pending = payload


class Z8HostTests(unittest.TestCase):
    def test_all_z8_ptp_aliases_are_admitted(self):
        for model in ('Z 8', 'Z8'):
            for version in ('3.11', 'V3.11'):
                self.assertEqual(identify(model, version), 'z8-c311')
                self.assertEqual(identify(model, version, 'z8-c311'), 'z8-c311')
        self.assertEqual(check_profile('z8-c311'), 'z8-c311')

    def test_other_model_or_firmware_is_rejected(self):
        for model, version in (('Z 9', '3.11'), ('ZR', '3.11'), ('Z 8', '3.10'),
                               ('Z 8', '3.12'), ('Z 8', '5.32'), ('Nikon Z8', '3.11')):
            with self.assertRaises(ValueError):
                identify(model, version, 'z8-c311')
        with self.assertRaises(ValueError):
            identify('Z 8', '3.11', 'z9-c532')

    def test_upstream_model_aliases_preserved(self):
        self.assertEqual(identify('Z 9', 'V5.32'), 'z9-c532')
        self.assertEqual(identify('ZR', '1.10'), 'zr-c110')

    def test_fxi1_application_and_module_target_match_application(self):
        identity = parse_identity(endpoint_identity())
        self.assertEqual(identity['firmware_code'], 311)
        self.assertEqual(identity['model'], 'Nikon Z8')
        self.assertEqual(identity['firmware'], 'C 3.11')
        self.assertEqual(identity['application_sha256'], IDENTITY.hex())
        self.assertEqual(identity['module_target_sha256'], IDENTITY.hex())
        self.assertNotEqual(identity['module_target_sha256'], COMPONENT.hex())

    def test_client_hello_accepts_z8_without_native_transport(self):
        endpoint = SyntheticEndpoint()
        report = Client(endpoint).hello()
        self.assertEqual(report['firmware'], 'C 3.11')
        self.assertEqual(report['model'], 'Nikon Z8')
        self.assertEqual(report['identity']['module_target_sha256'], IDENTITY.hex())
        self.assertEqual(len(endpoint.writes), 1)

    def test_inconsistent_fxi1_firmware_is_rejected(self):
        client = Client(SyntheticEndpoint(firmware=532))
        with self.assertRaisesRegex(ValueError, 'identity differs'):
            client.hello()
        self.assertEqual(client.session, 0)

    def test_sdk_uses_complete_profile_without_mutating_registry(self):
        before = tuple(platform_profiles.PROFILES)
        profiles = build_sdk_module.sdk_profiles()
        self.assertEqual(tuple(platform_profiles.PROFILES), before)
        self.assertIn('z8-c311', platform_profiles.PROFILES)
        self.assertEqual(profiles['z8-c311']['port_scope'],'complete-native-core')
        self.assertEqual(profiles['z8-c311'],platform_profiles.PROFILES['z8-c311'])
        self.assertIn('camera.card.seek64',profiles['z8-c311']['functions'])
        self.assertIn('rtos.task.create',profiles['z8-c311']['functions'])
        self.assertIn('z8-c311', profiles)
        self.assertEqual(profiles['z8-c311']['module_identity'], IDENTITY.hex())
        self.assertEqual(profiles['z8-c311']['sha256'], IDENTITY.hex())
        self.assertFalse(profiles['z8-c311']['runtime_ready'])
        self.assertFalse(profiles['z8-c311']['physical_qualified'])

    def test_module_header_accepts_only_chosen_z8_identity(self):
        data = synthetic_module()
        self.assertEqual(validate_package(data, IDENTITY)['entry_abi'], 1)
        for wrong in (COMPONENT, bytes.fromhex(platform_profiles.PROFILES['z9-c532']['module_identity'])):
            with self.assertRaisesRegex(ValueError, 'module target'):
                validate_package(data, wrong)
        changed = bytearray(data)
        changed[24:56] = COMPONENT
        with self.assertRaisesRegex(ValueError, 'module target'):
            validate_package(changed, IDENTITY)

    def test_module_corruption_remains_rejected(self):
        changed = bytearray(synthetic_module())
        changed[-1] ^= 1
        with self.assertRaisesRegex(ValueError, 'checksum'):
            validate_package(changed, IDENTITY)

    def test_host_imports_do_not_load_usb_or_com_or_open_devices(self):
        script = r'''
import importlib, importlib.abc, sys
sys.path.insert(0, sys.argv[1])
class RefuseDeviceLibraries(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'usb' or fullname.startswith('usb.') or fullname == 'comtypes' or fullname.startswith('comtypes.'):
            raise AssertionError('import tried to access native device library: ' + fullname)
sys.meta_path.insert(0, RefuseDeviceLibraries())
for name in ('ptp_contract', 'ptp_identity', 'ptp_client', 'ptp_usb', 'ptp_wpd', 'ptp_process', 'ptp_transport', 'ptp_remote', 'build_sdk_module'):
    importlib.import_module(name)
print('inert imports verified')
'''
        result = subprocess.run([sys.executable, '-B', '-c', script, str(ROOT / 'host')],
                                check=True, capture_output=True, text=True, timeout=30)
        self.assertIn('inert imports verified', result.stdout)

if __name__ == '__main__':
    unittest.main()
