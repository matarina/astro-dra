"""Source-only concept/relationship reading, reusing the existing verifier.

The reader has no report/claim/verdict input. Notes are fallible model output;
quote location and source scope do not establish entailment or completeness.
"""
from dataclasses import asdict
import json

from .independent_verification import VerificationQuestion, build_verification_prompt, parse_verification_response


CONCEPT_COMPARISON_INSTRUCTIONS = """CONCEPT AND RELATION COMPARISON:
Compare the named concepts and relationships themselves, across languages,
using their supplied original terms and definitions. A shared gene/entity list,
study object or method does not make different processes or relations equivalent.
Check subject, predicate, object, direction, certainty and study context separately.
Preserve supported findings and legitimate aliases; lexical mismatch alone is
not contradiction. If translation or identity cannot be resolved from evidence,
retain the source's original term and uncertainty rather than assert equivalence
or invent a replacement fact. Attribute any proposed correction to exact source
evidence, and keep the existing native response schema and repair conditions.
"""


def source_fact_questions(passages, original_question):
    ids=[p.source_id for p in passages]
    if len(ids)!=len(set(ids)):raise ValueError('One canonical view per source required')
    return tuple(VerificationQuestion(
        question_id=f'source-facts-{p.source_id}',source_ids=(p.source_id,),
        text=('What named concepts, definitions and relationships does this supplied source establish? '
              'Keep the original names and defining features. Distinguish entity identities, '
              'subject/predicate/object, study inputs/settings, methods, observations and limitations. '
              'Give at most four short sentences and three exact source quotations, prioritizing '
              'central named concepts and relationships. This is a bounded reading note, not an '
              'exhaustive inventory or negative evidence for omitted details. Do not assess a report '
              'or infer equivalence from a shared entity list. Preserve unresolved or absent fields. '
              'Metadata is not full-text evidence; it cannot establish unknown article eligibility. '
              'Research request (context, not evidence): '+str(original_question)),
        requested_fields=('original concept names and definitions','source-specific relationships',
                          'study context and quantities','qualifiers and evidence limits')) for p in passages)


def source_fact_prompt(passages, original_question):
    passages=tuple(passages)
    return build_verification_prompt(source_fact_questions(passages,original_question),passages)


def parse_source_facts(raw, passages, original_question):
    passages=tuple(passages)
    return parse_verification_response(raw,source_fact_questions(passages,original_question),passages)


def comparison_notes(answers):
    rows=[{**asdict(a),'evidence_status':a.evidence_status,'effective_status':a.effective_status} for a in answers]
    return ('FALLIBLE SOURCE-ONLY READING NOTES (not primary evidence, not independent adjudication):\n'
            'These were produced without seeing the report. Verify them against the unchanged supplied '
            'original sources. Missing notes/fields are not negative evidence, and located quotes do not '
            'guarantee correct interpretation or complete coverage. Never approve a change merely because '
            'a note says so.\n'+json.dumps(rows,ensure_ascii=False))
