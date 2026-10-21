"""Bounded offline repair. PDF inputs + official identities only; no truth input.

Not a provider. Parsed candidates are not PIT qualification. The regression scorer
may certify only tested identities against its separate, frozen source truth.
"""
import hashlib
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

LABELS = {
    'NP': {'归属于上市公司股东的净利润', '归属于母公司股东的净利润',
           '归属于母公司所有者的净利润'},
    'OCF': {'经营活动产生的现金流量净额'},
    'EQ': {'归属于上市公司股东的净资产', '归属于母公司股东的净资产',
           '归属于上市公司股东的所有者权益', '归属于母公司股东的所有者权益',
           '归属于母公司所有者权益合计', '归属于上市公司股东的股东权益',
           '归属于母公司股东的权益'},
}
UNITS = {'元': 1, '万元': 10000, '百万元': 1000000}


def compact(text):
    return re.sub(r'\s+', '', text or '')


def amount(text):
    t = compact(text).translate(str.maketrans('（）。−－', '().--'))
    if not re.fullmatch(r'\(?[-+]?\d+(?:,\d{3})*(?:\.\d+)?\)?', t):
        return None
    if t.startswith('(') != t.endswith(')'):
        return None
    if t.startswith('('):
        t = '-' + t[1:-1]
    try:
        return Decimal(t.replace(',', ''))
    except InvalidOperation:
        return None


def field_id(label):
    t = compact(label)
    t = re.sub(r'^\d+[.．、]', '', t)
    t = re.sub(r'[（(]净亏损以.{0,12}号填列[）)]', '', t)
    t = re.sub(r'[（(](?:人民币)?(?:百万元|万元|元)[）)]', '', t)
    return next((f for f, aliases in LABELS.items() if t in aliases), None)


def unit_from(text):
    t = compact(text)
    if '单位' not in t and not re.search(r'[（(](?:人民币)?(?:百万元|万元|元)[）)]', t):
        return None
    found = re.findall(r'(百万元|万元|元)(?![/／股])', t)
    found = set(found)
    if len(found) != 1:
        return None
    u = found.pop()
    return {'unit': u, 'multiplier': UNITS[u], 'raw': text}


def preceding_unit(lines, top, lower_bound):
    eligible = [l for l in lines if lower_bound <= l['top'] and l['bottom'] <= top
                and unit_from(l['text'])]
    if not eligible:
        return None
    line = max(eligible, key=lambda l: l['bottom'])
    return {**unit_from(line['text']), 'bbox': line.get('bbox'), 'top': line['top']}


def explicit_scope(lines, top):
    titles = [l['text'] for l in lines if l['bottom'] < top and
              re.search(r'(?:母公司|合并)(?:资产负债|利润|现金流量)表', compact(l['text']))]
    if not titles:
        return None
    return 'parent' if '母公司' in titles[-1] else 'consolidated'


def header_period(text, report_period, field):
    t = compact(text)
    if re.search(r'比|增减|变动', t):
        return None
    quarter = re.search(r'第([一二三四])季度', t)
    if quarter and not re.search(r'20\d{2}', t):
        return None
    year = int(report_period[:4])
    if re.search(r'上年[度]?末|年初', t):
        return f'{year-1}-12-31'
    if '上年同期' in t:
        return f'{year-1}' + report_period[4:]
    if re.search(r'本报告期|本期末|本期|报告期末', t):
        return report_period
    ys = re.findall(r'(?<!\d)(20\d{2})(?!\d)', t)
    if len(set(ys)) != 1:
        return None
    y = ys[0]
    if quarter:
        month = '一二三四'.index(quarter[1]) * 3 + 3
        return f'{y}-{month:02d}-{30 if month in (6, 9) else 31:02d}'
    date = re.search(r'20\d{2}年(\d{1,2})月(\d{1,2})日', t)
    if date:
        return f'{y}-{int(date[1]):02d}-{int(date[2]):02d}'
    if '年末' in t or field == 'EQ' and report_period.endswith('12-31'):
        return y + '-12-31'
    return y + report_period[4:]


def unique_value(values):
    if not values:
        return {'status': 'UNKNOWN', 'reason': 'NO_PROVEN_FIELD_UNIT_COLUMN'}
    selected = min(values, key=lambda v: Decimal(v.get('quantum_CNY', '0')))
    if len({Decimal(v['value_CNY']) for v in values}) != 1:
        # Keep the directly disclosed, finest value. Never calculate a substitute.
        # Only same-PDF locations with an explicit source precision may corroborate.
        compatible = all(v.get('source_sha256') == selected.get('source_sha256') and
                         'quantum_CNY' in v and abs(Decimal(v['value_CNY']) -
                         Decimal(selected['value_CNY'])) <= Decimal(v['quantum_CNY']) / 2
                         for v in values)
        if not compatible:
            return {'status': 'UNKNOWN', 'reason': 'SOURCE_OR_LOCATION_CONFLICT', 'candidates': values}
    return {**selected, 'status': 'PARSED_LOCAL_EVIDENCE_NOT_PIT',
            'corroborating_locations': len(values)}


def lines_of(page):
    words = page.extract_words(x_tolerance=2, y_tolerance=3)
    groups = []
    for w in sorted(words, key=lambda w: (w['top'], w['x0'])):
        line = next((g for g in reversed(groups[-3:]) if abs(g['top'] - w['top']) < 3), None)
        if line is None:
            line = {'top': w['top'], 'bottom': w['bottom'], 'words': []}
            groups.append(line)
        line['words'].append(w)
        line['bottom'] = max(line['bottom'], w['bottom'])
    for line in groups:
        line['words'].sort(key=lambda w: w['x0'])
        line['text'] = ' '.join(w['text'] for w in line['words'])
        line['bbox'] = [min(w['x0'] for w in line['words']), line['top'],
                        max(w['x1'] for w in line['words']), line['bottom']]
    return groups


def grid_rows(table):
    texts = table.extract(x_tolerance=2, y_tolerance=3)
    result = []
    for row, values in zip(table.rows, texts):
        cells = [{'text': t or '', 'bbox': list(b)}
                 for b, t in zip(row.cells, values) if b is not None]
        result.append({'cells': cells, 'bbox': list(row.bbox)})
    return result


def numeric_cells(row):
    return [c for c in row['cells'] if amount(c['text']) is not None]


def column_identity(headers, box, source, field):
    x = (box[0] + box[2]) / 2
    matching = [c for c in headers if c['bbox'][0] - 1 <= x <= c['bbox'][2] + 1]
    period = None
    period_cell = None
    adjustment = None
    for c in matching:
        t = compact(c['text'])
        hp = header_period(t, source['period'], field)
        if hp:
            period, period_cell = hp, c
        if re.fullmatch(r'调整[前后](?:[（(]\d+[）)])?', t):
            adjustment = 'unadjusted' if '前' in t else 'adjusted'
    if period is None:
        return None
    column = 'current' if period == source['period'] else adjustment or 'comparative'
    return {'period': period, 'column': column, 'period_header': period_cell,
            'adjustment': adjustment}


def continuity(previous, current, page_no, page, lines):
    """No page concatenation. Require adjacency, edge alignment and no new section."""
    if not previous or previous['page'] != page_no - 1:
        return None
    a, b = previous['bbox'], current['bbox']
    if a[3] < previous['height'] * .73 or b[1] > page.height * .2:
        return None
    if abs(a[0] - b[0]) > 3 or abs(a[2] - b[2]) > 3:
        return None
    between = ''.join(l['text'] for l in lines if l['bottom'] < b[1])
    if re.search(r'[（(][一二三四五六七八九十][）)]|非经常性|分季度|重要事项', compact(between)):
        return None
    prior_edges = previous['edges']
    current_edges = current['edges']
    if len(prior_edges) != len(current_edges) or any(abs(x-y) > 3 for x, y in zip(prior_edges, current_edges)):
        return None
    return {'previous_page': previous['page'], 'current_page': page_no,
            'matching_column_edges': current_edges,
            'reason': 'ADJACENT_EDGE_ALIGNED_NO_NEW_SECTION',
            'previous_bbox': a, 'current_bbox': b}


def record(source, field, label, cell, unit, identity, page_no, row_box, table_box,
           proof, scope='consolidated', mode='summary'):
    val = amount(cell['text'])
    return {'id': source['id'], 'code': source['code'], 'field': field,
            **identity, 'scope': scope, 'mode': mode, 'label': label,
            'raw_text': cell['text'], 'source_amount': str(val), 'unit': unit['unit'],
            'multiplier': unit['multiplier'], 'unit_evidence': unit,
            'value_CNY': str(val * unit['multiplier']), 'physical_page': page_no,
            'quantum_CNY': str(Decimal(10) ** val.as_tuple().exponent * unit['multiplier']),
            'cell_bbox': cell['bbox'], 'row_bbox': row_box, 'table_bbox': table_box,
            'continuity': proof, 'announcement_date': source['date'],
            'source_sha256': source['sha256'], 'source_path': source['path'],
            'duration': 'INSTANT_END' if field == 'EQ' else
                        'FY_CUMULATIVE' if identity['period'].endswith('12-31') else
                        'Q1_YTD_EQUALS_SINGLE_QUARTER' if identity['period'].endswith('03-31') else
                        'YTD_NOT_SINGLE_QUARTER',
            'pit_qualified': False, 'status': 'PARSED_LOCAL_EVIDENCE_NOT_PIT'}


def parse_grid(page, page_no, table, source, lines, previous, lower_bound):
    rows = grid_rows(table)
    edges = sorted({round(c['bbox'][0], 1) for r in rows for c in r['cells']} |
                   {round(c['bbox'][2], 1) for r in rows for c in r['cells']})
    state = {'page': page_no, 'height': page.height, 'bbox': list(table.bbox),
             'edges': edges, 'headers': [], 'unit': None}
    proof = continuity(previous, state, page_no, page, lines)
    headers = list(previous['headers']) if proof else []
    unit = preceding_unit(lines, table.bbox[1], lower_bound)
    if unit:
        unit = {**unit, 'physical_page': page_no, 'origin': 'PRECEDING_THIS_TABLE'}
    if unit is None and proof:
        unit = previous['unit']
        if unit:
            unit = {**unit, 'inherited_with_continuity': proof}
    found = []
    issues = []
    scope = explicit_scope(lines, table.bbox[1]) or 'consolidated'
    for i, row in enumerate(rows):
        nums = numeric_cells(row)
        if not nums:
            headers.extend(row['cells'])
            continue
        first_x = min(c['bbox'][0] for c in nums)
        label = ''.join(c['text'] for c in row['cells'] if c['bbox'][2] <= first_x + 1)
        # Some PDFs split a label across ruled rows but keep the amount in the first.
        j = i + 1
        while j < len(rows) and not numeric_cells(rows[j]):
            left = ''.join(c['text'] for c in rows[j]['cells'] if c['bbox'][2] <= first_x + 1)
            if not left or any(header_period(c['text'], source['period'], 'EQ') for c in rows[j]['cells']):
                break
            label += left
            j += 1
        field = field_id(label)
        if field is None:
            # This is a header only when no data label is present (e.g. year numerals).
            if not compact(label):
                headers.extend(row['cells'])
            continue
        own_unit = unit_from(label)
        if own_unit:
            own_unit = {**own_unit, 'physical_page': page_no, 'bbox': row['bbox'], 'origin': 'THIS_FIELD_LABEL'}
        chosen_unit = own_unit or unit
        if own_unit and unit and own_unit['multiplier'] != unit['multiplier']:
            chosen_unit = None
        for cell in nums:
            identity = column_identity(headers, cell['bbox'], source, field)
            if chosen_unit is None or identity is None:
                issues.append({'field': field, 'page': page_no, 'label': label,
                               'reason': 'UNIT_UNKNOWN_OR_CONFLICT' if chosen_unit is None else 'COLUMN_UNKNOWN',
                               'raw_text': cell['text']})
                continue
            found.append(record(source, field, label, cell, chosen_unit, identity,
                                page_no, row['bbox'], list(table.bbox), proof, scope=scope))
    state.update(headers=headers, unit=unit)
    return found, issues, state


def word_money_row(line):
    nums = [w for w in line['words'] if amount(w['text']) is not None and ',' in w['text']]
    if len(nums) < 2:
        return None
    left = min(w['x0'] for w in nums)
    label = ''.join(w['text'] for w in line['words'] if w['x1'] < left)
    return label, nums


def parse_unruled_summary(page, n, source, lines, previous):
    """A narrow position fallback for an unruled consolidated annual summary."""
    text = compact(''.join(l['text'] for l in lines))
    rows = [(l, word_money_row(l)) for l in lines]
    rows = [(l, r) for l, r in rows if r and len(r[1]) == 4]
    start = '全年经营成果（人民币百万元）' in text and '合并数据' in text
    proof = None
    if start:
        year_words = [w for l in lines for w in l['words'] if re.fullmatch('20\\d{2}', w['text'])
                      and w['top'] < rows[0][0]['top']] if rows else []
        if len(year_words) != 3:
            return [], None
        anchors = [w['x1'] for w in rows[0][1][1]]
        adjustments = [w for l in lines for w in l['words'] if re.match('调整[前后]', w['text'])]
        headers = []
        for x in anchors:
            y = min(year_words, key=lambda w: abs((w['x0']+w['x1'])/2 - (x-18)))
            adj = next((w for w in adjustments if abs(w['x1']-x) < 4), None)
            headers.append({'period': y['text']+'-12-31',
                            'column': 'current' if y['text'] == source['period'][:4] else
                                      'unadjusted' if adj and '前' in adj['text'] else
                                      'adjusted' if adj else 'comparative',
                            'period_header': y, 'adjustment': adj['text'] if adj else None})
        unit = None
    elif previous and previous['page'] == n-1 and rows:
        anchors = [w['x1'] for w in rows[0][1][1]]
        before = compact(''.join(l['text'] for l in lines if l['bottom'] < rows[0][0]['top']))
        if (rows[0][0]['top'] > .2 * page.height or previous['last_bottom'] < .73 * previous['height']
                or any(abs(x-y) > 3 for x, y in zip(anchors, previous['anchors']))
                or re.search('单位|主要|每股计|重要事项|财务报表', before)):
            return [], None
        headers, unit = previous['headers'], previous['unit']
        proof = {'previous_page': n-1, 'current_page': n, 'numeric_column_right_edges': anchors,
                 'reason': 'ADJACENT_UNRULED_ROWS_ALIGNED_NO_NEW_HEADING'}
    else:
        return [], None
    found = []
    last_bottom = 0
    for line in lines:
        u = unit_from(line['text'])
        if u:
            unit = {**u, 'physical_page': n, 'bbox': line['bbox']}
        row = word_money_row(line)
        if not row or len(row[1]) != 4:
            continue
        label, nums = row
        if any(abs(w['x1']-x) > 3 for w, x in zip(nums, anchors)):
            continue
        last_bottom = line['bottom']
        field = field_id(label)
        if not field or unit is None:
            continue
        for w, identity in zip(nums, headers):
            cell = {'text': w['text'], 'bbox': [w['x0'], w['top'], w['x1'], w['bottom']]}
            found.append(record(source, field, label, cell, unit, identity, n,
                                line['bbox'], None, proof))
    return found, {'page': n, 'height': page.height, 'last_bottom': last_bottom,
                   'headers': headers, 'unit': unit, 'anchors': anchors}


def parse_group_cashflow(page, n, source, lines):
    text = compact(''.join(l['text'] for l in lines))
    if '合并及公司现金流量表' not in text:
        return []
    year_line = next((l for l in lines if len(re.findall(r'20\d{2}年', compact(l['text']))) == 4), None)
    groups = next((l for l in lines if '本集团' in compact(l['text']) and '本行' in compact(l['text'])), None)
    unit_line = next((l for l in lines if unit_from(l['text'])), None)
    if not year_line or not groups or not unit_line:
        return []
    years = re.findall(r'20\d{2}', compact(year_line['text']))
    headings = [w for w in groups['words'] if w['text'] in ('本集团', '本行')]
    if len(headings) != 2:
        return []
    found = []
    for line in lines:
        row = word_money_row(line)
        if not row or field_id(row[0]) != 'OCF' or len(row[1]) != 4:
            continue
        label, nums = row
        # The two scope headings must lie over their respective two amount columns.
        centers = [(w['x0']+w['x1'])/2 for w in nums]
        if not (centers[0]-25 <= (headings[0]['x0']+headings[0]['x1'])/2 <= centers[1]+25 and
                centers[2]-25 <= (headings[1]['x0']+headings[1]['x1'])/2 <= centers[3]+25):
            continue
        for j, w in enumerate(nums):
            period = years[j] + source['period'][4:]
            identity = {'period': period, 'column': 'current' if period == source['period'] else 'comparative',
                        'period_header': year_line['text'], 'scope_header': headings[j//2]}
            cell = {'text': w['text'], 'bbox': [w['x0'], w['top'], w['x1'], w['bottom']]}
            found.append(record(source, 'OCF', label, cell,
                {**unit_from(unit_line['text']), 'bbox': unit_line['bbox'], 'physical_page': n},
                identity, n, line['bbox'], None, None,
                scope='consolidated' if headings[j//2]['text'] == '本集团' else 'parent', mode='group_statement'))
    return found


def extract_document(root, source):
    """Only the fixed document + identity is input; no expected amounts/pages."""
    import pdfplumber
    path = Path(root) / source['path']
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != source['sha256']:
        return {'id': source['id'], 'facts': [], 'status': 'UNKNOWN_SOURCE_IDENTITY'}
    if source['kind'] != 'periodic':
        return {'id': source['id'], 'facts': [], 'status': 'NOTICE_NO_AUTOMATIC_MONETARY_REPLACEMENT'}
    facts, issues, tables_seen = [], [], []
    previous = None
    loose_previous = None
    front_text = []
    with pdfplumber.open(path) as doc:
        # First 30 physical pages is a deliberate limit, not a full-report engine.
        for i, page in enumerate(doc.pages[:30]):
            lines = lines_of(page)
            front_text.append(''.join(l['text'] for l in lines))
            loose, loose_previous = parse_unruled_summary(page, i+1, source, lines, loose_previous)
            facts.extend(loose)
            facts.extend(parse_group_cashflow(page, i+1, source, lines))
            tables = page.find_tables()
            lower = 0
            prior_page = previous
            for ti, table in enumerate(tables):
                found, problems, state = parse_grid(page, i+1, table, source, lines,
                                                   prior_page if ti == 0 else None, lower)
                facts.extend(found)
                issues.extend(problems)
                tables_seen.append({'page': i+1, 'bbox': list(table.bbox), 'facts': len(found),
                                    'continuity': next((f['continuity'] for f in found if f['continuity']), None)})
                lower = table.bbox[3]
                previous = state
            if not tables:
                previous = None
            page.close()
    issuer_verified = source['code'] in compact(''.join(front_text))
    if not issuer_verified:
        issues.append({'reason': 'ISSUER_CODE_NOT_OBSERVED_IN_BOUNDED_PDF_TEXT'})
        facts = []
    return {'id': source['id'], 'code': source['code'], 'status': 'BOUNDED_PARSED',
            'issuer_code_observed': issuer_verified, 'facts': facts, 'issues': issues,
            'tables': tables_seen, 'source_sha256': source['sha256']}
