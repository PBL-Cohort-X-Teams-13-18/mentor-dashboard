import streamlit as st
import requests
import base64
import json
import pandas as pd

# ---------------- CONFIGURATION ----------------
ORG_NAME = "PBL-Cohort-X-Teams-13-18"  # <-- REPLACE with your exact GitHub Organization name
TEAM_REPOS = [f"pbl-team-0{i}" for i in range(1, 7)]

STANDARD_KEYS = {
    "team_id", "project_title", "domain", "current_phase",
    "overall_progress_percent", "approach_summary", "members",
    "timeline", "competitions_and_papers"
}

st.set_page_config(page_title="PBL Mentor Command Center", page_icon="🎓", layout="wide")
st.title("🎓 PBL Mentor Command Center")
st.caption(f"Live tracking across all {len(TEAM_REPOS)} repositories in **{ORG_NAME}**")

# ---------------- AUTHENTICATION ----------------
github_token = None
if "GITHUB_TOKEN" in st.secrets:
    github_token = st.secrets["GITHUB_TOKEN"]
else:
    github_token = st.sidebar.text_input("🔑 Enter GitHub Personal Access Token", type="password")

if not github_token:
    st.info("👈 Enter your GitHub Personal Access Token in the sidebar (or configure `GITHUB_TOKEN` in Streamlit Secrets) to load team data.")
    st.stop()

HEADERS = {
    "Authorization": f"token {github_token}",
    "Accept": "application/vnd.github.v3+json"
}

if st.sidebar.button("🔄 Refresh Live Repo Data"):
    st.cache_data.clear()

# ---------------- API HELPER FUNCTIONS ----------------
@st.cache_data(ttl=120)
def fetch_team_json(repo_name):
    """Fetches and parses project_data.json from a team repository."""
    url = f"https://api.github.com/repos/{ORG_NAME}/{repo_name}/contents/project_data.json"
    res = requests.get(url, headers=HEADERS)
    if res.status_code == 200:
        try:
            content = base64.b64decode(res.json()["content"]).decode("utf-8")
            return json.loads(content), None
        except Exception as e:
            return None, f"Invalid JSON syntax in {repo_name}/project_data.json: {e}"
    return None, f"Could not find project_data.json in {repo_name} (HTTP {res.status_code})"

@st.cache_data(ttl=120)
def fetch_all_repo_contents(repo_name):
    """Recursively discovers ALL folders, subfolders, and files uploaded by students."""
    repo_url = f"https://api.github.com/repos/{ORG_NAME}/{repo_name}"
    repo_res = requests.get(repo_url, headers=HEADERS)
    if repo_res.status_code != 200:
        return {}
    default_branch = repo_res.json().get("default_branch", "main")

    tree_url = f"https://api.github.com/repos/{ORG_NAME}/{repo_name}/git/trees/{default_branch}?recursive=1"
    tree_res = requests.get(tree_url, headers=HEADERS)
    if tree_res.status_code != 200:
        return {}

    grouped_files = {}
    for item in tree_res.json().get("tree", []):
        if item["type"] == "blob" and not item["path"].endswith(".gitkeep"):
            parts = item["path"].split("/")
            folder = "/".join(parts[:-1]) if len(parts) > 1 else "📌 Root Directory"
            filename = parts[-1]
            file_web_url = f"https://github.com/{ORG_NAME}/{repo_name}/blob/{default_branch}/{item['path']}"
            grouped_files.setdefault(folder, []).append({
                "name": filename,
                "url": file_web_url,
                "size_kb": round(item.get("size", 0) / 1024, 1)
            })
    return grouped_files

@st.cache_data(ttl=120)
def fetch_release_assets(repo_name):
    """Fetches heavy files (>25MB up to 2GB) uploaded via GitHub Releases."""
    url = f"https://api.github.com/repos/{ORG_NAME}/{repo_name}/releases"
    res = requests.get(url, headers=HEADERS)
    assets = []
    if res.status_code == 200 and isinstance(res.json(), list):
        for rel in res.json():
            rel_name = rel.get("name") or rel.get("tag_name", "Release")
            for asset in rel.get("assets", []):
                assets.append({
                    "release": rel_name,
                    "name": asset["name"],
                    "url": asset["browser_download_url"],
                    "size_mb": round(asset.get("size", 0) / (1024 * 1024), 2)
                })
    return assets

@st.cache_data(ttl=120)
def fetch_contributor_commits(repo_name):
    """Fetches real GitHub commit counts per student username."""
    url = f"https://api.github.com/repos/{ORG_NAME}/{repo_name}/contributors"
    res = requests.get(url, headers=HEADERS)
    if res.status_code == 200 and isinstance(res.json(), list):
        return {item["login"].lower(): item["contributions"] for item in res.json()}
    return {}

# ---------------- LOAD DATA FOR ALL 6 TEAMS ----------------
all_teams_data = {}
errors = []
for repo in TEAM_REPOS:
    data, err = fetch_team_json(repo)
    if data:
        all_teams_data[repo] = data
    if err:
        errors.append(err)

# ---------------- DASHBOARD UI ----------------
tab1, tab2 = st.tabs(["📊 All 6 Teams Overview", "🔍 Team Deep-Dive, Roles & All Files"])

with tab1:
    st.subheader("Cohort Master Tracker")
    if errors:
        with st.expander("⚠️ Repository Warnings / Missing Files", expanded=False):
            for e in errors:
                st.warning(e)

    overview_rows = []
    for repo, data in all_teams_data.items():
        overview_rows.append({
            "Team ID": data.get("team_id", repo),
            "Project Title": data.get("project_title", "N/A"),
            "Domain": data.get("domain", "N/A"),
            "Current Phase": data.get("current_phase", "N/A"),
            "Progress": data.get("overall_progress_percent", 0),
            "Team Size": len(data.get("members", [])),
            "Papers & Events": len(data.get("competitions_and_papers", [])),
            "GitHub Repo": f"https://github.com/{ORG_NAME}/{repo}"
        })

    if overview_rows:
        df_overview = pd.DataFrame(overview_rows)
        st.dataframe(
            df_overview,
            column_config={
                "Progress": st.column_config.ProgressColumn("Progress", min_value=0, max_value=100, format="%d%%"),
                "GitHub Repo": st.column_config.LinkColumn("Open Repo")
            },
            use_container_width=True,
            hide_index=True
        )
    else:
        st.warning("No valid `project_data.json` files loaded yet. Check `ORG_NAME` and repository names.")

with tab2:
    selected_repo = st.selectbox("Select a Team Repository to Inspect:", TEAM_REPOS)
    team_data = all_teams_data.get(selected_repo)

    if not team_data:
        st.error(f"Could not load `project_data.json` for `{selected_repo}`.")
    else:
        col_header, col_link = st.columns([4, 1])
        with col_header:
            st.markdown(f"## 🚀 {team_data.get('team_id', selected_repo)}: {team_data.get('project_title', '')}")
            st.caption(f"**Domain:** {team_data.get('domain', 'N/A')} | **Current Phase:** {team_data.get('current_phase', 'N/A')}")
        with col_link:
            st.link_button("🔗 Open GitHub Repo", f"https://github.com/{ORG_NAME}/{selected_repo}", use_container_width=True)

        progress_val = min(max(int(team_data.get("overall_progress_percent", 0)), 0), 100)
        st.progress(progress_val / 100.0, text=f"Overall Project Completion: {progress_val}%")

        st.markdown("### 🧠 Approach & Methodology")
        st.info(team_data.get("approach_summary", "No approach summary provided yet."))

        st.divider()

        # 1. TEAM MEMBERS, ROLES & LIVE COMMIT VERIFICATION
        st.subheader("👥 Team Members, Responsibilities & Verified Git Commits")
        commits_map = fetch_contributor_commits(selected_repo)
        members_list = [dict(m) for m in team_data.get("members", [])]
        for m in members_list:
            gh_user = str(m.get("github_username", "")).strip().lower()
            m["Verified Commits"] = commits_map.get(gh_user, 0)
        if members_list:
            st.dataframe(pd.DataFrame(members_list), use_container_width=True, hide_index=True)
        else:
            st.caption("No team members listed.")

        # 2. TIMELINE & COMPETITIONS / PAPERS
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("📅 Project Timeline")
            timeline_list = team_data.get("timeline", [])
            if timeline_list:
                st.dataframe(pd.DataFrame(timeline_list), use_container_width=True, hide_index=True)
            else:
                st.caption("No timeline entries yet.")

        with col2:
            st.subheader("🏆 Competitions & Paper Presentations")
            comp_list = team_data.get("competitions_and_papers", [])
            if comp_list:
                st.dataframe(pd.DataFrame(comp_list), use_container_width=True, hide_index=True)
            else:
                st.caption("No competitions or papers logged yet.")

        # 3. EXTRA CUSTOM JSON SECTIONS ADDED BY STUDENTS
        extra_keys = [k for k in team_data.keys() if k not in STANDARD_KEYS]
        if extra_keys:
            st.divider()
            st.subheader("➕ Additional Team Data & External Links")
            for key in extra_keys:
                clean_title = key.replace("_", " ").title()
                st.markdown(f"**{clean_title}**")
                val = team_data[key]
                if isinstance(val, list):
                    st.dataframe(pd.DataFrame(val), use_container_width=True, hide_index=True)
                elif isinstance(val, dict):
                    st.json(val)
                else:
                    st.write(val)

        st.divider()

        # 4. RECURSIVE REPOSITORY FILE & CUSTOM FOLDER BROWSER
        st.subheader("📂 All Uploaded Repository Files (Auto-Discovers Custom Folders)")
        all_files_by_folder = fetch_all_repo_contents(selected_repo)
        if all_files_by_folder:
            for folder_name, file_list in sorted(all_files_by_folder.items()):
                with st.expander(f"📁 {folder_name} ({len(file_list)} files)", expanded=True):
                    for f in file_list:
                        st.markdown(f"- 📄 **[{f['name']}]({f['url']})** *({f['size_kb']} KB)*")
        else:
            st.caption("No files found in repository.")

        # 5. HEAVY FILES UPLOADED VIA GITHUB RELEASES
        release_assets = fetch_release_assets(selected_repo)
        if release_assets:
            st.subheader("📦 Heavy Files & Videos (GitHub Releases)")
            for asset in release_assets:
                st.markdown(f"- 🎞️ **[{asset['name']}]({asset['url']})** — *{asset['release']} ({asset['size_mb']} MB)*")
