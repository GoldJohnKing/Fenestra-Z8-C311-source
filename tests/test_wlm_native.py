"""Exercise production C WLM native composition; original I/O is not called."""
import hashlib,json,os,random,shutil,struct,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'host'))
import wlm_native as w
from z8_native_capsule import Patch,encode,decode,IMAGE,HOOK,EXEC,WRITE,POINTER,DATA,STOCK_SHA256
TARGET=bytes.fromhex(STOCK_SHA256);REQUIRED=0x81947c592af69a37

class NativeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  (ROOT/'build').mkdir(exist_ok=True)
  cls.temp=tempfile.TemporaryDirectory(prefix='wlm-native-test-',dir=ROOT/'build');cls.folder=Path(cls.temp.name);cls.exe=cls.folder/('driver.exe' if os.name=='nt' else 'driver')
  clang=shutil.which('clang') or 'C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Tools/Llvm/x64/bin/clang.exe'
  command=[clang,'-std=c11','-O1','-Wall','-Wextra','-Werror','-Wconversion','-Wshadow','-Wno-misleading-indentation','-I'+str(ROOT/'include'),*[str(ROOT/f)for f in ('tests/test_wlm_native_driver.c','src/wlm_native.c','src/memory.c','src/sha256.c')],'-o',str(cls.exe)]
  subprocess.run(command,check=True,capture_output=True,timeout=45)
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 def component(self,name,bit,rank,patches=None,entry=0,version=1,variants=None):
  if variants is None:variants=[dict(mask=0,value=0,capsule=encode(patches,rank+1,REQUIRED,entry))]
  return w.encode_component(name,version,bit,rank,variants,target=TARGET,requires_id=REQUIRED)
 def fixture(self):
  a=self.component('framing',1,10,[Patch(IMAGE,EXEC,0x408e0000,bytes(4),bytes.fromhex('c0035fd6')),Patch(HOOK,POINTER,0x44000000,bytes(8),struct.pack('<Q',0x408e0000))],0x408e0000)
  b=self.component('prores',2,11,[Patch(IMAGE,EXEC,0x408f0000,bytes(4),bytes.fromhex('c0035fd6'))],0x408f0000)
  variants=[dict(mask=3,value=i,capsule=encode([Patch(IMAGE,0,0x40930000,bytes(4096),bytes([i])*4096)],100+i,REQUIRED))for i in (1,2,3)]
  shared=self.component('shared.locale',0,90,variants=variants)
  return a,b,shared
 def actual(self,components,fail=0):
  files=[]
  for i,data in enumerate(components):
   p=self.folder/(str(i)+'.wnc');p.write_bytes(data);files.append(str(p))
  output=self.folder/'actual.fnc';output.unlink(missing_ok=True)
  completed=subprocess.run([str(self.exe),str(fail),str(output),TARGET.hex(),format(REQUIRED,'x'),*files],capture_output=True,text=True,timeout=20)
  self.assertEqual(completed.returncode,0,completed.stdout+completed.stderr);result=json.loads(completed.stdout);self.assertEqual(result['live'],0)
  return result,output.read_bytes()if output.exists()else None
 def test_all_small_compositions_actual_c_matches_reference(self):
  a,b,s=self.fixture()
  for rows in ([a,s],[b,s],[a,b,s],[s,b,a,s,a]):
   expected,meta=w.compose_components(rows,target=TARGET,requires_id=REQUIRED);actual,raw=self.actual(rows)
   self.assertEqual(actual['result'],0);self.assertEqual(raw,expected);self.assertEqual(actual['entries'],meta['entries']);self.assertEqual(actual['selection'],meta['selection'])
   parsed=decode(raw);hooks=[p for p in parsed['patches']if p.kind==HOOK]
   if hooks:self.assertEqual(hooks[0].depends,0)
 def test_empty_and_missing_selector(self):
  result,raw=self.actual([]);self.assertEqual(result['result'],0);self.assertIsNone(raw)
  result,_=self.actual([self.fixture()[2]]);self.assertNotEqual(result['result'],0)
 def test_every_allocation_failure_reclaims_scratch(self):
  rows=list(self.fixture());good,_=self.actual(rows)
  for fail in range(1,good['allocations']+1):
   result,raw=self.actual(rows,fail);self.assertNotEqual(result['result'],0);self.assertIsNone(raw)
 def test_unique_feature_update_does_not_require_other_bytes(self):
  a,b,s=self.fixture();before=[hashlib.sha256(x).digest()for x in (b,s)]
  updated=self.component('framing',1,10,[Patch(IMAGE,EXEC,0x408e0000,bytes(4),bytes.fromhex('1f2003d5')),Patch(HOOK,POINTER,0x44000000,bytes(8),struct.pack('<Q',0x408e0000))],0x408e0000,version=2)
  actual,raw=self.actual([updated,b,s]);expected,_=w.compose_components([updated,b,s],target=TARGET,requires_id=REQUIRED)
  self.assertEqual(actual['result'],0);self.assertEqual(raw,expected);self.assertNotEqual(a,updated);self.assertEqual(before,[hashlib.sha256(x).digest()for x in (b,s)])
 def test_conflicts_and_overlap_fail_closed(self):
  a,b,s=self.fixture();different=self.component('framing',1,10,[Patch(IMAGE,EXEC,0x408e0000,bytes(4),bytes.fromhex('1f2003d5'))],0x408e0000,version=2)
  collision=self.component('other',1,11,[Patch(IMAGE,0,0x40940000,bytes(4),bytes([1])*4)])
  overlap=self.component('other',2,11,[Patch(IMAGE,0,0x408e0002,bytes(4),bytes([2])*4)])
  for rows in ([a,different],[a,collision],[a,overlap]):
   result,_=self.actual(rows);self.assertNotEqual(result['result'],0)
 def test_corruption_metadata_and_compressed_reference_rejected(self):
  a,b,s=self.fixture()
  for at in (0,12,16,52,64,72,104,148,160,180,len(s)-1):
   bad=bytearray(s);bad[at]^=0x80;result,_=self.actual([a,b,bytes(bad)]);self.assertNotEqual(result['result'],0,str(at))
  # Preserve the outer hash while invalidating the first compressed block.
  bad=bytearray(s);boff=struct.unpack_from('<I',bad,140)[0];at=struct.unpack_from('<I',bad,boff+4)[0];bad[at:at+3]=bytes(3);bad[104:136]=w.digest(bad[160:]);result,_=self.actual([a,bytes(bad)]);self.assertNotEqual(result['result'],0)
 def test_ambiguous_selector_rejected_after_rehash(self):
  a,b,s=self.fixture();bad=bytearray(s);bad[224:232]=bad[160:168];bad[104:136]=w.digest(bad[160:]);result,_=self.actual([a,b,bytes(bad)]);self.assertNotEqual(result['result'],0)
 def test_lzss_roundtrip_and_bad_references(self):
  randomizer=random.Random(391)
  for data in (b'a',b'a'*4096,bytes(range(256))*16,randomizer.randbytes(4096)):
   self.assertEqual(w.lzss_unpack(w.lzss_pack(data),len(data)),data)
  for data,n in ((bytes(3),4),(b'\x01',1),(b'\xffa',1),(b'\x01aX',1)):
   with self.assertRaises(ValueError):w.lzss_unpack(data,n)

if __name__=='__main__':unittest.main()
