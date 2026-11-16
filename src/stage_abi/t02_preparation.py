"""Job-owned, bounded T02 preparation shared across task leases.

Only immutable geometry/index/neighbor operands are shared. Adapter decisions,
pin rejection history and acceptance proofs remain owned by each task. Leases
serialize access to the existing mutable LRU containers; callers may hand the
session to different threads but not different OS processes. No global service
or unchecked verdict cache is introduced.
"""
from collections import OrderedDict, Counter
from contextlib import contextmanager
from contextvars import ContextVar
import json
from threading import RLock
import os
import weakref
from .preparation import PreparedTree, NativeTree
from .loaded_geometry import geometry_checksum, SNAPSHOT_BYTES

from .preparation import Resources, ACTIVE as GEOMETRY_ACTIVE
from .store import canonical, digest
from src.native_preparation import ParsePreparation, ACTIVE as NATIVE_ACTIVE

ACTIVE = ContextVar('t02_preparation_session', default=None)


class T02Resources(Resources):
    """Reuse exact content even when an LRU eviction changed object identity.

    Trees already retain their operands strongly. Weak aliases allow subsequent
    artifact reads to find those same immutable shapes without retaining another
    geometry copy. Alias bookkeeping reserves 8 MiB from the existing 192 MiB
    geometry allowance; index and memo budgets are unchanged.
    """
    def __init__(self, binding):
        self.alias_limit = 8 * 1024**2
        self.aliases = OrderedDict()
        super().__init__(binding, geometry_bytes=SNAPSHOT_BYTES-self.alias_limit)

    def decode(self, body):
        key = digest(body)
        old = self.aliases.get(key)
        shape = None if old is None else old[0]()
        if shape is not None:
            if geometry_checksum(shape) != old[1]:
                raise ValueError('PREPARATION_DECODED_GEOMETRY_CHANGED')
            self.aliases.move_to_end(key)
            self.stats['geometry_reads'] += 1
            self.stats['geometry_hits'] += 1
            self.stats['index_operand_hits'] += 1
            return shape
        shape = super().decode(body)
        while self.aliases and len(self.aliases)*256 >= self.alias_limit:
            self.aliases.popitem(last=False)
        def expired(ref, k=key):
            row = self.aliases.get(k)
            if row is not None and row[0] is ref:
                self.aliases.pop(k, None)
        self.aliases[key] = (weakref.ref(shape, expired), geometry_checksum(shape))
        return shape

    def index(self, geometries, kwargs):
        # Source order stays part of the key. Equal sets in a different order
        # cannot reuse positional neighbor results.
        versions = tuple(geometry_checksum(g) for g in geometries)
        key = (versions, tuple(sorted(kwargs.items())))
        old = self.trees.get(key)
        if old is not None:
            self.trees.move_to_end(key)
            self.used_trees[id(old)] = old
            self.stats['index_hits'] += 1
            return old
        weight = len(geometries)*1024+512
        if weight > self.index_limit:
            self.stats['index_checked_legacy'] += 1
            return NativeTree(geometries, **kwargs)
        while self.trees and (self.index_weight+weight > self.index_limit or len(self.trees) >= 8):
            _, entry = self.trees.popitem(last=False)
            self.index_weight -= len(entry.expected)*1024+512
        tree = PreparedTree(geometries, kwargs)
        self.trees[key] = tree
        self.index_weight += weight
        self.used_trees[id(tree)] = tree
        self.stats['index_builds'] += 1
        return tree

    def diagnostics(self):
        return dict(super().diagnostics(), weak_alias_entries=len(self.aliases),
                    weak_alias_estimated_bytes=len(self.aliases)*256,
                    weak_alias_reserved_bytes=self.alias_limit,
                    total_geometry_allowance=SNAPSHOT_BYTES)

    def close(self):
        self.aliases.clear()
        super().close()


class T02Preparation:
    def __init__(self, scene, policy):
        if policy.get('stage') != 't02':
            raise ValueError('T02_PREPARATION_STAGE_REQUIRED')
        self.binding = self.key(scene, policy)
        self.resources = T02Resources(self.binding)
        self.native = ParsePreparation(self.binding)
        self.records = OrderedDict()
        self.record_bytes = 0
        self.record_limit = 4 * 1024**2
        self.stats = Counter()
        self.lock = RLock()
        self.pid = os.getpid()
        self.closed = False

    @staticmethod
    def key(scene, policy):
        # Full accepted predecessor and captured policy, not just source ID.
        return digest(canonical(['t02-preparation/1', scene, policy]))

    @contextmanager
    def task(self, scene, policy):
        with self.lock:
            if self.closed or os.getpid() != self.pid:
                raise ValueError('T02_PREPARATION_CLOSED_OR_FOREIGN_PROCESS')
            if self.key(scene, policy) != self.binding:
                raise ValueError('T02_PREPARATION_PREDECESSOR_OR_POLICY_CHANGED')
            if ACTIVE.get() is not None:
                raise ValueError('T02_PREPARATION_NESTED_TASK')
            # Shadow unrelated operation-level caches with this explicitly
            # bound session, then restore their ContextVars on every exit.
            tokens = (ACTIVE.set(self), GEOMETRY_ACTIVE.set(self.resources),
                      NATIVE_ACTIVE.set(self.native))
            try:
                self.validate()
                self.stats['tasks'] += 1
                yield self
                if self.key(scene, policy) != self.binding:
                    raise ValueError('T02_PREPARATION_INPUT_MUTATED')
                self.validate()
            except BaseException:
                # A failed task cannot leave suspect cache state reusable.
                self.close()
                raise
            finally:
                NATIVE_ACTIVE.reset(tokens[2])
                GEOMETRY_ACTIVE.reset(tokens[1])
                ACTIVE.reset(tokens[0])

    def record(self, key, build):
        """Return a fresh JSON value; a caller cannot mutate the stored proof."""
        if ACTIVE.get() is not self:
            raise ValueError('T02_PREPARATION_LEASE_REQUIRED')
        entry = self.records.get(key)
        if entry is None:
            raw = canonical(build())
            entry = (raw, digest(raw))
            self.stats['neighbor_builds'] += 1
            size = len(raw) + len(key) + 256
            if size <= self.record_limit:
                while self.records and (self.record_bytes + size > self.record_limit
                                        or len(self.records) >= 256):
                    old_key, old = self.records.popitem(last=False)
                    self.record_bytes -= len(old[0]) + len(old_key) + 256
                self.records[key] = entry
                self.record_bytes += size
        else:
            if digest(entry[0]) != entry[1]:
                raise ValueError('T02_PREPARATION_NEIGHBOR_CORRUPTED')
            self.records.move_to_end(key)
            self.stats['neighbor_hits'] += 1
        return json.loads(entry[0])

    def validate(self):
        self.resources.validate()
        self.native.validate()
        for raw, sha in self.records.values():
            if digest(raw) != sha:
                raise ValueError('T02_PREPARATION_NEIGHBOR_CORRUPTED')

    def diagnostics(self):
        return dict(self.stats, binding=self.binding, records=len(self.records),
                    record_bytes=self.record_bytes, record_limit=self.record_limit,
                    resources=self.resources.diagnostics(), native=self.native.diagnostics())

    def close(self):
        with self.lock:
            self.resources.close()
            self.native.close()
            self.records.clear()
            self.record_bytes = 0
            self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def neighbor_records(scene, original, current, source, policy, build):
    owner = ACTIVE.get()
    if owner is None:
        return build()
    # Existing callers re-read all content-addressed input bytes. Include live
    # supplied geometry too, so a changed overlay never hits a stale record.
    token = owner.resources.memo.token
    key = digest(canonical([scene, policy,
        [[sid, token(g)] for sid, g in original.items()],
        [[sid, token(g)] for sid, g in current.items()],
        None if source is None else [[sid, token(g)] for sid, g in source]]))
    return owner.record(key, build)


def predecessor_union(geometries, build):
    owner = ACTIVE.get()
    if owner is None:
        return build()
    # Preserve operand order and exact GEOS construction. No pruning,
    # regrouping or approximate union replaces the original expression.
    return owner.resources.memo.construct('t02-predecessor-union', geometries, (), build)
