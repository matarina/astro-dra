"""Experimental exact source windows for bounded NLI; no semantic aggregation.

The complete hypothesis is retained in every pair. Window coverage proves only
text exposure, not that a model reasons across windows or checks every relation.
"""
import hashlib


def source_windows(text, hypothesis, prefix, count_tokens, *, max_tokens=512,
                   overlap_chars=160, max_windows=128):
    if not all(isinstance(v, str) for v in (text, hypothesis, prefix)):
        raise TypeError('Text, hypothesis and prefix must be strings')
    if max_tokens < 4 or overlap_chars < 0 or max_windows < 1:
        raise ValueError('Invalid window budget')
    base = dict(source_chars=len(text), source_sha256=hashlib.sha256(text.encode()).hexdigest(),
                hypothesis_sha256=hashlib.sha256(hypothesis.encode()).hexdigest(),
                complete_hypothesis=hypothesis, prefix=prefix, windows=[],
                text_coverage_complete=False, semantic_verdict=None)
    if not text:
        return dict(base, status='empty_source')
    if count_tokens(prefix, hypothesis) >= max_tokens:
        return dict(base, status='complete_hypothesis_and_prefix_exceed_budget')
    start = 0
    while start < len(text):
        if len(base['windows']) == max_windows:
            return dict(base, status='window_budget_exhausted', first_uncovered_char=base['windows'][-1]['end'])
        low, high = start + 1, len(text)
        best = None
        # Token counts need not be monotonic in character length. Binary search
        # finds a fitting slice; exact final validation, rather than optimality,
        # is the contract. Every iteration must advance and eventually cover.
        while low <= high:
            end = (low + high) // 2
            n = count_tokens(prefix + text[start:end], hypothesis)
            if n <= max_tokens:
                best = (end, n)
                low = end + 1
            else:
                high = end - 1
        if best is None:
            return dict(base, status='no_source_character_fits', first_uncovered_char=start)
        end, n = best
        premise = prefix + text[start:end]
        assert count_tokens(premise, hypothesis) == n <= max_tokens
        base['windows'].append(dict(start=start, end=end, text=text[start:end],
                                    premise=premise, tokens=n))
        if end == len(text):
            return dict(base, status='covered', text_coverage_complete=True)
        start = max(start + 1, end - overlap_chars)
    raise AssertionError('Unreachable window state')
