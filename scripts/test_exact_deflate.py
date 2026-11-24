import zlib
import struct

def compress_exact_deflate(raw, target_len):
    # Try to find (level, K, num_empty_stored) such that len(sync_stream) + 5*num_empty + 5 + K == target_len
    # Note: after Z_SYNC_FLUSH, stream is byte-aligned!
    # Any additional empty non-final stored block is b"\x00\x00\x00\xff\xff" (5 bytes).
    # Final stored block with K literal bytes is b"\x01" + pack("<HH", K, K^0xffff) + raw[len(raw)-K:] (5 + K bytes).
    for level in (9, 8, 7, 6, 5, 4, 3, 2, 1):
        for K in range(0, min(len(raw), 120)):
            c = zlib.compressobj(level, zlib.DEFLATED, -15)
            prefix = c.compress(raw[:len(raw)-K]) + c.flush(zlib.Z_SYNC_FLUSH)
            rem = target_len - len(prefix) - (5 + K)
            if rem >= 0 and rem % 5 == 0:
                num_empty = rem // 5
                stream = prefix + (b"\x00\x00\x00\xff\xff" * num_empty) + b"\x01" + struct.pack("<HH", K, K ^ 0xFFFF) + raw[len(raw)-K:]
                assert len(stream) == target_len
                d = zlib.decompressobj(-15)
                out = d.decompress(stream)
                assert out == raw and d.eof and len(d.unused_data) == 0
                return stream
    # Fallback: Z_FINISH + trailing zeros
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    stream = c.compress(raw) + c.flush(zlib.Z_FINISH)
    assert len(stream) <= target_len, f"Compressed {len(stream)} > target {target_len}"
    return stream + b"\x00" * (target_len - len(stream))

raw = b"Hello Avalon Nano 3S! " * 186 + b"abcd"
s = compress_exact_deflate(raw, 200)
d = zlib.decompressobj(-15)
out = d.decompress(s)
print(f"Exact deflate test: len={len(s)}, match={out==raw}, eof={d.eof}, unused_len={len(d.unused_data)}")
