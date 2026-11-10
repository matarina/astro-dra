# Astro DRA

![Astro DRA banner](assets/banner.png)

Astro DRA is a research assistant built on [Local Deep Research](https://github.com/LearningCircuit/local-deep-research). It combines literature search, evidence collection, source-aware writing, and report publication in a Docker deployment. Models can be connected through an OpenAI-compatible endpoint.

The current source pool is **PubMed, SearXNG, and Europe PMC**. The system preserves source identity, abstracts, selected full-text context, and private research traces so that generated reports can be inspected later.

## Repository layout

| Path | Purpose |
| --- | --- |
| `compose.yaml`, `deployment/` | Main deployment entry point, pinned base image, patch manifest, and SearXNG configuration |
| `local_deep_research/` | Patches installed into the image, the `research_verify` modules, and their tests |
| `local-deep-research/` | Vendored upstream source snapshot and its local development material |
| `ldr-monitor/` | Deployment diagnostics and historical operational notes; check machine paths before use |
| `docs/` | Source layout, deployment notes, current research flow, and development records |

API keys and other secrets are supplied through environment variables. Do not commit `.env`, deployment overlays, logs, or user data.

## Evidence workflow

The application collects stable source identities and evidence from the configured source pool, supplies abstracts and bounded full-text context to the writer, and records source ranges and private traces. Native fact-consistency checking is enabled for generated reports. The separate save-before-publication citation audit is currently disabled, and reports retain unresolved or unverified states when evidence is incomplete.

Source material and trace preservation improve inspectability; they do not guarantee that a model will interpret every study correctly. Full-text availability, search coverage, selection criteria, cross-topic accuracy, and semantic review remain limited. See the [current research flow](docs/current-research-flow-20261016.md), [source layout](docs/source-layout.md), and [research verification module](local_deep_research/research_verify/README.md) for implementation boundaries.

## Deployment

Requirements: Docker Engine and the Docker Compose plugin.

Run these commands from the repository root:

```bash
cp .env.example .env
# Edit .env with the model endpoint, model name, credentials, and a random SEARXNG_SECRET.
python -c 'import secrets; print(secrets.token_hex(32))'
docker compose config --quiet
docker compose build
docker compose up -d
docker compose ps
```

Open <http://localhost:5000> and create the initial account. The default configuration listens only on the host loopback address. Remote access and migration details are documented in [Deployment](docs/deployment.md).

The root deployment starts from a pinned upstream runtime image and installs this repository's patches. Changes under `local-deep-research/` are not automatically installed into that image; the patch mapping and development boundary are described in [Source layout](docs/source-layout.md).

Useful commands:

```bash
docker compose logs --tail=100 local-deep-research
docker compose stop
```

Application data is stored in the `astro-dra_ldr_data` and `astro-dra_ldr_config` named volumes. User questions are also written as plain JSONL to `/data/logs/user_questions.log`; `LDR_ENABLE_FILE_LOGGING` does not control that separate question log.

## Testing

The project targets Python 3.12–3.14. From the repository root:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements-test.txt
PYTHONPATH=local_deep_research .venv/bin/python -m pytest -q local_deep_research/tests
```

These tests cover module behavior. They do not replace networked source checks, a complete research run, or semantic quality evaluation. Upstream tests use their own dependency environment; see [Source layout](docs/source-layout.md).

The upstream project is [LearningCircuit/local-deep-research](https://github.com/LearningCircuit/local-deep-research), licensed under MIT; see [LICENSE](local-deep-research/LICENSE).
