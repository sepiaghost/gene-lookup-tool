"""
Gene Lookup Tool
----------------
A Streamlit web app that searches the Ensembl REST API for gene
information: identifiers, genomic location, transcripts, and sequence.

Run locally:
    streamlit run app.py

Deploy for free on Streamlit Community Cloud (share.streamlit.io)
by pointing it at this repo.
"""

from __future__ import annotations

from urllib.parse import quote

import pandas as pd
import requests
import streamlit as st
from requests.adapters import HTTPAdapter, Retry

ENSEMBL_BASE = "https://rest.ensembl.org"
HEADERS = {"Content-Type": "application/json"}

# A shared session with automatic retries: transient timeouts / connection
# blips get retried a couple of times with a short backoff before giving up.
_session = requests.Session()
_retries = Retry(total=2, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
_session.mount("https://", HTTPAdapter(max_retries=_retries))

SPECIES = {
    "Human": "homo_sapiens",
    "Mouse": "mus_musculus",
    "Rat": "rattus_norvegicus",
    "Zebrafish": "danio_rerio",
    "Fruit fly": "drosophila_melanogaster",
    "C. elegans": "caenorhabditis_elegans",
}

# Ensembl only serves cDNA and protein sequence for transcripts, not genes,
# so those options use the gene's canonical transcript.
SEQUENCE_OPTIONS = {
    "Genomic (whole gene)": "genomic",
    "cDNA (canonical transcript)": "cdna",
    "Protein (canonical transcript)": "protein",
}


# ---------------------------------------------------------------------
# API helpers (cached so repeat lookups don't hammer Ensembl)
# ---------------------------------------------------------------------

def _get(path: str, params: dict | None = None, timeout: int = 60):
    """GET from Ensembl.

    Returns the response, or None when Ensembl says the symbol/ID doesn't
    exist (HTTP 400/404). Any other failure raises, so st.cache_data never
    stores a temporary error as if it were a real "not found" answer.
    """
    resp = _session.get(
        f"{ENSEMBL_BASE}{path}", headers=HEADERS, params=params, timeout=timeout
    )
    if resp.status_code in (400, 404):
        return None
    resp.raise_for_status()
    return resp


@st.cache_data(show_spinner=False, ttl=3600)
def lookup_symbol(species: str, symbol: str) -> dict | None:
    """Full gene record (with transcripts) from a gene symbol like BRCA1.

    One request does both jobs: it resolves the symbol and returns the record.
    """
    resp = _get(
        f"/lookup/symbol/{species}/{quote(symbol)}", params={"expand": 1}
    )
    return resp.json() if resp is not None else None


@st.cache_data(show_spinner=False, ttl=3600)
def lookup_gene(gene_id: str) -> dict | None:
    """Full gene record, including transcripts, from an Ensembl ID."""
    resp = _get(f"/lookup/id/{quote(gene_id)}", params={"expand": 1})
    return resp.json() if resp is not None else None


@st.cache_data(show_spinner=False, ttl=3600)
def get_sequence(seq_id: str, seq_type: str) -> str | None:
    """Fetch a sequence for a gene or transcript ID."""
    resp = _get(f"/sequence/id/{quote(seq_id)}", params={"type": seq_type}, timeout=40)
    return resp.json().get("seq") if resp is not None else None


@st.cache_data(show_spinner=False, ttl=3600)
def get_xrefs(gene_id: str) -> list:
    """External cross-references (UniProt, HGNC, etc.) for a gene."""
    resp = _get(f"/xrefs/id/{quote(gene_id)}")
    return resp.json() if resp is not None else []


def find_gene(species: str, query: str) -> dict | None:
    """Accept either a gene symbol or an Ensembl ID and return the gene record."""
    query = query.strip()
    if query.upper().startswith("ENS"):
        return lookup_gene(query)
    return lookup_symbol(species, query)


def canonical_transcript_id(gene: dict) -> str | None:
    """Pick the canonical transcript ID from an expanded gene record."""
    for t in gene.get("Transcript", []):
        if t.get("is_canonical"):
            return t.get("id")
    canonical = gene.get("canonical_transcript")
    return canonical.split(".")[0] if canonical else None


# ---------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------

def show_gene(gene: dict) -> None:
    """Render everything we know about one gene."""
    gene_id = gene.get("id", "")
    st.success(f"Found **{gene.get('display_name', gene_id)}**")

    # --- Summary ---
    st.subheader("Overview")
    c1, c2, c3 = st.columns([3, 3, 2])
    c1.markdown(f"**Ensembl ID**  \n`{gene_id}`")
    c2.markdown(f"**Biotype**  \n`{gene.get('biotype', '-')}`")
    c3.markdown(f"**Strand**  \n`{'+' if gene.get('strand') == 1 else '-'}`")
  

    st.markdown(f"**Description:** {gene.get('description', 'No description available.')}")
    start, end = gene.get("start"), gene.get("end")
    if start and end:
        st.markdown(
            f"**Location:** chr{gene.get('seq_region_name')}:"
            f"{start:,}-{end:,} ({gene.get('assembly_name', '')})"
        )

    # --- Transcripts ---
    transcripts = gene.get("Transcript", [])
    if transcripts:
        st.subheader(f"Transcripts ({len(transcripts)})")
        df = pd.DataFrame(
            [
                {
                    "Transcript ID": t.get("id"),
                    "Biotype": t.get("biotype"),
                    "Length (bp)": (t.get("end", 0) - t.get("start", 0) + 1),
                    "Is canonical": bool(t.get("is_canonical")),
                }
                for t in transcripts
            ]
        ).sort_values("Is canonical", ascending=False)
        st.dataframe(df, width="stretch", hide_index=True)

    # --- Cross-references ---
    try:
        with st.spinner("Fetching cross-references..."):
            xrefs = get_xrefs(gene_id)
    except requests.RequestException:
        xrefs = []
        st.caption("Cross-references are unavailable right now.")
    if xrefs:
        with st.expander(f"External cross-references ({len(xrefs)})"):
            xref_df = pd.DataFrame(
                [
                    {
                        "Database": x.get("dbname"),
                        "ID": x.get("primary_id"),
                        "Description": x.get("description", ""),
                    }
                    for x in xrefs
                ]
            )
            st.dataframe(xref_df, width="stretch", hide_index=True)

    # --- Sequence ---
    st.subheader("Sequence")
    option = st.radio("Sequence type", list(SEQUENCE_OPTIONS), horizontal=True)
    seq_type = SEQUENCE_OPTIONS[option]
    seq_id = gene_id if seq_type == "genomic" else canonical_transcript_id(gene)

    if seq_id is None:
        st.info("No canonical transcript is listed for this gene.")
    elif st.button("Fetch sequence"):
        try:
            with st.spinner("Downloading sequence from Ensembl..."):
                seq = get_sequence(seq_id, seq_type)
        except requests.RequestException:
            st.error("Couldn't reach Ensembl. Try again in a moment.")
            return
        if seq:
            unit = "aa" if seq_type == "protein" else "bp"
            st.text(f"{seq_id} · {len(seq):,} {unit}")
            st.text_area("FASTA sequence", value=seq, height=200)
            st.download_button(
                "Download FASTA",
                data=f">{seq_id} {seq_type}\n{seq}\n",
                file_name=f"{seq_id}_{seq_type}.fasta",
                mime="text/plain",
            )
        else:
            st.error("Sequence not available for this ID/type combination.")


st.set_page_config(page_title="Gene Lookup Tool", page_icon="🧬", layout="centered")

st.title("🧬 Gene Lookup Tool")
st.caption("Search Ensembl for gene identifiers, location, transcripts, and sequence.")

with st.form("search_form"):
    col1, col2 = st.columns([2, 1])
    with col1:
        query = st.text_input(
            "Gene symbol or Ensembl ID",
            placeholder="e.g. BRCA1, TP53, or ENSG00000012048",
        )
    with col2:
        species_label = st.selectbox("Species", list(SPECIES.keys()))
    submitted = st.form_submit_button("Search", width="stretch")

# Streamlit reruns the whole script on every click. Keeping the result in
# session_state means it survives clicks on "Fetch sequence" and the radio.
if submitted:
    st.session_state.pop("gene", None)
    if not query.strip():
        st.warning("Enter a gene symbol or Ensembl ID first.")
    else:
        try:
            with st.spinner("Querying Ensembl..."):
                gene = find_gene(SPECIES[species_label], query)
        except requests.RequestException as err:
            st.error("Couldn't reach Ensembl. Check your connection and try again.")
        else:
            if not gene:
                st.error(f"No match found for '{query}' in {species_label}.")
            else:
                st.session_state["gene"] = gene

if "gene" in st.session_state:
    show_gene(st.session_state["gene"])

st.divider()
st.caption(
    "Data from [Ensembl REST API](https://rest.ensembl.org/). "
    "Built as a bioinformatics portfolio project."
)
