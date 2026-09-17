# Publishing to this repository

Three POCs live here, each written in its own workspace, often at the same time. The folders never overlap, so parallel work is safe as long as everyone keeps to these rules.

## The rules

1. **One folder per POC, and you only touch yours.** `mcp_sprawl_poc/`, `layered_agent_poc/`, `headless_ai_poc/`. Never stage a change outside your folder. The two shared files, this one and `README.md`, are the only exception, and a change to them is announced first.
2. **Work in your own clone.** Do not share a working copy between sessions or people. A throwaway clone is fine.
3. **Rebase, never force-push.** `git pull --rebase` before pushing. Because the folders are disjoint, a rebase never conflicts. Rewriting published history is a last resort, and only after telling everyone who publishes here.
4. **Run your POC's checks before you push.** At minimum its fast tests and whatever boundary checks it has.
5. **Write your folder in the subject line:** `layered_agent_poc: warn when another process is using Ollama`. The body says what changed and why.
6. **No tool attribution in commit messages or pull requests.** No `Co-Authored-By` for an AI assistant, no "generated with" lines.
7. **Write only inside your own folder at run time.** Point every path an experiment uses at your folder, absolutely. A relative path can resolve against another project's root: that is how a run once mirrored itself into `layered_agent_poc/runs/2026-09-17-recorded/h2/`. For Part 2's platform, that means `LAP_RUNS_DIR`, `LAP_PLATFORM_DB`, `LAP_ENTERPRISE_DB`, `LAP_KNOWLEDGE_INDEX` and `LAP_MODEL_TRAFFIC`.
8. **Importing a neighbouring POC writes into it.** If your checks or experiments import another folder's package, Python leaves `__pycache__` there, and any state that project defaults to its own directory lands there too. Run your checks with `PYTHONDONTWRITEBYTECODE=1`, point every path setting at your own folder, and keep `__pycache__/` in both folders' `.gitignore`. For `layered_agent_poc` that means setting `LAP_KNOWLEDGE_INDEX` as well as the database and runs paths: unset, its runbook index is built inside that POC.
9. **Say when you change something others depend on.** `headless_ai_poc` uses `layered_agent_poc`'s service facade. Changing that facade, its commands or its configuration means telling whoever maintains the dependent POC, in the commit body and directly.
10. **Keep the machine's models in mind.** The POCs share one Ollama. Check before a long live run, and wait rather than compete: `uv run poc check --wait` in Part 2, or the equivalent elsewhere.

11. **Say which files must never change by accident.** Some committed files are byte-exact artefacts: a published report, a generated catalogue, the evidence of a cited run. List them in `<folder>/.publish-frozen`, one glob per line, `!` to make an exception. The script then refuses a publish that touches them, unless you pass `--allow-frozen` and say why in the message.

    Added files count too, not only modified ones, because a stray file written into a frozen folder by another run is the failure this catches. So the first publish of new evidence under a frozen glob needs `--allow-frozen` once. Deleting a frozen file is refused for the same reason.

## The script

`scripts/publish-poc.sh` enforces rules 1, 3, 4, 5, 6 and 11, and refuses to publish if something looks wrong.

```bash
# from anywhere, with a clone of this repo:
scripts/publish-poc.sh layered_agent_poc \
  --from ~/work/layered-agent-platform \
  --message "layered_agent_poc: warn when another process is using Ollama" \
  --checks "uv run pytest -m 'not ollama' -q && uv run lint-imports"
```

What it does, in order:

1. copies your working copy into the folder with `--from` (honouring each `.gitignore`), or uses what is already there;
2. stages only that folder, and stops if anything outside it is staged or modified;
3. stops if the message names an AI assistant as an author, or does not start with the folder name;
4. refuses if the commit changes a path listed in `<folder>/.publish-frozen`, unless `--allow-frozen`;
5. runs `--checks` inside the folder, or `<folder>/scripts/publish-checks.sh` when it exists;
6. commits, rebases onto `origin/main` and pushes, and prints the new commit.

`--dry-run` stops before the commit and shows what would be published. Every step prints what it is doing, so a failure says which rule stopped it.
