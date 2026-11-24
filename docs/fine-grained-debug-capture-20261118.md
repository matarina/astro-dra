# Fine-grained debug capture

`research_verify.debug_capture.capture_chat_completion` is an opt-in client
boundary for controlled model diagnostics. A caller supplies `capture_dir` to
write the complete request payload, raw response bytes, parsed response JSON,
and a receipt containing hashes, status, timing, usage, finish reason, visible
output, and provider model metadata. Returned fields named `reasoning_content`,
`thinking`, `reasoning`, `analysis`, or `thoughts` are indexed in the receipt.

The capture is not enabled by default and is not a production publication
gate. It cannot recover hidden chain-of-thought that an endpoint does not return.
The debug directory is created with mode 0700 and its files with mode 0600.
Callers must keep captured prompts, source packets, and responses in a private
run directory and outside Git.

## Research requests on 5006

The `openai_endpoint` Chat Completions adapter records reasoning text returned by the provider before LangChain normalizes the response. Enable this for research jobs with `LDR_APP_DEBUG=true` or the effective `app.debug` setting. `LDR_REASONING_CAPTURE=false` explicitly disables it, and `true` explicitly enables it. Web workers use the current research ID. The isolated runner establishes the same job scope before constructing the model. A call outside a research context produces no research receipt.

Each model call writes a gzip JSON file to `$LDR_DATA_DIR/research_traces/<research-id>/model-reasoning/<call-id>.json.gz`. An explicit `LDR_RESEARCH_TRACE_DIR` replaces the trace root. On 5006 the default root is `/data/research_traces` in the persistent app volume. In a synthesis trace, the `provider_reasoning_call` event gives the stage and the relative receipt path. Calls outside a named synthesis stage use the stage `research`.

Read `choices[].reasoning_fields` for the text. Normal replies, tool-bound calls and streaming replies use the same format. Stream deltas are joined separately for each choice and provider field. `status` records completion, interruption or error. Inspect the choice's `finish_reason`, `unterminated_inline`, `reasoning_present` and `observation_errors` when diagnosing incomplete output. The recorder saves the returned text at full length, with credential redaction. A provider may return no reasoning text. The logs can only contain text the API supplied while capture was active.

The reason files are private (mode 0600 inside job directories restricted to the owner). They are stored separately from the published report. For diagnostics requiring request payloads and raw HTTP responses, the explicit capture helper above remains available.
