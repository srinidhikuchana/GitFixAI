import streamlit as st
import requests
import re
import json
import base64
from datetime import datetime, timezone
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

st.set_page_config(page_title="GitHub Issue Solver", layout="wide")

OPEN_ROUTER_API_KEY = st.secrets.get("OPENROUTER_API_KEY", "")
MODEL = "openrouter/free"

for key, default in [
    ("issues", []),
    ("selected_index", 0),
    ("repo_info", None),
    ("repo_overview", ""),
    ("readme_text", ""),
    ("duplicate_matrix", {}),
    ("classifications", {}),
    ("health", {}),
    ("recommended", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ---------- GitHub data ----------

def fetch_issues(owner, repo):
    url = f"https://api.github.com/repos/{owner}/{repo}/issues"
    response = requests.get(
        url,
        params={"state": "open", "per_page": 50},
        headers={"Accept": "application/vnd.github+json"},
        timeout=10
    )
    if response.status_code != 200:
        st.error(f"GitHub Error: {response.json().get('message')}")
        return []
    return [issue for issue in response.json() if "pull_request" not in issue]


def fetch_repo_info(owner, repo):
    url = f"https://api.github.com/repos/{owner}/{repo}"
    response = requests.get(url, headers={"Accept": "application/vnd.github+json"}, timeout=10)
    return response.json() if response.status_code == 200 else None


def fetch_readme(owner, repo):
    url = f"https://api.github.com/repos/{owner}/{repo}/readme"
    response = requests.get(url, headers={"Accept": "application/vnd.github+json"}, timeout=10)
    if response.status_code != 200:
        return ""
    content = response.json().get("content", "")
    try:
        return base64.b64decode(content).decode("utf-8", errors="ignore")
    except Exception:
        return ""


# ---------- AI calls ----------

def call_ai(prompt):
    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPEN_ROUTER_API_KEY}", "Content-Type": "application/json"},
        json={"model": MODEL, "messages": [{"role": "user", "content": prompt}]},
        timeout=30
    )
    if response.status_code != 200:
        err = response.json().get("error", {})
        return f"Error {response.status_code}: {err.get('message', response.text)}"
    return response.json()["choices"][0]["message"]["content"]


def generate_repo_overview(repo_info, readme_text):
    description = repo_info.get("description") or "No description provided."
    language = repo_info.get("language") or "Not specified"
    readme_excerpt = readme_text[:3000] if readme_text else "No README found."

    prompt = f"""
You are analyzing a GitHub repository. Give a short, practical summary.

Repository: {repo_info.get('full_name')}
Description: {description}
Primary Language: {language}
Stars: {repo_info.get('stargazers_count', 0)}
Forks: {repo_info.get('forks_count', 0)}
Open Issues: {repo_info.get('open_issues_count', 0)}

README (partial):
{readme_excerpt}

Provide plain text, no markdown symbols beyond simple line breaks:
1. What this project does
2. Likely tech stack (be explicit this is inferred, not verified)
3. Who it is for
4. Anything a contributor should know before fixing issues
Keep it under 180 words.
"""
    return call_ai(prompt)


def classify_issues_batch(issues):
    """One AI call classifies every issue by type, priority, area. Returns dict keyed by issue number."""
    if not issues:
        return {}

    listing = "\n".join(
        f"#{i['number']}: {i['title']} :: {(i.get('body') or '')[:200]}"
        for i in issues
    )
    prompt = f"""
Classify each GitHub issue below. Respond with ONLY a JSON array, no prose, no markdown fences.
Each element: {{"number": <int>, "type": "bug|feature|docs|question|other", "priority": "high|medium|low", "area": "<short area name>"}}

Issues:
{listing}
"""
    raw = call_ai(prompt)
    cleaned = re.sub(r"```json|```", "", raw).strip()
    try:
        parsed = json.loads(cleaned)
        return {item["number"]: item for item in parsed if "number" in item}
    except Exception:
        return {}


# ---------- Local computation (no AI, real data) ----------

def compute_duplicate_matrix(issues, min_similarity=0.15, top_n=5):
    """Pairwise TF-IDF similarity across all fetched issues, computed once."""
    if len(issues) < 2:
        return {}

    documents = [f"{i['title']} {i.get('body') or ''}" for i in issues]
    vectorizer = TfidfVectorizer(stop_words="english")
    try:
        matrix = vectorizer.fit_transform(documents)
    except ValueError:
        return {}

    sim_matrix = cosine_similarity(matrix)
    result = {}
    for idx, issue in enumerate(issues):
        scores = [
            (issues[j], float(sim_matrix[idx][j]))
            for j in range(len(issues))
            if j != idx and sim_matrix[idx][j] >= min_similarity
        ]
        scores.sort(key=lambda x: x[1], reverse=True)
        result[issue["number"]] = scores[:top_n]
    return result


def days_old(created_at_str):
    created = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - created).days


def compute_repo_health(repo_info, readme_text, issues):
    """Heuristic scores from real signals only. Labeled as estimates — not a substitute for real linting/test coverage tools."""
    readme_len = len(readme_text)
    has_install = bool(re.search(r"install", readme_text, re.IGNORECASE))
    has_usage = bool(re.search(r"usage|getting started|example", readme_text, re.IGNORECASE))
    doc_score = min(100, readme_len / 30)
    doc_score += 10 if has_install else 0
    doc_score += 10 if has_usage else 0
    doc_score = min(100, doc_score)

    stale_count = sum(1 for i in issues if days_old(i["created_at"]) > 180)
    stale_ratio = stale_count / len(issues) if issues else 0
    issue_mgmt_score = max(0, 100 - stale_ratio * 100)

    overall = round((doc_score + issue_mgmt_score) / 2)

    return {
        "documentation": round(doc_score),
        "issue_management": round(issue_mgmt_score),
        "overall": overall,
        "stale_count": stale_count,
    }


def compute_recommended_next(issues, classifications, duplicate_matrix):
    priority_weight = {"high": 3, "medium": 2, "low": 1}
    best_issue, best_score, best_reasons = None, -1, []

    for issue in issues:
        number = issue["number"]
        classification = classifications.get(number, {})
        priority = classification.get("priority", "medium")
        age = days_old(issue["created_at"])
        dup_count = len(duplicate_matrix.get(number, []))

        score = priority_weight.get(priority, 2) * 10 + min(age, 180) / 10 + dup_count * 5

        if score > best_score:
            reasons = [f"AI priority: {priority}", f"open for {age} days"]
            if dup_count:
                reasons.append(f"{dup_count} related/duplicate issue(s)")
            best_issue, best_score, best_reasons = issue, score, reasons

    if best_issue is None:
        return None
    return {"issue": best_issue, "reasons": best_reasons}


def solve_issue(title, body, repo_context=""):
    context_block = f"\nRepository Context:\n{repo_context}\n" if repo_context else ""
    prompt = f"""
You are an experienced open-source contributor.
{context_block}
Issue Title:
{title}

Issue Description:
{body or "(No description provided)"}

Provide:
1. Root Cause
2. Fix Plan
3. Files Likely To Edit
4. Example Code Hint
5. Testing Steps
"""
    return call_ai(prompt)


# ---------- UI ----------

st.title("GitHub Issue Solver")
st.write("Fetch GitHub issues and generate AI-powered fix suggestions.")

repo_url = st.text_input("GitHub Repository URL", placeholder="https://github.com/owner/repo")

if st.button("Fetch Issues"):
    match = re.search(r"github\.com/([^/]+)/([^/]+)", repo_url.strip())
    if not match:
        st.error("Enter a valid GitHub repository URL")
        st.stop()

    owner, repo = match.groups()
    repo = repo.rstrip("/")

    with st.spinner("Fetching repository data..."):
        st.session_state.repo_info = fetch_repo_info(owner, repo)
        st.session_state.readme_text = fetch_readme(owner, repo)
        st.session_state.issues = fetch_issues(owner, repo)
        st.session_state.selected_index = 0

    if st.session_state.repo_info:
        with st.spinner("Generating repository summary..."):
            st.session_state.repo_overview = generate_repo_overview(
                st.session_state.repo_info, st.session_state.readme_text
            )
        st.session_state.health = compute_repo_health(
            st.session_state.repo_info, st.session_state.readme_text, st.session_state.issues
        )

    if st.session_state.issues:
        with st.spinner("Computing duplicate/related issues..."):
            st.session_state.duplicate_matrix = compute_duplicate_matrix(st.session_state.issues)
        with st.spinner("Running AI triage..."):
            st.session_state.classifications = classify_issues_batch(st.session_state.issues)
        st.session_state.recommended = compute_recommended_next(
            st.session_state.issues, st.session_state.classifications, st.session_state.duplicate_matrix
        )

# Repository X-Ray
if st.session_state.repo_info:
    info = st.session_state.repo_info
    health = st.session_state.health

    with st.expander("Repository X-Ray", expanded=True):
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Stars", info.get("stargazers_count", 0))
        col2.metric("Forks", info.get("forks_count", 0))
        col3.metric("Open Issues", info.get("open_issues_count", 0))
        col4.metric("Language", info.get("language") or "N/A")

        if st.session_state.repo_overview:
            st.markdown("**AI Repository Summary**")
            st.markdown(st.session_state.repo_overview)

        if health:
            st.markdown("**Repository Health (estimated from README and issue age — not a substitute for linting or test-coverage tools)**")
            st.progress(health["documentation"] / 100, text=f"Documentation: {health['documentation']}/100")
            st.progress(health["issue_management"] / 100, text=f"Issue Backlog Health: {health['issue_management']}/100")
            st.write(f"Overall (estimate): {health['overall']}/100")
            st.write(f"Stale issues (open more than 180 days): {health['stale_count']}")

# AI Triage
if st.session_state.issues and st.session_state.classifications:
    classifications = st.session_state.classifications
    with st.expander("AI Triage Report", expanded=True):
        type_counts, priority_counts = {}, {}
        for c in classifications.values():
            type_counts[c.get("type", "other")] = type_counts.get(c.get("type", "other"), 0) + 1
            priority_counts[c.get("priority", "medium")] = priority_counts.get(c.get("priority", "medium"), 0) + 1

        col1, col2 = st.columns(2)
        with col1:
            st.write("By type")
            for t, count in type_counts.items():
                st.write(f"{t}: {count}")
        with col2:
            st.write("By priority")
            for p, count in priority_counts.items():
                st.write(f"{p}: {count}")

        total_duplicate_pairs = sum(len(v) for v in st.session_state.duplicate_matrix.values()) // 2
        st.write(f"Related/duplicate issue pairs found: {total_duplicate_pairs}")

        if st.session_state.recommended:
            rec = st.session_state.recommended
            st.markdown("**Recommended next fix**")
            st.write(f"#{rec['issue']['number']} - {rec['issue']['title']}")
            st.write("Why: " + "; ".join(rec["reasons"]))

# Issue selection and solving
if st.session_state.issues:
    selected_issue = st.selectbox(
        "Choose an Issue",
        st.session_state.issues,
        index=st.session_state.selected_index,
        format_func=lambda x: f"#{x['number']} - {x['title']}"
    )

    classification = st.session_state.classifications.get(selected_issue["number"])
    if classification:
        st.write(
            f"Type: {classification.get('type', 'n/a')} | "
            f"Priority: {classification.get('priority', 'n/a')} | "
            f"Area: {classification.get('area', 'n/a')}"
        )

    with st.expander("Issue Details"):
        st.markdown(selected_issue.get("body") or "_No description provided._")

    duplicates = st.session_state.duplicate_matrix.get(selected_issue["number"], [])
    if duplicates:
        with st.expander(f"Related or Duplicate Issues ({len(duplicates)})", expanded=True):
            for dup_issue, score in duplicates:
                st.write(f"#{dup_issue['number']} - {dup_issue['title']}  (similarity: {score * 100:.0f}%)")

    if st.button("Generate Solution"):
        with st.spinner("Analyzing issue..."):
            repo_context = st.session_state.repo_overview or ""
            solution = solve_issue(selected_issue["title"], selected_issue.get("body", ""), repo_context)

        st.subheader("AI Solution")
        st.markdown(solution)

        st.download_button(
            "Download Solution",
            data=solution,
            file_name=f"issue_{selected_issue['number']}_solution.txt",
            mime="text/plain"
        )
