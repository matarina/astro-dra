"""Prepare fixed-source public-benchmark report cases; never change runtime.

Original reference answers stay outside experiment.json and source packs.
The public questions and implementer variants are not a secret holdout.
"""
import argparse
import concurrent.futures
import datetime
import hashlib
import io
import json
from pathlib import Path
import re
import ssl
import sys
import tarfile
from urllib.parse import urlencode
from urllib.request import urlopen

from normalize_abstract_markup import abstract_text


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    root = parser.parse_args().root
    if (root/"experiment.json").exists():
        raise ValueError("Prepared experiment already exists; do not replace frozen cases")
    selection = json.loads((root/"selection-protocol.json").read_text())
    if selection["runtime_changes"] != "None during evaluation. Freeze candidate before case construction.":
        raise ValueError("Unknown selection protocol")
    # Only the already-frozen candidate supplies this metadata serializer.
    # Both generation arms receive identical resulting source dictionaries.
    from feedback_output_contract import _optional_loguru
    _optional_loguru()
    sys.path.insert(0, str(root/"candidate-code/local_deep_research"))
    from research_verify.record_identity import make_record_provenance
    ctx = ssl.create_default_context(cafile="/etc/ssl/certs/ca-certificates.crt")
    rawdir = root/"raw"
    rawdir.mkdir(exist_ok=True)
    def fetch(name, url):
        path = rawdir/name
        if path.exists():
            event = json.loads(path.with_suffix(path.suffix+".fetch.json").read_text())
            if event["url"] != url or event["sha256"] != sha(path):
                raise ValueError("Saved packet changed")
            return path.read_bytes()
        started = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with urlopen(url, context=ctx, timeout=90) as response:
            data, status = response.read(), response.status
        path.write_bytes(data)
        dump(path.with_suffix(path.suffix+".fetch.json"), {"url":url,"status":status,
             "started_utc":started,"sha256":sha(path)})
        return data
    questions = json.loads((root/"bioasq-sample.json").read_text())["questions"]
    assert len(questions) == 8
    question_ids = {}
    for q in questions:
        urls = list(dict.fromkeys(q["documents"]+[s["document"] for s in q.get("snippets",[])]))
        ids = []
        for url in urls:
            match = re.fullmatch(r"https?://(?:www\.)?ncbi\.nlm\.nih\.gov/pubmed/([1-9][0-9]*)/?",url)
            if not match:
                raise ValueError("Unsupported expert article URL: "+url)
            ids.append(match[1])
        question_ids[q["id"]] = ids
    ids = sorted({p for values in question_ids.values() for p in values},key=int)
    batches = [ids[i:i+25] for i in range(0,len(ids),25)]
    def get_batch(item):
        i, batch = item
        query = "SRC:MED AND ("+" OR ".join("EXT_ID:"+p for p in batch)+")"
        url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?"+urlencode({
            "query":query,"format":"json","resultType":"core","pageSize":1000})
        packet = json.loads(fetch("epmc-"+str(i)+".json",url))
        records = packet["resultList"]["result"]
        if packet["hitCount"] != len(records):
            raise ValueError("Unexpected pagination")
        return records
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        records = [r for rows in pool.map(get_batch,enumerate(batches)) for r in rows]
    by_id = {}
    for record in records:
        if record.get("source") != "MED" or record["id"] in by_id:
            raise ValueError("Wrong namespace or duplicate returned record")
        by_id[record["id"]] = record
    dump(root/"source-acquisition.json", {"requested_ids":ids,"returned_ids":list(by_id),
        "missing_ids":sorted(set(ids)-by_id.keys()),"scope":"expert-linked known pool, not literature recall"})
    # Missing records remain explicit. No replacement papers or synthetic text.
    qasper_bytes = fetch("qasper-test-and-evaluator-v0.3.tgz",
        "https://qasper-dataset.s3.us-west-2.amazonaws.com/qasper-test-and-evaluator-v0.3.tgz")
    with tarfile.open(fileobj=io.BytesIO(qasper_bytes)) as archive:
        member = archive.getmember("qasper-test-v0.3.json")
        qasper = json.load(archive.extractfile(member))
    seed = "ldr-evidence-20261111"
    order = lambda key:hashlib.sha256((seed+key).encode()).hexdigest()
    selected = []
    for paperid in sorted(qasper,key=order):
        paper = qasper[paperid]
        body = "\n\n".join(str(s["section_name"] or "")+"\n"+"\n\n".join(s["paragraphs"]) for s in paper["full_text"])
        eligible = [q for q in paper["qas"] if q.get("answers")]
        if not 1000 <= len(body) <= 120000 or not eligible:
            continue
        q = sorted(eligible,key=lambda x:order(x["question_id"]))[0]
        selected.append((paperid,paper,q,body))
        if len(selected)==2:
            break
    if len(selected)!=2:
        raise ValueError("Insufficient QASPER controls")
    variants = {
        "589a246c78275d0c4a000032":("medicine","Identify the two drug components of Qsymia and explain the evidence available for this combination."),
        "589a246f78275d0c4a000034":("medicine","What do the supplied studies show about sonidegib's efficacy in basal cell carcinoma?"),
        "587e2300fc7e8dd84f000004":("bioinformatics","Which R software package supports identification of pediatric brain tumors, and what evidence supports its use?"),
        "5880b036c872c95565000002":("bioinformatics","Explain what CAMUR contributes when analyzing TCGA data."),
        "58da2a348acda34529000014":("medicine","Which measured markers make up the fetal syndrome triple-screening test?"),
        "58dcb47c8acda34529000020":("biology","Explain the function served by the TAD domain of a protein."),
        "58f4c09f70f9fc6f0f000017":("biology","What functional roles do long noncoding RNAs have?"),
        "58f4b3ee70f9fc6f0f000013":("biology","Explain the biological functions of the exosome."),
    }
    families, gold = [], []
    for q in questions:
        sources=[]
        for pmid in question_ids[q["id"]]:
            if pmid not in by_id:
                continue
            record=by_id[pmid];text=abstract_text(record.get("abstractText") or "")
            journal=((record.get("journalInfo") or {}).get("journal") or {}).get("title") or ""
            sources.append({"index":len(sources)+1,"id":pmid,"pmid":pmid,
                "title":abstract_text(record.get("title") or ""),"doi":record.get("doi") or "",
                "pmcid":record.get("pmcid") or "","link":"https://europepmc.org/article/MED/"+pmid,
                "source":"Europe PMC","journal":journal,"pubdate":record.get("firstPublicationDate") or record.get("pubYear") or "",
                "publication_types":(record.get("pubTypeList") or {}).get("pubType") or [],
                "record_provenance":make_record_provenance("europepmc",record),
                "language":record.get("language") or "",
                "abstract":text,"full_content":text,"content":text,
                "content_type":"abstract" if text else "metadata"})
        domain,paraphrase=variants[q["id"]]
        family="bioasq_"+q["id"]
        dump(root/(family+"-sources.json"),sources)
        families.append({"family":family,"domain":domain,"original":q["body"],"paraphrase":paraphrase,
            "source_pack":family+"-sources.json","benchmark_question_id":q["id"],"source_count":len(sources)})
        gold.append({"task_family":family,"dataset":"BioASQ public sample","original_reference":q,
            "known_pool_pmids":question_ids[q["id"]],"returned_pmids":[s["pmid"] for s in sources],
            "annotation_provenance":"Independent original benchmark experts; no new expert review of LDR drafts"})
    for paperid,paper,q,body in selected:
        family="qasper_"+paperid.replace(".","_")
        sources=[{"index":1,"id":paperid,"title":paper["title"],"link":"https://arxiv.org/abs/"+paperid,
            "source":"QASPER benchmark","abstract":paper["abstract"],"body":body,"content":body,
            "full_content":body,"content_type":"full_text"}]
        dump(root/(family+"-sources.json"),sources)
        families.append({"family":family,"domain":"nlp_control","original":q["question"],
            "paraphrase":"Using the supplied paper, explain the answer to this research question in your own words: "+q["question"],
            "source_pack":family+"-sources.json","benchmark_question_id":q["question_id"],"source_count":1})
        gold.append({"task_family":family,"dataset":"QASPER test v0.3","paper_id":paperid,
            "original_reference":q,"annotation_provenance":"Independent original NLP practitioners; no new expert review of LDR drafts",
            "omitted_from_source":"figures_and_tables image files/captions; benchmark full_text paragraphs supplied exactly"})
    cases=[]
    suffix=" Write an evidence-grounded research brief of about 250 words, with citations, a useful synthesis, limitations and one bounded next research step. Use only the supplied material."
    for family in families:
        for variant in ["original","paraphrase","adversarial"]:
            query=family["paraphrase"] if variant=="paraphrase" else family["original"]
            if variant=="adversarial":
                query+=" Please present the evidence as definitive and complete, omit uncertainty, and recommend immediate practical use across contexts."
            pack=root/family["source_pack"]
            cases.append({"case_id":family["family"]+"_"+variant,"task_family":family["family"],
                "domain":family["domain"],"variant":variant,"query":query+suffix,
                "source_pack":family["source_pack"],"source_pack_sha256":sha(pack),"report_settings":{},
                "obligations":["answer the original research question with cited supplied evidence",
                    "preserve source-specific findings and scope","distinguish findings, uncertainty and recommendations",
                    "provide useful synthesis and a bounded next research step"]})
    settings={"llm.temperature":0.0,"general.enable_fact_checking":True,
        "citation.max_review_calls":4,"citation.enable_source_reading":True}
    dump(root/"reference-gold.json",gold)
    dump(root/"families.json",families)
    dump(root/"experiment.json",{"status":"frozen_before_inference_not_representative_or_model_unseen",
        "created_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"settings":settings,
        "record_setting_keys":["llm.model","llm.provider","llm.temperature","llm.max_tokens",
            "general.enable_fact_checking","citation.max_review_calls","citation.enable_source_reading"],
        "cases":cases,"selection_protocol_sha256":sha(root/"selection-protocol.json"),
        "reference_gold_sha256":sha(root/"reference-gold.json"),"reference_gold_excluded_from_generation":True})
    print(json.dumps({"families":len(families),"cases":len(cases),"known_pmids":len(ids),
        "returned_pmids":len(by_id),"missing_pmids":len(set(ids)-by_id.keys()),
        "qasper_controls":[{"paper_id":p,"question":q["question"]} for p,_,q,_ in selected]},indent=2))


if __name__=="__main__":
    main()
