"""Correlate a provider response with the research stage that requested it."""

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps


_active_call = ContextVar("dra_model_call_stage", default=("research", None))


def current_model_call():
    stage, trace = _active_call.get()
    return stage, getattr(trace, "trace_id", None)


def current_model_trace():
    return _active_call.get()[1]


@contextmanager
def model_call_stage(stage, trace=None):
    token = _active_call.set((stage, trace if trace is not None else current_model_trace()))
    try:
        yield
    finally:
        _active_call.reset(token)


def traced_model_stage(default):
    def decorate(method):
        @wraps(method)
        def wrapped(self, prompt, *, trace=None, stage=default):
            with model_call_stage(stage, trace):
                return method(self, prompt, trace=trace, stage=stage)
        return wrapped
    return decorate
