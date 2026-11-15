# GitHub publication checklist

This folder is prepared for a **public** GitHub repository named `SecureChain`.

## Before the first push

1. Replace `[COPYRIGHT HOLDER]` in `LICENSE` with the copyright holder's name.
2. Create an empty public repository named `SecureChain` on GitHub.
   Do not initialize it with a README, license, or `.gitignore`.
3. Open PowerShell in this project folder and run:

```powershell
git init
git branch -M main
git add .
git status
```

4. Review `git status` carefully. Do not proceed if it lists:
   - `data/` or any `.db`, `.sqlite`, or `.sqlite3` file
   - `venv/`, `.venv/`, `__pycache__/`, or `.pytest_cache/`
   - private keys, wallet keystores, `.env` files, or Streamlit secrets
5. If the staged file list is safe, commit and connect the remote:

```powershell
git commit -m "Initial release: SecureChain"
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/SecureChain.git
git push -u origin main
```

Replace `YOUR_GITHUB_USERNAME` with your actual GitHub username.

## Verification after publishing

Open the repository page and confirm that the README renders correctly, source files and documentation are present, and no local database, wallet key, environment, or cache files were uploaded.

## Notes

- `screenshots/` is intentionally empty except for `.gitkeep`. Add genuine screenshots of the running app when available.
- `data/securechain.db` is intentionally not included. The app creates its database on first run.
- Install dependencies locally with `pip install -r requirements.txt`.
