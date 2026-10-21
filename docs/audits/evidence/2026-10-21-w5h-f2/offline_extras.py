"""Two bounded position-based checks required by this sample, not a PDF framework."""
import hashlib
import re
from pathlib import Path
from parser_f2 import (amount, compact, field_id, lines_of, preceding_unit,
                       word_money_row, record, grid_rows, column_identity)


def notice_levels(root, source):
    import pdfplumber
    path = Path(root)/source['path']
    if hashlib.sha256(path.read_bytes()).hexdigest() != source['sha256']:
        return []
    found = []
    with pdfplumber.open(path) as doc:
        for n, page in enumerate(doc.pages[:30], 1):
            lines = lines_of(page)
            for i, line in enumerate(lines):
                if compact(line['text']) != '合并资产负债表项目':
                    continue
                heading = lines[i:i+4]
                dates = [re.search(r'(20\d{2})年(\d{1,2})月(\d{1,2})日', compact(l['text'])) for l in heading]
                m = next((m for m in dates if m), None)
                adj = next((l for l in heading if all(t in compact(l['text']) for t in
                                                    ['调整前','调整金额','调整后'])), None)
                unit = preceding_unit(lines, line['top'], max(0,line['top']-60))
                if not m or not adj or not unit:
                    continue
                labels = [w for w in adj['words'] if w['text'] in ('调整前','调整金额','调整后')]
                if [w['text'] for w in labels] != ['调整前','调整金额','调整后']:
                    continue
                period = f'{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}'
                for row in lines[i+1:]:
                    if row['top'] > adj['bottom'] and ('合并利润表' in row['text'] or '①' in row['text']):
                        break
                    money = word_money_row(row)
                    if not money or len(money[1]) != 3 or field_id(money[0]) != 'EQ':
                        continue
                    if any(abs((w['x0']+w['x1'])/2-(h['x0']+h['x1'])/2)>55
                           for w,h in zip(money[1],labels)):
                        continue
                    for j, column in [(0,'unadjusted'),(2,'adjusted')]:
                        w = money[1][j]
                        cell = {'text':w['text'], 'bbox':[w['x0'],w['top'],w['x1'],w['bottom']]}
                        found.append(record(source,'EQ',money[0],cell,
                            {**unit,'physical_page':n,'origin':'THIS_UNRULED_ADJUSTMENT_BLOCK'},
                            {'period':period,'column':column,'period_header':heading[0],
                             'adjustment':labels[j], 'duration':'INSTANT_START' if period.endswith('01-01') else 'INSTANT_END'},
                            n,row['bbox'],[line['bbox'][0],line['top'],row['bbox'][2],row['bottom']],
                            {'reason':'EXPLICIT_CONSOLIDATED_DATE_AND_ALIGNED_BEFORE_DELTA_AFTER_COLUMNS'},
                            mode='notice_adjustment'))
    return found


def eps_columns(root, source):
    import pdfplumber
    path = Path(root)/source['path']
    if hashlib.sha256(path.read_bytes()).hexdigest() != source['sha256']:
        return []
    found = []
    with pdfplumber.open(path) as doc:
        for n,page in enumerate(doc.pages[:30],1):
            for table in page.find_tables():
                headers = []
                for row in grid_rows(table):
                    nums = [c for c in row['cells'] if amount(c['text']) is not None]
                    if not nums:
                        headers += row['cells']
                        continue
                    label = compact(row['cells'][0]['text'])
                    # The per-share unit must be printed on this exact field.
                    if not re.fullmatch(r'基本每股收益[（(]元[/／]股[）)]', label):
                        if not compact(row['cells'][0]['text']):
                            headers += row['cells']
                        continue
                    for cell in nums:
                        identity = column_identity(headers,cell['bbox'],source,'EPS')
                        if identity:
                            found.append({'id':source['id'],'code':source['code'],'field':'EPS',
                                **identity,'value_per_share':str(amount(cell['text'])),
                                'unit':'元/股','raw_text':cell['text'],'physical_page':n,
                                'cell_bbox':cell['bbox'],'row_bbox':row['bbox'],
                                'source_sha256':source['sha256'],'source_path':source['path'],
                                'announcement_date':source['date'],'pit_qualified':False})
    return found
