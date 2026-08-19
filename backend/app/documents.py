"""Document ingestion: extract text from the PDF pack, split into sections, tag each
section with authority metadata, and index for lexical search.

Authority tiers (lower number = higher precedence, per Support Policy v3 section 1):
  1 = signed customer agreement
  2 = current support policy / SOP
  3 = current product documentation
  4 = deprecated policy (never authoritative -- kept only so the agent can warn about it)
Historical ticket resolutions are handled separately (see tools/history.py) since they
live in the structured workbook, not the PDF pack, and are context-only, not tier-ranked.
"""
import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from rank_bm25 import BM25Okapi

from app.config import DATA_PACK_DIR

DOC_METADATA = {
    "01_Support_Policy_v3_CURRENT.pdf": dict(
        doc_type="policy", status="CURRENT", effective_date="2026-05-01",
        authority_tier=2, account_id=None,
    ),
    "02_Support_Policy_v2_DEPRECATED.pdf": dict(
        doc_type="policy", status="DEPRECATED", effective_date="2025-01-01",
        authority_tier=4, account_id=None,
    ),
    "03_Cancellation_and_Service_Credit_SOP_v4.pdf": dict(
        doc_type="sop", status="CURRENT", effective_date="2026-06-15",
        authority_tier=2, account_id=None,
    ),
    "04_Product_Operations_Guide_and_Known_Issues.pdf": dict(
        doc_type="product_guide", status="CURRENT", effective_date="2026-08-14",
        authority_tier=3, account_id=None,
    ),
    "05_Northstar_Logistics_Enterprise_Agreement.pdf": dict(
        doc_type="agreement", status="CURRENT", effective_date="2026-01-01",
        authority_tier=1, account_id="ACCT-001",
    ),
    "06_LumenWorks_Service_Agreement.pdf": dict(
        doc_type="agreement", status="CURRENT", effective_date="2026-03-01",
        authority_tier=1, account_id="ACCT-002",
    ),
}


@dataclass
class Chunk:
    source_file: str
    heading: str
    text: str
    doc_type: str
    status: str
    effective_date: str
    authority_tier: int
    account_id: str | None = None


def _extract_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    raw = "\n".join(page.extract_text() or "" for page in reader.pages)
    # pypdf emits extra inter-word spaces from this PDF's font metrics; collapse them but
    # keep line breaks so heading detection (one heading per line) still works.
    return "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in raw.splitlines())


_HEADING_RE = re.compile(r"^(?:\d+\.\s+.+|[A-Z][A-Za-z &-]{2,60})$")


def _split_into_sections(raw_text: str, title: str) -> list[tuple[str, str]]:
    """Split on numbered ('1. Scope...') or short title-case lines used as headings.
    Falls back to one section (the whole doc) if nothing heading-like is found.
    """
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    sections: list[tuple[str, list[str]]] = []
    current_heading = title
    current_body: list[str] = []
    for line in lines:
        if line == title:
            continue
        if re.match(r"^\d+\.\s+\S", line) and len(line) < 80:
            if current_body:
                sections.append((current_heading, current_body))
            current_heading = line
            current_body = []
        else:
            current_body.append(line)
    if current_body:
        sections.append((current_heading, current_body))
    if not sections:
        return [(title, raw_text)]
    return [(h, " ".join(b)) for h, b in sections]


def load_chunks() -> list[Chunk]:
    chunks: list[Chunk] = []
    for filename, meta in DOC_METADATA.items():
        path = DATA_PACK_DIR / filename
        text = _extract_text(path)
        title = text.splitlines()[0].strip() if text.splitlines() else filename
        for heading, body in _split_into_sections(text, title):
            chunks.append(Chunk(
                source_file=filename,
                heading=heading,
                text=body,
                doc_type=meta["doc_type"],
                status=meta["status"],
                effective_date=meta["effective_date"],
                authority_tier=meta["authority_tier"],
                account_id=meta["account_id"],
            ))
    return chunks


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class DocumentIndex:
    def __init__(self, chunks: list[Chunk] | None = None):
        self.chunks = chunks if chunks is not None else load_chunks()
        corpus = [_tokenize(f"{c.heading} {c.text}") for c in self.chunks]
        self._bm25 = BM25Okapi(corpus) if corpus else None

    def search(self, query: str, top_k: int = 5, account_id: str | None = None,
               is_customer: bool = False) -> list[Chunk]:
        """Search chunks, scoped so a customer session never sees another account's
        agreement. Internal sessions (is_customer=False) see everything.
        """
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(_tokenize(query))
        ranked = sorted(zip(scores, self.chunks), key=lambda p: p[0], reverse=True)
        results = []
        for score, chunk in ranked:
            if score <= 0:
                continue
            if is_customer and chunk.doc_type == "agreement" and chunk.account_id != account_id:
                continue  # never leak another account's contract terms to a customer
            results.append(chunk)
            if len(results) >= top_k:
                break
        return results
