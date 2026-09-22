#!/usr/bin/env python3
"""INDEPENDENT verifier. No CLI state, no config — everything from the chain.
Recomputes entry hashes for the whole chain and proves the artifact link:
entry seq=1 must hash to the deployed program .so on disk.
"""
import json, urllib.request, base64, struct, hashlib, sys
from solders.pubkey import Pubkey
from solders.keypair import Keypair

RPC = "http://localhost:8899"
PROG = Pubkey.from_string("FKgdakDasWFRJr7CBKq6atBRf2TZjJNfjvmGSKTn1pVv")

def rpc(m, p):
    r = urllib.request.Request(RPC, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(),
                               headers={"Content-Type": "application/json"})
    out = json.loads(urllib.request.urlopen(r, timeout=40).read())
    assert "error" not in out, out["error"]
    return out["result"]

def rd(pk, commit="finalized"):
    v = rpc("getAccountInfo", [str(pk), {"encoding": "base64", "commitment": commit}])["value"]
    return base64.b64decode(v["data"][0]) if v else None

agent = Keypair.from_bytes(bytes(json.load(open("agent_live.json"))))
apub = agent.pubkey()
idp = Pubkey.find_program_address([b"agent", bytes(apub)], PROG)[0]
wof = lambda s: Pubkey.find_program_address([b"work", bytes(apub), struct.pack("<Q", s)], PROG)[0]

ident = rd(idp)
assert ident, "identity not on chain"
agent_on = ident[0:32]
assert agent_on == bytes(apub), "identity.agent != caller"
name = ident[64:96].split(b"\0")[0].decode()
wc = int.from_bytes(ident[128:136], "little")
print(f"identity on-chain: name={name!r} work_count={wc} owner={Pubkey.from_bytes(agent_on)}")

def entry_hash(agent_b, seq, ts, data_h, amount, prev):
    h = hashlib.sha256()
    h.update(agent_b); h.update(struct.pack("<Q", seq)); h.update(struct.pack("<Q", ts))
    h.update(data_h); h.update(struct.pack("<Q", amount)); h.update(prev)
    return h.digest()

prev = bytes(32)
for seq in range(wc):
    w = rd(wof(seq))
    assert w, f"entry {seq} missing on chain"
    seq_v = int.from_bytes(w[32:40], "little")
    ts = int.from_bytes(w[40:48], "little")
    dh = w[48:80]
    prev_on = w[80:112]
    amt = int.from_bytes(w[112:120], "little")
    onchain_h = w[120:152]
    assert seq_v == seq, f"seq mismatch at {seq}"
    assert w[0:32] == agent_on, f"agent mismatch at {seq}"
    if prev_on != prev:
        raise SystemExit(f"PREV LINK BROKEN at seq {seq}")
    exp = entry_hash(agent_on, seq, ts, dh, amt, prev)
    if exp != onchain_h:
        raise SystemExit(f"HASH MISMATCH at seq {seq}")
    prev = exp
    print(f"  seq {seq}: ts={ts} amount={amt} data_hash={dh[:6].hex()}.. entry_hash OK")

print(f"\nINDEPENDENT VERIFY: {wc} entries, chain intact")
print(f"root hash: 0x{prev.hex()}")

# artifact cross-check: seq=1 was logged with @target/deploy/proofofagent.so
so_hash = hashlib.sha256(open("/karl/proofofagent/target/deploy/proofofagent.so", "rb").read()).digest()
w1 = rd(wof(1))
on_disk = w1[48:80]
if so_hash == on_disk:
    print("ARTIFACT LINK PROVEN: on-chain data_hash(seq=1) == sha256(target/deploy/proofofagent.so)")
else:
    print("ARTIFECT MISMATCH", so_hash.hex()[:12], on_disk.hex()[:12]); sys.exit(1)
