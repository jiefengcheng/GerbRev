"""Reuse ordered owner operands during one immutable export pass."""

from src.component_clearance import joined
from src.stage_abi.loaded_geometry import GeometryMemo


class EncodedOwnerProjection:
    def __init__(self, scope, encoded_current):
        self._operands = {
            owner: tuple(parts)
            for owner, parts in scope.projection_operands(encoded_current).items()
        }
        self._memo = GeometryMemo('encoded-owner-projection')

    def owner_surface(self, owner):
        parts = self._operands[owner]
        # The projection captures its own immutable geometry references. The
        # key is local to this instance and the memo still verifies each hit.
        return self._memo.construct('encoded-owner-surface', [], (owner,),
                                    lambda: joined(parts))
