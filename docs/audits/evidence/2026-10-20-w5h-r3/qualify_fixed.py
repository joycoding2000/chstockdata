import hashlib
import io
import json
import struct
import zipfile
from pathlib import Path
from parse_samples import OUT, parse_blob

ORIGINAL = {'FN74': '26476970977.57', 'FN96': '4100926148.57', 'FN107': '1842794237.84', 'FN271': '32032959807.76'}
REVISION = {'FN74': '17578618640.06', 'FN96': '2149836281.41', 'FN107': '-4840052606.46', 'FN271': '28413344515.00'}

def main():
    path = OUT / 'http_gpcw20171231.response'
    blob = path.read_bytes()
    catalog = (OUT.parent / '2026-10-20-w5h-r2/tdx_financial_catalog.raw').read_text(encoding='utf-8')
    catalog_row = next(x.strip().split(',') for x in catalog.splitlines() if x.startswith('gpcw20171231.zip'))
    assert len(blob) == int(catalog_row[2])
    assert hashlib.md5(blob).hexdigest() == catalog_row[1]
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        members = [{'name': x.filename, 'bytes': x.file_size, 'crc32': f'{x.CRC:08x}'} for x in z.infolist()]
        assert len(members) == 1 and members[0]['name'] == 'gpcw20171231.dat'
        assert members[0]['bytes'] < 30_000_000
        dat = z.read(members[0]['name'])
    result = {'zip_file': path.name, 'zip_bytes': len(blob), 'zip_sha256': hashlib.sha256(blob).hexdigest(), 'zip_md5': hashlib.md5(blob).hexdigest(), 'prior_official_catalog_match': True, 'catalog_row': catalog_row, 'zip_crc_verified': True, 'members': members, 'dat_sha256': hashlib.sha256(dat).hexdigest(), 'parse': parse_blob(dat)}
    assert result['parse']['report_date'] == 20171231
    fn = result['parse']['fixed_securities']['600518']['fn']
    result['600518_comparison'] = {}
    for field in ORIGINAL:
        original, revision = float(ORIGINAL[field]), float(REVISION[field])
        actual = fn[field]
        result['600518_comparison'][field] = {'actual_float32': actual, 'original_disclosure_yuan': ORIGINAL[field], 'revision_disclosure_yuan': REVISION[field], 'matches_original_rounded_float32': struct.unpack('<f', struct.pack('<f', original))[0] == actual, 'matches_revision_rounded_float32': struct.unpack('<f', struct.pack('<f', revision))[0] == actual, 'difference_from_original_yuan': actual-original, 'difference_from_revision_yuan': actual-revision}
    from mootdx.financial.financial import Financial
    stream = io.BytesIO(dat)
    stream.name = 'gpcw20171231.dat'
    parsed = Financial.__new__(Financial).parse(stream)
    result['installed_mootdx_crosscheck'] = {}
    for code, r in result['parse']['fixed_securities'].items():
        found = next(x for x in parsed if x[0] == code)
        result['installed_mootdx_crosscheck'][code] = all(found[int(field[2:])+1] == value for field, value in r['fn'].items())
    result['pit'] = [
        {'T': '2018-04-24', 'allowed_2017_report': 'NEITHER_ORIGINAL_NOR_REVISION', 'observed_row': 'MIXED_REVISION_FIELDS', 'available_version_asof_proven': False},
        {'T': '2018-04-27', 'allowed_2017_report': 'ORIGINAL_DISCLOSED_2018-04-26', 'observed_row': 'REVISED_REVENUE_PROFIT_EQUITY_WITH_ORIGINAL_OCF_AND_ORIGINAL_ANNOUNCEMENT_DATE', 'available_version_asof_proven': False},
        {'T': '2019-05-06', 'allowed_2017_report': 'REVISION_DISCLOSED_2019-04-30', 'observed_row': 'REVISED_REVENUE_PROFIT_EQUITY_BUT_OCF_DOES_NOT_MATCH_REVISION', 'available_version_asof_proven': False},
    ]
    result['qualification'] = 'HISTORICAL_PERIOD_VALUES_ONLY / MIXED_REVISION_FIELDS / NOT_ASOF_VERIFIED'
    (OUT / 'fixed_2017_qualification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
