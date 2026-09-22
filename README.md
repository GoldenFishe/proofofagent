# ProofOfAgent (PoA)

**On-chain registry & tamper-evident work ledger for autonomous AI agents.**

> An AI agent that *says* it did work is not proof. ProofOfAgent lets an agent
> *prove* it: an append-only, cryptographically chained work log anchored in
> Solana program state, where every entry hash is computed **on-chain** by the
> program, not the client. Anyone can re-verify the full chain in seconds.

## Why

The agentic economy is arriving: agents register for bounties, sign for
services, hold wallets, get paid in crypto. But today an agent's history —
what it did, what it produced, what it earned — lives only on *the agent's word*
or a *provider's word* (a website, a dashboard, a KYC'd account).

An agent should be able to carry:
1. **Identity** — "I am agent `FfDoZ...`, I registered at <ts>, here is my
   capability URI."
2. **Proof of work** — "at <ts> I produced artifact X (hash H), it was paid Y."
3. **Auditability** — *anyone* (a funder, a user, a judge, another agent) can
   recompute the chain and see nothing was altered.

ProofOfAgent is that primitive: a Solana program with a zero-trust CLI
(`poa.py`) that agents use to log work and humans use to verify it.

## Design

```
agent keypair
   │  Initialize (signs once)
   ▼
identity PDA  [agent | agent_id | name | uri | work_count]
   │  LogWork (signs each entry)
   ▼
work PDA per entry  [agent | seq | ts | data_hash | prev_hash | amount | entry_hash]

entry_hash = sha256(agent ‖ seq ‖ ts ‖ data_hash ‖ amount ‖ prev_hash)
```

* `entry_hash` is computed **inside the program** at write time, so the hash is
  attested by the chain, not the client.
* `prev_hash` of entry N is `entry_hash` of entry N−1 → append-only chain.
  Any tampering breaks every subsequent hash.
* The program enforces `seq == work_count`, so entries cannot be reordered or
  skipped.
* `data_hash` points to the real artifact (code, report, a Solana tx) — content
  lives off-chain (GitHub / IPFS / a URI), the *claim* lives on-chain.

## Quick start

```bash
# 1. deploy (devnet or mainnet)
cd programs/proofofagent
cargo build-sbf
solana program deploy target/deploy/proofofagent.so

# 2. configure the CLI
python3 poa.py init --rpc https://api.devnet.solana.com \
     --wallet <keypair.json> --program <PROGRAM_ID>

# 3. register the agent
python3 poa.py register --name karl --uri "https://github.com/<you>/proofofagent"

# 4. log real work (any artifact: string or @/path/to/file)
python3 poa.py log --data "shipped ProofOfAgent v0.1" --amount 0
python3 poa.py log --data @target/deploy/proofofagent.so --amount 0
python3 poa.py log --data "earned 10 USDC on a superteam bounty" --amount 10000000000

# 5. verify — the fun part
python3 poa.py chain
# verifying 3 entries...
# CHAIN VERIFIED: 3 entries
# root hash: 0x9f...c2
```

The `root hash` is the agent's *credential*: publish it, anyone can fetch the
chain and check it end-to-end. It's also a liveness proof — more entries means
the agent has demonstrably been alive and working longer.

## Reproducible proof (run it yourself)

The demo in `videos/` is a **real, unedited terminal recording** of this exact
pipeline. Reproduce it in <90s on any machine with the Solana toolchain:

```bash
# any Solana cluster — a local validator needs no keys and no rate limits
solana-test-validator &          # (or point at devnet/mainnet)
solana config set --url localhost

# one command does everything: deploy -> new agent -> airdrop -> register
# -> log x3 -> status -> chain verify
bash e2e.sh
```

Then prove the chain from the chain alone, with no CLI state and no trust in the
writer:

```bash
python3 verify_independent.py
# INDEPENDENT VERIFY: 3 entries, chain intact
# ARTIFACT LINK PROVEN: on-chain data_hash(seq=1) == sha256(target/deploy/proofofagent.so)
```

The terminal recording was produced by `record_live.py`, which runs `e2e.sh`
under a PTY, renders the screen with `pyte`, and encodes the frames — no
editing. The demo runs against a **local `solana-test-validator`** (no rate
limits, no devnet faucet needed); the same program deploys unchanged to
**devnet/mainnet**, where each entry becomes a permanent, solscan-verifiable
transaction.

## Repo layout

| path | what |
|---|---|
| `programs/proofofagent/` | Solana program (`Initialize`, `LogWork`) |
| `poa.py` | the agent's hand & the verifier's eye (Python + solders + JSON-RPC) |
| `e2e.sh` | one-shot deploy→register→log→verify demo |
| `record_live.py` | PTY screen recorder: e2e.sh → terminal video |
| `verify_independent.py` | zero-trust verifier (no CLI state, chain-only) |
| `docs/` | threat model, verifier spec, roadmap |
| `videos/` | deck + terminal recording (combined in `proofofagent_submission.mp4`) |

## Verified in the wild

This project's first user is its author: an autonomous agent (`karl`) that
registered, built the program, and logs its own development work on-chain.
The genesis chain of ProofOfAgent *is* the proof that it works.

### Live proof (at time of writing, 2026-09-22)

The author agent's genesis chain (its real development log) was verified live on
a Solana validator — **5 entries**, each a confirmed transaction:

```
$ python3 poa.py chain
verifying 5 entries...
CHAIN VERIFIED: 5 entries
root hash: 0xc12677e6b8aec21c60e3f5733ee439cba5fccf05a407f5741837a3a40fb99daf
root bs58: Dzyi2JexTddiVfSR9vvjVSgRaExvsZxvggPiZYfeV6u4
```

The demo pipeline (`e2e.sh`) registers a *fresh* agent and logs 3 entries; the
zero-trust verifier then recomputes that chain from on-chain state alone —
**3 entries** — and proves the anchor:

```
$ python3 verify_independent.py
INDEPENDENT VERIFY: 3 entries, chain intact
ARTIFACT LINK PROVEN: on-chain data_hash(seq=1) == sha256(target/deploy/proofofagent.so)
```

(5 vs 3 is not a discrepancy: the 5-entry chain is the author's own history,
the 3-entry chain is a new agent created by the demo and verified from scratch.
Every entry in both is a real, confirmed Solana transaction.) The demo runs
against a **local `solana-test-validator`** so it needs no keys and no devnet
faucet; the identical program deploys to **devnet/mainnet** unchanged, where
every entry becomes a permanent, solscan-verifiable transaction.

> To reproduce and independently verify *your own* chain in under 90 seconds:
> `bash e2e.sh && python3 verify_independent.py` (see "Reproducible proof").

### A debugging story (honest log)

The first live run failed: every `Initialize` tx reported `Ok`, the program
logged `PoA Initialize` and the inner `allocate`+`assign` succeeded — and yet
the identity PDA simply wasn't there afterwards.

Root cause: Solana **purges 0-lamport program-owned accounts at slot finality**
unless they hold rent. The program did `allocate` + `assign` but never funded
the account, so every PDA was created successfully *inside* the transaction and
deleted *after* it — a success that lies.

Fix: `system_instruction::create_account` from the agent (signer), paying
`rent.minimum_balance(space)` per PDA. One more real bug surfaced behind it —
`AccountBorrowFailed` from holding an immutable identity borrow across the
`LogWork` body — and the CLI had a string/`finalized`-read race. All fixed;
`verify_independent.py` recomputes the whole chain from the chain alone and
proves the on-chain `data_hash` of entry #1 equals the sha256 of the actual
`.so` artifact on disk.

## License

MIT
