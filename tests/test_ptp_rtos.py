"""RTOS wait ownership and output tests; no camera or USB transport."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'host'))
from ptp_rtos import RtosDebug


class Endpoint:
    def __init__(self,states,outputs):
        self.states=list(states);self.outputs=outputs;self.requests=[]

    def query(self,operation,data):
        if operation!=7:raise AssertionError('RTOS operation required')
        op=struct.unpack_from('<I',data)[0]
        self.requests.append((op,data[4:]))
        if op==4:
            job,phase,produced=self.states.pop(0)
            raw=bytearray(64)
            struct.pack_into('<4s5I',raw,0,b'FXS1',1,3,phase,job,77)
            struct.pack_into('<QIIQ4I',raw,24,0,produced,0,123,1,0,5000,0)
            return bytes(raw)
        if op==6:
            job,offset,count=struct.unpack_from('<III',data,4)
            return self.outputs[job][offset:offset+count]
        raise AssertionError('Unexpected RTOS request')


class RtosWaitTests(unittest.TestCase):
    def test_foreign_job_rejected_before_output_is_read(self):
        endpoint=Endpoint([(2,3,5)],{2:b'OTHER'})
        streamed=[]
        with self.assertRaisesRegex(ValueError,'job identity'):
            RtosDebug(endpoint).wait_job(1,stream=streamed.append)
        self.assertEqual([op for op,_ in endpoint.requests],[4])
        self.assertEqual(streamed,[])

    def test_job_change_after_partial_output_does_not_mix_logs(self):
        endpoint=Endpoint([(1,2,3),(2,3,7)],{1:b'OWN',2:b'FOREIGN'})
        streamed=[]
        with self.assertRaisesRegex(ValueError,'job identity'):
            RtosDebug(endpoint).wait_job(1,stream=streamed.append)
        self.assertEqual(b''.join(streamed),b'OWN')
        reads=[struct.unpack('<III',raw)[0] for op,raw in endpoint.requests if op==6]
        self.assertEqual(reads,[1])

    def test_matching_job_retains_segmented_output_and_streaming(self):
        output=bytes(range(256))*4+b'first!last'
        endpoint=Endpoint([(9,2,1025),(9,3,len(output))],{9:output})
        streamed=[]
        result=RtosDebug(endpoint).wait_job(9,stream=streamed.append)
        self.assertEqual(result['job'],9)
        self.assertEqual(result['state'],'done')
        self.assertEqual(result['output'],output)
        self.assertEqual(b''.join(streamed),output)
        reads=[struct.unpack('<III',raw) for op,raw in endpoint.requests if op==6]
        self.assertEqual(reads,[(9,0,1024),(9,1024,1),(9,1025,len(output)-1025)])

    def test_matching_cancelled_jobs_keep_their_output(self):
        for phase in (4,5):
            with self.subTest(phase=phase):
                endpoint=Endpoint([(7,phase,3)],{7:b'LOG'})
                result=RtosDebug(endpoint).wait_job(7)
                self.assertEqual(result['phase'],phase)
                self.assertEqual(result['output'],b'LOG')

    def test_invalid_job_rejected_before_query(self):
        for job in (0,-1,1<<32):
            with self.subTest(job=job):
                endpoint=Endpoint([],{})
                with self.assertRaisesRegex(ValueError,'job identifier'):
                    RtosDebug(endpoint).wait_job(job)
                self.assertEqual(endpoint.requests,[])


if __name__=='__main__':unittest.main()
