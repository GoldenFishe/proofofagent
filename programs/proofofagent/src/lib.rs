//! ProofOfAgent — on-chain registry & work ledger for autonomous AI agents.
//!
//! Design:
//!   * `Initialize` — agent signs once, creating an identity PDA
//!     holding (agent, agent_id, name, uri, work_count).
//!   * `LogWork`    — agent appends a work entry. Entry N stores the hash of
//!     entry N-1, forming an append-only, tamper-evident chain where every
//!     entry hash is computed ON-CHAIN by the program.
//!
//! entry_hash = sha256(agent || seq || ts || data_hash || amount || prev_hash)
//!
//! Anyone can recompute the entire chain from entry 0 with `poa chain`.

use borsh::BorshSerialize;
use sha2::{Digest, Sha256};
use solana_program::{
    account_info::{next_account_info, AccountInfo},
    entrypoint::ProgramResult,
    entrypoint::entrypoint,
    msg,
    program::invoke_signed,
    program_error::ProgramError,
    pubkey::Pubkey,
    rent::Rent,
    system_instruction,
    system_program,
    sysvar::Sysvar,
};

pub mod state {
    pub const AGENT_SEED: &[u8] = b"agent";
    pub const WORK_SEED: &[u8] = b"work";

    // Identity: agent(32) + agent_id(32) + name(32) + uri(32) + work_count(8) = 136
    pub const IDENTITY_SPACE: usize = 136;
    // Work: agent(32)+seq(8)+ts(8)+data_hash(32)+prev_hash(32)+amount(8)+entry_hash(32)+pad(8)=160
    pub const WORK_SPACE: usize = 160;

    pub const OFF_AGENT: usize = 0;
    pub const OFF_AGENT_ID: usize = 32;
    pub const OFF_NAME: usize = 64;
    pub const OFF_URI: usize = 96;
    pub const OFF_WORK_COUNT: usize = 128;

    pub const W_AGENT: usize = 0;
    pub const W_SEQ: usize = 32;
    pub const W_TS: usize = 40;
    pub const W_DATA: usize = 48;
    pub const W_PREV: usize = 80;
    pub const W_AMOUNT: usize = 112;
    pub const W_HASH: usize = 120;
}

pub fn sha256(data: &[u8]) -> [u8; 32] {
    let d = Sha256::digest(data);
    let mut out = [0u8; 32];
    out.copy_from_slice(&d);
    out
}

pub fn entry_hash(
    agent: &[u8],
    seq: u64,
    ts: u64,
    data: &[u8; 32],
    amount: u64,
    prev: &[u8; 32],
) -> [u8; 32] {
    let mut buf = Vec::with_capacity(120);
    buf.extend_from_slice(agent);
    buf.extend_from_slice(&seq.to_le_bytes());
    buf.extend_from_slice(&ts.to_le_bytes());
    buf.extend_from_slice(data);
    buf.extend_from_slice(&amount.to_le_bytes());
    buf.extend_from_slice(prev);
    sha256(&buf)
}

#[derive(BorshSerialize, Debug)]
pub enum Instruction {
    Initialize {
        name: [u8; 32],
        uri: [u8; 32],
    },
    LogWork {
        seq: u64,
        timestamp: u64,
        data_hash: [u8; 32],
        amount: u64,
    },
}

fn identity_pda(agent: &Pubkey, program_id: &Pubkey) -> (Pubkey, u8) {
    Pubkey::find_program_address(&[state::AGENT_SEED, agent.as_ref()], program_id)
}

fn work_pda(agent: &Pubkey, seq: u64, program_id: &Pubkey) -> (Pubkey, u8) {
    Pubkey::find_program_address(
        &[state::WORK_SEED, agent.as_ref(), &seq.to_le_bytes()],
        program_id,
    )
}

pub fn ix_initialize(name: [u8; 32], uri: [u8; 32]) -> Vec<u8> {
    let mut v = vec![0u8];
    v.extend_from_slice(&name);
    v.extend_from_slice(&uri);
    v
}

pub fn ix_log_work(seq: u64, timestamp: u64, data_hash: [u8; 32], amount: u64) -> Vec<u8> {
    let mut v = vec![1u8];
    v.extend_from_slice(&seq.to_le_bytes());
    v.extend_from_slice(&timestamp.to_le_bytes());
    v.extend_from_slice(&data_hash);
    v.extend_from_slice(&amount.to_le_bytes());
    v
}

fn parse_instruction(data: &[u8]) -> Result<Instruction, ProgramError> {
    let mut r = &data[..];
    if r.is_empty() {
        return Err(ProgramError::InvalidInstructionData);
    }
    match r[0] {
        0 => {
            r = &r[1..];
            let name = r
                .get(0..32)
                .ok_or(ProgramError::InvalidInstructionData)?
                .try_into()
                .unwrap();
            let uri = r
                .get(32..64)
                .ok_or(ProgramError::InvalidInstructionData)?
                .try_into()
                .unwrap();
            Ok(Instruction::Initialize { name, uri })
        }
        1 => {
            r = &r[1..];
            if r.len() < 48 {
                return Err(ProgramError::InvalidInstructionData);
            }
            let seq = u64::from_le_bytes(r[0..8].try_into().unwrap());
            let timestamp = u64::from_le_bytes(r[8..16].try_into().unwrap());
            let data_hash = r[16..48].try_into().unwrap();
            let amount = u64::from_le_bytes(r[48..56].try_into().unwrap());
            Ok(Instruction::LogWork {
                seq,
                timestamp,
                data_hash,
                amount,
            })
        }
        _ => Err(ProgramError::InvalidInstructionData),
    }
}

fn handler(program_id: &Pubkey, accounts: &[AccountInfo], data: &[u8]) -> ProgramResult {
    let mut iter = accounts.iter();
    match parse_instruction(data)? {
        Instruction::Initialize { name, uri } => {
            msg!("PoA Initialize");
            let agent = next_account_info(&mut iter)?;
            if !agent.is_signer {
                return Err(ProgramError::MissingRequiredSignature);
            }
            let identity = next_account_info(&mut iter)?;
            let system = next_account_info(&mut iter)?;
            if *system.key != system_program::id() {
                return Err(ProgramError::InvalidAccountData);
            }
            let (expected, bump) = identity_pda(agent.key, program_id);
            if *identity.key != expected {
                return Err(ProgramError::InvalidAccountData);
            }

            let _rent = Rent::get()?;
            if identity.data_is_empty() {
                invoke_signed(
                    &system_instruction::allocate(&identity.key, state::IDENTITY_SPACE as u64),
                    &[identity.clone()],
                    &[&[state::AGENT_SEED, agent.key.as_ref(), &[bump]]],
                )?;
                invoke_signed(
                    &system_instruction::assign(&identity.key, program_id),
                    &[identity.clone()],
                    &[&[state::AGENT_SEED, agent.key.as_ref(), &[bump]]],
                )?;
            } else if identity.owner != program_id {
                return Err(ProgramError::InvalidAccountOwner);
            }

            let mut id = identity.try_borrow_mut_data()?;
            id[state::OFF_AGENT..state::OFF_AGENT + 32].copy_from_slice(agent.key.as_ref());
            id[state::OFF_AGENT_ID..state::OFF_AGENT_ID + 32]
                .copy_from_slice(&sha256(agent.key.as_ref()));
            id[state::OFF_NAME..state::OFF_NAME + 32].copy_from_slice(&name);
            id[state::OFF_URI..state::OFF_URI + 32].copy_from_slice(&uri);
            id[state::OFF_WORK_COUNT..state::OFF_WORK_COUNT + 8].fill(0u8);
            Ok(())
        }
        Instruction::LogWork {
            seq,
            timestamp,
            data_hash,
            amount,
        } => {
            msg!("PoA LogWork seq={seq}");
            let agent = next_account_info(&mut iter)?;
            if !agent.is_signer {
                return Err(ProgramError::MissingRequiredSignature);
            }
            let identity = next_account_info(&mut iter)?;
            let work = next_account_info(&mut iter)?;
            let system = next_account_info(&mut iter)?;
            if *system.key != system_program::id() {
                return Err(ProgramError::InvalidAccountData);
            }
            let (exp_id, bump_id) = identity_pda(agent.key, program_id);
            if *identity.key != exp_id {
                return Err(ProgramError::InvalidAccountData);
            }
            let (exp_work, bump_work) = work_pda(agent.key, seq, program_id);
            if *work.key != exp_work {
                return Err(ProgramError::InvalidAccountData);
            }

            let id = identity.try_borrow_data()?;
            if id.len() != state::IDENTITY_SPACE {
                return Err(ProgramError::AccountDataTooSmall);
            }
            if id[state::OFF_AGENT..state::OFF_AGENT + 32] != *agent.key.as_ref() {
                return Err(ProgramError::InvalidAccountData);
            }
            let work_count = u64::from_le_bytes(
                id[state::OFF_WORK_COUNT..state::OFF_WORK_COUNT + 8].try_into().unwrap(),
            );
            if seq != work_count {
                msg!("expected seq={work_count} got {seq}");
                return Err(ProgramError::InvalidInstructionData);
            }

            let mut prev = [0u8; 32];
            if seq > 0 {
                let (exp_prev, _) = work_pda(agent.key, seq - 1, program_id);
                let prev_acc = accounts
                    .iter()
                    .find(|a| a.key == &exp_prev)
                    .ok_or(ProgramError::InvalidAccountData)?;
                let pd = prev_acc.try_borrow_data()?;
                prev.copy_from_slice(&pd[state::W_HASH..state::W_HASH + 32]);
            }

            let hash = entry_hash(agent.key.as_ref(), seq, timestamp, &data_hash, amount, &prev);


            if work.data_is_empty() {
                let seq_bytes = seq.to_le_bytes();
                invoke_signed(
                    &system_instruction::allocate(&work.key, state::WORK_SPACE as u64),
                    &[work.clone()],
                    &[&[state::WORK_SEED, agent.key.as_ref(), &seq_bytes, &[bump_work]]],
                )?;
                invoke_signed(
                    &system_instruction::assign(&work.key, program_id),
                    &[work.clone()],
                    &[&[state::WORK_SEED, agent.key.as_ref(), &seq_bytes, &[bump_work]]],
                )?;
            } else if work.owner != program_id {
                return Err(ProgramError::InvalidAccountOwner);
            }

            let mut w = work.try_borrow_mut_data()?;
            w[state::W_AGENT..state::W_AGENT + 32].copy_from_slice(agent.key.as_ref());
            w[state::W_SEQ..state::W_SEQ + 8].copy_from_slice(&seq.to_le_bytes());
            w[state::W_TS..state::W_TS + 8].copy_from_slice(&timestamp.to_le_bytes());
            w[state::W_DATA..state::W_DATA + 32].copy_from_slice(&data_hash);
            w[state::W_PREV..state::W_PREV + 32].copy_from_slice(&prev);
            w[state::W_AMOUNT..state::W_AMOUNT + 8].copy_from_slice(&amount.to_le_bytes());
            w[state::W_HASH..state::W_HASH + 32].copy_from_slice(&hash);

            let mut idm = identity.try_borrow_mut_data()?;
            idm[state::OFF_WORK_COUNT..state::OFF_WORK_COUNT + 8]
                .copy_from_slice(&work_count.wrapping_add(1).to_le_bytes());
            Ok(())
        }
    }
}

entrypoint!(handler);

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hash_deterministic_and_chained() {
        let a = [7u8; 32];
        let h0 = entry_hash(&a, 0, 1000, &[1; 32], 42, &[0; 32]);
        assert_eq!(h0, entry_hash(&a, 0, 1000, &[1; 32], 42, &[0; 32]));
        let h1 = entry_hash(&a, 1, 1001, &[2; 32], 43, &h0);
        assert_ne!(h0, h1);
        assert_ne!(h0, entry_hash(&a, 0, 1000, &[1; 32], 43, &[0; 32]));
    }
}
