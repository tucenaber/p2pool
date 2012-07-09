'''
forest data structure
'''

import itertools
import weakref

from p2pool.util import skiplist, variable


class TrackerSkipList(skiplist.SkipList):
    def __init__(self, tracker):
        skiplist.SkipList.__init__(self)
        self.tracker = tracker
        
        self_ref = weakref.ref(self, lambda _: tracker.removed.unwatch(watch_id))
        watch_id = self.tracker.removed.watch(lambda item: self_ref().forget_item(item.hash))
    
    def previous(self, element):
        return self.tracker._delta_type.from_element(self.tracker.items[element]).tail


class DistanceSkipList(TrackerSkipList):
    def get_delta(self, element):
        return element, 1, self.previous(element)
    
    def combine_deltas(self, (from_hash1, dist1, to_hash1), (from_hash2, dist2, to_hash2)):
        if to_hash1 != from_hash2:
            raise AssertionError()
        return from_hash1, dist1 + dist2, to_hash2
    
    def initial_solution(self, start, (n,)):
        return 0, start
    
    def apply_delta(self, (dist1, to_hash1), (from_hash2, dist2, to_hash2), (n,)):
        if to_hash1 != from_hash2:
            raise AssertionError()
        return dist1 + dist2, to_hash2
    
    def judge(self, (dist, hash), (n,)):
        if dist > n:
            return 1
        elif dist == n:
            return 0
        else:
            return -1
    
    def finalize(self, (dist, hash), (n,)):
        assert dist == n
        return hash

def get_attributedelta_type(attrs): # attrs: {name: func}
    class ProtoAttributeDelta(object):
        __slots__ = ['head', 'tail'] + attrs.keys()
        
        @classmethod
        def get_none(cls, element_id):
            return cls(element_id, element_id, **dict((k, 0) for k in attrs))
        
        @classmethod
        def from_element(cls, item):
            return cls(item.hash, item.previous_hash, **dict((k, v(item)) for k, v in attrs.iteritems()))
        
        def __init__(self, head, tail, **kwargs):
            self.head, self.tail = head, tail
            for k, v in kwargs.iteritems():
                setattr(self, k, v)
        
        def __add__(self, other):
            assert self.tail == other.head
            return self.__class__(self.head, other.tail, **dict((k, getattr(self, k) + getattr(other, k)) for k in attrs))
        
        def __sub__(self, other):
            if self.head == other.head:
                return self.__class__(other.tail, self.tail, **dict((k, getattr(self, k) - getattr(other, k)) for k in attrs))
            elif self.tail == other.tail:
                return self.__class__(self.head, other.head, **dict((k, getattr(self, k) - getattr(other, k)) for k in attrs))
            else:
                raise AssertionError()
        
        def __repr__(self):
            return '%s(%r, %r%s)' % (self.__class__, self.head, self.tail, ''.join(', %s=%r' % (k, getattr(self, k)) for k in attrs))
    ProtoAttributeDelta.attrs = attrs
    return ProtoAttributeDelta

AttributeDelta = get_attributedelta_type(dict(
    height=lambda item: 1,
))

class Tracker(object):
    def __init__(self, items=[], delta_type=AttributeDelta, subset_of=None):
        self.items = {} # hash -> item
        self.reverse = {} # delta.tail -> set of item_hashes
        
        self.heads = {} # head hash -> tail_hash
        self.tails = {} # tail hash -> set of head hashes
        
        self._deltas = {} # item_hash -> delta, ref
        self._reverse_deltas = {} # ref -> set of item_hashes
        
        self._ref_generator = itertools.count()
        self._delta_refs = {} # ref -> delta
        self._reverse_delta_refs = {} # delta.tail -> ref
        
        self.added = variable.Event()
        self.removed = variable.Event()
        
        if subset_of is None:
            self.get_nth_parent_hash = DistanceSkipList(self)
        else:
            self.get_nth_parent_hash = subset_of.get_nth_parent_hash
        
        self._delta_type = delta_type
        self._subset_of = subset_of
        
        for item in items:
            self.add(item)
    
    def add(self, item):
        assert not isinstance(item, (int, long, type(None)))
        delta = self._delta_type.from_element(item)
        if self._subset_of is not None:
            assert delta.head in self._subset_of.items
        
        if delta.head in self.items:
            raise ValueError('item already present')
        
        if delta.head in self.tails:
            heads = self.tails.pop(delta.head)
        else:
            heads = set([delta.head])
        
        if delta.tail in self.heads:
            tail = self.heads.pop(delta.tail)
        else:
            tail = self.get_last(delta.tail)
        
        self.items[delta.head] = item
        self.reverse.setdefault(delta.tail, set()).add(delta.head)
        
        self.tails.setdefault(tail, set()).update(heads)
        if delta.tail in self.tails[tail]:
            self.tails[tail].remove(delta.tail)
        
        for head in heads:
            self.heads[head] = tail
        
        self.added.happened(item)
    
    def remove(self, item_hash):
        assert isinstance(item_hash, (int, long, type(None)))
        if item_hash not in self.items:
            raise KeyError()
        if self._subset_of is not None:
            assert item_hash in self._subset_of.items
        
        item = self.items[item_hash]
        del item_hash
        
        delta = self._delta_type.from_element(item)
        
        children = self.reverse.get(delta.head, set())
        
        if delta.head in self.heads and delta.tail in self.tails:
            tail = self.heads.pop(delta.head)
            self.tails[tail].remove(delta.head)
            if not self.tails[delta.tail]:
                self.tails.pop(delta.tail)
        elif delta.head in self.heads:
            tail = self.heads.pop(delta.head)
            self.tails[tail].remove(delta.head)
            if self.reverse[delta.tail] != set([delta.head]):
                pass # has sibling
            else:
                self.tails[tail].add(delta.tail)
                self.heads[delta.tail] = tail
        elif delta.tail in self.tails and len(self.reverse[delta.tail]) <= 1:
            # move delta refs referencing children down to this, so they can be moved up in one step
            if delta.tail in self._reverse_delta_refs:
                for x in list(self._reverse_deltas.get(self._reverse_delta_refs.get(delta.head, object()), set())):
                    self.get_last(x)
                assert delta.head not in self._reverse_delta_refs, list(self._reverse_deltas.get(self._reverse_delta_refs.get(delta.head, None), set()))
            
            heads = self.tails.pop(delta.tail)
            for head in heads:
                self.heads[head] = delta.head
            self.tails[delta.head] = set(heads)
            
            # move ref pointing to this up
            if delta.tail in self._reverse_delta_refs:
                assert delta.head not in self._reverse_delta_refs, list(self._reverse_deltas.get(self._reverse_delta_refs.get(delta.head, object()), set()))
                
                ref = self._reverse_delta_refs[delta.tail]
                cur_delta = self._delta_refs[ref]
                assert cur_delta.tail == delta.tail
                self._delta_refs[ref] = cur_delta - self._delta_type.from_element(item)
                assert self._delta_refs[ref].tail == delta.head
                del self._reverse_delta_refs[delta.tail]
                self._reverse_delta_refs[delta.head] = ref
        else:
            raise NotImplementedError()
        
        # delete delta entry and ref if it is empty
        if delta.head in self._deltas:
            delta1, ref = self._deltas.pop(delta.head)
            self._reverse_deltas[ref].remove(delta.head)
            if not self._reverse_deltas[ref]:
                del self._reverse_deltas[ref]
                delta2 = self._delta_refs.pop(ref)
                del self._reverse_delta_refs[delta2.tail]
        
        self.items.pop(delta.head)
        self.reverse[delta.tail].remove(delta.head)
        if not self.reverse[delta.tail]:
            self.reverse.pop(delta.tail)
        
        self.removed.happened(item)
    
    def get_height(self, item_hash):
        return self.get_delta_to_last(item_hash).height
    
    def get_work(self, item_hash):
        return self.get_delta_to_last(item_hash).work
    
    def get_last(self, item_hash):
        return self.get_delta_to_last(item_hash).tail
    
    def get_height_and_last(self, item_hash):
        delta = self.get_delta_to_last(item_hash)
        return delta.height, delta.tail
    
    def _get_delta(self, item_hash):
        if item_hash in self._deltas:
            delta1, ref = self._deltas[item_hash]
            delta2 = self._delta_refs[ref]
            res = delta1 + delta2
        else:
            res = self._delta_type.from_element(self.items[item_hash])
        assert res.head == item_hash
        return res
    
    def _set_delta(self, item_hash, delta):
        other_item_hash = delta.tail
        if other_item_hash not in self._reverse_delta_refs:
            ref = self._ref_generator.next()
            assert ref not in self._delta_refs
            self._delta_refs[ref] = self._delta_type.get_none(other_item_hash)
            self._reverse_delta_refs[other_item_hash] = ref
            del ref
        
        ref = self._reverse_delta_refs[other_item_hash]
        ref_delta = self._delta_refs[ref]
        assert ref_delta.tail == other_item_hash
        
        if item_hash in self._deltas:
            prev_ref = self._deltas[item_hash][1]
            self._reverse_deltas[prev_ref].remove(item_hash)
            if not self._reverse_deltas[prev_ref] and prev_ref != ref:
                self._reverse_deltas.pop(prev_ref)
                x = self._delta_refs.pop(prev_ref)
                self._reverse_delta_refs.pop(x.tail)
        self._deltas[item_hash] = delta - ref_delta, ref
        self._reverse_deltas.setdefault(ref, set()).add(item_hash)
    
    def get_delta_to_last(self, item_hash):
        assert isinstance(item_hash, (int, long, type(None)))
        delta = self._delta_type.get_none(item_hash)
        updates = []
        while delta.tail in self.items:
            updates.append((delta.tail, delta))
            this_delta = self._get_delta(delta.tail)
            delta += this_delta
        for update_hash, delta_then in updates:
            self._set_delta(update_hash, delta - delta_then)
        return delta
    
    def get_delta(self, item, ancestor):
        assert self.is_child_of(ancestor, item)
        return self.get_delta_to_last(item) - self.get_delta_to_last(ancestor)
    
    def get_chain(self, start_hash, length):
        assert length <= self.get_height(start_hash)
        for i in xrange(length):
            yield self.items[start_hash]
            start_hash = self._delta_type.from_element(self.items[start_hash]).tail
    
    def is_child_of(self, item_hash, possible_child_hash):
        height, last = self.get_height_and_last(item_hash)
        child_height, child_last = self.get_height_and_last(possible_child_hash)
        if child_last != last:
            return None # not connected, so can't be determined
        height_up = child_height - height
        return height_up >= 0 and self.get_nth_parent_hash(possible_child_hash, height_up) == item_hash
