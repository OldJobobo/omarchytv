# Fork development

Read `FORK.md` before changing this fork's workflow or deployment profile.

- Keep `main` an unmodified upstream mirror. The primary checkout stays on `fork/workflow`.
- Start independently upstreamable changes from `upstream/main` in their own worktrees: `./fork/dev feature fix/name` or `feat/name`.
- `livingroom` is a tested, disposable integration ref, not an upstream PR branch. Do not hand-edit or commit on it.
- Keep every operator profile, real app/input list, host/key detail, recovery package, personal screenshot and third-party artwork under ignored `.local/`. Never force-add them.
- Feature branches must not depend on `fork/workflow` tooling or private files to run their public tests.
- Add ready features to `fork/series.json`; do not integrate unfinished work automatically.
- Update with guarded rebases, not merges of main into feature branches. Never auto-stash, hard-reset a user branch, or overwrite unrecorded integration commits.
- Every private code overlay must pin and check its upstream base hash, so upstream changes cannot be silently masked.
- Keep TV-entrypoint JavaScript ES5 and theme roles faithful to authored values. No runtime dependency/service/timer additions for profile handling.
- Helpers build off-device only. No command here is approval to install/reload/reboot the TV, change foreground/preferences, enable debug access, or weaken SSH/privacy/Home recovery.
- Pushing, force-pushing, uploading screenshots and publishing PRs require explicit operator authorization. Use independent feature branches, never the integration branch, for upstream PRs.

Checks:

```sh
node --test webos/tests/*.test.js
python -m unittest discover -s fork/tests -v
./fork/dev audit-public HEAD
```

Use `./fork/dev integrate` for the combined feature tests, followed by `./fork/dev build --package` for the private source/profile candidate. A built package is **not** a deployed or hardware-accepted package.
