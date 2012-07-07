import unittest
from p2pool.util import sharelog, variable
from p2pool.bitcoin import data as bitcoin_data
from p2pool.data import OkayTracker
from p2pool import networks
from p2pool import data as p2pool_data
import time

def set_time(x):
    sharelog.clock = lambda: x

class TestCaseLogger:
    def __init__(self): self.buffer = []
    def write(self, msg):
        import sys
        sys.stderr.write(msg)
        self.buffer.append(msg)
    def flush(self): pass

class MockTracker:
   verified = None

class MockWorkerBridge:
    net = networks.nets['bitcoin']
    def __init__(self):
        self.pseudoshare_received = variable.Event()
        self.new_work_event = variable.Event()
        self.current_work = variable.Variable(None)
        self.my_share_hashes = set()
        self.my_doa_share_hashes = set()
        self.tracker = OkayTracker(self.net, self.my_share_hashes, self.my_doa_share_hashes)
        self.bitcoind_work = variable.Variable({'bits':bitcoin_data.FloatingInteger.from_target_upper_bound(0xffff<<208), 'subsidy':5000000000})
        self.best_share_var = variable.Variable(None)
        self.my_pubkey_hash = 0

class MockShare:
    def __init__(self, share_hash, pow_hash=0x10000<<208, share_target=0xffff<<208, block_target=0xffff<<200, ):
        self.share_info = {'bits':bitcoin_data.FloatingInteger.from_target_upper_bound(share_target)}
        self.header = {'bits':bitcoin_data.FloatingInteger.from_target_upper_bound(block_target)}
        self.hash = share_hash 
        self.pow_hash = pow_hash

#class DataTestCase(unittest.TestCase):
#    def setUp(self):
#        self.wb = MockWorkerBridge()
#        self.data = sharelog.Data(self.wb)
#    def tearDown(self):
#        self.wb = None
#        self.data = None
#    def testCount(self):
#        self.assertEqual(0,self.data.count)
#    def testAverage(self):
#        self.assertEquals(0.0, self.data.age)

class LoggerTestCase(unittest.TestCase):
    def setUp(self):
        self.wb = MockWorkerBridge()
        self.wb.current_work.set({'subsidy':5000000000})
        self.log = TestCaseLogger()
        self.pseudotracker = sharelog.PseudoShareTracker()
    def tearDown(self):
        self.wb = None
        self.log = None
    def testEvent(self):
        class Result: success = False
        @self.wb.new_work_event.watch
        def _():
            Result.success = True
        self.wb.new_work_event.happened()
        self.failUnless(Result.success)
    def testGoodPseudoShareEvent(self):
        self.pseudotracker.track(self.wb, self.log)
        self.wb.new_work_event.happened()
        self.wb.pseudoshare_received.happened(0.0, True, 'tester')
        self.assertEqual(0,self.pseudotracker.count_accepted.count) 
        self.assertEqual(1,self.pseudotracker.count_rejected.count) 
    def testBadPseudoShareEvent(self):
        self.pseudotracker.track(self.wb, self.log)
        self.wb.new_work_event.happened()
        self.wb.pseudoshare_received.happened(0.0, False, 'tester')
        self.assertEqual(1,self.pseudotracker.count_accepted.count) 
        self.assertEqual(0,self.pseudotracker.count_rejected.count) 
    def testNewShare(self):
        #set_time(1341602883.753726)
        self.pseudotracker.track(self.wb, self.log)

        self.wb.new_work_event.happened()

        self.wb.pseudoshare_received.happened(0.0, True, 'tester')
        self.wb.pseudoshare_received.happened(0.0, False, 'tester')
        share = MockShare(0)
        self.wb.tracker.verified.added.happened(share)

        self.assertEqual(1,self.pseudotracker.count_accepted.count) 
        self.assertEqual(1,self.pseudotracker.count_in_current.count)
        self.assertEqual(1,self.pseudotracker.count_in_my_share.count)
        self.assertEqual(1,self.pseudotracker.count_in_block.count)

        self.wb.new_work_event.happened()

        self.wb.pseudoshare_received.happened(0.0, True, 'tester')
        self.wb.pseudoshare_received.happened(0.0, False, 'tester')
        share = MockShare(1)
        self.wb.my_share_hashes.add(share.hash)
        self.wb.tracker.verified.added.happened(share)

        self.assertEqual(2,self.pseudotracker.count_accepted.count) 
        self.assertEqual(1,self.pseudotracker.count_in_current.count)
        self.assertEqual(2,self.pseudotracker.count_in_my_share.count)
        self.assertEqual(2,self.pseudotracker.count_in_block.count)

        self.wb.new_work_event.happened()

        self.wb.pseudoshare_received.happened(0.0, True, 'tester')
        self.wb.pseudoshare_received.happened(0.0, False, 'tester')
        share = MockShare( 2,pow_hash = 0 )
        self.wb.tracker.verified.added.happened(share)

        self.assertEqual(3,self.pseudotracker.count_accepted.count) 
        self.assertEqual(1,self.pseudotracker.count_in_current.count)
        self.assertEqual(1,self.pseudotracker.count_in_my_share.count)
        self.assertEqual(3,self.pseudotracker.count_in_block.count)

        self.wb.new_work_event.happened()

        self.wb.pseudoshare_received.happened(0.0, True, 'tester')
        self.wb.pseudoshare_received.happened(0.0, False, 'tester')
        share = MockShare(3)
        self.wb.tracker.verified.added.happened(share)

        self.assertEqual(4,self.pseudotracker.count_accepted.count) 
        self.assertEqual(1,self.pseudotracker.count_in_current.count)
        self.assertEqual(2,self.pseudotracker.count_in_my_share.count)
        self.assertEqual(1,self.pseudotracker.count_in_block.count)
        #self.assertEqual(['1341602883.753726 share share:00000000 shared_dflty:1.00000000 block_dflty:256.00000000 pseudo:\n'], self.log.buffer)



if __name__=='__main__':
    unittest.main()

