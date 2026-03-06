"""Smoke-test: verify all 8 xref columns added in migration 0002.

Run with:
    uv run python manage_db/smoke_test_xref.py

What it does
------------
1. Connects to the currently-active lamin instance (mjouvencekb).
2. Starts a tracked run so LaminDB can generate UIDs.
3. Creates one record per affected model using the new xref columns.
4. Reads each record back and asserts the values round-tripped correctly.
5. Deletes all test records (leaves the instance clean).

Expected output: "All 8 xref-column checks passed ✓"
"""

from __future__ import annotations

import lamindb as ln
import lnschema_txgnn as lnx

# ---------------------------------------------------------------------------
# Connect + start run
# ---------------------------------------------------------------------------
ln.connect("jkobject/mjouvencekb")
ln.track(path=__file__)

ERRORS: list[str] = []

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def check(label: str, got, expected) -> None:
    if got != expected:
        ERRORS.append(f"FAIL [{label}]: got {got!r}, expected {expected!r}")
    else:
        print(f"  ✓  {label}")


# ---------------------------------------------------------------------------
# 1. Paper — pmc_id, arxiv_id
# ---------------------------------------------------------------------------
print("\n— Paper —")
paper = lnx.Paper(
    pmid="99999999",
    doi="10.9999/smoke",
    pmc_id="PMC9999999",
    arxiv_id="2303.99999",
    title="Smoke-test paper",
    year=2026,
)
paper.save()

p2 = lnx.Paper.get(pmid="99999999")
check("paper.pmc_id", p2.pmc_id, "PMC9999999")
check("paper.arxiv_id", p2.arxiv_id, "2303.99999")

# ---------------------------------------------------------------------------
# 2. Transcript — refseq_mrna, ccds_id
# ---------------------------------------------------------------------------
print("\n— Transcript —")
tx = lnx.Transcript(
    ensembl_transcript_id="ENST00000999999",
    refseq_mrna="NM_000001.1",
    ccds_id="CCDS9999.1",
    biotype="protein_coding",
)
tx.save()

t2 = lnx.Transcript.get(ensembl_transcript_id="ENST00000999999")
check("transcript.refseq_mrna", t2.refseq_mrna, "NM_000001.1")
check("transcript.ccds_id", t2.ccds_id, "CCDS9999.1")

# ---------------------------------------------------------------------------
# 3. Enhancer — ensembl_regulatory_id, encode_experiment_id
# ---------------------------------------------------------------------------
print("\n— Enhancer —")
enh = lnx.Enhancer(
    encode_id="EH38E9999999",
    ensembl_regulatory_id="ENSR00000000999",
    encode_experiment_id="ENCSR999ZZZ",
    chromosome="chr1",
    start_pos=1_000_000,
    end_pos=1_001_000,
)
enh.save()

e2 = lnx.Enhancer.get(encode_id="EH38E9999999")
check("enhancer.ensembl_regulatory_id", e2.ensembl_regulatory_id, "ENSR00000000999")
check("enhancer.encode_experiment_id", e2.encode_experiment_id, "ENCSR999ZZZ")

# ---------------------------------------------------------------------------
# 4. Mutation — clinvar_id, gnomad_id
# ---------------------------------------------------------------------------
print("\n— Mutation —")
mut = lnx.Mutation(
    rsid="rs9999999999",
    clinvar_id="999999",
    gnomad_id="1_999999_A_T",
    chromosome="chr1",
    position=999_999,
    ref_allele="A",
    alt_allele="T",
    consequence="missense_variant",
)
mut.save()

m2 = lnx.Mutation.get(rsid="rs9999999999")
check("mutation.clinvar_id", m2.clinvar_id, "999999")
check("mutation.gnomad_id", m2.gnomad_id, "1_999999_A_T")

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
print("\n— Cleanup —")
paper.delete(permanent=True)
tx.delete(permanent=True)
enh.delete(permanent=True)
mut.delete(permanent=True)
print("  Test records deleted.")

ln.finish()

# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------
print()
if ERRORS:
    print(f"FAILED — {len(ERRORS)} error(s):")
    for e in ERRORS:
        print(" ", e)
    raise SystemExit(1)
else:
    print("All 8 xref-column checks passed ✓")
