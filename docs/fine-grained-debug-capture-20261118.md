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
