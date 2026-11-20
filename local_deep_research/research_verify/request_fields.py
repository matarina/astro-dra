"""Report-blind requested-field reading and exact original-position anchors."""
import json

from .evidence_flow import review_units,visible_texts,visible_headers
from .request_additions import request_plan_prompt,_json


def atomic_request_prompt(question):
    return (request_plan_prompt(question)+'\nATOMIC CRITERIA: Separate independently '
        'assessable dimensions (for example publication period, paper count, '
        'ordering, original language, study type, method conjunction and each '
        'requested data field). Keep the SAME per-paper/per-modality scope. '
        'Do not combine them into one success label. Merge equivalent repeated '
        'instructions rather than recounting them; keep a literal supporting '
        'request_quote for every criterion. Do not add criteria not asked for.')


def original_anchors(report):
    anchors=[]
    for unit in review_units(report):
        if unit.kind in {'heading_candidate','table_candidate'}:continue
        start,end=unit.report_start,unit.report_end
        if report[start:end]!=unit.text:raise ValueError('Nonliteral original unit')
        anchors.append(dict(anchor_id=len(anchors),start=start,end=end,text=unit.text,
            preview=unit.text[:100],citation_ids=unit.citations))
    return anchors


def source_field_prompt(question,requirements,material,*,maximum_fields=3):
    if type(maximum_fields)is not int or not 1<=maximum_fields<=8:raise ValueError('Source-field bound')
    return ('Read ONLY the actual supplied sources for information explicitly '
        'requested by this user. No report, proposed edit, feedback or expected '
        'answer is supplied. Preserve original subject/study/analysis/modality/'
        'group/quantity units. Prioritize the actual requested substantive data '
        'fields over restating general metadata. Keep other criteria unresolved '
        'when the record does not establish them. Never infer journal metrics '
        'from prestige, article language from translated titles, or primary-study '
        'status from document availability. Metadata is not complete paper text. '
        'Separate multiple studies in one page; do not mix cohort/sample/cell '
        'counts. Return at most '+('three'if maximum_fields==3 else str(maximum_fields))+' located factual fields per source, each '
        'with one continuous literal own-source quotation and concise scope. '
        'Do not stitch passages. Missing notes are not negative evidence. '
        'Explicitly include every supplied source_id, even when fields is empty. '
        'Return JSON {"sources":[{"source_id":1,"fields":[{"requirement_id":0,'
        '"value":"actual requested data, not an absence disclaimer",'
        '"scope":"same study/analysis/modality/group and unit context",'
        '"quote":"continuous actual source passage"}],'
        '"unresolved_requirements":[0]}]}. These are fallible reading notes, '
        'not independent adjudication or paper-eligibility certification.\n'
        'USER REQUEST:\n'+question+'\nREQUIREMENTS:\n'+json.dumps(requirements,ensure_ascii=False)
        +'\nACTUAL SOURCE REGISTRY IDS:\n'+json.dumps(sorted(material.views))
        +'\nACTUAL SUPPLIED SOURCES:\n'+str(material))


def parse_source_fields(raw,requirements,material,*,maximum_fields=3):
    if type(maximum_fields)is not int or not 1<=maximum_fields<=8:raise ValueError('Source-field bound')
    rows=_json(raw)['sources'];texts=visible_texts(material);headers=visible_headers(material)
    if not isinstance(rows,list):raise ValueError('Invalid source-field rows')
    reqids={r['requirement_id']for r in requirements};byid={};rejected=[]
    for row in rows:
        sid=row.get('source_id')
        if type(sid)is not int or sid not in texts or sid in byid:raise ValueError('Source-field namespace mismatch')
        fields=row.get('fields',[])
        if not isinstance(fields,list)or len(fields)>maximum_fields:raise ValueError('Source-field bound exceeded')
        located=[]
        for field in fields:
            quote=field.get('quote');rid=field.get('requirement_id')
            if (type(rid)is not int or rid not in reqids or not isinstance(quote,str)or not quote.strip()
                or quote not in texts[sid]and quote not in headers.get(sid,'')):
                rejected.append(dict(source_id=sid,field=field,reason='unlocated_or_unscoped_field'));continue
            if not isinstance(field.get('value'),str)or not field['value'].strip():
                rejected.append(dict(source_id=sid,field=field,reason='missing_field_value'));continue
            located.append(field)
        unresolved=row.get('unresolved_requirements',[])
        if not isinstance(unresolved,list)or any(type(i)is not int or i not in reqids for i in unresolved):
            raise ValueError('Invalid unresolved requirement scope')
        unresolved=sorted((reqids-{f['requirement_id']for f in located})|set(unresolved))
        byid[sid]=dict(source_id=sid,fields=located,unresolved_requirements=unresolved,
            observation_status='model_reading_not_semantically_validated')
    result=[byid.get(sid,dict(source_id=sid,fields=[],unresolved_requirements=sorted(reqids),
                            observation_status='not_assessed'))for sid in sorted(texts)]
    return dict(sources=result,rejected_fields=rejected,quality_claim=None)
