# Upstream — en-croissant

**Purpose**: this file is the binding record of which upstream commit our GUI fork is based on, plus a verbatim snapshot of upstream's README and a pointer to upstream's LICENSE.

Maintained per the integration contract: `docs/15_integration_surfaces/en-croissant.md` §1.

## Fork pin

| Field | Value |
|---|---|
| Upstream URL | https://github.com/franciscoBSalgueiro/en-croissant |
| Upstream tag | `v0.15.0` |
| Upstream commit | `6f2d2628f0fbe11cb62a7dd2f9c102bb52907d53` |
| Upstream commit date | 2026-03-17T17:26:54Z |
| Forked into this repo on | 2026-05-18 |
| License (inherited) | **GPL-3.0-only** (see `apps/desktop/LICENSE`) |

The machine-readable form of the commit hash is at `apps/desktop/.upstream-ref` (single line). CI reads this file.

## Upstream LICENSE

The upstream `LICENSE` file is preserved **byte-identically** at `apps/desktop/LICENSE`. Verified at fork time: sha256 `3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986`. CI enforces continued byte-identity (`tools/ci/check_forbidden_paths.py`, to be authored in Phase 1).

The upstream `LICENSE` is the GNU General Public License version 3 (29 June 2007). All CHESS COACH GUI source code — both upstream-inherited and CHESS-COACH-authored — is distributed under GPL-3.0-only.

## Upstream NOTICE

Upstream en-croissant at `v0.15.0` ships **no separate NOTICE file**. Verified at fork time. If a future upstream version adds one, the integration contract requires that we preserve it verbatim alongside the LICENSE file.

## Upstream README (verbatim snapshot at fork time)

What follows is the unmodified text of `README.md` from en-croissant at commit `6f2d2628f0fbe11cb62a7dd2f9c102bb52907d53`, captured here so that the upstream's own description of the project is preserved even though our own `apps/desktop/README.md` replaces it for the CHESS COACH product context.

---

<br />
<div align="center">
  <a href="https://github.com/franciscoBSalgueiro/en-croissant">
    <img width="115" height="115" src="https://github.com/franciscoBSalgueiro/en-croissant/blob/master/src-tauri/icons/icon.png" alt="Logo">
  </a>

<h3 align="center">En Croissant</h3>

  <p align="center">
    The Ultimate Chess Toolkit
    <br />
    <a href="https://www.encroissant.org"><strong>encroissant.org</strong></a>
    <br />
    <br />
    <a href="https://discord.gg/tdYzfDbSSW">Discord Server</a>
    ·
    <a href="https://www.encroissant.org/download">Download</a>
    .
    <a href="https://www.encroissant.org/docs">Explore the docs</a>
  </p>
</div>

En-Croissant is an open-source, cross-platform chess GUI that aims to be powerful, customizable and easy to use.

## Features

- Store and analyze your games from [lichess.org](https://lichess.org) and [chess.com](https://chess.com)
- Multi-engine analysis. Supports all UCI engines
- Prepare a repertoire and train it with spaced repetition
- Simple engine and database installation and management
- Absolute or partial position search in the database

<img src="https://github.com/franciscoBSalgueiro/encroisssant-site/blob/master/public/showcase.webp" />

## Building from source

Refer to the [Tauri documentation](https://tauri.app/start/prerequisites/) for the requirements on your platform.

En-Croissant uses pnpm as the package manager for dependencies. Refer to the [pnpm install instructions](https://pnpm.io/installation) for how to install it on your platform.

```bash
git clone https://github.com/franciscoBSalgueiro/en-croissant
cd en-croissant
pnpm install
pnpm build
```

The built app can be found at `src-tauri/target/release`

## Donate

If you wish to support the development of this GUI, you can do so [here](https://encroissant.org/support). All donations are greatly appreciated!

## Contributing

For contributing to this project please refer to the [Contributing guide](./CONTRIBUTING.md).

## License

This software is licensed under GPL-3.0 License.

---

End of upstream README snapshot.

## Rebase history

_(This section is appended one row per rebase; see integration contract §6.)_

| Date | New upstream commit | New tag | Conflicts encountered | PR | Notes |
|---|---|---|---|---|---|
| 2026-05-18 | `6f2d2628f0fbe11cb62a7dd2f9c102bb52907d53` | `v0.15.0` | initial fork (no rebase) | n/a | initial fork — see commit `HEAD` |

## Attribution

en-croissant is the original work of **Francisco Salgueiro** and contributors. CHESS COACH is a downstream fork. We are not affiliated with or endorsed by en-croissant or its author. Original copyright notices in upstream-inherited source files are preserved unchanged.
