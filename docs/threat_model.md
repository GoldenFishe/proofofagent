# ProofOfAgent — Threat Model & Verifier Spec

## Threat model

### Who
* **Agent** — holds a Solana keypair, may be compromised or malicious.
* **Verifier** — anyone: human, another agent, a judge, a bounty funder.
  Holds only public data (RPC reads). Never holds a key.
* **Chain** — Solana consensus. Assumed honest beyond reasonable doubt.

### What the program guarantees
1. **Authenticity** — only the agent's keypair can write to its accounts
   (all PDAs are seeded with the agent pubkey; agent must sign every ix).
2. **Append-only** — work accounts are PDA-only; once written, data cannot be
   modified (only the owner program writes, and there is no write-after path;
   `seq` is forced to grow by exactly 1).
3. **Chain integrity** — each entry hash is computed on-chain from its fields
   and the previous entry hash. A verifier recomputes `sha256(agent ‖ seq ‖ ts ‖
   data_hash ‖ amount ‖ prev_hash)` and compares with the stored value.
4. **Ordering** — `seq == work_count` enforced on every write; entries are
   dense, 0..N-1.

### What it does NOT guarantee (by design)
* **Off-chain artifact existence** — `data_hash` is a commitment to content;
  the content itself (code, report) must be published elsewhere (IPFS,
  GitHub, a URL in the identity `uri`). The chain proves *an artifact with
  this hash existed when the agent wrote the entry*, not what it does.
* **Timestamp** — `ts` is client-supplied; the entry's slot (block timestamp)
  is the honest upper bound ("written at or after slot T"). We store `ts` for
  agent-side ordering; verifiers who need strictness can use the tx slot.
* **Truthfulness of claims** — the ledger proves *that work was recorded*,
  not *that it was good*. Quality is a separate layer (reputation, market).

### Attack surfaces considered
| Attack | Mitigation |
|---|---|
| Agent rewrites old entry | PDA owner is program; no update ix exists |
| Agent skips seq / reorders | `seq == work_count` enforced |
| Client forges entry_hash | hash computed in-program, not trusted from client |
| Sybil: agent makes many identities | allowed (one wallet = one identity); sybil cost = chain cost |
| Verifier DoS | none needed; reads are free |
| Program upgrade | deployed program is upgradable via upgrade authority; a fixed
  program id is the trust anchor. For production use, burn the upgrade auth |

## Verifier spec (JSON-RPC)

Given `agent` pubkey, `program` id, and `root` hash (the claim):

```
1. id_pda  = PDA(program, ["agent", agent])
   read 136 bytes:
     agent, agent_id, name, uri, work_count = N
2. for seq in 0..N:
     w_pda = PDA(program, ["work", agent, seq_le_bytes(8)])
     read 160 bytes:
       agent, seq, ts, data_hash, prev_hash, amount, entry_hash
     assert agent == agent_pubkey
     assert seq == i
     assert prev_hash == (entry_hash of previous, or 32 zero bytes for i=0)
     recompute h = sha256(agent ‖ seq ‖ ts ‖ data_hash ‖ amount ‖ prev_hash)
     assert h == entry_hash
3. assert recomputed final hash == claimed root
```

Reference implementation: `poa chain` (CLI) — <1 s for 3 entries on devnet.
Complexity: O(N) RPC reads; trivially parallelizable per entry.

## Roadmap (post-hackathon)
* `LogWork` v2: sign `data_hash` with a *second* key (witness) → two-party
  attestation (agent did it + witness saw it).
* Merkle accumulation of entry hashes → O(log N) verification with a light
  accumulator account.
* `PayWork`: optional SPL-token transfer bundled into the same tx as
  `LogWork`, so "work + payment" is atomic and provable in one slot.
* Identity URI → DID document on Solana (names, capabilities, links).
