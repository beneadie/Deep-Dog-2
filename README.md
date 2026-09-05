# Deep Dog 2 — Deep Research Agent

A multi-agent deep research system built with [LangGraph](https://github.com/langchain-ai/langgraph) and [LangChain](https://github.com/langchain-ai/langchain). A supervisor agent decomposes a research question into sub-tasks and delegates to specialized platform sub-agents (Web, Reddit, Substack) that search, read, and synthesize sources into a cited final report.

This project builds on Deep Dog 1, which was built upon [ThinkDepth Deep Research](https://github.com/thinkdepthai/Deep_Research) by Paichun Lin. See [LICENSE](LICENSE) for the applicable attribution and license notices.

Pipeline: `clarify_with_user` → `write_research_brief` → `write_draft_report` → `supervisor_subgraph` (parallel sub-agents) → `final_report_generation` — see `deep_research/research_agent_full.py:235` and `deep_research/research_agent_scope.py`.

## Features

- **Supervisor + sub-agent architecture** — configurable platform agents at `deep_research/config.py:449` (`ResearchWeb`, `ResearchReddit`, `ResearchSubstack`; `ResearchGeneral`, `ResearchPubMed`, `ResearchArxiv`, `ResearchSEC` available but disabled by default)
- **Multiple search providers** — Tavily and/or Exa (`WEB_SEARCH_ENGINE` at `deep_research/config.py:658`)
- **Provider-agnostic models** — DeepSeek, MiMo, Meta Muse, Gemini, OpenAI, GLM, and OpenRouter-hosted models via a single `get_model()` factory (`deep_research/config.py:883`)
- **Model fallback chains** — per-role fallback lists (`SUBAGENT_MODEL_FALLBACK_CHAIN`, `SUPERVISOR_MODEL_FALLBACK_CHAIN`, `DRAFT_REPORT_MODEL_FALLBACK_CHAIN`)
- **Cited reports** — markdown report + `research_data_*.json` sources file + optional research trace
- **LangGraph execution** — recursion limit, timeouts, and observability logging

## Requirements

- **Python** 3.10+ (tested with 3.14.4)
- **Package manager:** `pip` or [`uv`](https://docs.astral.sh/uv/)
- **API keys:** at least one LLM provider + one search provider (see Environment)

## Installation

### 1. Clone

```bash
git clone https://github.com/anomalyco/Deep-Dog-2.git
cd "Deep Dog 2"
```

### 2. Install dependencies

**With uv (recommended):**

```bash
uv sync
# or directly:
uv pip install -r requirements.txt
```

**With pip + venv:**

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

> **Note on `requirements.txt` encoding:** the file is stored as UTF-16 LE with BOM. If `pip install -r requirements.txt` fails with a decoding error, convert first:
>
> ```bash
> iconv -f UTF-16 -t UTF-8 requirements.txt | pip install -r /dev/stdin
> ```

## Environment Setup

Create a `.env` file in the project root (next to `run_research.py`). `run_research.py:75` loads it via `python-dotenv`.

```bash
cp .env.example .env  # if you create one, otherwise create .env manually
```

### Required variables

| Variable | Description |
|---|---|
| `DEEPSEEK_API_KEY` or `DEEPSEEK_KEY` | DeepSeek native API (`api.deepseek.com`) |
| `OPENROUTER_API_KEY` | OpenRouter — required if any model routes via OpenRouter (e.g. `nvidia/nemotron-3.5-lightning`, `deepseek-baba-singapore`) |
| `TAVILY_API_KEY` | Tavily search — required if `WEB_SEARCH_ENGINE=tavily` or `both` |
| `EXA_API_KEY` | Exa search — required if `WEB_SEARCH_ENGINE=exa` (default) or `both` |

You only need keys for the providers you actually use. The model factories at `deep_research/config.py:682` skip chain entries whose key is missing and fall back to the next model.

### Optional / commonly used

| Variable | Description |
|---|---|
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Google Gemini |
| `OPENAI_API_KEY` | OpenAI |
| `MIMO_API_KEY` | MiMo native API |
| `META_API_KEY` | Meta Muse native API |
| `ZHIPUAI_API_KEY` | Z.AI GLM |
| `PUBMED_EMAIL` | PubMed E-utilities contact |
| `SEC_EDGAR_CONTACT_EMAIL` | SEC EDGAR contact |
| `PERPLEXITY_KEY` | Substack/Perplexity search |

### Example `.env`

```ini
# LLM
DEEPSEEK_API_KEY=sk-...
OPENROUTER_API_KEY=sk-or-...

# Search (at least one)
EXA_API_KEY=...
TAVILY_API_KEY=...

# Optional overrides
# SUPERVISOR_MODEL=deepseek-v4-pro
# SUBAGENT_MODEL=nvidia/nemotron-3.5-lightning
# WEB_SEARCH_ENGINE=exa
```

## Usage

All commands assume you are in the project root (where `run_research.py` lives).

### Quick start

```bash
# with uv
uv run python run_research.py --prompt "What are the latest developments in AI safety?"

# without uv (venv activated)
python run_research.py --prompt "What are the latest developments in AI safety?"
```

### From a prompt file

```bash
uv run python run_research.py --prompt-file input.txt
uv run python run_research.py --prompt-file input.txt --output-dir my_outputs
```

### CLI reference

```
python run_research.py --help
```

| Flag | Description | Default |
|---|---|---|
| `--prompt`, `-p` | Research question as a string (mutually exclusive with `--prompt-file`) | — |
| `--prompt-file`, `-f` | Path to a file containing the research prompt | — |
| `--output-dir`, `-o` | Directory for output files | `outputs` |
| `--thread-id`, `-t` | Thread ID for the session | auto-generated `YYYY-MM-DD_HH-MM-SS_xxx` |

Defined at `run_research.py:615`.

### Programmatic API

```python
import asyncio
from pathlib import Path
from run_research import run_research

result = asyncio.run(run_research(
    prompt="What are the latest developments in quantum error correction?",
    output_dir=Path("outputs"),
))

print(result["output_file"])   # Path to research_*.md
print(result["final_report"])  # str
print(result["sources"])       # list[dict]
print(result["trace_content"]) # str | None
```

Return dict documented at `run_research.py:167`.

### Standalone platform runner

Run a single platform sub-agent without the supervisor — useful for testing/benchmarking. See `deep_research/run_platform.py:1`.

```bash
python -m deep_research.run_platform --agent reddit --topic "NVIDIA earnings Q4" --output-mode report
python -m deep_research.run_platform --agent pubmed --topic "GLP-1 efficacy" --output-mode sources

# Options
# --agent: reddit | web | substack | pubmed | arxiv | sec | general
# --output-mode: sources | report | sources_inline | report_inline
# --provider / -m: model iterations, reads, saves, etc.
```

## Output

Each run creates timestamped files in `--output-dir` (default `outputs/`, gitignored at `.gitignore:14`):

```
outputs/
  research_2026-09-01_10-30-00_abc.md      # final report (markdown)
  research_data_2026-09-01_10-30-00_abc.json  # structured sources + metadata
  trace_2026-09-01_10-30-00_abc.md         # supervisor ↔ sub-agent trace (if ENABLE_RESEARCH_TRACE)
  error_2026-09-01_10-30-00_abc.txt        # error dump on failure
```

Report structure (`run_research.py:333`): header → Research Prompt → Research Brief → Final Report (with `## Sources` citations). Sources JSON contains `thread_id`, `timestamp`, `prompt`, `sources`, `final_report`.

## Configuration

All tuning lives in `deep_research/config.py:1`. Most values can be overridden via environment variables.

### Model selection

| Variable | Default | Description |
|---|---|---|
| `SUPERVISOR_MODEL` | `deepseek-v4-pro` | Supervisor + final report writer |
| `SUPERVISOR_MODEL_FALLBACK_CHAIN` | `SUPERVISOR_MODEL,deepseek-v4-pro` | Comma-separated fallback list |
| `SUBAGENT_MODEL` | `nvidia/nemotron-3.5-lightning` | Platform sub-agents + research brief |
| `SUBAGENT_MODEL_FALLBACK_CHAIN` | `SUBAGENT_MODEL,deepseek-v4-flash` | Comma-separated fallback list |
| `DRAFT_REPORT_MODEL` | `nvidia/nemotron-3.5-lightning` | Initial cold draft pass |
| `DRAFT_REPORT_MODEL_FALLBACK_CHAIN` | `DRAFT_REPORT_MODEL,deepseek-v4-flash,deepseek-v4-pro` | Fallback for draft |

See `config.py:20-64` for the full model catalog (DeepSeek, MiMo, Muse Spark, Gemini, GPT, Nemotron, GLM, OpenRouter slugs).

### Routing

| Variable | Default | Description |
|---|---|---|
| `ROUTE_VIA_OPENROUTER` | `false` | Global default: route DeepSeek/MiMo/Meta via OpenRouter |
| `SUBAGENT_ROUTE_VIA_OPENROUTER` | inherit | Override for sub-agents + brief |
| `SUPERVISOR_ROUTE_VIA_OPENROUTER` | inherit | Override for supervisor + refine + final write (cache-tied) |
| `DRAFT_ROUTE_VIA_OPENROUTER` | inherit | Override for draft report (cold pass) |
| `DRAFT_REPORT_REASONING_EFFORT` | `""` | `low`/`medium`/`high` — only honored via OpenRouter |

### Research depth & timing

| Variable | Default | Description |
|---|---|---|
| `RESEARCH_TIME_MIN_MINUTES` | `5` | Minimum before `ResearchComplete` allowed |
| `RESEARCH_TIME_MAX_MINUTES` | `15` | Target max research time |
| `SUPERVISOR_MAX_ITERATIONS` | `30` | Supervisor loop cap |
| `SUBAGENT_MAX_ITERATIONS` | `5` | Tool-call rounds per sub-agent |
| `SUBAGENT_MAX_READS` / `MAX_SAVES` / `MAX_SEARCHES` / `MAX_CONCURRENCY` | `10/10/3/3` | Per-iteration caps |
| `DEFAULT_MAX_TOTAL_READS` | `25` | Total read budget per sub-agent |
| `SUBAGENT_TIMEOUT_SECONDS` | `600` | Per-sub-agent wall clock |

### Agent & prompt control

| Variable | Default | Description |
|---|---|---|
| `ENABLED_AGENTS` | `ResearchWeb, ResearchReddit, ResearchSubstack` | Which sub-agents supervisor may call (`config.py:449`) |
| `GENERAL_AGENT_PLATFORMS` | `[]` (all) | Platforms the general agent may use |
| `PROMPT_VERSION` | `OPEN` | `OPEN` / `LEGACY` |
| `SUBAGENT_OUTPUT_MODE` | `sources` | `sources` / `report` / `sources_inline` / `report_inline` |
| `DISCOVERY_OUTPUT_MODE` | `report_inline` | Output mode for discovery sub-agents |

### Other

| Variable | Default | Description |
|---|---|---|
| `OUTPUT_MODE` | `file` | `file` / `db` / `both` |
| `SAVE_REPORT_TO_FILE` | `true` | Write reports to disk |
| `SAVE_SUBAGENT_REPORTS_TO_FILE` | `false` | Also write each sub-agent `.md` |
| `ENABLE_SOURCE_LOG` | `true` | Log sources to JSONL/JSON |
| `WEB_SEARCH_ENGINE` | `exa` | `tavily` / `exa` / `both` |

## Project Structure

```
Deep Dog 2/
├── run_research.py              # Main entry point (CLI + programmatic API)
├── requirements.txt             # Pinned dependencies (UTF-16 LE)
├── deep_research/
│   ├── config.py                # All configuration & model factory (get_model)
│   ├── research_agent_full.py   # Full LangGraph workflow (deep_researcher_builder)
│   ├── research_agent_scope.py  # Scoping: clarify → brief → draft
│   ├── multi_agent_supervisor.py# Supervisor agent & delegation logic
│   ├── run_platform.py          # Standalone single-platform runner
│   ├── agents/                  # Platform agents (web, reddit, substack, ...)
│   ├── prompts*.py              # Prompt bundles (open, legacy)
│   ├── state_*.py               # Graph state schemas
│   ├── observability.py         # Run folder & source aggregation
│   ├── utils.py                 # Helpers (extract_text, date, etc.)
│   └── citation_utils.py        # Citation formatting
└── outputs/                     # Generated reports (gitignored)
```

## Troubleshooting

- **`ValueError: OPENROUTER_API_KEY not found`** — the active model chain requires that key. Set it in `.env` or switch the chain to a provider you have a key for (e.g. `SUBAGENT_MODEL=deepseek-v4-flash` with `DEEPSEEK_API_KEY`).
- **`pip install -r requirements.txt` fails** — file is UTF-16 LE; use the `iconv` workaround above or re-save as UTF-8.
- **`ModuleNotFoundError: deep_research`** — run from the project root, not from inside `deep_research/`. `run_research.py:61` expects to be at the root.
- **Research hangs** — check `SUBAGENT_TIMEOUT_SECONDS` (600s) and `SUPERVISOR_TIMEOUT_SECONDS` (420s) at `config.py:311`; a stalled provider will be bounded. Inspect `outputs/error_*.txt`.
- **Chinese content filter rejections** — if using native DeepSeek/MiMo with sensitive topics, set `CHINESE_MODERATION=true` (`config.py:523`).

## License

MIT — see [LICENSE](LICENSE).
