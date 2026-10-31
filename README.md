# 🧬 Gene Lookup Tool

A small web app for looking up a gene in [Ensembl](https://www.ensembl.org/). Type a gene symbol (like `BRCA1`) or an Ensembl ID (like `ENSG00000012048`), pick a species, and get the gene's identifiers, genomic location, transcripts, external cross-references, and sequence.

Built with Python and [Streamlit](https://streamlit.io/), using the [Ensembl REST API](https://rest.ensembl.org/). No API key is needed.

<!-- Add a screenshot: save it as screenshot.png in this folder, then uncomment the next line -->
<!-- ![Gene Lookup Tool screenshot](screenshot.png) -->

**Live demo:** _ 

https://github.com/user-attachments/assets/090d14e3-762e-4623-be5a-139bb4340a3c







## Features

- Search by gene symbol or Ensembl ID across 6 species: human, mouse, rat, zebrafish, fruit fly, and *C. elegans*
- Overview: Ensembl ID, biotype, strand, description, and genomic location with assembly
- Transcript table with biotype, length, and which transcript is canonical
- External cross-references (HGNC, UniProt, and others)
- Genomic, cDNA, or protein sequence, with FASTA download. cDNA and protein come from the gene's canonical transcript, because Ensembl serves them per transcript.
- Retries on temporary network errors, clear messages when Ensembl can't be reached, and cached lookups so repeat searches don't re-query Ensembl

## Run it locally

You need Python 3.10 or newer.

```bash
git clone https://github.com/sepiaghost/gene-lookup-tool.git
cd gene-lookup-tool

python -m venv venv
# Windows (PowerShell):  venv\Scripts\Activate.ps1
# macOS / Linux:         source venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

The app opens at http://localhost:8501.

## How it works

| Step | Ensembl endpoint |
| --- | --- |
| Gene symbol to Ensembl ID | `/xrefs/symbol/{species}/{symbol}` |
| Gene record and transcripts | `/lookup/id/{id}?expand=1` |
| External cross-references | `/xrefs/id/{id}` |
| Sequence | `/sequence/id/{id}?type=genomic\|cdna\|protein` |

Results are cached for one hour. "Not found" answers (HTTP 400/404) are treated as normal results, while network and server errors are raised and reported to the user instead of being cached.

## Limitations

- Only the first match is used when a symbol maps to more than one gene.
- Genomic sequences for large genes can be many megabases, so fetching them may be slow.
- Ensembl rate-limits heavy use, so this is meant for interactive lookups, not bulk queries.

## Data

Gene data comes from the Ensembl REST API. See [Ensembl's terms of use](https://www.ensembl.org/info/about/legal/index.html).
