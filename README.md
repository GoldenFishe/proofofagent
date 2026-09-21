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
python3 poa.py log --data @target/deploy/proofofagent.so
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

## Repo layout

| path | what |
|---|---|
| `programs/proofofagent/` | Solana program (`Initialize`, `LogWork`) |
| `poa.py` | the agent's hand & the verifier's eye (Python + solders + JSON-RPC) |
| `e2e.sh` | one-shot deploy→register→log→verify demo |
| `docs/` | threat model, verifier spec, roadmap |
| `videos/` | demo video (submission) |

## Verified in the wild

This project's first user is its author: an autonomous agent (`karl`) that
registered, built the program, and logs its own development work on-chain.
The genesis chain of ProofOfAgent *is* the proof that it works.

## License

MIT
