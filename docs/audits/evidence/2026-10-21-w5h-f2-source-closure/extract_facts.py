"""Finite extension: explicit dated grids and explicitly defined narrative periods.

No truth input, no source-specific amount patches. OCR remains separate until
its unit, subject and column identity have independent correctness evidence.
"""
import hashlib
import re
import sys
import time
from decimal import Decimal
from fetch_named import OUT, ROOT, F2, read, save
sys.path.insert(0,str(F2))
import parser_f2 as base

ALIASES = {k:set(v) for k,v in base.LABELS.items()}
ALIASES['NP'].update(['归属于母公司所有者净利润','归属于上市公司股东净利润','归属于母公司的净利润'])
ALIASES['EQ'].update(['归属于母公司所有者权益合计','归属于母公司股东权益合计'])
ALIASES['OCF'].update(['经营活动现金流量净额','经营活动现金流净额'])
UNITS = {'元':1,'万元':10000,'百万元':1000000,'亿元':100000000}


def field_id(label):
    t = base.compact(label)
    t = re.sub(r'^[(（]?\d+[)）.．、]?','',t)
    t = re.sub(r'[（(](?:人民币)?(?:亿元|百万元|万元|元)[）)]','',t)
    return next((f for f,ls in ALIASES.items() if t in ls),None)


def unit_from(text):
    t = base.compact(text)
    if not ('单位' in t or re.search(r'[（(](?:人民币)?(?:亿元|百万元|万元|元)[）)]',t)):
        return None
    us = set(re.findall(r'亿元|百万元|万元|元(?![/／股])',t))
    if len(us)!=1:
        return None
    u = us.pop()
    return {'unit':u,'multiplier':UNITS[u],'raw_text':text}


def period(text):
    t = base.compact(text)
    if re.search(r'同比|增减|变动|比上|期初|年初',t):
        return None
    m = re.search(r'(20\d{2})年(\d{1,2})月(\d{1,2})日',t) or re.search(r'(20\d{2})[./-](\d{1,2})[./-](\d{1,2})(?!月)',t)
    if m:
        return f'{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}'
    m = re.search(r'(20\d{2})年(?:1[-~～至－])?(\d{1,2})月(?:末)?',t)
    if m:
        month = int(m[2])
        return f'{m[1]}-{month:02d}-{30 if month in (6,9) else 31:02d}'
    m = re.fullmatch(r'(20\d{2})[年度末]*',t)
    return m[1]+'-12-31' if m else None


def pack(d,field,label,raw,p,unit,page,scope,column,proof,box=None,headers=None,method='GRID'):
    val = base.amount(raw)
    if val is None:
        return None
    return {'id':d['id'],'code':d['code'],'field':field,'period':p,'scope':scope,
        'column':column,'label':label,'raw_text':raw,'source_amount':str(val),
        'duration':('INSTANT_END' if field=='EQ' else 'FY_CUMULATIVE' if p.endswith('-12-31') else
                    'Q1_YTD_EQUALS_SINGLE_QUARTER' if p.endswith('-03-31') else
                    'H1_CUMULATIVE' if p.endswith('-06-30') else 'DURATION_UNKNOWN'),
        'value_CNY':str(val*unit['multiplier']),'unit':unit['unit'],'multiplier':unit['multiplier'],
        'unit_evidence':unit,'physical_page':page,'bbox':box,'period_evidence':headers,
        'proof':proof,'method':method,'quantum_CNY':str(Decimal(10)**val.as_tuple().exponent*unit['multiplier']),
        'announcement_date':d['date'],'source_sha256':d['sha256'],'source_path':d['path'],
        'pit_qualified':False,'status':'CANDIDATE_PENDING_INDEPENDENT_QUALIFICATION'}


def narrative(d,text_pages):
    definitions = []
    for p in text_pages[:20]:
        t = base.compact(p['text'])
        m = re.search(r'报告期[、/最近三年一期]*指((?:20\d{2}年度[、和及]*){3}(?:和?20\d{2}年1[-－~至]?[36]月)?)',t)
        if m:
            parts = re.findall(r'20\d{2}年(?:1[-－~至]?[36]月|度)',m[1])
            ps = [period(s) for s in parts]
            if all(ps):
                definitions.append((ps,p['physical_page'],m[0]))
    if not definitions or any(v[0]!=definitions[0][0] for v in definitions):
        return []
    ps,def_page,def_text = definitions[0]
    found = []
    patterns = {'NP':r'归属于母公司所有者(?:的)?净利润分别为',
                'OCF':r'经营活动(?:产生的)?现金流(?:量)?净额分别为'}
    for p in text_pages:
        text = base.compact(p['text'])
        for field,pattern in patterns.items():
            for m in re.finditer(pattern+r'((?:[-\d,.]+万元[、和]?){3,4})',text):
                amounts = re.findall(r'(-?[\d,]+\.\d+)万元',m[1])
                if len(amounts)!=len(ps):
                    continue
                for per,raw in zip(ps,amounts):
                    found.append(pack(d,field,m[0].split('分别为')[0],raw,per,
                        {'unit':'万元','multiplier':10000,'raw_text':m[0],'physical_page':p['physical_page']},
                        p['physical_page'],'consolidated','as_disclosed',
                        {'period_definition_page':def_page,'period_definition':def_text},
                        headers=def_text,method='DEFINED_NARRATIVE'))
    return found



def complete_open_edges(page, rows, table):
    """pdfplumber can detect inner rules while omitting both open outer edges.

    Extend only within the same ruled row's physical y range. An explicit
    dated outer header is required before its numeric column can be used.
    """
    for row in rows:
        top,bottom = row['bbox'][1],row['bbox'][3]
        if top<0 or bottom>page.height:
            continue
        for left,right in ((0,table.bbox[0]),(table.bbox[2],page.width)):
            if right-left<3:
                continue
            text = page.crop((left,top,right,bottom)).extract_text() or ''
            if text.strip():
                row['cells'].append({'text':text,'bbox':[left,top,right,bottom]})
        row['cells'].sort(key=lambda c:c['bbox'][0])
    return rows



def dated_narrative(d,text_pages):
    """One-page explicitly enumerated annual sequence; never join a next page."""
    found=[]
    pattern=r'((?:20\d{2}年度[、及和]*){3})，?公司经营活动产生的现金流量净额分别为((?:-?[\d,.]+万元[、和及]*){3})(?![-、和及\d])'
    for page in text_pages:
        text=base.compact(page['text'])
        for m in re.finditer(pattern,text):
            ps=[period(t) for t in re.findall(r'20\d{2}年度',m[1])]
            amounts=re.findall(r'(-?[\d,]+\.\d+)万元',m[2])
            if len(ps)!=len(amounts) or len(ps)!=3: continue
            for p,raw in zip(ps,amounts):
                found.append(pack(d,'OCF','经营活动产生的现金流量净额',raw,p,
                    {'unit':'万元','multiplier':10000,'raw_text':m[0],'physical_page':page['physical_page']},
                    page['physical_page'],'consolidated','as_disclosed',
                    {'reason':'EXPLICIT_SAME_SENTENCE_ANNUAL_SEQUENCE'},headers=m[1],method='DATED_NARRATIVE'))
    return found



def annual_report_quote(d,text_pages):
    """Explicit audited annual-report quotations, retaining their coarse units."""
    identity=None
    for p in text_pages[:3]:
        text=base.compact(p['text'])
        m=re.search(r'对.{2,120}?(20\d{2})年财务报表',text)
        if m and '合并及公司' in text and '审字' in text:
            identity={'period':m[1]+'-12-31','physical_page':p['physical_page'],'audit_context':text[:700]}
            break
    if not identity: return []
    patterns={
      'NP':r'归属于母公司股东的净利润[（(]以下简称[“\"]净利润[”\"][）)](-?[\d,.]+)亿元',
      'OCF':r'报告期内，你公司经营活动产生的现金流量净额(-?[\d,.]+)亿元'}
    found=[]
    for p in text_pages:
        text=base.compact(p['text'])
        for field,pat in patterns.items():
            for m in re.finditer(pat,text):
                found.append(pack(d,field,m[0],m[1],identity['period'],
                    {'unit':'亿元','multiplier':100000000,'raw_text':m[0],'physical_page':p['physical_page']},
                    p['physical_page'],'consolidated','as_disclosed',identity,
                    headers='EXPLICIT_QUOTE_OF_IDENTIFIED_ANNUAL_REPORT',method='ANNUAL_REPORT_QUOTE'))
    return found


def grids(d,text_pages):
    import pdfplumber
    selected = set()
    for p in text_pages:
        text=base.compact(p['text'])
        partial_signal=any(a[:-2] in text for labels in ALIASES.values() for a in labels if len(a)>8)
        if p['target_signal'] or partial_signal:
            selected.update(range(max(1,p['physical_page']-3),min(len(text_pages),p['physical_page']+1)+1))
    found,issues = [],[]
    prev = None
    scope_state = None
    pending = None
    carry = None
    with pdfplumber.open(ROOT/d['path']) as pdf:
        for n in sorted(selected):
            page = pdf.pages[n-1]
            lines = base.lines_of(page)
            tables = page.find_tables()
            lower = 0
            for table in tables:
                rows = complete_open_edges(page,base.grid_rows(table),table)
                edges = sorted({round(c['bbox'][0],1) for r in rows for c in r['cells']}|
                               {round(c['bbox'][2],1) for r in rows for c in r['cells']})
                state = {'page':n,'height':page.height,'bbox':list(table.bbox),'edges':edges,'unit':None}
                proof = base.continuity(prev,state,n,page,lines) or base.same_page_unit_block(prev,state,n,lines)
                if carry:
                    tails=[c for r in rows[:3] for c in r['cells'] if base.compact(c['text'])=='净额']
                    if proof and carry['page']==n-1 and tails and field_id(carry['label']+'净额')==carry['field']:
                        found.extend({**f,'label':carry['label']+'净额',
                            'label_continuation':{'physical_page':n,'bbox':tails[0]['bbox'],'raw_text':tails[0]['text']},
                            'proof':proof} for f in carry['facts'])
                    carry=None
                unit_lines = [l for l in lines if lower<=l['top'] and l['bottom']<=table.bbox[1] and unit_from(l['text'])]
                unit = {**unit_from(unit_lines[-1]['text']),'bbox':unit_lines[-1]['bbox'],'physical_page':n} if unit_lines else None
                if unit is None and proof:
                    unit = prev.get('unit')
                scope = base.explicit_scope(lines,table.bbox[1])
                if unit is None and pending and pending['page']==n-1 and table.bbox[1]<page.height*.2:
                    unit = pending['unit']
                    scope = pending['scope']
                    proof = {'reason':'EXPLICIT_DANGLING_CAPTION_AND_UNIT_ON_PREVIOUS_PAGE',
                             'caption':pending['caption'],'previous_page':n-1,'current_page':n}
                pending = None
                if scope:
                    scope_state = scope
                elif not proof:
                    scope_state = None
                headers = []
                if proof and prev['page']==n-1:
                    headers += prev.get('headers',[])
                for i,row in enumerate(rows):
                    for c in row['cells']:
                        if period(c['text']) or re.fullmatch(r'调整[前后]',base.compact(c['text'])) or (len(base.compact(c['text']))<20 and re.search(r'增幅|增长|同比|变动|比上年',base.compact(c['text']))):
                            headers.append(c)
                    nums = base.numeric_cells(row)
                    if not nums:
                        continue
                    left = min(c['bbox'][0] for c in nums)
                    label = ''.join(c['text'] for c in row['cells'] if c['bbox'][2]<=left+1)
                    label = re.sub(r'[-—\s]+$','',label)
                    field = field_id(label)
                    partial = next((f for f,ls in ALIASES.items() if any(a==base.compact(label)+'净额' for a in ls)),None) if field is None and i==len(rows)-1 else None
                    field=field or partial
                    if field is None:
                        continue
                    own_unit = unit_from(label)
                    chosen = {**own_unit,'physical_page':n} if own_unit else unit
                    if own_unit and unit and own_unit['multiplier']!=unit['multiplier']:
                        chosen = None
                    row_scope = scope_state or ('consolidated' if field in ('NP','EQ') else 'unknown')
                    for c in nums:
                        x = (c['bbox'][0]+c['bbox'][2])/2
                        hs = [h for h in headers if h['bbox'][0]-1<=x<=h['bbox'][2]+1]
                        if any(re.search(r'增幅|增长|同比|变动|比上年',base.compact(h['text'])) for h in hs):
                            continue
                        ps = [period(h['text']) for h in hs if period(h['text'])]
                        if not ps or not chosen:
                            issues.append({'page':n,'field':field,'raw':c['text'],
                                           'reason':'PERIOD_OR_THIS_TABLE_UNIT_UNKNOWN'})
                            continue
                        per = ps[-1]
                        adj = next(('unadjusted' if '前' in h['text'] else 'adjusted' for h in reversed(hs)
                                    if re.fullmatch(r'调整[前后]',base.compact(h['text']))),None)
                        fact=pack(d,field,label,c['text'],per,chosen,n,row_scope,
                                  adj or 'as_disclosed',proof,box=c['bbox'],headers=hs)
                        if partial:
                            if carry is None:carry={'page':n,'label':base.compact(label),'field':field,'facts':[]}
                            carry['facts'].append(fact)
                        else:
                            found.append(fact)
                state.update(unit=unit,headers=headers)
                prev = state
                lower = table.bbox[3]
            if not tables:
                prev = None
            end = tables[-1].bbox[3] if tables else 0
            captions = [l for l in lines if l['top']>=end and
                        re.search(r'(?:合并|母公司)现金流量表',base.compact(l['text']))]
            if captions:
                caption = captions[-1]
                units = [l for l in lines if l['top']>caption['bottom'] and unit_from(l['text'])]
                if units and not any(l['top']>units[-1]['bottom'] and len(base.compact(l['text']))>12 for l in lines):
                    pending = {'page':n,'caption':caption,'scope':'parent' if '母公司' in caption['text'] else 'consolidated',
                               'unit':{**unit_from(units[-1]['text']),'physical_page':n,'bbox':units[-1]['bbox']}}
            page.close()
    return found,issues


def extract_all():
    sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    target = OUT/'parsed_source_facts.json'
    if target.exists() and read(target).get('code_sha256')==sha:
        return read(target)['facts']
    facts,issues,costs = [],[],[]
    for d in read(OUT/'documents.json'):
        t = time.perf_counter()
        assert hashlib.sha256((ROOT/d['path']).read_bytes()).hexdigest()==d['sha256']
        pages = read(OUT/'text'/f"{d['id']}.json")['pages']
        a,b = grids(d,pages)
        facts += a+narrative(d,pages)+dated_narrative(d,pages)+annual_report_quote(d,pages)
        issues.append({'id':d['id'],'issues':b})
        costs.append({'id':d['id'],'machine_seconds':time.perf_counter()-t,'grid_facts':len(a)})
        print({'id':d['id'],'grid_facts':len(a)},flush=True)
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest()==sha, 'Parser changed during extraction'
    save('parsed_source_facts.json',{'code_sha256':sha,'facts':facts,'issues':issues,'costs':costs,
                                   'expected_amounts_read':False})
    return facts


from pathlib import Path
if __name__=='__main__':
    extract_all()
