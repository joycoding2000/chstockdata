# DR04-P offline response evidence

These 30 `.bin` files are byte-for-byte copies of saved Sina responses from
the Owner-authorized 2026-10-17 investigation. No new source request was made.
`manifest.json` retains original request identities, acquisition times, byte
lengths and SHA-256 values. Its hashes also identify the reviewed contract,
original evidence manifest, original request log and copied calendar.

Read-only origin: sibling `mishi-radar/outputs/s08-fund-universe-investigation-2026-10-17/evidence/`.
The source contract is in `outputs/dr04-minimum-consumer-contract-2026-10-17/`.
The Owner's current implementation authorization and two later limitations
supersede that document's proposal-stage authorization wording.

P01/P02/P04/P06 reuse original bytes. Other anomalies and edge cases are
explicitly synthesized in test memory; the evidence files are never edited.
Mocked HTTP acquisition times in test results are simulated observations,
not new live source evidence. Original acquisition times remain in the manifest.

Fixtures establish reproducibility and observation identity only. They do
not establish source finality, historical PIT, full-market availability,
S08 qualification, or permission to enter DR04-M.
