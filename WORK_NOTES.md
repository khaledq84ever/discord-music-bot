# Work Notes — Discord Music Bot

## 2026-06-03 — Dependency upgrade + build-failure fix

Bumped deps, but the first pass **broke the Railway build**:
`PyNaCl>=1.6.2` conflicts with `discord.py[voice] 2.7.1`, which requires
`PyNaCl<1.6,>=1.5.0` → `ResolutionImpossible` (deploy FAILED, 0 active replicas).

**Fix (`requirements.txt`):** `PyNaCl>=1.5.0,<1.6`. Verified the resolution with
`pip install --dry-run` before redeploying.

**Lesson:** the `[voice]` extra caps PyNaCl — don't blindly pin "latest". Always check
`environment_status` + build logs per service after a dep bump.

**Verified:** build → *"Successfully installed PyNaCl-1.5.0 … discord.py-2.7.1"*; deploy
logs → *"Logged in as Music Application#1093 — in 8 servers"*.
**Shipped:** Railway `music-bot` SUCCESS · GitHub `master` commit `ad3718b`.
