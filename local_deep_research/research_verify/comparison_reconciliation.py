"""Experimental review handoff; observations never establish scientific truth."""
import json

from .claim_language import bilingual_notes


def review_observations(review, claims):
    """Keep coverage/disagreements but never pass an earlier proposed rewrite."""
    fields=('evidence_source_id','source_id','source_ids','status','reviewer_status',
            'atom_checks','evidence_quote','evidence_sources')
    def without_replacements(value):
        if isinstance(value,dict):return {k:without_replacements(v) for k,v in value.items() if k!='replacement'}
        if isinstance(value,list):return [without_replacements(v) for v in value]
        return value
    byid={}
    for row in [*review.get('issues',[]),*review.get('checked',[])]:
        i=row.get('claim_id')
        if type(i) is not int or i not in claims or i in byid:raise ValueError('Ambiguous prior review scope')
        byid[i]={'claim_id':i,**{k:without_replacements(row[k]) for k in fields if k in row}}
    return [byid.get(i,dict(claim_id=i,status='unchecked')) for i in claims]


def reconciliation_notes(claims, readings, fidelity, english_review, original_review=None):
    observations={'english_reading_check':review_observations(english_review,claims)}
    if original_review is not None:observations['original_language_check']=review_observations(original_review,claims)
    return (bilingual_notes(readings,fidelity)+'\n\n'
        'SEPARATE FALLIBLE REVIEW OBSERVATIONS, WITHOUT SUGGESTED REWRITES:\n'
        'Reviewers may miss different attributes. Their positive/negative statuses are '
        'neither evidence nor a vote. Reassess the ORIGINAL unit against the ORIGINAL '
        'supplied source context, covering the distinct attributes it actually asserts. '
        'Keep both reviewers\' findings and unknowns in view: a matching entity list '
        'cannot resolve a different relationship or identity; an unreviewed attribute '
        'is not supported by silence. Do not assume every discrepancy is a correction. '
        'Preserve correct supported content and translation ambiguity. First identify '
        'which ORIGINAL attributes are supported, contradicted or unknown from source '
        'evidence; then compose any minimal necessary replacement yourself in the '
        'ORIGINAL UNIT\'S LANGUAGE, preserving structure, citations and qualifiers. '
        'Return the existing native JSON schema with original claim_ids. No reviewer '
        'rewrite is supplied for copying. A later independent source-grounded semantic '
        'confirmation must still accept any proposal before application.\n'
        +json.dumps(observations,ensure_ascii=False))
