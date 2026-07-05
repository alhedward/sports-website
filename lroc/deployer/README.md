# LROC deployer

This folder keeps the local deployment helper with the repository so the current deployment workflow is versioned with the site package.

## Files

- `deploy_helper.py` — Tkinter deployment helper. Run with `python3 lroc/deployer/deploy_helper.py` from anywhere, or copy it locally if preferred.
- `file.deploy.txt` — sample/package deploy script template using the helper placeholders.

## Local requirements

```bash
sudo apt install python3-tk
```

For GitHub Actions monitoring inside the helper:

```bash
gh auth login
gh auth status
```

The helper prefers the `file.deploy.txt` shipped at the package site root, for example `lroc/file.deploy.txt`, when deploying a tarball. The copy in this folder is a reference/template for maintaining the helper workflow.

## Latest package picker

The **Latest…** picker auto-refreshes the selected folder every 2 seconds, so newly downloaded package tarballs appear without pressing Refresh. Selecting a package still requires double-click, Enter, or Select before the deploy confirmation prompt is shown.
