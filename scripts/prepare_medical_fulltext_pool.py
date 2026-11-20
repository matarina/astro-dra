"""Freeze author-distributed clinical text/ICO/gold before selection tuning."""
import argparse
from collections import Counter,defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path
import tarfile


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--root",type=Path,required=True)
    root=parser.parse_args().root
    if (root/"pool-freeze.json").exists():raise ValueError("Do not overwrite a frozen evaluation pool")
    archive=root/"evidence-inference-v2.0.response"
    expected=json.loads((root/"v2-fetch.json").read_text())["sha256"]
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=expected:raise ValueError("Author archive changed")
    def digest(value):return hashlib.sha256(value.encode()).hexdigest()
    def dump(name,value):
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n")
    with tarfile.open(archive) as tar:
        def text(name):return tar.extractfile(name).read().decode("utf-8-sig")
        (root/"author-README.md").write_text(text("README.md"))
        split=text("splits/ev2_test_article_ids.txt").splitlines()
        (root/"author-test-article-ids.txt").write_text("\n".join(split)+"\n")
        test={x.removeprefix("PMC").strip() for x in split if x.strip()}
        prompts=list(csv.DictReader(io.StringIO(text("prompts_merged.csv"))))
        annotations=list(csv.DictReader(io.StringIO(text("annotations_merged.csv"))))
        grouped=defaultdict(list)
        for row in annotations:grouped[row["PromptID"]].append(row)
        candidates=[];ties=0;invalid=0
        for prompt in prompts:
            if prompt["PMCID"] not in test:continue
            rows=grouped[prompt["PromptID"]]
            valid=[r for r in rows if r["Valid Label"]=="True" and r["Valid Reasoning"]=="True" and r["Label Code"] in {"-1","0","1"}]
            counts=Counter(r["Label Code"] for r in valid)
            if not counts:invalid+=1;continue
            majority=counts.most_common()
            if len(majority)>1 and majority[0][1]==majority[1][1]:ties+=1;continue
            candidates.append((digest("ldr-medical-fulltext-20261111"+prompt["PromptID"]),prompt,rows,majority[0][0],dict(counts)))
        chosen=[];seen_articles=set();label_counts=Counter()
        for _,prompt,rows,label,counts in sorted(candidates):
            if label_counts[label]>=6 or prompt["PMCID"] in seen_articles:continue
            name="txt_files/PMC"+prompt["PMCID"]+".txt"
            if name not in tar.getnames():raise ValueError("Selected original article text missing")
            body=text(name)
            chosen.append((prompt,rows,label,counts,body));label_counts[label]+=1;seen_articles.add(prompt["PMCID"])
        if dict(label_counts)!={"-1":6,"0":6,"1":6}:raise ValueError("Insufficient article-distinct label strata")
        inputs=[];gold=[];strata=Counter()
        for prompt,rows,label,counts,body in chosen:
            caseid="ei_"+prompt["PromptID"]
            strata[label]+=1
            split="development" if strata[label]<=2 else "reserved"
            source_path="texts/PMC"+prompt["PMCID"]+".txt"
            p=root/source_path;p.parent.mkdir(exist_ok=True);p.write_text(body)
            inputs.append({"case_id":caseid,"article_id":"PMC"+prompt["PMCID"],"split":split,
                "intervention":prompt["Intervention"],"comparator":prompt["Comparator"],"outcome":prompt["Outcome"],
                "question":"According to this trial report, what effect did "+prompt["Intervention"]+" have on "+prompt["Outcome"]+" compared with "+prompt["Comparator"]+"? Explain the reported evidence, scope and limitations.",
                "source_text_file":source_path,"source_text_sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"source_chars":len(body)})
            findings=[]
            for row in rows:
                record={"annotation":row,"offset_in_bounds":False,"exact_span_equals_reasoning":None}
                try:
                    start,end=int(row["Evidence Start"]),int(row["Evidence End"])
                    record["offset_in_bounds"]=0<=start<=end<=len(body)
                    if record["offset_in_bounds"]:
                        record["original_offset_text"]=body[start:end]
                        record["exact_span_equals_reasoning"]=body[start:end]==row["Annotations"]
                except ValueError:pass
                findings.append(record)
            gold.append({"case_id":caseid,"article_id":"PMC"+prompt["PMCID"],"split":split,
                "majority_author_label_code":label,"valid_author_label_counts":counts,"annotations":findings,
                "gold_scope":"Author-annotated statistical result direction, not clinical importance, truth, full-report correctness or citation entailment"})
    dump("inputs.json",inputs);dump("reference-gold.json",gold)
    names=["selection-protocol.json","v2-fetch.json","author-README.md","author-test-article-ids.txt","inputs.json","reference-gold.json"]+[i["source_text_file"] for i in inputs]
    freeze={"status":"frozen_before_material_selection_tuning_no_model_calls","archive_sha256":expected,
        "original_test_articles":len(test),"eligible_test_prompts":len(candidates),"excluded_tied_prompts":ties,"excluded_without_valid_author_labels":invalid,
        "selected_prompts":18,"distinct_articles":len(seen_articles),"label_counts":dict(label_counts),
        "splits":{"development":6,"reserved":12},"reserved_status":"Not inspected as tuning examples; public dataset, not secret/model-unseen; labels were read programmatically for stratification",
        "sha256":{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},"new_material_selection_code":False}
    dump("pool-freeze.json",freeze)
    print(json.dumps({k:freeze[k] for k in ["selected_prompts","distinct_articles","label_counts","splits","excluded_tied_prompts"]},indent=2))


if __name__=="__main__":main()
