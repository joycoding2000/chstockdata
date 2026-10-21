"""Read original local inputs, decode only two fixed securities, preserve originals."""
import hashlib
import io
import json
import math
import struct
import zipfile
from pathlib import Path

OUT = Path(__file__).resolve().parent
FIELDS = [1, 4, 6, 64, 72, 74, 95, 96, 107, 230, 232, 234, 238, 239, 271, 281, 314]

def parse_blob(b):
    header = struct.unpack_from('<hIHIII', b)
    version, report, count, data_start, rec_bytes, tail = header
    assert version == 1 and rec_bytes % 4 == 0 and count > 0
    base = 20 + count * 11
    assert base <= len(b)
    rows = {}
    for i in range(count):
        code, flag, offset = struct.unpack_from('<6scI', b, 20 + i * 11)
        assert base <= offset and offset + rec_bytes <= len(b)
        code = code.rstrip(b'\0').decode('ascii')
        if code in ('600518', '600519'):
            values = struct.unpack_from(f'<{rec_bytes // 4}f', b, offset)
            rows[code] = {'index_position': i, 'market_flag_hex': flag.hex(), 'record_offset': offset, 'fn': {f'FN{k}': values[k-1] for k in FIELDS if k <= len(values)}}
    return {'header': list(header), 'report_date': report, 'securities_count': count, 'fields_per_record': rec_bytes//4, 'all_index_offsets_in_bounds': True, 'fixed_securities': rows}

def main():
    p = Path('D:/Dev/Projects/easy_tdx/examples/09_file_download/downloads/gpcw20260331.zip')
    blob = p.read_bytes()
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        members = [{'name': x.filename, 'bytes': x.file_size, 'compressed_bytes': x.compress_size, 'crc32_hex': f'{x.CRC:08x}'} for x in z.infolist()]
        assert len(members) == 1 and members[0]['name'] == 'gpcw20260331.dat'
        assert members[0]['bytes'] <= 30_000_000
        dat = z.read(members[0]['name'])  # CRC verified by zipfile, no extraction.
    existing_dat = p.with_suffix('') / 'gpcw20260331.dat'
    d = {'origin_path': str(p), 'bytes': len(blob), 'mtime_ns': p.stat().st_mtime_ns, 'sha256': hashlib.sha256(blob).hexdigest(), 'md5': hashlib.md5(blob).hexdigest(), 'magic_hex': blob[:8].hex(), 'zip_crc_verified': True, 'members': members, 'dat_sha256': hashlib.sha256(dat).hexdigest(), 'existing_dat_path': str(existing_dat), 'existing_dat_matches_zip': existing_dat.read_bytes() == dat, 'parse': parse_blob(dat)}
    # Reuse only the installed parser's read-only DAT branch, bypassing config/network initialization.
    from mootdx.financial.financial import Financial
    obj = Financial.__new__(Financial)
    stream = io.BytesIO(dat)
    stream.name = 'gpcw20260331.dat'
    parsed = obj.parse(stream)
    checks = {}
    for code, row in d['parse']['fixed_securities'].items():
        r = next(x for x in parsed if x[0] == code)
        checks[code] = {'report_matches': r[1] == d['parse']['report_date'], 'all_selected_float32_values_match': all(r[k+1] == value for k, value in [(int(fn[2:]), v) for fn, v in row['fn'].items()])}
    d['installed_mootdx_parser_crosscheck'] = checks
    (OUT / 'local_financial_sample.json').write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(d, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
