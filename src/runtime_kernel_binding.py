"""Exact approved source revisions; immutable treatment contracts stay pinned."""
import json,hashlib
from pathlib import Path
MANIFEST_SHA256='b6088181a24cc8335a1e5b3597b059c8b0059f7c157c10cd4dc170b1451a235a'
def matches(root,name,expected):
    raw=(root/name).read_bytes();actual=hashlib.sha256(raw).hexdigest()
    if actual==expected:return True
    body=(root/'contracts/runtime_preparation/kernel_binding.json').read_bytes()
    if hashlib.sha256(body).hexdigest()!=MANIFEST_SHA256:raise ValueError('PREPARED_KERNEL_BINDING_CHANGED')
    spec=json.loads(body)
    row=spec['kernels'].get(name)
    return row is not None and row['original_sha256']==expected and row['prepared_sha256']==actual
