#!/usr/bin/env python3
"""Build a canonical, non-topic source identity crosswalk for immune evaluation inputs."""
from __future__ import annotations
import hashlib, json, re
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / 'evaluation/frontier-strategy-20261113/immune-evidence/production-original-sourcepack.json'
FROZEN = ROOT / 'evaluation/scholar-controlled-pilot-corrected-20261112/inputs/historical-immune-base.json'
DRAFT = ROOT / 'evaluation/scholar-controlled-pilot-corrected-20261112/inputs/historical-immune-inherited-draft.md'
DENOM = ROOT / 'evaluation/pane2-independent-review-20261113/pane2-correction-denominator-audit-v1.json'
OUT = ROOT / 'evaluation/frontier-strategy-20261113/immune-evidence/source-identity-crosswalk-20261114.json'


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm_doi(value):
    if not value:
        return None
    value = str(value).strip().lower()
    value = re.sub(r'^https?://(dx\.)?doi\.org/', '', value)
    return value or None


def norm_id(value):
    if not value:
        return None
    return str(value).strip().lower() or None


def norm_url(value):
    if not value:
        return None
    raw = str(value).strip()
    try:
        parts = urlsplit(raw)
        if not parts.netloc:
            return None
        if parts.query or parts.fragment:
            return None
        path = re.sub(r'/+$', '', parts.path.lower())
        return f'{parts.scheme.lower()}://{parts.netloc.lower()}{path}'
    except ValueError:
        return None


def identity_keys(record):
    keys = set()
    for field in ('doi',):
        value = norm_doi(record.get(field))
        if value:
            keys.add(('doi', value))
    for field in ('pmid', 'pmcid'):
        value = norm_id(record.get(field))
        if value:
            keys.add((field, value))
    for field in ('link', 'url'):
        value = norm_url(record.get(field))
        if value:
            keys.add(('url', value))
            parts = urlsplit(value)
            if parts.netloc in {'pmc.ncbi.nlm.nih.gov', 'www.ncbi.nlm.nih.gov', 'europepmc.org'}:
                match = re.search(r'/(?:articles/)?(PMC\d+)(?:/|$)', parts.path, re.I)
                if match:
                    keys.add(('pmcid', match.group(1).lower()))
            match = re.search(r'/doi/(10\.\d{4,9}/[^/?#]+)', parts.path, re.I)
            if match:
                keys.add(('doi', norm_doi(match.group(1))))
            match = re.search(r'/articles/(10\.\d{4,9}/[^/?#]+)', parts.path, re.I)
            if match:
                keys.add(('doi', norm_doi(match.group(1))))
            match = re.search(r'/([0-9]{6,})(?:/|$)', parts.path)
            if parts.netloc in {'pubmed.ncbi.nlm.nih.gov', 'europepmc.org'} and match:
                keys.add(('pmid', match.group(1)))
    return sorted(keys)


def explicit_identifiers(record):
    return {
        'doi': norm_doi(record.get('doi')),
        'pmid': norm_id(record.get('pmid')),
        'pmcid': norm_id(record.get('pmcid')),
    }


def has_identifier_conflict(packet_record, frozen_record):
    packet_ids = explicit_identifiers(packet_record)
    frozen_ids = explicit_identifiers(frozen_record)
    return any(packet_ids[field] and frozen_ids[field] and packet_ids[field] != frozen_ids[field]
               for field in packet_ids)


def main():
    packet = json.loads(PACKET.read_text())['sources']
    frozen = json.loads(FROZEN.read_text())
    frozen_by_key = {}
    packet_rows = []
    frozen_rows = []
    packet_records = {}
    frozen_records = {}
    for record in packet:
        keys = identity_keys(record)
        packet_records[str(record.get('index'))] = record
        row = {'packet_index': str(record.get('index')), 'title': record.get('title'), 'identity_keys': keys}
        packet_rows.append(row)
    for record in frozen:
        keys = identity_keys(record)
        frozen_records[str(record.get('index'))] = record
        row = {'frozen_index': str(record.get('index')), 'title': record.get('title'), 'identity_keys': keys}
        frozen_rows.append(row)
        for key in keys:
            frozen_by_key.setdefault(tuple(key), []).append(row['frozen_index'])
    crosswalk = []
    for row in packet_rows:
        candidate_ids = sorted({fid for key in row['identity_keys'] for fid in frozen_by_key.get(tuple(key), [])})
        conflict_ids = [fid for fid in candidate_ids
                        if has_identifier_conflict(packet_records[row['packet_index']], frozen_records[fid])]
        frozen_ids = [fid for fid in candidate_ids if fid not in conflict_ids]
        if conflict_ids and not frozen_ids:
            status = 'identifier_conflict'
        else:
            status = 'exact_match' if len(frozen_ids) == 1 else ('ambiguous_exact_match' if frozen_ids else 'no_exact_match')
        crosswalk.append({**row, 'frozen_indices': frozen_ids,
                          'conflict_frozen_indices': conflict_ids, 'status': status})
    draft_refs = sorted({int(v) for v in re.findall(r'\[(\d+)\]', DRAFT.read_text())})
    exact = [row for row in crosswalk if row['status'] == 'exact_match']
    payload = {
        'schema_version': 'immune_source_identity_crosswalk.v1',
        'identity_method': 'DOI, PMID, PMCID or canonical URL intersection only; no numeric index, title, topic or feedback matching',
        'inputs': {
            'packet': {'path': str(PACKET.relative_to(ROOT)), 'sha256': digest(PACKET), 'source_count': len(packet)},
            'frozen': {'path': str(FROZEN.relative_to(ROOT)), 'sha256': digest(FROZEN), 'source_count': len(frozen)},
            'draft': {'path': str(DRAFT.relative_to(ROOT)), 'sha256': digest(DRAFT), 'citation_ids': draft_refs},
            'denominator_audit': {'path': str(DENOM.relative_to(ROOT)), 'sha256': digest(DENOM), 'denominator': 7},
        },
        'counts': {
            'packet_records': len(packet),
            'frozen_records': len(frozen),
            'exact_packet_records': len(exact),
            'unique_frozen_matches': len({fid for row in exact for fid in row['frozen_indices']}),
            'no_exact_match': sum(row['status'] == 'no_exact_match' for row in crosswalk),
            'ambiguous_exact_match': sum(row['status'] == 'ambiguous_exact_match' for row in crosswalk),
            'identifier_conflict': sum(row['status'] == 'identifier_conflict' for row in crosswalk),
        },
        'crosswalk': crosswalk,
        'denominator_audit_snapshot': {
            'source_artifact': str(DENOM.relative_to(ROOT)),
            'denominator': 7,
            'rows_embedded': False,
            'is_identity_crosswalk': False,
            'note': 'The correction denominator is referenced for audit context only; no issue labels, feedback text, or numeric source IDs are copied into this identity crosswalk.',
        },
        'matched_run_validity': {
            'currently_possible': False,
            'reason': 'The packet and frozen namespaces collide numerically and most denominator sources have no exact canonical match; a matched run requires an explicit crosswalk and citation remap.',
        },
        'required_before_matched_fulltext_run': [
            'Freeze one canonical source record per packet/frozen identity with DOI/PMID/PMCID/URL and title/date metadata.',
            'Bind every full-text XML/HTML/text artifact to that identity with acquisition URL, version state, byte/text SHA-256 and offsets.',
            'Produce an old-ID to new-ID citation remap for the inherited draft; never reuse numeric IDs across namespaces.',
            'Blind the crosswalk and full-text annotations from generation/judging as feedback labels or expected answers.',
        ],
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'output': str(OUT.relative_to(ROOT)), 'sha256': digest(OUT), 'counts': payload['counts']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
