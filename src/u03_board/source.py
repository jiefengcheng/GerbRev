"""Normalize route evidence to the shared artifact format."""
from src.stage_abi.contracts import finite_json


def route_evidence(value):
    """Translate the native helper's tuple pairs at the U03 evidence boundary.

    This changes representation only. The shared artifact validator remains
    strict; arbitrary Python objects, sets and nonfinite values still reject.
    """
    if type(value) in (list,tuple):value=[route_evidence(v) for v in value]
    elif type(value) is dict:value={k:route_evidence(v) for k,v in value.items()}
    finite_json(value)
    return value
