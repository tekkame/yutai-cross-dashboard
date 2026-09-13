# -*- coding: utf-8 -*-
"""
deploy_to_github.py - GitHubへの自動プッシュ＆デプロイマネージャー
GitHub Personal Access Token (PAT) を安全に取得し、
リポジトリ (tekkame/yutai-cross-dashboard) へ同期・プッシュします。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path

# 出力文字コード
sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(__file__).resolve().parent
REPO_NAME = "yutai-cross-dashboard"
DEFAULT_BRANCH = "main"

# トークン探索候補
TOKEN_CANDIDATES = [
    BASE_DIR / ".github_token",
    Path("C:/Users/tekka/Desktop/antigravity/mitsubishi_hems/.github_token"),
    Path(os.environ.get("GITHUB_TOKEN_PATH", "")),
]

def get_token() -> str:
    # 1. 環境変数
    env_token = os.environ.get("GITHUB_TOKEN", "").strip()
    if env_token:
        return env_token

    # 2. ファイル探索
    for p in TOKEN_CANDIDATES:
        if p.exists() and p.is_file():
            content = p.read_text(encoding="utf-8").strip()
            if content:
                print(f"[AUTH] トークンファイルを検出: {p}")
                return content

    raise FileNotFoundError("GitHub トークンが見つかりません。mitsubishi_hems の .github_token または GITHUB_TOKEN を確認してください。")

def get_username(token: str) -> str:
    url = "https://api.github.com/user"
    req = urllib.request.Request(url, headers={"Authorization": f"token {token}", "User-Agent": "YutaiDeployer"})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data.get("login", "tekkame")

def ensure_repo_exists(token: str, username: str, repo_name: str) -> str:
    """リポジトリが存在するか確認し、なければ作成する"""
    check_url = f"https://api.github.com/repos/{username}/{repo_name}"
    req = urllib.request.Request(check_url, headers={"Authorization": f"token {token}", "User-Agent": "YutaiDeployer"})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"[REPO] 既存リポジトリを確認: {data.get('html_url')}")
            return data.get("html_url")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"[REPO] リポジトリ '{repo_name}' が未作成のため新規作成します...")
            create_url = "https://api.github.com/user/repos"
            payload = json.dumps({
                "name": repo_name,
                "description": "株主優待クロス取引 一般信用売り在庫トラッカー＆実戦ダッシュボード (Streamlit Cloud)",
                "private": False,
                "auto_init": False
            }).encode("utf-8")
            create_req = urllib.request.Request(
                create_url,
                data=payload,
                headers={"Authorization": f"token {token}", "User-Agent": "YutaiDeployer", "Content-Type": "application/json"}
            )
            with urllib.request.urlopen(create_req) as c_resp:
                c_data = json.loads(c_resp.read().decode("utf-8"))
                print(f"[REPO] 新規リポジトリ作成完了: {c_data.get('html_url')}")
                return c_data.get("html_url")
        else:
            raise

def run_cmd(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0 and "nothing to commit" not in res.stdout:
        print(f"[CMD WARN/ERR] {' '.join(cmd)}\n{res.stderr}\n{res.stdout}")
    return res

def deploy(commit_msg: str = "Update yutai-cross-dashboard for Streamlit Cloud"):
    print("=======================================================")
    print("  株主優待ダッシュボード GitHub デプロイ開始")
    print("=======================================================\n")

    token = get_token()
    username = get_username(token)
    repo_url = ensure_repo_exists(token, username, REPO_NAME)

    # Git初期化確認
    git_dir = BASE_DIR / ".git"
    if not git_dir.exists():
        print("[GIT] Git リポジトリを初期化中...")
        run_cmd(["git", "init"], BASE_DIR)
        run_cmd(["git", "branch", "-M", DEFAULT_BRANCH], BASE_DIR)

    # リモートURL設定 (トークン付き)
    remote_url = f"https://{username}:{token}@github.com/{username}/{REPO_NAME}.git"
    remotes = run_cmd(["git", "remote"], BASE_DIR).stdout
    if "origin" in remotes.split():
        run_cmd(["git", "remote", "set-url", "origin", remote_url], BASE_DIR)
    else:
        run_cmd(["git", "remote", "add", "origin", remote_url], BASE_DIR)

    # ステージングとコミット
    print("[GIT] ファイルのステージング中...")
    run_cmd(["git", "add", "."], BASE_DIR)
    
    # ユーザー名/メール設定 (未設定の場合)
    run_cmd(["git", "config", "user.name", username], BASE_DIR)
    run_cmd(["git", "config", "user.email", f"{username}@users.noreply.github.com"], BASE_DIR)

    print(f"[GIT] コミット作成: '{commit_msg}'")
    run_cmd(["git", "commit", "-m", commit_msg], BASE_DIR)

    print(f"[GIT] GitHub ({username}/{REPO_NAME}:{DEFAULT_BRANCH}) へプッシュ中...")
    push_res = run_cmd(["git", "push", "-u", "origin", DEFAULT_BRANCH, "--force"], BASE_DIR)
    
    if push_res.returncode == 0 or "Everything up-to-date" in push_res.stderr or "Everything up-to-date" in push_res.stdout:
        print("\n=======================================================")
        print("  🎉 GITHUB プッシュ成功！")
        print("=======================================================")
        print(f"リポジトリURL: {repo_url}")
        print("\n【Streamlit Cloud 設定手順】")
        print("1. https://share.streamlit.io にアクセス")
        print("2. 'Create app' をクリック")
        print(f"3. Repository: {username}/{REPO_NAME}")
        print(f"4. Branch: {DEFAULT_BRANCH}")
        print("5. Main file path: app.py")
        print("6. 'Deploy!' をクリックすると数分で公開ダッシュボードが稼働します！\n")
    else:
        print(f"[ERROR] プッシュ失敗: {push_res.stderr}")

if __name__ == "__main__":
    msg = sys.argv[1] if len(sys.argv) > 1 else "Release Yutai Cross Dashboard v2.0 (Serverless + Streamlit Cloud)"
    deploy(msg)
