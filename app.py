# app.py
import os
import re
import random
import traceback

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from github import Github, GithubException
from langchain_groq import ChatGroq


# ---------- Config ----------
PROMPT = '''You are an intelligent assistant that converts user-provided book summaries into a structured Markdown file for publishing on a website.

### Instructions:
- Always return the output as **valid Markdown** (`.md` format).  
- Preserve the **user’s original summary** exactly as written.  
- Generate a **short AI summary** (3–5 sentences).  
- Add **metadata** and extra information as frontmatter at the top.  
- Include:  
  - title  
  - author  
  - genre/category  
  - themes  
  - mood  
  - tags (comma separated)  
  - user_rating (out of 5, as provided)  

- After the frontmatter, structure the file with clear sections:  
  1. Short AI Summary  
  2. User’s Original Summary  
  3. Related Books You Might Like  
  4. Tagline  

- If some metadata is missing, infer or mark "N/A".  
- Tagline must be **one line, catchy, curiosity-driven**.  
'''

REPO_FULL_NAME = "CNS-PRADHYUMNA/Note2Site"
REPO_SUMMARIES_DIR = "Summaries"
CLEAR_DELAY_MS = 10_000   # 10000 ms = 10 seconds; change to 15000 for 15s

# ---------- Helper functions ----------


def invoke_groq_to_md(book_summary: str) -> str:
    api_key = os.getenv("GROK_API_KEY")
    if not api_key:
        raise RuntimeError("GROK_API_KEY not set in environment.")
    client = ChatGroq(model="openai/gpt-oss-20b", api_key=api_key)
    messages = [
        {"role": "system", "content": PROMPT},
        {"role": "user", "content": book_summary}
    ]
    res = client.invoke(messages)
    md = getattr(res, "content", None)
    if not md:
        md = str(res)
    return md


def extract_title(md_content: str) -> str:
    m = re.search(r'title:\s*"(.*?)"', md_content)
    if m:
        return m.group(1)
    first_line = md_content.strip().splitlines()[
        0] if md_content.strip() else ""
    candidate = re.sub(r'[^A-Za-z0-9\s\-]', '', first_line).strip()
    if candidate:
        return candidate[:120]
    return f"bookNum{random.randint(0, 10000)}"


def safe_filename_from_title(title: str) -> str:
    safe = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_")
    if not safe:
        safe = f"book_{random.randint(0, 10000)}"
    return f"{safe}.md"


def push_to_github(path: str, content: str, commit_message: str) -> str:
    token = os.getenv("GIT_PAT")
    if not token:
        raise RuntimeError("GIT_PAT not set in environment.")
    gh = Github(token)
    repo = gh.get_repo(REPO_FULL_NAME)
    try:
        existing = repo.get_contents(path)
        repo.update_file(path=path, message=commit_message,
                         content=content, sha=existing.sha)
        return "updated"
    except GithubException as e:
        if e.status == 404:
            repo.create_file(
                path=path, message=commit_message, content=content)
            return "created"
        else:
            raise


# ---------- Streamlit UI & safe clear-on-reload logic ----------
st.set_page_config(page_title="Push Book Summary → Git", layout="centered")

# ----- If URL contains ?clear=1, clear session_state keys BEFORE widgets are created -----
params = st.query_params
if params.get("clear") == ["1"]:
    for k in ("book_summary", "last_generated_path"):
        if k in st.session_state:
            del st.session_state[k]
    # remove the query param from the URL without reloading (so subsequent interactions are clean)
    components.html(
        "<script>history.replaceState(null, '', window.location.pathname);</script>",
        height=0,
    )

st.title("Push Book Summary → Git")
st.markdown("Paste the raw book summary below (exact text will be preserved).")

# Ensure key exists BEFORE creating widget (prevents modification-after-create error)
if "book_summary" not in st.session_state:
    st.session_state["book_summary"] = ""

book_summary = st.text_area(
    "Book summary (raw)",
    height=220,
    key="book_summary",
    placeholder="Paste the user's summary here..."
)

col1, col2 = st.columns([1, 1])
with col1:
    push_button = st.button("Generate & Push to Git")
with col2:
    clear_button = st.button("Clear")

if clear_button:
    st.session_state.pop("book_summary", None)   # removes the key safely


if push_button:
    raw_summary = (st.session_state.get("book_summary") or "").strip()
    if not raw_summary:
        st.error("Please paste a non-empty book summary.")
    else:
        try:
            with st.spinner("Generating Markdown and pushing to Git..."):
                md = invoke_groq_to_md(raw_summary)
                title = extract_title(md)
                filename = safe_filename_from_title(title)
                file_path = f"{REPO_SUMMARIES_DIR}/{filename}"
                commit_msg = f"Added book summary: {title}"
                action = push_to_github(file_path, md, commit_msg)
                st.session_state["last_generated_path"] = file_path

            st.success(
                f"Successfully {action} `{file_path}` in repo `{REPO_FULL_NAME}`.")
            st.markdown("**Generated Markdown (preview):**")
            st.code(md, language="markdown")
            github_url = f"https://github.com/{REPO_FULL_NAME}/blob/main/{file_path}"
            st.markdown(f"[Open on GitHub]({github_url})")

        except Exception:
            st.error("Push failed.")
            st.exception(traceback.format_exc())
