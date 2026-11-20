"""Per-fact assignment, scoped comparison and conditional source-grounded full-report candidate repair; no independent score; not independent source adjudication."""
import json,argparse
from pathlib import Path
from scripts.run_related_report_revision_20261115 import R,TOKENIZER,read,write,sha
from scripts.experiment_error_receipt import error_receipt
from research_verify.retention_inventory import inventory_prompt,parse_inventory
from research_verify.report_occurrences import occurrence_texts,comparison_prompt,parse_comparisons,parse_occurrence_inventory

from research_verify.occurrence_groups import grouping_prompt,parse_groups,group_comparison_prompt,parse_group_comparisons

from research_verify.occurrence_assignment import assignment_prompt,parse_assignments
from scripts.run_token_index_report_repair_20261115 import prepare_cases
from research_verify.token_span_edits import token_edit_prompt,parse_token_edits
from research_verify.field_comparison import edit_confirmation_prompt,apply_confirmed_edits
from research_verify.dimension_comparison import preview_confirmation_prompt
from research_verify.request_fields import original_anchors

def main():
 p=argparse.ArgumentParser();p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--execute',action='store_true');p.add_argument('--preflight',type=Path);p.add_argument('--replay',type=Path);a=p.parse_args();assert not(a.execute and a.replay)
 base=R/'token-index-report-repair-model-20261115-v1/attempt';report=(base/'candidate-report-0.txt').read_text();question=(base/'original-question-0.txt').read_text();texts=occurrence_texts(report,{5})
 from tokenizers import Tokenizer
 assert sha(TOKENIZER)=='4607b3d1929c5ca263a81d7153c6d6ecdbc71c9e933c0fb2df2abf181bf6df61'
 tok=Tokenizer.from_file(str(TOKENIZER));tokens=lambda s:len(tok.encode(s,add_special_tokens=False).ids)
 a.out_dir.mkdir(parents=True,exist_ok=False)
 code=[Path(__file__),*Path('local_deep_research/research_verify').glob('*.py'),*[Path(n)for n in read(base/'prestart-freeze.json')if n.startswith('scripts/')]]
 cache=R/'report-occurrences-model-20261115-v1/attempt'
 paths=[base/n for n in ['candidate-report-0.txt','original-question-0.txt','completion.json']]+[cache/n for n in ['call-00-response.txt','call-00-prompt.txt','calls.json','completion.json']]
 cached_call=read(cache/'calls.json')[0];assert cached_call['status']=='returned'and cached_call['response_metadata']['finish_reason']=='stop'and sha(cache/'call-00-response.txt')==cached_call['response_sha256']
 assert inventory_prompt(question,texts)==(cache/'call-00-prompt.txt').read_text()
 inventory_parse=parse_occurrence_inventory((cache/'call-00-response.txt').read_text(),texts);cached_inventories=inventory_parse['inventories']
 descriptor_path=R/'grouped-report-occurrences-model-20261115-v1/attempt/grouped.json';descriptors=read(descriptor_path)['groups'];paths.append(descriptor_path)
 cases,source_paths=prepare_cases();case=dict(cases[0],report=report,anchors=original_anchors(report));paths.extend(source_paths);code.append(Path('scripts/run_token_index_report_repair_20261115.py'))
 if a.execute:
  assert a.preflight and read(a.preflight/'completion.json')['status']=='preflight_only'
  assert all(sha(Path(n))==h for n,h in read(a.preflight/'prestart-freeze.json').items());paths.extend(a.preflight/n for n in ['completion.json','prestart-freeze.json','plan.json'])
 if a.replay:paths.extend(f for f in a.replay.rglob('*')if f.is_file()and 'code'not in f.parts)
 freeze={str(f):sha(f)for f in [*code,*paths,TOKENIZER]};write(a.out_dir/'prestart-freeze.json',freeze)
 for f in code:
  q=a.out_dir/'code'/f.resolve().relative_to(Path.cwd());q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(f.read_bytes())
 (a.out_dir/'report.txt').write_text(report);(a.out_dir/'question.txt').write_text(question);write(a.out_dir/'occurrences.json',texts)
 settings={'llm.provider':'openai_endpoint','llm.model':'deepseek-v4-flash','llm.temperature':0,'llm.max_tokens':8000,'llm.max_retries':0,'llm.request_timeout':180,'general.enable_fact_checking':True,'verify.enable_citation_qc':False}
 prompt=assignment_prompt(question,cached_inventories,descriptors);assert int(tokens(prompt)*1.1)+8000+8192<=131072
 (a.out_dir/'inventory-prompt.txt').write_text(prompt)
 write(a.out_dir/'plan.json',dict(scope=__doc__,settings=settings,maximum_fresh_calls=4,occurrences=len(texts),report_chars=len(report),
  limits=['Known IFcandidate only','Direct citation-linked occurrences only; no uncited coverage guarantee','Inventory partial coverage and consistency opinions not primary truth','Conditional isolated source5 repair only; no deployment/new research/independent correction credit'],independent_correction_credit=0))
 calls=[];model=None;failure=None;inventories=None;comparisons=None;revision=None
 def invoke(prompt,stage):
  nonlocal model
  assert len(calls)<4 and int(tokens(prompt)*1.1)+8000+8192<=131072
  i=len(calls);pp=a.out_dir/f'call-{i:02d}-prompt.txt';pp.write_text(prompt);row=dict(index=i,stage=stage,prompt_sha256=sha(pp),estimated_tokens=tokens(prompt),status='started');calls.append(row);write(a.out_dir/'calls.json',calls)
  try:
   if a.replay:
    prev=read(a.replay/'calls.json')[i];assert prev['stage']==stage and prev['prompt_sha256']==row['prompt_sha256']and prev['status']=='returned'
    rp=a.replay/f'call-{i:02d}-response.txt';assert sha(rp)==prev['response_sha256'];raw=rp.read_text();meta=prev['response_metadata'];row['origin']='strict_replay'
   else:
    if model is None:
     from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
     from local_deep_research.config.thread_settings import settings_context
     from local_deep_research.config.llm_config import get_llm
     defaults=read(Path('/install/.venv/lib/python3.14/site-packages/local_deep_research/defaults/default_settings.json'));effective=apply_environment_overrides_to_snapshot({k:v.get('value')for k,v in defaults.items()})|settings
     with settings_context(type('Settings',(),{'username':None,'get_setting':staticmethod(lambda k,d=None:effective.get(k,d))})()):model=get_llm(settings_snapshot=effective)
    row['origin']='fresh_model';response=model.invoke(prompt);raw=str(response.content);meta=response.response_metadata
   rp=a.out_dir/f'call-{i:02d}-response.txt';rp.write_text(raw);row.update(status='returned',response_sha256=sha(rp),response_metadata=meta);assert meta.get('finish_reason')=='stop';return raw
  except Exception as exc:row.update(status='unavailable',failure=error_receipt(exc));raise
  finally:write(a.out_dir/'calls.json',calls)
 if a.execute or a.replay:
  try:
   if a.preflight:assert prompt==(a.preflight/'inventory-prompt.txt').read_text()
   inventories=cached_inventories;write(a.out_dir/'inventories.json',inventories);write(a.out_dir/'inventory-parse.json',inventory_parse)
   grouped=parse_assignments(invoke(prompt,'assign_every_report_fact'),inventories,descriptors);write(a.out_dir/'grouped.json',grouped)
   results=parse_group_comparisons(invoke(group_comparison_prompt(question,report,grouped),'bounded_group_consistency'),grouped)
   comparisons=dict(groups=grouped,results=results);write(a.out_dir/'comparisons.json',comparisons)
   answer=report;changes=[];decisions=[];edits=None
   if any(r.get('relationship')=='conflict'for r in results):
    values=[case[k]for k in ['question','report','material','requirements','anchors','observations']]
    navigation=dict(results=[{k:v for k,v in r.items()if k!='actual_facts'}for r in results],descriptors=[{k:g[k]for k in ['group_id','study','method','field','quantity_unit']}for g in grouped['groups']],routing=[dict(fact_key=r['fact_key'],text_id=r['actual_fact']['text_id'],fact_id=r['actual_fact']['fact_id'],group_ids=r['group_ids'],status=r['status'],assertion_kind=r.get('assertion_kind'),availability_scope=r.get('availability_scope'))for r in grouped['assignments']])
    prefix='Report-only routing/consistency opinions below are FALLIBLE NAVIGATION, NEVER primary evidence. Verify with actual full source and original request. Do not erase abstract availability qualifiers or leave the same error in another occurrence.\n'+json.dumps(navigation,ensure_ascii=False)+'\n'
    edits=parse_token_edits(invoke(prefix+token_edit_prompt(*values,[],case['source_ids']),'source_grounded_cross_occurrence_proposals'),report,case['material'],case['requirements'],case['anchors'],case['source_ids'],case['observations'])
    if edits['eligible']:
     confirm=preview_confirmation_prompt(edit_confirmation_prompt(*values,[],edits['eligible']),report,edits['eligible'])
     answer,changes,decisions=apply_confirmed_edits(invoke(confirm,'separate_full_report_preview_confirmation'),report,edits['eligible'])
   (a.out_dir/'candidate-report.txt').write_text(answer)
   revision=dict(proposals=edits,changes=changes,decisions=decisions,report_chars=len(answer),sha256=sha(a.out_dir/'candidate-report.txt'),independent_correction_credit=0);write(a.out_dir/'revision.json',revision)
  except Exception as exc:failure=error_receipt(exc)
 write(a.out_dir/'completion.json',dict(status='unavailable'if failure else('completed_report_occurrences_diagnostic'if a.execute or a.replay else'preflight_only'),failure=failure,
  logical_calls=len(calls),fresh_calls=sum(c.get('origin')=='fresh_model'for c in calls),inventories=inventories,comparisons=comparisons,revision=revision,frozen_inputs_unchanged=all(sha(Path(n))==h for n,h in freeze.items()),independent_correction_credit=0))
 print(json.dumps(dict(failure=failure,calls=len(calls),comparisons=len(comparisons['results'])if comparisons else None,independent_correction_credit=0)))
 if failure:raise SystemExit(2)
if __name__=='__main__':main()
