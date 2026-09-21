#!/usr/bin/env bash
# End-to-end: deploy program, fund agent, register, log x3, verify chain.
set -e
export PATH="$HOME/.local/share/solana/install/active_release/bin:$HOME/.cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
cd /karl/proofofagent

echo "== deploy =="
OUT=$(solana program deploy target/deploy/proofofagent.so 2>&1)
echo "$OUT" | grep -E "Program Id" || { echo "$OUT"; exit 1; }
PROGRAM=$(echo "$OUT" | grep -oE "Program Id: [A-Za-z0-9]+" | awk '{print $3}')
echo "PROGRAM=$PROGRAM"

echo "== new agent =="
AGENT_KP=/karl/proofofagent/agent_genesis.json
rm -f $AGENT_KP
solana-keygen new -o $AGENT_KP --no-passphrase >/dev/null 2>&1
AGENT=$(solana-keygen pubkey $AGENT_KP | grep -oE "[1-9A-HJ-NP-Za-km-z]{32,45}")
echo "AGENT=$AGENT"

echo "== airdrop agent =="
SIG=$(curl -s -X POST http://localhost:8899 -H 'Content-Type: application/json' \
  -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"requestAirdrop\",\"params\":[\"$AGENT\", 5000000000]}" \
  | python3 -c "import json,sys; print(json.load(sys.stdin).get('result',''))")
sleep 6
BAL=$(curl -s -X POST http://localhost:8899 -H 'Content-Type: application/json' \
  -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"getBalance\",\"params\":[\"$AGENT\"]}" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['result']['value']/1e9)")
echo "agent balance: $BAL SOL"

echo "== configure CLI =="
python3 poa.py init --rpc http://localhost:8899 --wallet $AGENT_KP --program $PROGRAM

echo "== register =="
python3 poa.py register --name karl --uri "karl://genesis"

echo "== log 1 =="
python3 poa.py log --data "bootstrapped ProofOfAgent v0.1: program deployed, CLI live" --amount 0

echo "== log 2 =="
cp target/deploy/proofofagent.so /tmp/poa_so_artifact
python3 poa.py log --data @/tmp/poa_so_artifact --amount 0

echo "== log 3 (paid work) =="
python3 poa.py log --data "colosseum worldsfair project submission prep complete" --amount 10000000000

echo "== status =="
python3 poa.py status

echo "== chain verification =="
python3 poa.py chain

echo "== DONE =="
echo "PROGRAM=$PROGRAM" > /karl/proofofagent/genesis_env.sh
echo "AGENT=$AGENT" >> /karl/proofofagent/genesis_env.sh
