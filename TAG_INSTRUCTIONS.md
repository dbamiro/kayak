# Kayak v1.0.0-rc1 — tag instructions

Step-by-step commands to commit the release candidate and create the annotated tag.

**Do not run the tag step until you have reviewed the staged diff and completed [PRE_TAG_CHECKLIST.md](PRE_TAG_CHECKLIST.md).**

Current default branch: `main` · Remote: `origin` (`https://github.com/dbamiro/kayak.git`)

---

## 1. Inspect git status and diff

From repo root:

```bash
cd /path/to/Kayak

# Working tree overview
git status

# Short status (easier to scan)
git status --short

# Confirm secrets are ignored (should print .gitignore rules, not errors)
git check-ignore -v .env verified_specials.csv web/.env.local web/node_modules

# Confirm no env backup file remains
test ! -f .env.pre-dryrun-backup && echo "OK: no env backup"

# Diff vs last commit (unstaged)
git diff --stat
git diff

# Diff for already-staged files (after git add)
git diff --cached --stat
git diff --cached

# Full history context
git log -5 --oneline
```

**Stop if** `.env`, `web/.env.local`, `verified_specials.csv`, env backups, or real leasing CSV appear in `git status` as staged (`A`/`M` in first column) or in `git diff --cached`.

---

## 2. Commit release-candidate changes

Stage everything intended for rc1 (gitignore excludes secrets and build artifacts):

```bash
git add -A

# Re-check staged diff before commit
git status --short
git diff --cached --stat
```

Optional: run quality gates one more time:

```bash
./.venv/bin/python -m pytest -q
cd web && npm run build && cd ..
./scripts/smoke.sh   # API on :8000, DB bootstrapped
```

Commit (see suggested message below):

```bash
git commit -m "$(cat <<'EOF'
Kayak v1.0.0-rc1 — production release candidate.

Freeze v1 for first production deploy: auth, search/specials, Deal Reports,
Stripe Hunt Pass, admin CSV import, production scripts, Docker prod stack,
and launch documentation. No new product features after this commit.

EOF
)"
```

Verify:

```bash
git log -1 --stat
git status
```

---

## 3. Suggested commit message

**Subject (≤72 chars):**

```
Kayak v1.0.0-rc1 — production release candidate
```

**Body:**

```
Freeze v1 for first production deploy: auth, search/specials, Deal Reports,
Stripe Hunt Pass, admin CSV import, production scripts, Docker prod stack,
and launch documentation. No new product features after this commit.
```

---

## 4. Create annotated tag `v1.0.0-rc1`

**Only after the rc1 commit is on `main` and tests/build/smoke pass.**

```bash
git tag -a v1.0.0-rc1 -m "$(cat <<'EOF'
Kayak v1.0.0-rc1 — first production release candidate.

See RELEASE_NOTES.md and LAUNCH.md for deploy steps.
EOF
)"

# Verify tag points at expected commit
git show v1.0.0-rc1 --no-patch
git log -1 --oneline v1.0.0-rc1
```

To retag locally **before pushing** (only if tag was created in error):

```bash
git tag -d v1.0.0-rc1
# fix commit, then recreate tag with command above
```

---

## 5. Push branch and tag

```bash
# Push rc1 commit on main
git push origin main

# Push annotated tag
git push origin v1.0.0-rc1
```

Verify on GitHub: tag `v1.0.0-rc1` appears on the rc1 commit.

**Deploy from tag on the server:**

```bash
git fetch origin tag v1.0.0-rc1
git checkout v1.0.0-rc1
# then follow LAUNCH.md / LAUNCH_CHECKLIST.md
```

---

## 6. Rollback if deploy fails

### A. Application rollback (previous git tag)

On the production server:

```bash
cd /path/to/Kayak
git fetch origin --tags

# List tags to find previous release
git tag -l 'v*' --sort=-v:refname

# Check out previous known-good tag (example: first commit before rc1)
git checkout 6921b80   # or previous tag, e.g. v1.0.0-beta

docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
```

If you changed `.env` for the failed deploy, restore from backup:

```bash
cp .env.backup-YYYYMMDD .env
./scripts/check_prod_env.sh
docker compose -f docker-compose.prod.yml up -d --build
```

### B. Database rollback (migration failed)

Kayak migrations are **forward-only**. Do not run ad-hoc down SQL in production without a plan.

1. **Stop API/web** to prevent partial writes:

   ```bash
   docker compose -f docker-compose.prod.yml stop api web jobs
   ```

2. **Restore Postgres from snapshot** taken before deploy (recommended in [LAUNCH_CHECKLIST.md](LAUNCH_CHECKLIST.md)):

   ```bash
   # Example — adjust for your backup path/host
   pg_restore -d kayak_prod --clean --if-exists /backups/kayak_pre_rc1.dump
   ```

3. **Redeploy previous app version** (section A), then verify:

   ```bash
   ./scripts/prod_verify_db.sh
   API_URL=https://api.example.com ./scripts/prod_smoke.sh
   ```

### C. Delete remote tag (only if rc1 must be withdrawn)

Use only if the tag was pushed by mistake and no one should deploy it:

```bash
git push origin :refs/tags/v1.0.0-rc1
git tag -d v1.0.0-rc1   # locally
```

Create a fixed tag (e.g. `v1.0.0-rc2`) after the fix — **do not force-move** a tag others may have pulled unless the team agrees.

---

## Related docs

| Doc | Purpose |
|-----|---------|
| [PRE_TAG_CHECKLIST.md](PRE_TAG_CHECKLIST.md) | Gates before tagging |
| [RELEASE_NOTES.md](RELEASE_NOTES.md) | v1.0.0-rc1 release summary |
| [LAUNCH.md](LAUNCH.md) | Production deploy runbook |
| [LAUNCH_CHECKLIST.md](LAUNCH_CHECKLIST.md) | Launch-day steps |
