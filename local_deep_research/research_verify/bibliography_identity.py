"""Exact identifier mappings across report bibliographies and source registries.

Only serialization and identifier equality are established. A registry entry
is not authenticated by this helper, and a title/journal is never a match key.
"""
import hashlib
import re
from urllib.parse import unquote, urlsplit
from .report_syntax import layout


def bibliography_entries(report):
    _,sections=layout(report);entries=[]
    for section in sections:
        text=report[section.heading_end:section.end]
        starts=list(re.finditer(r'(?m)^[ \t\f]*\[([0-9]+)\][ \t]+',text))
        for i,match in enumerate(starts):
            a=section.heading_end+match.start()
            b=section.heading_end+(starts[i+1].start() if i+1<len(starts) else len(text))
            value=report[a:b]
            entries.append(dict(source_id=match[1],start=a,end=b,text=value,
                sha256=hashlib.sha256(value.encode()).hexdigest()))
    for entry in entries:
        entry['source_id_unique']=sum(e['source_id']==entry['source_id'] for e in entries)==1
    return entries


def identifiers(record):
    values={}
    def add(kind,value):
        value=str(value or '').strip()
        if kind=='doi':
            value=re.sub(r'^https?://(?:dx\.)?doi\.org/','',value,flags=re.I).casefold()
            if not re.fullmatch(r'10\.[0-9]{4,9}/\S+',value):return
        elif kind=='pmid':
            if not re.fullmatch(r'[1-9][0-9]*',value):return
        elif kind in {'pmcid','ppr'}:
            value=value.upper()
            if not re.fullmatch(('PMC' if kind=='pmcid' else 'PPR')+r'[1-9][0-9]*',value):return
        values.setdefault(kind,set()).add(value)
    for key in ('doi','pmid','pmcid','ppr'):add(key,record.get(key))
    for url in [record.get('link'),record.get('url')]:
        if not url:continue
        try:parts=urlsplit(str(url))
        except ValueError:continue
        host=(parts.hostname or '').lower();path=unquote(parts.path).strip('/')
        if host in {'doi.org','dx.doi.org'}:add('doi',path)
        elif host=='pubmed.ncbi.nlm.nih.gov':add('pmid',path)
        elif host=='pmc.ncbi.nlm.nih.gov' and path.startswith('articles/'):
            add('pmcid',path[len('articles/'):])
        elif host in {'europepmc.org','www.europepmc.org'}:
            m=re.fullmatch(r'article/(MED|PMC|PPR)/([^/]+)',path,re.I)
            if m:add({'MED':'pmid','PMC':'pmcid','PPR':'ppr'}[m[1].upper()],m[2])
    for key,label in [('doi','DOI'),('pmid','PMID'),('pmcid','PMCID')]:
        for m in re.finditer(r'(?m)^[ \t]*'+label+r':[ \t]*([^\r\n]+)',record.get('text','')):
            add(key,m[1])
    for m in re.finditer(r'(?m)^[ \t]*URL:[ \t]*(https?://[^\s]+)',record.get('text','')):
        for key,items in identifiers({'url':m[1]}).items():
            values.setdefault(key,set()).update(items)
    return {key:sorted(items) for key,items in sorted(values.items())}


def match_identifiers(entry, records):
    left=identifiers(entry);matches=[];conflicts=[]
    if entry.get('source_id_unique') is False:
        return dict(status='nonunique_bibliography_source_id',identifiers=left,matches=[],conflicts=[])
    for key,record in records.items():
        right=identifiers(record)
        shared=set(left)&set(right)
        agreeing=[k for k in shared if set(left[k])&set(right[k])]
        if not agreeing:continue
        disagreement=[k for k in shared if left[k]!=right[k]]
        row=dict(record_key=str(key),matched_fields=sorted(agreeing),identifiers=right)
        if disagreement or any(len(v)!=1 for v in left.values()) or any(len(v)!=1 for v in right.values()):
            conflicts.append(dict(**row,disagreement_fields=sorted(disagreement)))
        else:matches.append(row)
    status=('identifier_conflict' if conflicts else 'one_record_match' if len(matches)==1
            else 'multiple_record_matches' if matches else 'no_identifier_match')
    return dict(status=status,identifiers=left,matches=matches,conflicts=conflicts)
