# Base digest captured from the existing deployment; no implicit upstream upgrade.
ARG LDR_BASE_IMAGE=localdeepresearch/local-deep-research@sha256:ce95481a35d3eebc2c1ae7bd34fad426108c3fb8d1a22f66c9e772276869c2f0
FROM ${LDR_BASE_IMAGE}
USER root
# Discover site-packages through the application interpreter, not a Python minor version.
RUN /usr/local/bin/pip3 install --no-cache-dir --no-input \
      --target="$(/install/.venv/bin/python -c 'import sysconfig; print(sysconfig.get_path("purelib"))')" \
      "ddgs==9.16.0"
# Keep dependency installation cached across verifier-only edits.
COPY local_deep_research/ /tmp/astro-dra/overlays/
COPY deployment/install_overlays.py deployment/overlay-manifest.json deployment/install_accounts.py /tmp/astro-dra/
RUN /install/.venv/bin/python /tmp/astro-dra/install_overlays.py \
      --source /tmp/astro-dra/overlays --manifest /tmp/astro-dra/overlay-manifest.json \
    && /install/.venv/bin/python /tmp/astro-dra/install_accounts.py --source /tmp/astro-dra/overlays \
    && /install/.venv/bin/python -c "import ddgs, research_verify; from research_verify.doi_validator import DoiValidator; from research_verify.constraint_matcher import ConstraintMatcher; from research_verify.citation_qc import CitationQc; from research_verify.publication import Publication" \
    && rm -rf /tmp/astro-dra
# Inherit entrypoint, command, healthcheck and its switch to ldruser.
