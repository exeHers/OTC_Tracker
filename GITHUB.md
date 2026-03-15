# Push this project to GitHub

Follow these steps to put the OTC Tracker on GitHub. You need a GitHub account and Git installed.

**Can the assistant push to GitHub for you?** No. The assistant can run `git init`, `git add`, and `git commit` on your machine, but **pushing** requires logging into GitHub (your account, password or Personal Access Token, and any 2FA). The assistant has no access to your credentials or the GitHub API, so you have to run `git push` yourself from your PC.

---

## 1. Install Git (if needed)

- Download: [git-scm.com](https://git-scm.com/)
- Or: `winget install Git.Git` (Windows)

---

## 2. Create a new repo on GitHub

1. Go to [github.com](https://github.com) and sign in.
2. Click **+** (top right) → **New repository**.
3. Choose a name (e.g. `otc-trading-tracker` or `Trading-Journal`).
4. Choose **Public** (or Private if you prefer).
5. **Do not** add a README, .gitignore, or license (we already have .gitignore).
6. Click **Create repository**.

---

## 3. Initialize Git and push from your PC

Open **PowerShell** or **Command Prompt** and run:

```powershell
cd "c:\Users\donov\Desktop\Trading Journal"

# Initialize repo (only if you haven’t already)
git init

# Add the remote (replace YOUR_USERNAME and YOUR_REPO with your GitHub username and repo name)
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git

# Stage all files (respects .gitignore)
git add .

# First commit
git commit -m "Initial commit: OTC Tracker desktop + mobile + Android"

# Push (main branch; use master if your default is master)
git branch -M main
git push -u origin main
```

When you run `git push`, Git will ask you to sign in. Use:

- **Username:** your GitHub username  
- **Password:** a **Personal Access Token** (GitHub no longer accepts account passwords for push).  
  - Create one: GitHub → **Settings** → **Developer settings** → **Personal access tokens** → **Tokens (classic)** → **Generate new token**. Give it `repo` scope, copy it, and paste it when prompted.

---

## 4. After the first push

- Your code is on GitHub at `https://github.com/YOUR_USERNAME/YOUR_REPO`.
- To push later changes:
  ```powershell
  cd "c:\Users\donov\Desktop\Trading Journal"
  git add .
  git commit -m "Describe what you changed"
  git push
  ```

**Note:** `config.json` and `trades.csv` are in `.gitignore`, so your personal data and settings are not uploaded. The repo stays clean for others to clone and use.
