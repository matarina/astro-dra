"""Preserve report content; store optional citation advice outside the report body."""
from __future__ import annotations
from hashlib import sha256
import re
from urllib.parse import urlsplit
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict
from .citation_qc import CitationQc
from .claims import CITE_RE, extract_report_claims, extract_legacy_report_claims
from .config import VerifyConfig, get_config
from .models import ClaimCheck
from .evidence import paper_identity, source_artifacts
from .revision import RevisionResult
from .citation_display import cited_indices, legacy_cited_indices, render_report, render_report_current, format_sources
from .synthesis_trace import start_trace, source_snapshot, text_digest
from .evidence_grounding import EvidenceGroundingV1, build_evidence_grounding

NOTICE = "当前没有可保留的已核验结论。"
KEY = "claim_publication"

def digest(text: str) -> str:
    return sha256(text.encode()).hexdigest()

class PublishedSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    index: int = Field(ge=1)
    original_indices: list[int]
    paper_id: str
    artifact_id: str
    title: str = ""
    url: str = ""
    source_kind: str = "unknown"
    document_type: str = "unknown"
    status: str = "unverified"
    status_reason: str = ""
    identity_status: str = "missing"
    identity_provenance: dict = Field(default_factory=dict)
    publication_state: str = "unknown"
    peer_review_status: str = "unknown"
    relevance_status: str = "unknown"
    evidence_scope: str = "unknown"
    temporal_validity: str = "unknown"
    contradiction_status: str = "unknown"

class Publication(BaseModel):
    schema_version: Literal["1.0", "2.0", "2.1", "2.2", "2.3"] = "2.3"
    status: Literal["unverified", "traceability_checked", "partial", "withheld"]
    content: str
    content_sha256: str
    verified_body: str = ""
    sources: list[PublishedSource] = Field(default_factory=list)
    revision: RevisionResult | None = None  # Historical report metadata only.
    report_body: str = ""
    citation_audit: list[ClaimCheck] = Field(default_factory=list)
    citation_audit_numbering: Literal["original"] = "original"
    audit_status: Literal["completed", "disabled", "unavailable", "no_cited_claims"] = "disabled"
    warnings: list[str] = Field(default_factory=list)
    reason_code: str = "publication_complete"
    # Additive metadata.  Historical reports omit this field and remain valid.
    evidence_grounding: EvidenceGroundingV1 | None = None

    def metadata(self) -> dict:
        return {KEY: self.model_dump(mode="json")}

class SourceCollector:
    """Ambiguous indices cannot silently select the first paper or text."""
    def __init__(self, sources: list[dict]):
        self.sources, self.ambiguous = {}, set()
        for position, source in enumerate(sources, 1):
            if not isinstance(source, dict):
                continue
            try:
                index = int(source.get("index", position))
                if index < 1:
                    continue
            except (TypeError, ValueError):
                continue
            copied = {**source, "index": index}
            existing = self.sources.get(index)
            if existing is not None:
                a = {(x.paper_id, x.artifact_id) for x in source_artifacts(existing) if x}
                b = {(x.paper_id, x.artifact_id) for x in source_artifacts(copied) if x}
                if paper_identity(existing) != paper_identity(copied) or a != b:
                    self.ambiguous.add(index)
            else:
                self.sources[index] = copied

    def find_by_index(self, index: int):
        return None if index in self.ambiguous else self.sources.get(index)

def collect_publication_sources(system, links: list[dict]) -> list[dict]:
    """Prefer original evidence snapshots, never merge text by URL/title."""
    collector = getattr(getattr(system, "strategy", None), "collector", None)
    if collector is None:
        return list(links)
    resolved = []
    for position, source in enumerate(links, 1):
        try:
            index = int(source.get("index", position))
            original = collector.find_by_index(index)
        except Exception:
            original = None
        resolved.append(original if isinstance(original, dict) else source)
    return resolved

def safe_url(value) -> str:
    if not isinstance(value, str):
        return ""
    try:
        parts = urlsplit(value)
        if parts.scheme not in {"https", "http"} or not parts.hostname or parts.username or parts.password:
            return ""
    except ValueError:
        return ""
    return value.replace("(", "%28").replace(")", "%29").replace(" ", "%20").replace("\n","").replace("\r","")

def withheld(reason: str) -> Publication:
    """Compatibility helper for historical callers; new research never gates on QC."""
    revision = RevisionResult(status="withheld", reason_code=reason, body_sha256=digest(""))
    return Publication(schema_version="1.0", status="withheld", content=NOTICE,
                       content_sha256=digest(NOTICE), revision=revision, reason_code=reason)


def _render_report_v2(body: str, sources: list[PublishedSource]) -> str:
    urls = {s.index: s.url for s in sources if s.url}
    def hyperlink(match):
        numbers = [int(n) for n in re.split(r"\s*,\s*", match.group(1))]
        # Do not overwrite unresolved or ambiguous references with a guessed URL.
        if not all(n in urls for n in numbers):
            return match.group()
        return ", ".join(f"[{n}]({urls[n]})" for n in numbers)
    # Only format citations in answer prose. Bibliography entry labels (including
    # grouped [1, 2] labels) must stay intact for RIS/BibTeX/Quarto parsers.
    for claim in reversed(extract_legacy_report_claims(body)):
        if claim.citations:
            body = (body[:claim.report_start] + CITE_RE.sub(hyperlink, claim.text)
                    + body[claim.report_end:])
    return body


def publish_report(draft: str, sources: list[dict], model=None, cfg: VerifyConfig | None=None, *,
                   research_spec=None, writer_context=None, pending_findings=None,
                   proposed_changes=None) -> Publication:
    with start_trace("publication") as trace:
        if trace:
            trace.record("publication_input", {"text": draft, "text_sha256": text_digest(draft),
                         "sources": source_snapshot(sources)})
        result = _publish_report(draft, sources, model, cfg,
                                 research_spec=research_spec,
                                 writer_context=writer_context,
                                 pending_findings=pending_findings,
                                 proposed_changes=proposed_changes)
        trace.record("publication_output", {"text": result.content,
                     "input_text_sha256": text_digest(draft),
                     "text_sha256": result.content_sha256,
                     "sources": [source.model_dump() for source in result.sources],
                     "warnings": result.warnings, "audit_status": result.audit_status})
        if result.evidence_grounding is not None:
            trace.record("evidence_grounding", result.evidence_grounding.model_dump(mode="json"))
        return result


def _publish_report(draft: str, sources: list[dict], model=None, cfg: VerifyConfig | None=None, *, _schema_version="2.3",
                    research_spec=None, writer_context=None, pending_findings=None,
                    proposed_changes=None) -> Publication:
    """Number/link citations and optionally audit; no semantic rewriting or QC gate."""
    from .source_identity import classify_source, reconcile_identities
    collector = SourceCollector(reconcile_identities(sources))
    selected, warnings, identities = [], [], {}
    modern = _schema_version in {"2.2", "2.3"}
    order = cited_indices(draft, expand_ranges=_schema_version == "2.3") if modern else legacy_cited_indices(draft)
    missing = {index for index in order if collector.find_by_index(index) is None}
    next_index = 1
    for index in order:
        source = collector.find_by_index(index)
        if source is None:
            warnings.append(f"unresolved_citation:{index}")
            continue
        identity = paper_identity(source) or f"unresolved:{index}"
        if identity in identities:
            identities[identity].original_indices.append(index)
            continue
        # Preserve unresolved labels without ever assigning them a known URL.
        while next_index in missing:
            next_index += 1
        artifacts = source_artifacts(source)
        artifact = next((item for item in artifacts if item is not None), None)
        provenance = classify_source(source)
        published = PublishedSource(
            index=next_index, original_indices=[index], paper_id=identity,
            artifact_id=artifact.artifact_id if artifact else "",
            title=str(source.get("title") or source.get("name") or ""),
            url=safe_url(source.get("link") or source.get("url") or
                         (artifact.source_url if artifact else "")),
            source_kind=str(provenance.get("source_kind") or "unknown"),
            document_type=str(provenance.get("document_type") or "unknown"),
            status=str(provenance.get("publication_status") or "unverified"),
            status_reason=str(provenance.get("publication_status_reason") or ""),
            identity_status=str(provenance.get("identity_status") or "missing"),
            identity_provenance=provenance.get("identity_provenance") or {},
            publication_state=str(provenance.get("publication_state") or "unknown"),
            peer_review_status=str(provenance.get("peer_review_status") or "unknown"),
            relevance_status=str(provenance.get("relevance_status") or "unknown"),
            evidence_scope=str(provenance.get("evidence_scope") or "unknown"),
            temporal_validity=str(provenance.get("temporal_validity") or "unknown"),
            contradiction_status=str(provenance.get("contradiction_status") or "unknown"),
        )
        selected.append(published)
        identities[identity] = published
        next_index += 1
    checks, audit_status = [], "disabled"
    try:
        cfg = cfg or get_config()
        if cfg.module_enabled("citation_qc"):
            qc = CitationQc(model, cfg)
            claims = [c for c in qc.extract_claims(draft) if c.citations]
            if not claims:
                audit_status = "no_cited_claims"
            elif model is None:
                audit_status = "unavailable"
            else:
                checks = qc.check(claims, collector)
                audit_status = "completed"
                if any(c.reason_code == "judge_unverifiable" and
                       c.model_reason == "semantic_schema_or_judge_error"
                       for row in checks for c in row.citation_checks):
                    audit_status = "unavailable"
    except Exception:
        audit_status = "unavailable"
        warnings.append("citation_audit_error")
    content = (render_report_current(draft, selected, expand_ranges=_schema_version == "2.3")
               if modern else render_report(draft, selected))
    grounding = build_evidence_grounding(draft, list(collector.sources.values()), checks=checks,
                                         research_spec=research_spec,
                                         writer_context=writer_context,
                                         pending_findings=pending_findings,
                                         proposed_changes=proposed_changes,
                                         review={
                                             "status": "completed" if audit_status == "completed" else "not_run",
                                             "failure_reasons": [] if audit_status == "completed" else [audit_status],
                                             "reviewed_claim_ids": [], "skipped_claim_ids": [],
                                         })
    return Publication(schema_version=_schema_version, status="unverified", content=content, content_sha256=digest(content),
                       report_body=draft, sources=selected, citation_audit=checks,
                       audit_status=audit_status, warnings=warnings,
                       reason_code="report_preserved",
                       evidence_grounding=grounding)


def render_content(body: str, sources: list[PublishedSource], revision: RevisionResult) -> str:
    if not body:
        return NOTICE + ("\n\n" + revision.pending_section if revision.pending_section else "")
    urls={s.index:s.url for s in sources}
    def hyperlink(match):
        return ", ".join("["+n+"]("+urls[int(n)]+")" if urls[int(n)] else "["+n+"]"
                         for n in re.split(r"\s*,\s*",match.group(1)))
    content=CITE_RE.sub(hyperlink,body)
    if revision.pending_section:
        content+="\n\n"+revision.pending_section
    return content+"\n\n"+CitationQc.render_section(revision.final_checks)


def publication_for_report(content: str, metadata: dict | None, sources: list[dict], model=None) -> Publication:
    # Detailed generator may already have published this exact final text.
    if isinstance(metadata, dict) and KEY in metadata:
        try:
            return validate_publication(content, metadata)
        except Exception:
            pass  # Stale advisory metadata must not suppress newly generated text.
    return publish_report(content, sources, model)


def presentation_for_publication(publication: Publication) -> Publication:
    """Upgrade old advisory reports for display/export without editing stored data."""
    if publication.schema_version != "2.0":
        return publication
    sources = [dict(index=old, paper_id=source.paper_id, title=source.title, url=source.url,
                    doi=source.paper_id[4:] if source.paper_id.startswith("doi:") else None,
                    pmid=source.paper_id[5:] if source.paper_id.startswith("pmid:") else None)
               for source in publication.sources for old in source.original_indices]
    return _publish_report(publication.report_body, sources, cfg=VerifyConfig(enable_verify=False), _schema_version="2.1")


def validate_publication(content: str, metadata: dict | None) -> Publication:
    """Validate serialization integrity; advisory verdicts never authorize report content."""
    publication=Publication.model_validate((metadata or {}).get(KEY))
    if publication.evidence_grounding is not None:
        EvidenceGroundingV1.model_validate(publication.evidence_grounding)
    if content!=publication.content or digest(content)!=publication.content_sha256:
        raise ValueError("publication_content_mismatch")
    if publication.schema_version in {"2.0", "2.1", "2.2", "2.3"}:
        if publication.status != "unverified" or publication.revision is not None or publication.verified_body:
            raise ValueError("advisory_publication_state_mismatch")
        indices = [source.index for source in publication.sources]
        if len(indices) != len(set(indices)):
            raise ValueError("duplicate_source_index")
        cited = {int(n) for m in CITE_RE.finditer(publication.report_body)
                 for n in re.split(r"\s*,\s*", m.group(1))}
        modern = publication.schema_version in {"2.2", "2.3"}
        expand_ranges = publication.schema_version == "2.3"
        if modern or publication.schema_version == "2.1":
            cited = set(cited_indices(publication.report_body, expand_ranges=expand_ranges)
                        if modern else legacy_cited_indices(publication.report_body))
            originals = [old for source in publication.sources for old in source.original_indices]
            if len(originals) != len(set(originals)) or not set(originals) <= cited:
                raise ValueError("uncited_source_mapping")
        elif not set(indices) <= cited:
            raise ValueError("uncited_source_mapping")
        if any(source.url != safe_url(source.url) for source in publication.sources):
            raise ValueError("publication_url_invalid")
        if modern:
            rendered = render_report_current(publication.report_body, publication.sources, expand_ranges=expand_ranges)
        else:
            renderer = render_report if publication.schema_version == "2.1" else _render_report_v2
            rendered = renderer(publication.report_body, publication.sources)
        if content != rendered:
            raise ValueError("publication_render_mismatch")
        return publication
    # Read-only compatibility validation for reports written before rule removal.
    revision=publication.revision
    if revision is None:
        raise ValueError("legacy_revision_missing")
    try:
        rendered = render_content(publication.verified_body, publication.sources, revision)
    except (KeyError, TypeError) as exc:
        raise ValueError("publication_render_mapping_invalid") from exc
    if content != rendered:
        raise ValueError("publication_render_mismatch")
    if any(s.url != safe_url(s.url) for s in publication.sources):
        raise ValueError("publication_url_invalid")
    if publication.status!=revision.status or publication.verified_body!=revision.verified_body:
        raise ValueError("publication_state_mismatch")
    if revision.body_sha256!=digest(publication.verified_body):
        raise ValueError("publication_body_mismatch")
    sources={s.index:s for s in publication.sources}
    if len(sources)!=len(publication.sources) or list(sources)!=list(range(1,len(sources)+1)):
        raise ValueError("publication_index_mismatch")
    if publication.status=="withheld":
        if publication.verified_body or sources or revision.final_checks:
            raise ValueError("withheld_contains_facts")
    else:
        claims=extract_report_claims(publication.verified_body)
        if not claims or len(claims)!=len(revision.final_checks):
            raise ValueError("publication_claim_mismatch")
        for claim,check in zip(claims,revision.final_checks):
            if claim.text!=check.claim or check.verdict!="supported" or claim.citations!=check.citations:
                raise ValueError("publication_claim_mismatch")
            if {c.citation_index for c in check.citation_checks}!=set(claim.citations):
                raise ValueError("publication_evidence_missing")
            for item in check.citation_checks:
                source=sources.get(item.citation_index)
                if (not source or source.paper_id!=item.paper_id or source.artifact_id!=item.artifact_id
                        or item.verdict!="supported" or not item.evidence or not item.evidence.quote_verified
                        or not item.evidence.locator
                        or item.evidence.locator.paper_id!=source.paper_id
                        or item.evidence.locator.artifact_id!=source.artifact_id):
                    raise ValueError("publication_evidence_mismatch")
    return publication
