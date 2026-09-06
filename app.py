import streamlit as st
import requests
import re
import base64
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

st.set_page_config(page_title="GitHub Issue Solver")

OPEN_ROUTER_API_KEY = st.secrets.get("OPENROUTER_API_KEY", "")
MODEL = "openrouter/free"

if "issues" not in st.session_state:
    st.session_state.issues = []
if "selected_index" not in st.session_state:
    st.session_state.selected_index = 0
if "repo_info" not in st.session_state:
    st.session_state.repo_info = None
if "repo_overview" not in st.session_state:
    st.session_state.repo_overview = ""


def fetch_issues(owner, repo):
    url = f"https://api.github.com/repos/{owner}/{repo}/issues"
    response = requests.get(
        url,
        params={"state": "open", "per_page": 20},
        headers={"Accept": "application/vnd.github+json"},
        timeout=10
    )
    if response.status_code != 200:
        st.error(f"GitHub Error: {response.json().get('message')}")
        return []
    return [
        issue for issue in response.json()
        if "pull_request" not in issue
    ]


def fetch_repo_info(owner, repo):
    url = f"https://api.github.com/repos/{owner}/{repo}"
    response = requests.get(
        url,
        headers={"Accept": "application/vnd.github+json"},
        timeout=10
    )
    if response.status_code != 200:
        return None
    return response.json()


def fetch_readme(owner, repo):
    url = f"https://api.github.com/repos/{owner}/{repo}/readme"
    response = requests.get(
        url,
        headers={"Accept": "application/vnd.github+json"},
        timeout=10
    )
    if response.status_code != 200:
        return ""
    content = response.json().get("content", "")
    try:
        return base64.b64decode(content).decode("utf-8", errors="ignore")
    except Exception:
        return ""


def call_ai(prompt):
    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPEN_ROUTER_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}]
        },
        timeout=30
    )
    if response.status_code != 200:
        err = response.json().get("error", {})
        msg = err.get("message", response.text)
        return f"Error {response.status_code}: {msg}"
    return response.json()["choices"][0]["message"]["content"]


def generate_repo_overview(repo_info, readme_text):
    description = repo_info.get("description") or "No description provided."
    language = repo_info.get("language") or "Not specified"
    stars = repo_info.get("stargazers_count", 0)
    forks = repo_info.get("forks_count", 0)
    open_issues = repo_info.get("open_issues_count", 0)
    readme_excerpt = readme_text[:3000] if readme_text else "No README found."

    prompt = f"""
You are analyzing a GitHub repository. Give a short, practical overview.

Repository: {repo_info.get('full_name')}
Description: {description}
Primary Language: {language}
Stars: {stars}
Forks: {forks}
Open Issues: {open_issues}

README (partial):
{readme_excerpt}

Provide, in plain text with short headers, no markdown symbols beyond headers:
1. What this project does
2. Likely tech stack
3. Who it is for
4. Anything relevant a contributor should know before fixing issues
Keep it under 200 words.
"""
    return call_ai(prompt)


def find_duplicate_issues(selected_issue, all_issues, top_n=5, min_similarity=0.15):
    others = [i for i in all_issues if i["number"] != selected_issue["number"]]
    if not others:
        return []

    documents = [
        f"{selected_issue['title']} {selected_issue.get('body') or ''}"
    ] + [
        f"{issue['title']} {issue.get('body') or ''}" for issue in others
    ]

    vectorizer = TfidfVectorizer(stop_words="english")
    try:
        tfidf_matrix = vectorizer.fit_transform(documents)
    except ValueError:
        return []

    similarities = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:]).flatten()

    scored = [
        (others[i], float(similarities[i]))
        for i in range(len(others))
        if similarities[i] >= min_similarity
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_n]


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


st.title("GitHub Issue Solver")
st.write("Fetch GitHub issues and generate AI-powered fix suggestions.")

repo_url = st.text_input(
    "GitHub Repository URL",
    placeholder="https://github.com/owner/repo"
)

if st.button("Fetch Issues"):
    match = re.search(r"github\.com/([^/]+)/([^/]+)", repo_url.strip())
    if not match:
        st.error("Enter a valid GitHub repository URL")
        st.stop()

    owner, repo = match.groups()
    repo = repo.rstrip("/")

    with st.spinner("Fetching repository info..."):
        st.session_state.repo_info = fetch_repo_info(owner, repo)

    with st.spinner("Fetching issues..."):
        st.session_state.issues = fetch_issues(owner, repo)
        st.session_state.selected_index = 0

    if st.session_state.repo_info:
        with st.spinner("Generating repository overview..."):
            readme_text = fetch_readme(owner, repo)
            st.session_state.repo_overview = generate_repo_overview(
                st.session_state.repo_info, readme_text
            )

if st.session_state.repo_info:
    info = st.session_state.repo_info
    with st.expander("Repository Overview", expanded=True):
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Stars", info.get("stargazers_count", 0))
        col2.metric("Forks", info.get("forks_count", 0))
        col3.metric("Open Issues", info.get("open_issues_count", 0))
        col4.metric("Language", info.get("language") or "N/A")
        if st.session_state.repo_overview:
            st.markdown(st.session_state.repo_overview)

if st.session_state.issues:
    selected_issue = st.selectbox(
        "Choose an Issue",
        st.session_state.issues,
        index=st.session_state.selected_index,
        format_func=lambda x: f"#{x['number']} - {x['title']}"
    )

    with st.expander("Issue Details"):
        st.markdown(selected_issue.get("body") or "_No description provided._")

    duplicates = find_duplicate_issues(selected_issue, st.session_state.issues)
    if duplicates:
        with st.expander(f"Possible Duplicate or Related Issues ({len(duplicates)})", expanded=True):
            for dup_issue, score in duplicates:
                st.write(f"#{dup_issue['number']} - {dup_issue['title']}  (similarity: {score * 100:.0f}%)")

    if st.button("Generate Solution"):
        with st.spinner("Analyzing issue..."):
            repo_context = st.session_state.repo_overview if st.session_state.repo_overview else ""
            solution = solve_issue(
                selected_issue["title"],
                selected_issue.get("body", ""),
                repo_context
            )

        st.subheader("AI Solution")
        st.markdown(solution)

        st.download_button(
            "Download Solution",
            data=solution,
            file_name=f"issue_{selected_issue['number']}_solution.txt",
            mime="text/plain"
        )
