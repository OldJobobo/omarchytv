# Source-first OmarchyTV fork

Fork:
https://github.com/OldJobobo/omarchytv

Upstream:
https://github.com/piermark/omarchytv

This fork separates reusable source changes from one TV's configuration. The existing deployed build is recovery evidence, **not** the source tree to keep patching. No workflow command pushes, installs, reloads, launches apps, or contacts a TV.

## Layout and branches

| Layer | Purpose |
| --- | --- |
| `main` | Unmodified upstream mirror; never edit here. |
| `fork/workflow` | Primary checkout: this guide, guarded helpers and pinned off-device tools only. |
| `fix/*`, `feat/*` | Independent changes based on `upstream/main`, each usable as an upstream PR. |
| `livingroom` | Disposable, tested merge of the ready features in `fork/series.json`; never PR this branch upstream. |
| `.local/worktrees/` | Independent feature workspaces. |
| `.local/profiles/<name>/` | Ignored operator defaults, app/input catalogs, palette additions and asset manifests. |
| `.local/recovery/` | Exact previously deployed payload/package and checksums. |
| `.local/operator/` | Private device references and separately reviewed operational/recovery helpers. |
| `.local/builds/` | Source-derived app trees, candidate IPKs, validation logs and content manifests. |

Current reusable branches:

- `fix/semantic-theme-roles`: exact authored semantic roles, selection/focus separation, black-channel handling and ES5 shared rendering. Its PR remains parked; keeping the code on a branch does not publish a PR.
- `fix/legacy-display-state`: CSS-variable fallback preserves runtime visibility.
- `fix/disabled-weather-fetch`: disabled widgets do not fetch forecasts.
- `feat/home-profile`: optional validated fallback catalogs/defaults and a truthful plain-text terminal summary. See `webos/HOME-PROFILES.md` on that branch/integration.

All four start at upstream, **not each other**. Their public tests need only Node. The workflow is deliberately a separate branch so tool/profile changes cannot contaminate a feature PR.

## One-time setup

The existing local checkout and ignored profile are already initialized. For a fresh checkout:

```sh
gh repo clone OldJobobo/omarchytv
cd omarchytv
git remote add upstream "$(gh repo view piermark/omarchytv --json url --jq '.url + ".git"')"
git fetch upstream main
git switch --track origin/fork/workflow
./fork/dev setup
npm_config_cache="$PWD/.local/npm-cache" npm ci --prefix fork --ignore-scripts
```

Restore the ignored profile from a **private** backup; Git does not contain or back it up. This session's original off-device artifacts remain untouched too. The example profile is a schema template, not a complete licensed asset collection or hardware inventory.

`setup` installs a conservative, owned pre-push guard, preserves unrelated hooks, disables upstream pushes, and keeps `.local/` ignored even when checking out an upstream-only feature. Dependency installation is local to `fork/node_modules`; no global packages or TV dependencies are installed. The legacy webOS packaging CLI has deprecated transitive dependencies; it is an isolated off-device build tool, not shipped in the app.

## Routine upstream update

```sh
./fork/dev status
./fork/dev update
./fork/dev update --apply
./fork/dev integrate
./fork/dev build --profile livingroom --package
```

- `update` alone is a local preview, with no fetch/ref changes.
- `--apply` requires clean managed worktrees, fetches upstream, fast-forwards the local mirror, then rebases/tests the workflow and independent feature branches. It never auto-stashes, enables `updateRefs`, or force-pushes. Before-ref snapshots and partial-progress records stay in `.local/updates/`.
- If a rebase conflicts, its worktree is retained with the conflict. Resolve and `git rebase --continue`, or explicitly abort there. Earlier successful rebases are recorded; there is no hidden reset.
- `integrate` creates a detached candidate, merges ready features, runs all combined tests, then moves only the previously recorded disposable ref. User commits/unrecorded refs and checked-out integration refs are not overwritten. Failed candidates stay available for inspection.
- Build-time asset hashes and overlay-base hashes catch stale/generated/private overlays rather than silently hiding upstream changes. Review an overlay against the new upstream file before updating its pin.
- The remote fork's `main` is not silently pushed. Updating/publishing remote refs is a separate, authorized operation.

Upstream may add UI, runtime behavior or hardware requirements. A successful source build does not authorize deployment or establish old-TV acceptance. Review upstream changes and the candidate before touching the running system.

## Add a fix or feature

```sh
./fork/dev feature fix/short-description
```

The returned worktree starts at `upstream/main`, with no operator files or workflow commits. Make a small source change, add a focused test and commit it there. When ready, add its branch to `fork/series.json` on `fork/workflow`, commit that list change, then rebuild integration. Unfinished branches are not integrated automatically.

Before an authorized publication:

```sh
./fork/dev pr-diff fix/short-description
./fork/dev audit-public fix/short-description
```

Review the whole diff, tests and attribution. Only then explicitly push that feature to `origin`, and create its PR against `piermark/omarchytv:main` with the feature as head. Rebased, already-published branches need an explicitly authorized `--force-with-lease`, never a blind force. Do not push `livingroom` as an upstream PR branch.

The guard scans **every fork-only commit**, including private content removed before the tip. It blocks obvious private artifacts, raw image/package additions, private-LAN literals, home paths and private-key markers. This is a backstop, not a general secret detector, asset-license review or permission to publish.

## Private profile contract

`profile.json` contains a `home` object for the optional source interface plus excluded theme IDs, manifest inspectability and an app-size budget. Optional `terminalLogo` replaces only the terminal's wordmark at build time (plain text or block art, at most 4096 characters); omit it to retain upstream branding. Keep personal wordmarks in the ignored profile. Test the composer with `node --test fork/tests/*.test.cjs`. Existing user localStorage wins over defaults; fresh defaults do not force a theme on an existing user.

`catalog.json` contains only `extraThemes` and static `wallpapers` mappings. **Stock palettes come from the selected upstream source**, so new upstream palette corrections are not frozen into an old data dump. Authored RGB values in additional palettes remain exact. Per-theme shell styles are not fabricated or inferred.

`assets.json` pins the relative filenames and SHA-256 values in `assets/`: fonts/generated upstream resources, bounded stills and notices. Assets cannot mask changed source files. Wallpaper paths must be local WebP stills, at most 1920×1080; animated media and video are refused. Catalog intros are empty. No runtime image collection, service or timer is added by the profile layer.

`overlay-base.json` pins original upstream hashes for intentional private code overlays in `overlay/`. The current legacy Home adapter is such an overlay; it is not mixed into a generic PR. External Homebrew SSH repair, privacy controls, inspector protection and startup hooks remain separately managed. The build does not install or reconfigure them.

`build` archives the committed integration source, adds only pinned profile files, composes data without evaluating data scripts, validates entrypoint ES5, resolves all palettes, checks asset paths/dimensions/budget, then packages with `--no-minify`. It never modifies the source checkout or deployed snapshot. The manifest records every app/profile file hash, source commit, tool lock and IPK hash. Matching inputs reproduce app-file contents; the SDK's container metadata is not promised bit-for-bit reproducible.

A newly source-built upstream-version candidate is **not** identical to the reviewed older deployed minified package. The recovery snapshot retains that exact package. Build output says `built-not-deployed`; never infer that a current TV state or historical preferences should be restored automatically.

`--[ Pi :: gpt-6.1-sol ]--`\
   `--- on behalf of:` @OldJobobo
