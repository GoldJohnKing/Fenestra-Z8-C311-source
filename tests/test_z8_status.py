"""Exercise the user status command over actual FXP2 client framing."""
import struct,unittest,zlib
from test_z8_host import SyntheticEndpoint,IDENTITY
from ptp_client import Client,HEADER,HELLO
from z8_status import read_status
CAPABILITIES=355
class Endpoint(SyntheticEndpoint):
 def __init__(self,active=1):
  super().__init__();identity=bytearray(self.identity);struct.pack_into('<I',identity,28,CAPABILITIES);self.identity=bytes(identity);self.active=active
 def read(self,operation,params,maximum):
  if operation==HELLO:return struct.pack('<4sIQ4I',b'FXP2',2,123,1024,CAPABILITIES,311,1)+bytes(32)
  request=HEADER.unpack_from(self.pending)
  if request[2]!=1:return super().read(operation,params,maximum)
  payload=struct.pack('<3I',311,self.active,CAPABILITIES)+bytes(20)
  raw=HEADER.pack(b'FXP2',2,request[2],request[3],request[4],len(payload),0x80000000,0)+payload
  return raw[:28]+struct.pack('<I',zlib.crc32(raw))+raw[32:]
class Z8StatusTests(unittest.TestCase):
 def test_real_client_frame_to_human_status(self):
  endpoint=Endpoint();result=read_status(Client(endpoint))
  self.assertEqual(result['application_sha256'],IDENTITY.hex());self.assertTrue(result['fenestra_active']);self.assertEqual(result['build_identity'],'ab'*32)
  self.assertEqual(len(endpoint.writes),2)
 def test_wrong_application_rejected_before_status_request(self):
  endpoint=Endpoint();identity=bytearray(endpoint.identity);identity[64]^=1;endpoint.identity=bytes(identity)
  with self.assertRaisesRegex(ValueError,'exact Z8'):read_status(Client(endpoint))
  self.assertEqual(len(endpoint.writes),1)
 def test_inconsistent_backend_status_is_rejected(self):
  with self.assertRaisesRegex(ValueError,'disagree'):read_status(Client(Endpoint(active=2)))
if __name__=='__main__':unittest.main()
