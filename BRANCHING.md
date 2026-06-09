# Git Flow Branching Strategy

This repository uses a simplified Git Flow branching model.

## Branch Overview

| Branch | Purpose |
|--------|---------|
| `main` | Production-ready code. Only receives merges from `develop` (releases) or hotfix branches. |
| `develop` | Integration branch for testing. All feature branches are merged here before going to `main`. |
| `feature/*` | Short-lived branches for new features, branched off `develop` and merged back into `develop`. |

## Setup Commands

### 1. Production branch (`main`)

`main` is the default production branch. It is already set up in this repository.

```bash
# Verify you are on main
git checkout main
```

### 2. Create the `develop` integration branch from `main`

```bash
git checkout main
git pull origin main
git checkout -b develop
git push -u origin develop
```

### 3. Create a feature branch from `develop`

```bash
# Start a new feature
git checkout develop
git pull origin develop
git checkout -b feature/desktop-tests
git push -u origin feature/desktop-tests

# ... do your work, then open a PR back into develop ...
```

## Typical Workflow

```text
main
 └── develop
       └── feature/desktop-tests   ← work here, PR → develop
```

1. Branch off `develop` to start a feature.
2. Commit your changes on the feature branch.
3. Open a Pull Request from `feature/desktop-tests` → `develop`.
4. After review and testing, merge into `develop`.
5. When `develop` is stable, open a Pull Request from `develop` → `main` to release.
