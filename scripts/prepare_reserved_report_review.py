"""Create arm-hidden review packets using the frozen prose sampling protocol."""

import argparse
from collections import Counter
from dataclasses import asdict
import gzip
import hashlib
import json
from pathlib import Path


ARMS = ("baseline", "candidate")


def read(path):
    return json.loads(path.read_bytes())


def digest(data):
    return hashlib.sha256(data).hexdigest()


def stable_hash(*values):
    return digest(json.dumps(values, ensure_ascii=False).encode())


def verify_files(root, manifest):
    for name, expected in manifest.items():
        if digest((root / name).read_bytes()) != expected:
            raise ValueError(f"Frozen file changed: {name}")


def review_units(body, report_id, seed):
    from research_verify.claims import extract_report_claims

    claims = extract_report_claims(body)
    inventory = Counter(claim.kind for claim in claims)
    prose = []
    for claim in claims:
        start, end = claim.report_start, claim.report_end
        if start is None or end is None or not 0 <= start < end <= len(body):
            raise ValueError(f"Out of range span in {report_id}: {start}, {end}")
        if body[start:end] != claim.text:
            raise ValueError(f"Prose coordinate mismatch in {report_id}: {start}, {end}")
        if claim.kind == "prose_candidate":
            prose.append({**asdict(claim), "unit_id": stable_hash(seed, "unit", report_id, start, end)})
    if len(prose) != len({unit["unit_id"] for unit in prose}):
        raise ValueError(f"Duplicate prose spans in {report_id}")
    return inventory, sorted(prose, key=lambda unit: unit["unit_id"])[:4]


def writer_exposure(root, arm, case_id, sources):
    from research_verify.evidence_flow import visible_texts

    trace_key = digest(f"bioinformatics-native-{arm}-{case_id}".encode())[:32]
    trace_root = root / arm / "traces" / trace_key
    stages, exposure = Counter(), []
    sources_by_id = {source["index"]: source for source in sources}
    writer_materials, writer_requests = 0, 0
    for log in sorted(trace_root.rglob("events.jsonl")):
        materials, requests = {}, {}
        for line in log.read_text().splitlines():
            event = json.loads(line)
            stages[(event["stage"], event.get("status", "unknown"))] += 1
            if event.get("status") != "recorded":
                continue
            raw = gzip.decompress((log.parent / event["file"]).read_bytes())
            if len(raw) != event["bytes"] or digest(raw) != event["sha256"]:
                raise ValueError(f"Trace payload changed: {log.parent / event['file']}")
            stage = event["stage"]
            if stage not in {"writer_sources", "writer_request"}:
                continue
            target = materials if stage == "writer_sources" else requests
            payload = json.loads(raw)
            if payload["batch"] in target:
                raise ValueError(f"Multiple {stage} records in one batch: {log}")
            target[payload["batch"]] = payload
        writer_materials += len(materials)
        writer_requests += len(requests)
        for batch, material in materials.items():
            prompt = requests.get(batch, {}).get("prompt", "")
            rendered = material["text"]
            if not rendered or rendered not in prompt:
                continue
            for index, text in visible_texts(rendered).items():
                source = sources_by_id.get(index, {})
                complete_fields = [field for field in ("full_content", "abstract", "content")
                                   if source.get(field) and source[field] in text]
                exposure.append(dict(batch=batch, index=index, writer_text_chars=len(text),
                                     writer_text_sha256=digest(text.encode()),
                                     verbatim_supplied_fields=complete_fields))
    return dict(trace_records={f"{stage}/{status}": count for (stage, status), count in sorted(stages.items())},
                writer_material_events=writer_materials, writer_request_events=writer_requests,
                linked_source_views=exposure)


def collect(root, protocol_path, phase):
    from research_verify import claims, evidence_flow, report_syntax

    freeze = read(root / "freeze.json")["sha256"]
    verify_files(root, freeze)
    if phase == "reserved" and protocol_path.resolve() != (root / "reserved-assessment-protocol.json").resolve():
        raise ValueError("Use the reserved run's frozen assessment protocol")
    if phase == "reserved" and "reserved-assessment-protocol.json" not in freeze:
        raise ValueError("Assessment protocol is missing from the freeze manifest")
    protocol = read(protocol_path)
    seed = protocol["sample_seed"]
    manifest = read(root / "candidate-code-hashes.json")
    for module in (claims, evidence_flow, report_syntax):
        file = Path(module.__file__)
        if digest(file.read_bytes()) != manifest[f"local_deep_research/research_verify/{file.name}"]:
            raise ValueError(f"The common parser differs from the frozen candidate: {file}")

    cases = [case for case in read(root / "experiment.json")["cases"] if case["split"] == phase
             and (phase == "reserved" or case["variant"] == "original")]
    if phase == "reserved" and len(cases) != protocol["scheduled_pairs"]:
        raise ValueError("Scheduled pair count differs from assessment protocol")
    expected = {(arm, case["case_id"]) for arm in ARMS for case in cases}
    executions = [json.loads(line) for line in (root / f"{phase}-orchestration.log").read_text().splitlines()]
    terminal = {(entry["arm"], entry["case_id"]): entry for entry in executions}
    if len(terminal) != len(executions) or terminal.keys() != expected:
        raise ValueError("Run requires exactly one terminal orchestration entry per scheduled report")

    reports, bindings, packs = [], {}, {}
    for case in cases:
        pack_hash = case["source_pack_sha256"]
        path = root / case["source_pack"]
        if digest(path.read_bytes()) != pack_hash:
            raise ValueError(f"Source pack changed: {path}")
        sources = read(path)
        source_ids = {source["index"] for source in sources}
        if len(source_ids) != len(sources):
            raise ValueError(f"Ambiguous citation numbering in {path}")
        packs.setdefault(pack_hash, sources)
        settings = set()
        for arm in ARMS:
            case_id = case["case_id"]
            report_id = stable_hash(seed, "report", case_id, arm)
            generated = root / arm / f"{case_id}.json"
            row = read(generated) if generated.is_file() else None
            exit_code = terminal[(arm, case_id)]["exit_code"]
            status = row["status"] if row else "missing"
            entry = dict(report_id=report_id, query=case["query"], source_pack_sha256=pack_hash,
                         generation_status=status, body=None, structural_units={}, sampled_units=[])
            binding = dict(case_id=case_id, arm=arm, family=case["task_family"], domain=case["domain"],
                           variant=case["variant"], generation_status=status, exit_code=exit_code,
                           generated_sha256=digest(generated.read_bytes()) if row else None)
            if status == "completed":
                if (exit_code != 0 or row["case_id"] != case_id or row["system"] != arm
                        or row["query"] != case["query"] or row["source_pack_sha256"] != pack_hash):
                    raise ValueError(f"Mismatched report binding: {generated}")
                settings.add((row["model"], row["settings_sha256"]))
                body = row["body"]
                publication = row["publication"]["claim_publication"]
                if publication["report_body"] != body:
                    raise ValueError(f"Pre-publication draft changed: {generated}")
                received = row["sources"]
                binding["provided_fields_preserved"] = (
                    len(received) == len(sources) and all(
                        all(key in got and got[key] == value for key, value in source.items())
                        for got, source in zip(received, sources)
                    )
                )
                binding["publication_status"] = publication["status"]
                binding["audit_status"] = publication["audit_status"]
                binding["writer_exposure"] = writer_exposure(root, arm, case_id, sources)
                inventory, sample = review_units(body, report_id, seed)
                for unit in sample:
                    unit["citations_missing_from_pack"] = sorted(set(unit["citations"]) - source_ids)
                entry.update(body=body, structural_units=inventory, sampled_units=sample)
            reports.append(entry)
            bindings[report_id] = binding
        if len(settings) > 1:
            raise ValueError(f"Model or settings mismatch for pair {case['case_id']}")
    return sorted(reports, key=lambda report: report["report_id"]), packs, bindings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("protocol", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--phase", choices=("development", "reserved"), required=True)
    args = parser.parse_args()
    reports, packs, bindings = collect(args.root, args.protocol, args.phase)
    args.output.mkdir(mode=0o700)
    packets = args.output / "review"
    packets.mkdir(mode=0o700)
    files = {
        "review/reports.json": reports,
        "review/source-packs.json": packs,
        "private-bindings.json": bindings,
    }
    receipt = {"phase": args.phase, "reports": len(reports), "pack_count": len(packs),
               "generation_status": dict(Counter(report["generation_status"] for report in reports)),
               "structural_prose_units": sum(report["structural_units"].get("prose_candidate", 0) for report in reports),
               "sampled_prose_units": sum(len(report["sampled_units"]) for report in reports),
               "protocol_sha256": digest(args.protocol.read_bytes()),
               "sampler_sha256": digest(Path(__file__).read_bytes()), "sha256": {}}
    for name, data in files.items():
        raw = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode()
        (args.output / name).write_bytes(raw)
        receipt["sha256"][name] = digest(raw)
    (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
