# Sports deployment helper

This is the sports-aware copy of the local deployment helper.

Run locally with:

```bash
python3 deploy_helper_sports.py
```

or, once this package has been copied into a repository:

```bash
python3 sports/deployer/deploy_helper.py
```

It adds `sports` as a selectable deployment context and can detect a `sports/` folder inside `.zip`, `.tar.gz`, or `.tgz` deployment packages.
