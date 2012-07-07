import itertools
import time
from p2pool.util import logging
from p2pool.bitcoin import data as bitcoin_data
from p2pool import data as p2pool_data
import sys


clock = time.time

class Counter:
    def __init__(self):
        self.active = False
        self.count = 0
        self.start = 0
    def incr(self):
        if not self.active: raise Exception()
        if self.active:
            self.count += 1
    def deactivate(self):
        self.active = False
    def activate(self, t):
        if not self.active:
            self.active = True
            self.count = 0
            self.start = t

class PseudoShareTracker:

    def __init__(self):
        self.count_accepted    = Counter()
        self.count_rejected    = Counter()
        self.count_in_current  = Counter()
        self.count_in_my_share = Counter()
        self.count_in_block    = Counter()

    def track(self, wb, logfile):
        get_current_txouts = lambda: p2pool_data.get_expected_payouts(
                wb.tracker,
                wb.best_share_var.value, 
                wb.bitcoind_work.value['bits'].target, 
                wb.bitcoind_work.value['subsidy'], 
                wb.net)

        @wb.pseudoshare_received.watch
        def _(attempts, doa, user):
            if doa:
                self.count_rejected.incr()
            else:
                self.count_accepted.incr()
                self.count_in_current.incr()
                self.count_in_my_share.incr()
                self.count_in_block.incr()

        @wb.tracker.verified.added.watch
        def _(share):#, timestamp, pseudo_share_count):
            timestamp = clock()

            share_dflty = bitcoin_data.target_to_difficulty(share.share_info['bits'].target)
            block_dflty = bitcoin_data.target_to_difficulty(share.header['bits'].target)

            logfile.write('%.6f share share:%s diff:%.8f diff:%.8f acc:%d rej:%d n:%d b:%d\n' % (
                timestamp, p2pool_data.format_hash(share.hash), share_dflty, block_dflty, self.count_accepted.count, self.count_rejected.count, self.count_in_my_share.count, self.count_in_block.count))
            self.count_in_current.deactivate()

            if share.hash in wb.my_share_hashes:
                #age = timestamp - my_share_data.start
                logfile.write('%.6f mined share:%s diff:%.8f n:%d b:%d\n' % (
                    timestamp, p2pool_data.format_hash(share.hash), block_dflty, self.count_in_my_share.count, self.count_in_block.count))
                self.count_in_my_share.deactivate()

            if share.pow_hash <= share.header['bits'].target:
                #age = timestamp - block_data.start
                logfile.write('%.6f block share:%s diff:%.8f n:%d b:%d pay:%.8f subsidy:%.8f\n' % (
                    timestamp, p2pool_data.format_hash(share.hash), block_dflty, self.count_in_my_share.count, self.count_in_block.count,
                    get_current_txouts().get(bitcoin_data.pubkey_hash_to_script2(wb.my_pubkey_hash), 0)*1e-8, wb.current_work.value['subsidy']*1e-8))
                self.count_in_block.deactivate()

        @wb.new_work_event.watch
        def _():
            timestamp = clock()

            self.count_accepted.activate(timestamp)
            self.count_rejected.activate(timestamp)
            self.count_in_current.activate(timestamp)
            self.count_in_my_share.activate(timestamp)
            self.count_in_block.activate(timestamp)



