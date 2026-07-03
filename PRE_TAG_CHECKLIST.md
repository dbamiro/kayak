# Pre-tag checklist — v1.0.0-rc1

Run before creating the release tag. **Release hygiene only** — no product changes unless a secret leak or launch blocker is found.

---

## 1. Secrets and local files (must pass)

- [ ] **`.env`** exists locally but is **gitignored** — never staged
- [ ] **`web/.env.local`** gitignored — never staged
- [ ] **`verified_specials.csv`** and **`data/`** gitignored — real leasing data never committed
- [ ] **No env backup files** in repo root (e.g. `.env.pre-dryrun-backup`, `.env.backup`) — delete if present
- [ ] **`git status`** shows no `.env`, secrets, or real CSV imports in staged/untracked files you intend to commit
- [ ] **`.env.example`** and **`.env.production.example`** contain placeholders only — no real keys

```bash
git status --short
git check-ignore -v .env verified_specials.csv web/.env.local 2>/dev/null || true
test ! -f .env.pre-dryrun-backup && echo "OK: no env backup file"
```

**Stop if:** any secret file is tracked or about to be committed.

---

## 2. Files that must NOT be committed

| Path | Action |
|------|--------|
| `.env`, `.env.*` (except `*.example`) | Gitignore; keep local only |
| `.env.pre-dryrun-backup` | Delete |
| `verified_specials.csv`, `data/*.csv` | Gitignore |
| `web/.env.local` | Gitignore |
| `web/node_modules/`, `web/.next/` | Gitignore |
| `tmp/` | Gitignore |
| `.venv/` | Gitignore |
| Accidental junk (e.g. stray `)` file from shell) | Delete |

**Safe to commit:** application code, `fixtures/incentives_import_template.csv`, `fixtures/incentives_import_example.csv`, docs, scripts, `sql/`, tests, `web/` source (not build artifacts).

---

## 3. Quality gates (must pass)

From repo root:

```bash
./.venv/bin/python -m pytest -q
cd web && npm run build && cd ..
./scripts/smoke.sh   # API must be running on :8000; DB bootstrapped
```

- [ ] **pytest:** 141 passed (or current full-suite count)
- [ ] **web build:** completes without error
- [ ] **smoke.sh:** `/health`, `/search`, `/incentives`, `/plans`, deal report preview

Optional pre-launch (production server):

```bash
./scripts/check_prod_env.sh
ALLOW_PROD_BOOTSTRAP=yes ./scripts/prod_migrate.sh --bootstrap   # fresh DB only
./scripts/prod_verify_db.sh
docker compose -f docker-compose.prod.yml build
```

---

## 4. Release artifacts

- [ ] [RELEASE_NOTES.md](RELEASE_NOTES.md) updated for `v1.0.0-rc1`
- [ ] [LAUNCH.md](LAUNCH.md) and [LAUNCH_CHECKLIST.md](LAUNCH_CHECKLIST.md) current
- [ ] [docs/DEPLOYMENT_READINESS_REPORT.md](docs/DEPLOYMENT_READINESS_REPORT.md) reflects dry-run status

---

## 5. Stage and review diff

```bash
git add -A
git status
git diff --cached --stat
```

- [ ] No secrets, env backups, or real CSV in the staged diff
- [ ] No `node_modules` or `.next` in staged diff
- [ ] Commit message describes rc1 scope (features frozen, launch-ready)

---

## 6. Create tag (when ready)

See **[TAG_INSTRUCTIONS.md](TAG_INSTRUCTIONS.md)** for full commit, tag, push, and rollback commands.

Quick reference:

```bash
git add -A && git status && git diff --cached --stat
git commit -m "Kayak v1.0.0-rc1 — production release candidate"
git tag -a v1.0.0-rc1 -m "Kayak v1.0.0-rc1 — first production release candidate"
git push origin main
git push origin v1.0.0-rc1
```

---

## 7. Post-tag launch (not part of tag)

These happen **after** tag on the production server — see [LAUNCH_CHECKLIST.md](LAUNCH_CHECKLIST.md):

1. Deploy from tag
2. Bootstrap prod DB (plans only)
3. Import verified incentives CSV
4. Stripe test checkout + webhook
5. Manual browser QA
6. Go live

---

## Quick go / no-go

| Check | Required for tag |
|-------|------------------|
| Secrets gitignored / not staged | Yes |
| pytest pass | Yes |
| web production build pass | Yes |
| smoke.sh pass | Yes |
| RELEASE_NOTES.md present | Yes |
| Real inventory imported | No (post-deploy) |
| Stripe live mode | No (post-deploy) |

**Tag `v1.0.0-rc1` when rows 1–3 and quality gates pass.**
