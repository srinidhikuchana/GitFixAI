# GitHub-Issue-Solver

An AI-powered tool that fetches open GitHub issues and suggests solutions using OpenRouter LLMs.

## Features
- Fetch open issues from any public GitHub repo
- Filter by label (bug, good first issue, help wanted)
- AI-generated fix plans with root cause, steps, code hints & files to edit
- Download solution as .txt

## Setup

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Get API Key
Free at https://openrouter.ai/

## Tech Stack
- Python + Streamlit (UI)
- GitHub REST API (issues)
- OpenRouter API (LLM inference)
