"""Advisory same-citation identity differences, never primary-source verdicts.

Year variants can reflect distinct publication dates; journal variants can be
aliases or extraction mistakes. No candidate authorizes a report edit.
"""
import hashlib
from collections import defaultdict


def identity_conflict_candidates(report, mentions):
    groups=defaultdict(lambda:defaultdict(list))
    for mention in mentions:
        a,b=mention['report_start'],mention['report_end']
        if not (0<=a<b<=len(report)) or hashlib.sha256(report[a:b].encode()).hexdigest()!=mention['report_text_sha256']:
            raise ValueError('Identity mention report binding mismatch')
        for field,value in mention['claims'].items():
            start,end=mention['field_positions'][field]
            if not (a<=start<end<=b) or report[start:end]!=value:
                raise ValueError('Identity field coordinate mismatch')
            key=' '.join(value.casefold().split())
            groups[(str(mention['source_id']),field)][key].append(dict(
                mention_id=mention['mention_id'],value=value,start=start,end=end))
    candidates=[]
    for (source_id,field),values in sorted(groups.items()):
        if len(values)<2:continue
        candidates.append(dict(source_id=source_id,field=field,
            status='different_reported_values_need_primary_review',
            values=[dict(normalized_value=key,occurrences=rows) for key,rows in values.items()]))
    return candidates
