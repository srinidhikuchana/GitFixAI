import streamlit as st
import requests
import re

st.set_page_config(page_title="GitHub Issue Solver")

OPEN_ROUTER_API_KEY = st.secrets.get("OPENROUTER_API_KEY", "")
MODEL = "openrouter/free"

if "issues" not in st.session_state:
    st.session_state.issues = []
if "selected_index" not in st.session_state:
    st.session_state.selected_index = 0

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


def solve_issue(title, body):
    prompt = f"""
You are an experienced open-source contributor.

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
    with st.spinner("Fetching issues..."):
        st.session_state.issues = fetch_issues(owner, repo)
        st.session_state.selected_index = 0

if st.session_state.issues:
    selected_issue = st.selectbox(
        "Choose an Issue",
        st.session_state.issues,
        index=st.session_state.selected_index,
        format_func=lambda x: f"#{x['number']} - {x['title']}"
    )

    with st.expander("Issue Details"):
        st.markdown(selected_issue.get("body") or "_No description provided._")

    if st.button("Generate Solution"):
        with st.spinner("Analyzing issue..."):
            solution = solve_issue(
                selected_issue["title"],
                selected_issue.get("body", "")
            )

        st.subheader("AI Solution")
        st.markdown(solution)

        st.download_button(
            "Download Solution",
            data=solution,
            file_name=f"issue_{selected_issue['number']}_solution.txt",
            mime="text/plain"
        )
