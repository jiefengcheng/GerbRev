"""Index parity for full attachment checks, including failure outcomes."""
from shapely.geometry import box, MultiPolygon, Polygon
from src.u05_board.attachment_export import PreparedAttachmentCopper, obligation_check


def run(required, before, regions, already=False, prepared=None):
    try:
        return ('PASS', obligation_check(required, before, regions, already=already, prepared=prepared))
    except ValueError as exc:
        return ('FAIL', str(exc))


before=MultiPolygon([box(0,0,1,1),box(2,0,3,1),box(10,10,11,11)])
index=PreparedAttachmentCopper(before)
cases=[
    (box(.95,.2,1.1,.8),[box(.95,.2,1.1,.8)],False),
    (box(.2,.2,.8,.8),[],True),
    (box(4,4,5,5),[],True),
    (box(.2,.2,.8,.8),[box(.2,.2,.8,.8)],False),
    (Polygon(),[],True),
    (box(1,.2,2,.8),[box(1,.2,2,.8)],False),
]
for required,regions,already in cases:
    assert run(required,before,regions,already)==run(required,before,regions,already,index)
try:
    obligation_check(box(0,0,1,1),box(0,0,1,1),[],already=True,prepared=index)
except ValueError as exc:
    assert str(exc)=='ATTACHMENT_PREDECESSOR_INDEX_CHANGED'
else:
    raise AssertionError('stale predecessor index accepted')
print('PASS: attachment result and failure parity; stale predecessor rejected')
