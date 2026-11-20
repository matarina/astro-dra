"""Source-blind rendering of a proposed correction, not factual approval."""
import json

from .claim_language import parse_translations


def proposal_render_prompt(issues):
    return ('Render each proposed local replacement in the language of its ORIGINAL '
        'report unit, preserving the original list/table formatting and explicit citation '
        'scope. This is faithful linguistic rendering, NOT scientific checking. Preserve '
        'the PROPOSED meaning, including every named concept, relation, quantity, negation '
        'and qualifier; do not restore the original assertion when the proposal differs. '
        'Do not copy an entire English proposal into a non-English original. Keep technical '
        'names in their original spelling when translation is uncertain, and list the '
        'uncertainty rather than substituting a familiar different concept. Do not add '
        'findings, silently correct the proposal, or decide whether it should be applied. '
        'No paper evidence is supplied. Independent source confirmation comes later. '
        'Return only JSON {"translations":[{"claim_id":0,"text":"replacement in '
        'original report language","uncertain_terms":[]}]}, exactly one per claim_id.\n'
        +json.dumps([dict(claim_id=i['claim_id'],original=i['statement'],proposed=i['replacement'])
                    for i in issues],ensure_ascii=False))


def parse_rendered_proposals(raw, issues):
    claims={i['claim_id']:{'text':i['replacement']} for i in issues}
    if len(claims)!=len(issues):raise ValueError('Duplicate proposal scope')
    return parse_translations(raw,claims)
