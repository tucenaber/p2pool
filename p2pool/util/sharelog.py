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
        self.count_duplicates  = Counter()
        self.count_rejected    = Counter()
        self.count_in_current  = Counter()
        self.count_in_my_share = Counter()
        self.count_in_block    = Counter()

    def track(self, wb, logfile):

        @wb.pseudoshare_event.watch
        def _(header_hash, doa, duplicate, user):
            timestamp = clock()
            if duplicate:
                self.count_duplicates.incr()
            if doa:
                self.count_rejected.incr()
            if not doa and not duplicate:
                self.count_accepted.incr()
                self.count_in_current.incr()
                self.count_in_my_share.incr()
                self.count_in_block.incr()
            logfile.write('%.6f pseudo hash:%064x doa:%s dup:%s user:%s\n' % (timestamp, header_hash, 'yes' if doa else 'no', 'yes' if duplicate else 'no', user))

        @wb.tracker.verified.added.watch
        def _(share):#, timestamp, pseudo_share_count):
            data = {}
            data['timestamp'] = clock()

            data = dict(
                 timestamp   = clock(),
                 share_dflty = bitcoin_data.target_to_difficulty(share.share_info['bits'].target),
                 block_dflty = bitcoin_data.target_to_difficulty(share.header['bits'].target),
                 share_hash  = p2pool_data.format_hash(share.hash),
                 prev_hash   = p2pool_data.format_hash(share.previous_hash),
                 pow_hash    = share.pow_hash,
                 accepted    = self.count_accepted.count,
                 duplicates  = self.count_duplicates.count,
                 rejected    = self.count_rejected.count,
                 own_count   = self.count_in_my_share.count,
                 block_count = self.count_in_block.count
            )

            logfile.write('%(timestamp).6f share share:%(share_hash)s prev:%(prev_hash)s hash:%(pow_hash)064x ds:%(share_dflty).8f db:%(block_dflty).8f acc:%(accepted)d dup:%(duplicates)d rej:%(rejected)d own:%(own_count)d block:%(block_count)d\n' % data)
            self.count_in_current.deactivate()

            if share.hash in wb.my_share_hashes:
                logfile.write('%(timestamp).6f mined share:%(share_hash)s prev:%(prev_hash)s hash:%(pow_hash)064x ds:%(share_dflty).8f db:%(block_dflty).8f acc:%(accepted)d dup:%(duplicates)d rej:%(rejected)d own:%(own_count)d block:%(block_count)d\n' % data)
                self.count_in_my_share.deactivate()

            if share.pow_hash <= share.header['bits'].target:
                data.update({
                    'pay':share.check(wb.tracker).get(bitcoin_data.pubkey_hash_to_script2(wb.my_pubkey_hash), 0)*1e-8, 
                    'subsidy':share.share_info['share_data']['subsidy']*1e-8
                })
                logfile.write('%(timestamp).6f block share:%(share_hash)s prev:%(prev_hash)s hash:%(pow_hash)064x db:%(block_dflty).8f acc:%(accepted)d dup:%(duplicates)d rej:%(rejected)d block:%(block_count)d pay:%(pay).8f subsidy:%(subsidy).8f\n' % data)
                self.count_in_block.deactivate()

        @wb.new_work_event.watch
        def _():
            timestamp = clock()

            self.count_accepted.activate(timestamp)
            self.count_rejected.activate(timestamp)
            self.count_in_current.activate(timestamp)
            self.count_in_my_share.activate(timestamp)
            self.count_in_block.activate(timestamp)



