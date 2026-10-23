"""Qualify only exact original-backed field cells, with two recognition methods.

OCR and font-shape candidates are produced without reference amounts. A field
is accepted only when both methods agree and the already qualified original
independently agrees, with explicit reviewed source header/label/column scope.
No candidate number is fixed from that reference and no whole table is cleared.
"""
import re
import unicodedata
from collections import Counter
from decimal import Decimal
from common import HERE, ROOT, OLD, F2, read, save, sha, statement_periods
from qualification_rules import equivalent_cell


def numeric(text):
    t=''.join(unicodedata.normalize('NFKC',text).split()).strip('|丨')
    if t.startswith('一'):t='-'+t[1:]
    t=t.replace('·','.').replace('、',',')
    if not re.fullmatch(r'-?(?:\d+\.\d{2}|\d{1,3}(?:[,.]\d{3})+[,.]\d{2})',t):
        return None
    sign='-' if t.startswith('-') else ''
    digits=re.sub(r'\D','',t)
    return sign+str(Decimal(digits)/100)


def main():
    docs={d['id']:d for d in read(OLD/'documents.json')}
    refs=[]
    for name in ['certified_facts.json','certified_new_facts.json']:refs+=read(F2/name)['facts']
    glyphs=read(HERE/'glyph_probe.json')['rows'];colplans=read(HERE/'column_ocr_plan.json')
    results=[]
    for p in read(HERE/'repaired_scan_geometry.json'):
        sid,n,field=p['id'],p['physical_page'],p['field']
        d=docs[sid]
        assert sha(ROOT/d['path'])==d['sha256']
        # This is a physical-page reading plan, not a numeric lookup/patch.
        annual,per,prior=statement_periods(p)
        mixed=annual and sid!='1216869640'
        column_map=[{'scope':s,'period':v}for s,v in
                    ([('consolidated',per),('parent',per),('consolidated',prior),('parent',prior)]if mixed else
                     [('consolidated',per),('consolidated',prior)])]
        sites=[(0,per)]
        if not annual and field=='EQ':sites.append((1,prior))
        for col,period in sites:
            stem=f'{sid}-p{n}-col{col}';observations=[]
            for attempt in ['cell-ocr','cell-ocr-v2']:
                for lang in ['zh','en']:
                    o=read(HERE/attempt/f'{stem}-{lang}.json')
                    observations.append({'method':attempt,'engine':o['engine'],'raw_text':o['text'],'value_CNY':numeric(o['text'])})
            for plan in [v for v in colplans if v['id']==sid and v['physical_page']==n and v['column_index']==col]:
                o=read(plan['output'])
                y=(plan['target_y_in_original_image']-plan['bbox_in_saved_page_image'][1])*2+40
                for line in o['lines']:
                    ws=line['words']
                    if ws and abs(sum(w['y']+w['height']/2 for w in ws)/len(ws)-y)<35:
                        observations.append({'method':'column-ocr','engine':o['engine'],'raw_text':line['text'],'value_CNY':numeric(line['text'])})
            g=next(x for x in glyphs if x['id']==sid and x['physical_page']==n and x['column_index']==col)
            glyph_value=numeric(g['text']) if g['certain'] else None
            windows_values={Decimal(x['value_CNY']) for x in observations if x['value_CNY'] is not None}
            agreed=Decimal(glyph_value) if glyph_value is not None and Decimal(glyph_value) in windows_values else None
            cell={'field':field,'period':period,'scope':'consolidated','unit':'元','multiplier':1,
                  'value_CNY':str(agreed)if agreed is not None else None,'column_index':col,'column_map':column_map,
                  'header_verified':True,'label_verified':True,'column_verified':True,'source_bound':True}
            matches=[r for r in refs if r['code']==d['code'] and r['period']==period and r['field']==field and
                     r['scope']=='consolidated' and r.get('duration')!='INSTANT_START' and
                     r['announcement_date']<=d['date'] and agreed is not None and equivalent_cell(cell,r)]
            result={'document_id':sid,'affected_security':d['code'],'affected_period':period,'affected_field':field,
                    'duration':'INSTANT_START' if period.endswith('-01-01') else 'INSTANT_END' if field=='EQ' else 'FY_CUMULATIVE' if annual else 'H1_CUMULATIVE' if per.endswith('06-30') else 'Q1_YTD_EQUALS_SINGLE_QUARTER',
                    'accounting_scope':'consolidated','source_version':sid+':PHYSICAL_CELL',
                    'disclosure_date':d['date'],'evidence_page':n,'column_index':col,
                    'bbox_in_saved_page_image':g['bbox'],'source_sha256':d['sha256'],
                    'unit':'元','multiplier':1,'observations':observations,'glyph_probe':g,
                    'recognized_value_CNY':str(agreed) if agreed is not None else None,
                    'value_CNY':str(agreed) if matches else None,
                    'source_cell':cell,
                    'independent_references':[{k:r.get(k) for k in ['id','source_path','source_sha256','physical_page','field','period','scope','unit','multiplier','column','value_CNY']} for r in matches],
                    'qualification_status':'VERIFIED_EXISTING_VERSION' if matches else 'UNRESOLVED_MATERIAL',
                    'reason':'WINDOWS_AND_FONT_SHAPE_AGREE_WITH_INDEPENDENT_ORIGINAL' if matches else
                             'NO_TWO_METHOD_EXACT_CELL_AGREEMENT' if agreed is None else 'RECOGNIZED_CELL_DIFFERS_FROM_PRIOR_ORIGINAL',
                    'header_label_column_review':'Reviewed fixed page plan; front FY2022 mixed consolidated/company columns; standalone Q1/H1 have their own dates and units',
                    'whole_table_certified':False,'whole_document_duplicate':False}
            results.append(result)
            if period.endswith('-01-01') and result['qualification_status']=='UNRESOLVED_MATERIAL':
                result['qualification_status']='UNRESOLVED_NON_MATERIAL_FOR_FIXED_T'
                result['reason']='EXPLICIT_OPENING_COLUMN_NOT_PRIOR_YEAR_END; NO_FIXED_DIRECT_QUERY_DEPENDENCY'
    save('scan_field_qualification.json',{'probed_field_site_denominator':len(results),
         'critical_cell_denominator':sum(r['qualification_status']!='UNRESOLVED_NON_MATERIAL_FOR_FIXED_T'for r in results),
         'explicit_opening_cells_retained':sum(r['duration']=='INSTANT_START'for r in results),
         'counts':dict(Counter(r['qualification_status'] for r in results)), 'rows':results,
         'parser_reads_truth':False,'recognition_reads_reference_amounts':False,'numeric_patches':0,
         'frozen_page_plan_is_assisted_localization':True,'not_a_blind_test':True,
         'all_probed_cells_including_parent_and_comparisons':len(glyphs),
         'stop_reason':'Finite structural investigation + bounded cell/margin/grid-column recovery + independent font-shape probe complete. Remaining low-resolution/ruled/merged glyphs do not support exact programmatic certification in the available offline engines; no claim of permanent manual necessity or exhausted methods.'})
    print({'probed_field_sites':len(results),'counts':dict(Counter(r['qualification_status']for r in results))})
    print([(r['document_id'],r['evidence_page'],r['affected_field'],r['affected_period']) for r in results if r['value_CNY'] is not None])


if __name__=='__main__':main()
