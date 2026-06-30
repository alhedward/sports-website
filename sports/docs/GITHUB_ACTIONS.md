# GitHub Actions layout

GitHub only discovers workflows from the repository root under `.github/workflows/`.

This package therefore stages workflows at the package root:

```text
.github/workflows/sports-validate.yml
sports/
```

When the deployment helper extracts the package, `sports/file.deploy.txt` copies the staged `.github/` folder into the repository parent folder, so the final repository layout becomes:

```text
sports-website/
  .github/workflows/sports-validate.yml
  sports/
```

Do not leave workflows only under `sports/.github/workflows/`; GitHub will not run them from there.
