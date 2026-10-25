# GitHub-Issue-Solver

An AI-powered tool that fetches open GitHub issues and suggests solutions using OpenRouter LLMs.

<!-- TODO: add a screenshot or GIF of the app here -->

## Features

- Fetch up to 20 open issues from any public GitHub repository (pull requests are filtered out)
- Pick an issue and generate a fix plan with: root cause, fix plan, files likely to edit, example code hint, and testing steps
- Download the generated solution as a `.txt` file

## What it does not do

- It does not modify your code or open pull requests — it only produces a plan you can follow
- It does not filter issues by label (see [Limitations](#limitations))

## Requirements

- Python 3.9+ (tested on Python 3.13)
- Network access to `api.github.com` and `openrouter.ai`
- An OpenRouter API key — the free tier is enough to try it out

## Setup

**1. Install dependencies**

```bash
pip install -r requirements.txt
```

On Windows, or when several Python installations exist, run it through the same
interpreter you start the app with:

```bash
python -m pip install -r requirements.txt
```

**2. Create the Streamlit secrets file**

The app reads the key from Streamlit's secrets store, which only looks at
`.streamlit/secrets.toml` (inside the project) or `~/.streamlit/secrets.toml`.
A `secrets.toml` somewhere else — for example in the repository root — is silently
ignored.

```bash
mkdir .streamlit
```

Create `.streamlit/secrets.toml` with:

```toml
OPENROUTER_API_KEY = "sk-or-v1-..."
```

- Get a key at <https://openrouter.ai/keys> (register, then create a key).
- The variable name must be exactly `OPENROUTER_API_KEY` — that is what `app.py` reads.
- **Never commit this file.** `.streamlit/secrets.toml` and `secrets.toml` are covered by `.gitignore`.

**3. Run the app**

```bash
streamlit run app.py
```

Streamlit prints a local URL (usually <http://localhost:8501>) and opens it in your browser.

## Usage

1. Paste a repository URL, e.g. `https://github.com/streamlit/streamlit`
2. Click **Fetch Issues** — the 20 most recent open issues are loaded (PRs excluded)
3. Choose an issue from the dropdown
4. Click **Generate Solution** — the plan usually takes 10–30 seconds; free models can take longer
5. Click **Download Solution** to save it as `issue_<number>_solution.txt`

## Configuration

| Setting | Where | Default |
| --- | --- | --- |
| Model | `MODEL` in `app.py` | `openrouter/free` (OpenRouter routes it to an available free model) |
| Issues per fetch | `per_page` in `fetch_issues()` | `20` |
| GitHub timeout | `timeout` in `fetch_issues()` | `10` s |
| OpenRouter timeout | `timeout` in `solve_issue()` | `30` s |

## Limitations

- **GitHub rate limit**: requests are unauthenticated, so the GitHub API allows
  **60 requests per hour** per IP. After that, fetching returns an error until the limit resets.
- **First page only**: only the most recent 20 open issues are fetched; there is no pagination.
- **No label filtering** (e.g. `good first issue`, `bug`) and no GitHub token support yet.
- **Free models are rate-limited**: `openrouter/free` may queue requests and can exceed the
  30-second timeout, in which case you get an error instead of a solution.
- **Text only**: results are a plan and code hints — nothing is written to your repository.

## Troubleshooting

**`StreamlitSecretNotFoundError: No secrets found`**

Streamlit did not find `.streamlit/secrets.toml`. `st.secrets` raises instead of returning
an empty value when no secrets file exists at all, so the app stops on its first line.
Create the file as described in [Setup](#setup) step 2 and restart the app.

**`SSLError: certificate verify failed`**

A local proxy or GitHub accelerator is intercepting TLS. Tools such as Steam++/Watt Toolkit
rewrite the `hosts` file to point `github.com`/`api.github.com` at `127.0.0.1` and serve
their own certificate. Browsers trust that certificate, but Python (`requests` + `certifi`)
does not. Either stop the accelerator, or point `requests` at a CA bundle that includes its
certificate:

```powershell
# combine certifi's bundle with your proxy's CA, then:
$env:REQUESTS_CA_BUNDLE = "C:\path\to\ca-bundle-with-proxy-ca.pem"
streamlit run app.py
```

**`GitHub Error: API rate limit exceeded`**

Unauthenticated limit (60 requests/hour) reached. Wait for the reset or use another network.

**`Error 401: No auth credentials found`**

The key is missing, empty, or not the one you expect — check `.streamlit/secrets.toml`
and restart Streamlit (secrets are read at startup).

**`Error 429 ...` / request timed out**

The free model is rate-limited or slow. Retry, or set `MODEL` in `app.py` to another
model from <https://openrouter.ai/models>.

## Project structure

```
.
├── app.py                    # Streamlit UI + GitHub/OpenRouter calls
├── requirements.txt
├── README.md
└── .streamlit/
    └── secrets.toml          # local only, never committed
```

## Tech stack

- Python + Streamlit (UI)
- `requests` (HTTP)
- GitHub REST API (issues)
- OpenRouter chat completions API (LLM inference)

## Contributing

Issues and pull requests are welcome. Please keep API keys out of commits — `secrets.toml`
and `.streamlit/secrets.toml` are listed in `.gitignore`, and the app has no automated
test suite yet, so a short note on how you verified a change is appreciated.

## License

This repository does not include a license file yet. Until one is added, the code is
under the default "all rights reserved" terms.
