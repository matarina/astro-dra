"""One user-grounded task contract shared by research stages."""

from contextlib import contextmanager
from contextvars import ContextVar
import json

ACTIVE_PLAN = ContextVar("dra_task_plan", default=None)


TASK_REQUIREMENTS_GUIDANCE = """Include task_requirements in the first search call
when the user specifies inclusion criteria, deliverable instructions, or extraction
questions. Omit it for an open question. Preserve independent requirements even when they
share the same user quote. Later calls can add grounded requirements omitted
from the first call. Use only keys applicable to this request.
Copy each user_quote as one contiguous excerpt from the user message.
- eligibility: [{criterion, user_quote}] for verifiable inclusion criteria,
  such as study design. Keep dates in their dedicated fields; handle journal
  impact factors with the search_journal tool when requested.
- questions: [{question, user_quote}] for facts or fields to extract.
- requirements: [{requirement, user_quote, status}] for deliverable instructions
  such as the number of papers, representative examples, or report format.
  Use status explicit or ambiguous.
- publication_years: {start, end, user_quote} for the search range.
- report_publication_years: same fields if report dates differ from search dates.
Use the search tool's own concepts argument for synonyms. Keep report fields
out of the database query unless useful search terms."""


def validate_task_plan(query, value):
    """Keep structured tool arguments backed by the user's wording."""
    result = {}
    for key, field in (("requirements", "requirement"), ("questions", "question"),
                       ("eligibility", "criterion")):
        records = value.get(key)
        if isinstance(records, list):
            grounded = [entry for item in records if (entry := _grounded(item, query))
                        and isinstance(entry.get(field), str) and entry[field].strip()]
            if grounded:
                result[key] = grounded
    for key in ("publication_years", "report_publication_years"):
        if years := _grounded(value.get(key), query):
            start, end = years.get("start"), years.get("end")
            if type(start) is int and type(end) is int and 1000 <= start <= end <= 9999:
                result[key] = years
    native = value.get("native_search")
    if isinstance(native, dict) and native.get("engine") in {"pubmed", "europepmc"}:
        if isinstance(native.get("query"), str) and native["query"].strip() and native["query"] in query:
            result["native_search"] = native
    if any(concepts := clean_concepts(value.get("concepts"))):
        result["concepts"] = concepts
    return result


def _grounded(item, query):
    if not isinstance(item, dict):
        return None
    quote = item.get("user_quote")
    if not isinstance(quote, str) or not quote.strip():
        return None
    if quote in query:
        return item
    # Models sometimes omit PDF copy/paste spaces. Recover the literal span
    # from the input instead of losing the requirement along with those spaces.
    positions = [i for i, char in enumerate(query) if not char.isspace()]
    compact = "".join(query[i] for i in positions)
    needle = "".join(char for char in quote if not char.isspace())
    start = compact.find(needle)
    if start < 0 or compact.find(needle, start + 1) != -1:
        return None
    return {**item, "user_quote": query[positions[start]:positions[start + len(needle) - 1] + 1]}


def clean_concepts(groups):
    if not isinstance(groups, list):
        return []
    return [[term.strip() for term in group[:8] if isinstance(term, str)
             and 0 < len(term.strip()) <= 160] for group in groups[:8] if isinstance(group, list)]


def describe_plan(plan):
    return "User-grounded task requirements:\n" + json.dumps(plan, ensure_ascii=False) if plan else ""


class DatabaseSearch(str):
    """A compiled query explicitly associated with its target syntax."""

    def __new__(cls, value, engine):
        self = super().__new__(cls, value)
        self.engine = engine
        return self


def compile_search(engine, query, concepts, plan, native_query=False):
    if engine not in {"pubmed", "europepmc"}:
        return query
    native = (plan or {}).get("native_search")
    if native and native["engine"] == engine and (not query or query == native["query"]):
        return DatabaseSearch(native["query"], engine)
    if native_query:
        return DatabaseSearch(query, engine)
    groups = clean_concepts(concepts) or (list((plan or {}).get("concepts", [])) if not query else [])
    if not any(groups):
        years = (plan or {}).get("publication_years")
        if engine == "europepmc" and years and query:
            start, end = years["start"], years["end"]
            return DatabaseSearch(f"({query}) AND FIRST_PDATE:[{start}-01-01 TO {end}-12-31]", engine)
        return query
    tag = "[Title/Abstract]" if engine == "pubmed" else ""
    clauses = []
    for group in groups:
        terms = ['"' + term.replace('"', " ").strip() + '"' + tag
                 for term in group if term.replace('"', " ").strip()]
        if terms:
            clauses.append("(" + " OR ".join(terms) + ")")
    years = (plan or {}).get("publication_years")
    if years:
        start, end = years["start"], years["end"]
        clauses.append(f"{start}[dp]:{end}[dp]" if engine == "pubmed"
                       else f"FIRST_PDATE:[{start}-01-01 TO {end}-12-31]")
    return DatabaseSearch(" AND ".join(clauses), engine) if clauses else query


@contextmanager
def search_scope(collector):
    token = ACTIVE_PLAN.set(collector)
    try:
        yield
    finally:
        ACTIVE_PLAN.reset(token)
