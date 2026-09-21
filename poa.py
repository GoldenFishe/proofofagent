#!/usr/bin/env python3
"""
poa — ProofOfAgent CLI (Python + solders + JSON-RPC)

Usage:
  poa.py init --rpc URL --wallet KEYPAIR.json --program PROGRAM_ID
  poa.py register --name karl --uri https://...
  poa.py log --data "..." --amount 0        # or --data @/path/file
  poa.py status
  poa.py info SEQ
  poa.py chain

Zero-trust verification: everything a verifier needs is on-chain.
"""
import sys, json, os, time, base64, struct, hashlib, urllib.request

CFG_PATH = "/karl/proofofagent/poa_config.json"

# ---- on-chain layout (mirrors the Rust program) ----
AGENT_SEED = b"agent"
WORK_SEED = b"work"
IDENTITY_SPACE = 136
WORK_SPACE = 160
OFF_AGENT, OFF_AGENT_ID, OFF_NAME, OFF_URI, OFF_WORK_COUNT = 0, 32, 64, 96, 128
W_AGENT, W_SEQ, W_TS, W_DATA, W_PREV, W_AMOUNT, W_HASH = 0, 32, 40, 48, 80, 112, 120

from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solders.instruction import Instruction, AccountMeta
from solders.message import MessageV0
from solders.transaction import VersionedTransaction
from solders.signature import Signature
from solders.hash import Hash

SYSTEM = Pubkey.from_string("11111111111111111111111111111111")

def load_cfg():
    with open(CFG_PATH) as f:
        return json.load(f)

def load_wallet(path):
    with open(path) as f:
        raw = f.read().strip()
    if raw.startswith("["):
        arr = json.loads(raw)
        return Keypair.from_bytes(bytes(arr))
    v = json.loads(raw)
    if "secretKeyHex" in v:
        return Keypair.from_bytes(bytes.fromhex(v["secretKeyHex"]))
    if "secretKeyBase58" in v:
        import base58
        return Keypair.from_bytes(base58.b58decode(v["secretKeyBase58"]))
    raise ValueError("unknown wallet format")

def rpc(cfg, method, params):
    req = urllib.request.Request(
        cfg["rpc"],
        data=json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode(),
        headers={"Content-Type":"application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        out = json.loads(r.read())
    if "error" in out:
        raise RuntimeError(f"rpc {method}: {out['error']}")
    return out["result"]

def get_data(cfg, pk):
    r = rpc(cfg, "getAccountInfo", [str(pk), {"encoding":"base64"}])
    v = r.get("value")
    if not v:
        return None
    return base64.b64decode(v["data"][0])

def agent_pda(agent: Pubkey, program: Pubkey):
    return Pubkey.find_program_address([AGENT_SEED, bytes(agent)], program)[0]

def work_pda(agent: Pubkey, seq: int, program: Pubkey):
    return Pubkey.find_program_address([WORK_SEED, bytes(agent), struct.pack("<Q", seq)], program)[0]

def send_tx(cfg, payer, ix, blockhash):
    msg = MessageV0.try_compile(payer.pubkey(), [ix], [], Hash.from_string(blockhash))
    tx = VersionedTransaction(msg, [payer])
    sig = rpc(cfg, "sendTransaction", [base64.b64encode(bytes(tx)).decode(),
                                       {"encoding":"base64","preflightCommitment":"confirmed","skipPreflight":False}])
    # confirm
    deadline = time.time() + 60
    while time.time() < deadline:
        s = rpc(cfg, "getSignatureStatuses", [[str(sig)]])
        st = s["value"][0]
        if st and st.get("confirmationStatus") in ("confirmed","finalized"):
            if st.get("err"):
                raise RuntimeError(f"tx failed on-chain: {st['err']}")
            return sig
        time.sleep(1.5)
    raise RuntimeError(f"tx {sig} not confirmed in 60s")

def latest_blockhash(cfg):
    r = rpc(cfg, "getLatestBlockhash", [{"commitment":"confirmed"}])
    return r["value"]["blockhash"]

def parse_identity(d):
    name = d[OFF_NAME:OFF_NAME+32].split(b"\0")[0].decode()
    uri = d[OFF_URI:OFF_URI+32].split(b"\0")[0].decode()
    work_count = int.from_bytes(d[OFF_WORK_COUNT:OFF_WORK_COUNT+8], "little")
    return {
        "agent": str(Pubkey.from_bytes(d[OFF_AGENT:OFF_AGENT+32])),
        "agent_id": bytes(d[OFF_AGENT_ID:OFF_AGENT_ID+32]).hex(),
        "name": name, "uri": uri, "work_count": work_count,
    }

def parse_work(d):
    return {
        "agent": str(Pubkey.from_bytes(d[W_AGENT:W_AGENT+32])),
        "seq": int.from_bytes(d[W_SEQ:W_SEQ+8], "little"),
        "timestamp": int.from_bytes(d[W_TS:W_TS+8], "little"),
        "data_hash": d[W_DATA:W_DATA+32].hex(),
        "prev_hash": d[W_PREV:W_PREV+32].hex(),
        "amount_lamports": int.from_bytes(d[W_AMOUNT:W_AMOUNT+8], "little"),
        "entry_hash": d[W_HASH:W_HASH+32].hex(),
    }

def entry_hash(agent_bytes, seq, ts, data_hash, amount, prev):
    h = hashlib.sha256()
    h.update(agent_bytes); h.update(struct.pack("<Q", seq)); h.update(struct.pack("<Q", ts))
    h.update(data_hash); h.update(struct.pack("<Q", amount)); h.update(prev)
    return h.digest()

def cmd_init(args):
    cfg = {"rpc": args["rpc"], "wallet": args["wallet"], "program": args["program"]}
    json.dump(cfg, open(CFG_PATH,"w"), indent=2)
    print(f"config -> {CFG_PATH}")

def cmd_register(args, cfg):
    kp = load_wallet(cfg["wallet"])
    agent = kp.pubkey()
    program = Pubkey.from_string(cfg["program"])
    id_pda = agent_pda(agent, program)
    name = args["name"].encode().ljust(32, b"\0")[:32]
    uri = args["uri"].encode().ljust(32, b"\0")[:32]
    data = bytes([0]) + name + uri
    ix = Instruction(program, data, [
        AccountMeta(agent, True, True),      # signer + writable (payer)
        AccountMeta(id_pda, False, True),    # writable: program allocates/writes it
        AccountMeta(SYSTEM, False, False),   # system program
    ])
    sig = send_tx(cfg, kp, ix, latest_blockhash(cfg))
    print(f"registered  tx https://solscan.io/tx/{sig}")
    d = get_data(cfg, id_pda)
    if d: print(json.dumps(parse_identity(d), indent=2))

def cmd_log(args, cfg):
    kp = load_wallet(cfg["wallet"])
    agent = kp.pubkey()
    program = Pubkey.from_string(cfg["program"])
    id_pda = agent_pda(agent, program)
    if args["data"].startswith("@"):
        content = open(args["data"][1:],"rb").read()
    else:
        content = args["data"].encode()
    data_hash = hashlib.sha256(content).digest()
    id_data = get_data(cfg, id_pda)
    if id_data is None:
        raise SystemExit("no identity — run: register")
    seq = int.from_bytes(id_data[OFF_WORK_COUNT:OFF_WORK_COUNT+8], "little")
    w_pda = work_pda(agent, seq, program)
    ts = int(time.time())
    data = bytes([1]) + struct.pack("<Q", seq) + struct.pack("<Q", ts) + data_hash + struct.pack("<Q", args["amount"])
    metas = [
        AccountMeta(agent, True, True),
        AccountMeta(id_pda, False, True),   # program bumps work_count -> writable
        AccountMeta(w_pda, False, True),    # program allocates/writes entry
        AccountMeta(SYSTEM, False, False),
    ]
    if seq > 0:
        # prev entry: program locates it by scanning accounts, so it may follow the first 4
        metas.append(AccountMeta(work_pda(agent, seq-1, program), False, False))
    ix = Instruction(program, data, metas)
    sig = send_tx(cfg, kp, ix, latest_blockhash(cfg))
    print(f"logged seq={seq}  tx https://solscan.io/tx/{sig}")

def cmd_status(cfg):
    kp = load_wallet(cfg["wallet"])
    agent = kp.pubkey()
    program = Pubkey.from_string(cfg["program"])
    d = get_data(cfg, agent_pda(agent, program))
    print(json.dumps(parse_identity(d), indent=2) if d else "not registered")

def cmd_info(seq, cfg):
    kp = load_wallet(cfg["wallet"])
    agent = kp.pubkey()
    program = Pubkey.from_string(cfg["program"])
    d = get_data(cfg, work_pda(agent, seq, program))
    print(json.dumps(parse_work(d), indent=2) if d else f"entry {seq}: none")

def cmd_chain(cfg):
    kp = load_wallet(cfg["wallet"])
    agent = kp.pubkey()
    program = Pubkey.from_string(cfg["program"])
    id_data = get_data(cfg, agent_pda(agent, program))
    if id_data is None:
        raise SystemExit("no identity")
    ident = parse_identity(id_data)
    count = ident["work_count"]
    print(f"verifying {count} entries...")
    prev = bytes(32)
    for seq in range(count):
        d = get_data(cfg, work_pda(agent, seq, program))
        if d is None:
            raise SystemExit(f"entry {seq} missing")
        w = parse_work(d)
        assert w["agent"] == str(agent), f"agent mismatch at {seq}"
        assert w["seq"] == seq, f"seq mismatch at {seq}"
        prev_on = bytes.fromhex(w["prev_hash"])
        onchain = bytes.fromhex(w["entry_hash"])
        data_h = bytes.fromhex(w["data_hash"])
        if prev_on and prev_on != prev:
            raise SystemExit(f"PREV LINK BROKEN at seq {seq}")
        exp = entry_hash(bytes(kp.pubkey()), seq, w["timestamp"], data_h, w["amount_lamports"], prev)
        if exp != onchain:
            raise SystemExit(f"HASH MISMATCH at seq {seq}\n  expected {exp.hex()}\n  on-chain {onchain.hex()}")
        prev = exp
    print(f"CHAIN VERIFIED: {count} entries")
    print(f"root hash: 0x{prev.hex()}")
    import base58
    print(f"root bs58: {base58.b58encode(prev).decode()}")

def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    cmd = sys.argv[1]
    a = {}
    rest = sys.argv[2:]
    while rest:
        k = rest[0]
        if k.startswith("--"):
            a[k[2:]] = rest[1]; rest = rest[2:]
        else:
            a[k] = rest[0]; rest = rest[1:]
    # positional seq for info
    if cmd == "info" and "seq" not in a:
        a["seq"] = int(sys.argv[2])
    if cmd == "init":
        cmd_init(a)
    else:
        cfg = load_cfg()
        if cmd == "register": cmd_register(a, cfg)
        elif cmd == "log": cmd_log(a, cfg)
        elif cmd == "status": cmd_status(cfg)
        elif cmd == "info": cmd_info(int(a["seq"]), cfg)
        elif cmd == "chain": cmd_chain(cfg)

if __name__ == "__main__":
    main()
