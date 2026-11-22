# Plan: Deploy a devbox on Hetzner (deploy)

**Status:** Planned (2026-11-22). Workstream scoped; awaiting kickoff: `deploy-t01` runs once this plan is merged and synced and `devbox-t06` has a PR. Roadmap: [NEXT.md item 19](../../NEXT.md#19-deploy-a-devbox).

---

## Execution Plan

### Locked Decisions

| Decision | Choice |
|---|---|
| Engine | **Terraform or OpenTofu, with the `hetznercloud/hcloud` provider.** The factory ships the module and runs `init`, `apply`, `plan` and `destroy` in a working directory of its own under `$FACTORY_HOME/deploy/NAME/`, where the local state lives. `deploy.engine` picks the binary; unset, it is the first of `terraform` and `tofu` on PATH |
| Secrets | **Over SSH after boot.** `factory deploy` writes the provider keys and the GitHub token into a file only the box's `factory` user can read, sending them on SSH's standard input, never in a command line. cloud-init `user_data`, which Hetzner stores and serves from its metadata service, and the Terraform state hold no secret. `HCLOUD_TOKEN` stays on the deploying machine |
| GitHub | **A fine-grained token from your account,** scoped to the one repository and read from `FACTORY_DEPLOY_GH_TOKEN`. PRs from the box are opened as you, as they are today. The deploying machine's own `gh` login is never copied |
| Lifecycle | **A ready box only.** `factory deploy` creates the box, or brings an existing one up to date when run again, and bootstraps it. `factory deploy --destroy --yes` deletes it. Starting `factory start` on the box stays yours, as on any devbox |

### Milestones

| # | Deliverable | Exit criteria | Parallelizable with |
|---|---|---|---|
| **M1** | The module and its settings | The t01 tests in `tests/test_deploy.py` pass | — |
| **M2** | `factory deploy` provisions and destroys | The t02 tests in `tests/test_deploy.py` pass | — |
| **M3** | The box is ready to run | The t03 tests in `tests/test_deploy.py` pass | — |
| **M4** | Docs | `tests/test_templates.py::test_the_docs_describe_deploy` passes, and `tests/test_templates.py` passes | — |

**Sequence:** `[devbox-t06 →] M1 → M2 → M3 → M4`. t01, t02 and t03 share `factory/deploy.py` and `tests/test_deploy.py`. t02 and t03 also share the `deploy` command in `factory/cli.py`.

### Task Contracts

| Milestone | Task IDs | Coverage |
|---|---|---|
| **M1** | `deploy-t01` | The `deploy:` settings in `factory/config.py`; the shipped module and cloud-init in `factory/templates/deploy/hetzner/`; rendering the working directory in new `factory/deploy.py`; new `tests/test_deploy.py` |
| **M2** | `deploy-t02` | `factory deploy`, `--dry-run` and `--destroy --yes` in `factory/cli.py` and `factory/deploy.py`, running the engine; tests in `tests/test_deploy.py` |
| **M3** | `deploy-t03` | Bootstrapping over SSH in `factory/deploy.py`: secrets, `gh`, git identity, clone, factory install, the sandbox check and `factory sync`; tests in `tests/test_deploy.py` |
| **M4** | `deploy-t04` | `docs/reference.md`, `docs/architecture.md`, `README.md`, `NEXT.md` and the factory-ops skill (template and installed copy); a new test in `tests/test_templates.py` |

```yaml
- id: deploy-t01
  goal: "`deploy:` in .factory/config.yaml describes one Hetzner box, and the factory ships a Terraform module and cloud-init for it. `deploy.render(cfg, home)` writes the module and the settings' variables into $FACTORY_HOME/deploy/NAME/ without any secret. Nothing runs Terraform yet"
  spec_refs:
    - "docs/plans/deploy.md#settings"
    - "docs/plans/deploy.md#the-module"
    - "factory/config.py"
  depends_on:
    - devbox-t06
  non_goals:
    - "Running Terraform or OpenTofu (deploy-t02)"
    - "Anything over SSH (deploy-t03)"
    - "Providers other than Hetzner, or more than one box per config"
    - "Changing this repository's .factory/config.yaml"
  acceptance:
    - "Config has a `deploy` field, None when the key is absent. Under `deploy:` the keys are provider (only `hetzner`), name (default `factory-devbox`), server_type (default `cx33`), location (default `fsn1`), image (default `ubuntu-24.04`), ssh_key (default `~/.ssh/id_ed25519.pub`), ssh_from (default [`0.0.0.0/0`, `::/0`]) and engine (`terraform` or `tofu`, default unset). An unknown key, a provider other than hetzner, an engine other than those two, or a name that isn't 1-63 lowercase letters, digits and hyphens raises ConfigError naming the key"
    - "factory/templates/deploy/hetzner/ holds main.tf, variables.tf, outputs.tf and cloud-init.yaml. main.tf requires the hetznercloud/hcloud provider at a pinned major version and declares an hcloud_ssh_key, an hcloud_firewall that allows inbound TCP 22 only from var.ssh_from, and an hcloud_server with that key, that firewall, the label factory = var.name, and user_data from cloud-init.yaml. outputs.tf outputs ipv4 and ipv6. No file reads HCLOUD_TOKEN or declares a variable for it: the provider reads it from the environment"
    - "cloud-init.yaml creates a user `factory` without sudo whose authorized key is the deploy key. It disables SSH password logins and installs git, curl, ca-certificates, bubblewrap and gh, the last from GitHub's apt repository. It installs uv for the factory user into ~/.local/bin and lets that user run bubblewrap, adding an AppArmor profile where the image restricts unprivileged user namespaces. It ends by writing /var/lib/factory/cloud-init-done. It contains no token, key or password"
    - "`deploy.render(cfg, home)` copies the module into home/deploy/NAME/, keeping a .terraform directory and any state already there. It writes terraform.tfvars.json with name, server_type, location, image, ssh_from and the ssh_key file's contents, and returns the directory. A missing ssh_key file raises DeployError `ssh key FILE not found: set deploy.ssh_key or create the key`. The directory and its files are readable only by their owner"
    - "A test asserts that no rendered file holds the value of HCLOUD_TOKEN, FACTORY_DEPLOY_GH_TOKEN or any provider key set in the environment"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_deploy.py::test_deploy_settings_have_defaults_and_reject_unknown_keys tests/test_deploy.py::test_the_module_declares_the_key_firewall_and_labelled_server tests/test_deploy.py::test_cloud_init_sets_up_the_factory_user_without_secrets tests/test_deploy.py::test_render_writes_the_module_and_variables_without_secrets"
    - "uv run pytest -q tests/test_deploy.py tests/test_config.py"
  risk: low

- id: deploy-t02
  goal: "`factory deploy` provisions the configured Hetzner box by running Terraform or OpenTofu on the rendered directory and prints its address. `--dry-run` shows the plan, and `--destroy --yes` deletes the box. It refuses before running anything when the engine, HCLOUD_TOKEN or the settings are missing"
  spec_refs:
    - "docs/plans/deploy.md#provisioning"
    - "factory/deploy.py"
    - "factory/cli.py"
  depends_on:
    - deploy-t01
  non_goals:
    - "Bootstrapping the box over SSH (deploy-t03)"
    - "Remote state backends, workspaces, or importing an existing server"
    - "Showing or managing the box anywhere but this command"
  acceptance:
    - "`factory deploy` exits 1 before running anything when: the config has no `deploy:` section (`no deploy: section in .factory/config.yaml`); the engine named by deploy.engine, or with none set both terraform and tofu, isn't on PATH (`deploy needs terraform or tofu on PATH`); or HCLOUD_TOKEN is unset (`set HCLOUD_TOKEN to a Hetzner Cloud API token first`)"
    - "Otherwise it renders the directory, then runs ENGINE init -input=false, then ENGINE apply -input=false -auto-approve in that directory. Each runs with TF_IN_AUTOMATION=1 and with HCLOUD_TOKEN taken from its own environment, and streams its output. It then runs ENGINE output -json and prints `NAME is up: ssh factory@IPV4`. A failing engine command stops the deploy with exit 1 and `ENGINE STEP failed (exit N)`"
    - "`factory deploy --dry-run` runs init, then ENGINE plan -input=false, and changes nothing else"
    - "`factory deploy --destroy` prints `this deletes NAME and everything on it, including its board; run again with --yes` and exits 1 without running the engine. With `--yes` it runs ENGINE destroy -input=false -auto-approve, then prints `NAME is gone`"
    - "No engine command line, and nothing the deploy writes, holds the value of HCLOUD_TOKEN"
    - "Tests run against a fake engine executable on PATH that records its arguments, working directory and environment, and prints a canned output -json. No test reaches the network"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_deploy.py::test_deploy_refuses_without_settings_engine_or_token tests/test_deploy.py::test_deploy_runs_init_and_apply_and_prints_the_address tests/test_deploy.py::test_dry_run_only_plans tests/test_deploy.py::test_destroy_needs_yes tests/test_deploy.py::test_the_token_never_reaches_a_command_line_or_file"
    - "uv run pytest -q tests/test_deploy.py"
  risk: medium

- id: deploy-t03
  goal: "After provisioning, `factory deploy` bootstraps the box over SSH so it is ready to run the worker. It waits for cloud-init, writes the secrets for the factory user, logs gh in with the token, sets the git identity, clones the repository, installs the same factory, checks the sandbox, runs `factory sync`, and prints the next steps. Running it again brings the box up to date"
  spec_refs:
    - "docs/plans/deploy.md#bootstrap"
    - "docs/plans/deploy.md#secrets"
    - "factory/deploy.py"
    - "factory/version.py"
  depends_on:
    - deploy-t02
  non_goals:
    - "Starting `factory start` or installing a service on the box"
    - "Copying a board between machines"
    - "Copying the deploying machine's gh login"
  acceptance:
    - "`factory deploy` also exits 1 before running the engine when FACTORY_DEPLOY_GH_TOKEN is unset (`set FACTORY_DEPLOY_GH_TOKEN to a fine-grained GitHub token for this repository first`), or when a provider key that the config's flows need is unset (`set KEY first`)"
    - "Every SSH command runs the system ssh as factory@IPV4. It uses BatchMode=yes, StrictHostKeyChecking=accept-new and a known_hosts file in the deploy directory. The deploy waits up to 10 minutes for SSH to answer and /var/lib/factory/cloud-init-done to exist, and stops with exit 1 and `the box isn't ready after 10 minutes` when they don't"
    - "Secrets travel only on ssh's standard input. The deploy writes ~/.config/factory/env (mode 600) on the box with export lines for each provider key the config's flows need. ~/.profile sources it. It runs gh auth login --with-token with FACTORY_DEPLOY_GH_TOKEN on standard input, then gh auth setup-git. A test asserts no ssh argument holds a secret's value"
    - "It sets the box's git user.name and user.email to this checkout's. It clones origin's URL into ~/REPO, or fetches and fast-forwards the trunk when ~/REPO already exists"
    - "When the repository is the factory itself, it installs the factory as uv tool install --editable ~/REPO. Otherwise it installs the factory at the commit this one runs from, or at its version's tag when that commit isn't known"
    - "It checks the sandbox by running bwrap --ro-bind / / --dev /dev true as the factory user. When that fails it stops with exit 1 and `bubblewrap can't run on the box: OUTPUT`. Then it runs factory sync in ~/REPO"
    - "It ends by printing three lines: `ssh factory@IPV4`, `cd REPO && factory start --budget USD`, and `ssh -L 8765:127.0.0.1:8765 factory@IPV4, then factory web --no-open on the box`"
    - "Run again against the same box, every step succeeds without duplicating its effects. ~/.profile sources the env file once"
    - "Tests run against a fake ssh executable on PATH that records each call's arguments and standard input, and answers the readiness check. No test reaches the network"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_deploy.py::test_deploy_refuses_without_the_github_token_or_provider_keys tests/test_deploy.py::test_bootstrap_waits_for_cloud_init_then_gives_up tests/test_deploy.py::test_secrets_go_on_ssh_stdin_only tests/test_deploy.py::test_bootstrap_clones_installs_checks_the_sandbox_and_syncs tests/test_deploy.py::test_a_second_deploy_updates_the_box_in_place tests/test_deploy.py::test_deploy_prints_the_next_steps"
    - "uv run pytest -q tests/test_deploy.py tests/test_version.py"
  risk: medium

- id: deploy-t04
  goal: "The docs describe `factory deploy`: docs/reference.md, docs/architecture.md, README.md, NEXT.md and the factory-ops skill, in its template and installed copy"
  spec_refs:
    - "docs/plans/deploy.md#design"
    - "docs/reference.md"
    - "docs/architecture.md"
    - "README.md"
    - "NEXT.md"
  depends_on:
    - deploy-t03
  non_goals:
    - "Changing behaviour"
    - "Docs for providers other than Hetzner"
  acceptance:
    - "docs/reference.md lists `factory deploy` with `--dry-run`, `--destroy` and `--yes`, and the deploy settings with their defaults. It names the environment variables HCLOUD_TOKEN and FACTORY_DEPLOY_GH_TOKEN and the fine-grained token's repository permissions: Contents, Pull requests and Workflows read and write; Actions, Checks and Commit statuses read. Its troubleshooting table has rows for each refusal and for `bubblewrap can't run on the box`"
    - "docs/architecture.md has a section headed `## Deploying a devbox` covering: the module and the state under $FACTORY_HOME/deploy/NAME/; what cloud-init installs; how the secrets travel, and that user_data and the state hold none; the bootstrap steps; re-running; and destroying, which deletes the box's board while PRs stay on GitHub for another board's refresh to take up. Its Policy says `factory deploy` spends money and is run by you, never by an agent"
    - "README.md's `## Run it on a devbox` section starts with `factory deploy` for Hetzner, before the by-hand setup"
    - "NEXT.md's item 19 row and section say deploy is done and link docs/architecture.md#deploying-a-devbox"
    - "The factory-ops skill has request rows for deploying a devbox, destroying it, and the token permissions. They are in factory/templates/skills/factory-ops/SKILL.md and .claude/skills/factory-ops/SKILL.md, which stay identical"
    - "docs/sessions/ has this task's session log entry, as the project rules require"
  verification:
    - "uv run pytest -q tests/test_templates.py::test_the_docs_describe_deploy"
    - "uv run pytest -q tests/test_templates.py"
  risk: low
```

Planned test additions, all new:
- **`deploy-t01`:** a new `tests/test_deploy.py` with four tests.
- **`deploy-t02`:** five tests added to `tests/test_deploy.py`.
- **`deploy-t03`:** six tests added to `tests/test_deploy.py`.
- **`deploy-t04`:** `tests/test_templates.py::test_the_docs_describe_deploy`.

The engine and ssh are fake executables on PATH, so every test runs offline in the sandbox. Every contract names a test that doesn't exist yet, so each one fits this repository's `strict` flow. Each verification filter must select its tests; zero matching tests is not a pass.

Done by hand: a real deploy. Running `factory deploy` against a Hetzner project spends money and needs `HCLOUD_TOKEN`, `FACTORY_DEPLOY_GH_TOKEN` and the provider keys, so no task runs it. The manual check is under [Verification](#verification).

### Risks

1. **bubblewrap is blocked on the image.** Ubuntu 24.04 restricts unprivileged user namespaces through AppArmor, which can stop `bwrap`, and the factory refuses to run without it. **Action:** cloud-init adds an AppArmor profile that lets `bwrap` create user namespaces. The bootstrap then runs `bwrap` as the factory user and stops with its output when it fails, so a broken sandbox never reaches `factory start`.
2. **Secrets leak through the provisioning path.** Hetzner keeps `user_data`, Terraform keeps state, and command lines show up in process lists. **Action:** secrets go only on ssh's standard input into a mode-600 file. `HCLOUD_TOKEN` reaches the engine only through its environment. Tests assert no rendered file, command line or ssh argument holds a secret's value.
3. **The state file is lost or copied.** Losing `$FACTORY_HOME/deploy/NAME/terraform.tfstate` orphans the server, which still bills. **Action:** the server carries the label `factory=NAME`, so it can be found in the Hetzner console. The docs say to keep the deploy directory and how to delete the server by hand. The state holds no secret.
4. **SSH is open to the internet.** The firewall allows port 22 from `ssh_from`, which defaults to everywhere. **Action:** key-only logins, no password authentication, a `factory` user without sudo, and `deploy.ssh_from` to narrow the range. The web page stays loopback-only and is reached through `ssh -L`.
5. **Two boards run one backlog.** The box gets its own board, while the laptop's board still exists. **Action:** the docs say to stop running the backlog on the laptop once the box runs it. `factory status --refresh` on the box takes up the open `factory/*` PRs. Claiming tasks across boards stays out of scope.
6. **Hetzner types and prices move.** CX plans were repriced and some older ones withdrawn in 2026. **Action:** `server_type`, `location` and `image` are settings, the default is the current CX33, and the docs point at Hetzner's own page for prices.

---

## Problem

[devbox](devbox.md) gives the factory `factory start`, a worker that runs the backlog unattended, but someone still has to build the box it runs on. That README section (`devbox-t06`) lists the steps by hand:
- a Linux server;
- bwrap working;
- uv and gh installed;
- an authenticated gh;
- the provider key in the worker's environment;
- the repository cloned and the factory installed at a matching version.

Each step is easy to get wrong in a way that only shows hours later: a sandbox that refuses to start, a broad personal token copied onto a server, a key left in shell history. Nothing in the factory provisions or tears down a machine (`factory/` has no cloud code), and agents are refused `terraform apply` and `destroy` (`factory/tools.py:22`). So deploying belongs to a command you run.

## Goal

With `HCLOUD_TOKEN`, `FACTORY_DEPLOY_GH_TOKEN` and the provider keys set, `factory deploy` creates a Hetzner box that is ready to run the backlog and prints how to start the worker on it. Running it again brings the box up to date, and `factory deploy --destroy --yes` removes it.

## Design

### Settings

```yaml
deploy:
  provider: hetzner
  name: factory-devbox          # server name, firewall and key names, label factory=<name>
  server_type: cx33             # 4 vCPU, 8 GB
  location: fsn1
  image: ubuntu-24.04
  ssh_key: ~/.ssh/id_ed25519.pub
  ssh_from: ["0.0.0.0/0", "::/0"]
  # engine: tofu                # default: the first of terraform, tofu on PATH
```

### The module

`factory/templates/deploy/hetzner/` is packaged with the factory, since hatch ships everything under `factory/`:

```text
main.tf        terraform { required_providers { hcloud = { source = "hetznercloud/hcloud", version = "~> 1.0" } } }
               hcloud_ssh_key      deploy key (var.ssh_public_key)
               hcloud_firewall     inbound tcp 22 from var.ssh_from; nothing else
               hcloud_server       var.server_type, var.image, var.location, the key, the firewall,
                                   labels { factory = var.name }, user_data = file("cloud-init.yaml")
variables.tf   name, server_type, location, image, ssh_public_key, ssh_from
outputs.tf     ipv4, ipv6
cloud-init.yaml  user factory (no sudo, key only) · no password SSH · git curl ca-certificates bubblewrap
                 · gh from GitHub's apt repository · AppArmor profile for bwrap · uv in ~factory/.local/bin
                 · touch /var/lib/factory/cloud-init-done
```

`deploy.render` copies these into `$FACTORY_HOME/deploy/NAME/` and writes `terraform.tfvars.json` from the settings. It leaves `.terraform/`, the lock file and the state where they are, so re-running is a normal Terraform update.

### Provisioning

```text
factory deploy [--dry-run | --destroy [--yes]]
  refuse: no deploy: · no engine · no HCLOUD_TOKEN · (t03) no FACTORY_DEPLOY_GH_TOKEN · missing provider keys
  render $FACTORY_HOME/deploy/NAME/
  ENGINE init -input=false
  ├─ --dry-run   ENGINE plan -input=false
  ├─ --destroy   (needs --yes) ENGINE destroy -input=false -auto-approve ─► "NAME is gone"
  └─ default     ENGINE apply -input=false -auto-approve ─► ENGINE output -json ─► bootstrap (t03)
```

The engine runs on your machine with your environment, so the hcloud provider reads `HCLOUD_TOKEN` itself. It never runs in an agent's sandbox, where `terraform apply` and `destroy` stay refused.

### Secrets

| Secret | Lives on | Reaches the box |
|---|---|---|
| `HCLOUD_TOKEN` | the deploying machine | never |
| `FACTORY_DEPLOY_GH_TOKEN` (fine-grained, one repository) | the deploying machine | ssh stdin → `gh auth login --with-token` (gh keeps it in `~factory/.config/gh/hosts.yml`) |
| provider keys (`OPENROUTER_API_KEY`, …) | the deploying machine | ssh stdin → `~factory/.config/factory/env` (mode 600), sourced by `~/.profile` |

The token's repository permissions are:
- **Read and write:** Contents, for pushing `factory/*` branches; Pull requests; Workflows, for pushing a branch that touches `.github/workflows`.
- **Read:** Actions, for the CI logs that `ci_failed` fixes need; Checks; Commit statuses.

The worker reads the env file through the shell you start it from. Agents never see it, because the sandbox clears the environment.

### Bootstrap

```text
wait ≤ 10 min: ssh answers and /var/lib/factory/cloud-init-done exists
write ~/.config/factory/env (stdin) · source it from ~/.profile (once)
gh auth login --with-token (stdin) · gh auth setup-git
git config --global user.name / user.email (from this checkout)
clone origin into ~/REPO, or fetch and fast-forward the trunk
install the factory: editable from ~/REPO for the factory itself, else pinned to this factory's commit or tag
bwrap --ro-bind / / --dev /dev true          (the sandbox works, or stop)
factory sync in ~/REPO
print: ssh factory@IP · cd REPO && factory start --budget USD · ssh -L 8765:127.0.0.1:8765 factory@IP
```

Every step is idempotent, so `factory deploy` on an existing box only updates it.

## Files Changed

| File | Change |
|---|---|
| `factory/config.py` | `DeployConfig` and the `deploy` field (t01) |
| `factory/templates/deploy/hetzner/main.tf`, `variables.tf`, `outputs.tf`, `cloud-init.yaml` | New: the module (t01) |
| `factory/deploy.py` | New: render (t01), the engine runs (t02), the bootstrap (t03) |
| `factory/cli.py` | `factory deploy` (t02, t03) |
| `tests/test_deploy.py` | New: t01, t02 and t03 tests |
| `tests/test_templates.py` | t04 test |
| `docs/reference.md`, `docs/architecture.md`, `README.md`, `NEXT.md`, factory-ops skill (template and installed copy) | t04 |

## Test Plan

### Unit tests

- **t01:**
  - settings defaults and each ConfigError;
  - the module declares the key, the firewall (port 22 only) and the labelled server, and has no token variable;
  - cloud-init creates the `factory` user without sudo, sets up bwrap and uv, and holds no secret;
  - render copies the module, writes the variables, keeps `.terraform/` and the state, sets owner-only permissions, and writes no secret.
- **t02,** with a fake engine on PATH:
  - each refusal;
  - init then apply, with the token only in the environment, and the printed address;
  - `--dry-run` only plans;
  - `--destroy` without `--yes` runs nothing, and with it destroys;
  - the token appears in no argument or file.
- **t03,** with a fake ssh on PATH:
  - the token and key refusals;
  - the readiness wait, and giving up at 10 minutes, with an injected clock;
  - secrets only on stdin;
  - clone, install (editable versus pinned), the sandbox check and `factory sync`;
  - a second deploy updates in place, sourcing the env file once;
  - the three next-step lines.

### End-to-end tests

- **t02 and t03:** `factory deploy` through `cli.main` against the fake engine and the fake ssh together. Nothing reaches the network.
- **t04:** `tests/test_templates.py::test_the_docs_describe_deploy` checks the documented command, settings, variables, permissions and README section.

## Verification

- Every contract's verification passes at its candidate.
- **By hand, after t03,** with a Hetzner project and the three secrets set:
  1. `factory deploy --dry-run` shows one key, one firewall and one server.
  2. `factory deploy` prints `factory-devbox is up` and the next steps.
  3. On the box, `factory start --budget 2 --until-idle` builds one ready task's PR, which appears on GitHub as opened by you.
  4. A second `factory deploy` changes nothing and succeeds.
  5. `factory deploy --destroy --yes` removes the server, and the Hetzner console shows no server labelled `factory=factory-devbox`.

## Cross-Workstream Coordination

- **Depends on:** [devbox](devbox.md). `deploy-t01` waits for `devbox-t06`, the last devbox task, so a deployed box runs the finished worker and its README section exists to extend.
- **Required by:** none.
- **Overlaps, with no ordering:** [security-review](security-review.md) `security-review-t02` changes `factory/config.py`, and `security-review-t06` changes `factory/cli.py`. The factory's conflict resolution handles them.
- **Related:** NEXT.md item 6 ("Runs need this machine"). One deployed box runs the backlog; a shared board and hosted workspaces stay open there.

## Notes / Out of Scope

- **Running the worker as a service on the box** (the Lifecycle decision). You start `factory start` over SSH, in tmux or screen.
- **Status, SSH or tunnel subcommands.** The deploy prints the commands to use.
- **Providers other than Hetzner, several boxes, remote Terraform state, workspaces,** and importing an existing server.
- **A bot GitHub account.** PRs from the box are opened as you, by the fine-grained token.
- **Copying the laptop's board to the box, or the box's board back before a destroy.** PRs stay on GitHub, and a refresh takes them up.
- **Backups, monitoring, and OS upgrades of the box beyond cloud-init's first boot.** A re-run of `factory deploy` updates the factory and the repository, not the OS.
