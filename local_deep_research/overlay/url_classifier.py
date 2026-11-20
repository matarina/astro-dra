"""
URL Classifier for content fetching.

Determines the type of URL to route to the appropriate downloader.
"""

import re
from enum import Enum
from typing import Optional
from urllib.parse import urlparse
from research_verify.pmc_identity import academic_url_ids


class URLType(Enum):
    """Types of URLs we can handle."""

    ARXIV = "arxiv"
    PUBMED = "pubmed"
    PMC = "pmc"  # PubMed Central
    SEMANTIC_SCHOLAR = "semantic_scholar"
    BIORXIV = "biorxiv"
    MEDRXIV = "medrxiv"
    DOI = "doi"
    PDF = "pdf"  # Direct PDF link
    HTML = "html"  # Generic web page
    INVALID = "invalid"  # Dangerous/unsupported URL schemes


# URL schemes that should be rejected (security risk)
DANGEROUS_SCHEMES = {"javascript", "data", "file", "vbscript", "about"}


class URLClassifier:
    """Classifies URLs to determine the appropriate downloader."""

    # ArXiv patterns
    ARXIV_PATTERNS = [
        r"arxiv\.org/abs/",
        r"arxiv\.org/pdf/",
        r"arxiv\.org/html/",
        r"ar5iv\.org/",
    ]

    # PubMed patterns
    PUBMED_PATTERNS = [
        r"pubmed\.ncbi\.nlm\.nih\.gov/\d+",
        r"ncbi\.nlm\.nih\.gov/pubmed/\d+",
    ]

    # PMC patterns (PubMed Central - full text)
    # Note: patterns match lowercase since URLs are lowercased before matching
    PMC_PATTERNS = [
        r"ncbi\.nlm\.nih\.gov/pmc/articles/pmc",
        r"europepmc\.org/article/pmc",
        r"europepmc\.org/articles/pmc",
    ]

    # Semantic Scholar patterns
    SEMANTIC_SCHOLAR_PATTERNS = [
        r"semanticscholar\.org/paper/",
        r"api\.semanticscholar\.org/",
    ]

    # BioRxiv/MedRxiv patterns
    BIORXIV_PATTERNS = [
        r"biorxiv\.org/content/",
    ]

    MEDRXIV_PATTERNS = [
        r"medrxiv\.org/content/",
    ]

    # DOI patterns
    DOI_PATTERNS = [
        r"doi\.org/10\.",
        r"dx\.doi\.org/10\.",
    ]

    @classmethod
    def classify(cls, url: str) -> URLType:
        """
        Classify a URL to determine its type.

        Args:
            url: The URL to classify

        Returns:
            URLType enum indicating the type of content
        """
        url_lower = url.lower().strip()

        # Check for dangerous URL schemes first (security)
        try:
            parsed = urlparse(url_lower)
            if parsed.scheme in DANGEROUS_SCHEMES:
                return URLType.INVALID
            # Only allow http/https schemes
            if parsed.scheme and parsed.scheme not in ("http", "https", ""):
                return URLType.INVALID
        except Exception:
            return URLType.INVALID

        pmid, pmcid = academic_url_ids(url)
        if pmid:
            return URLType.PUBMED
        if pmcid:
            return URLType.PMC

        # Check for direct PDF link first
        if cls._is_pdf_url(url_lower):
            return URLType.PDF

        host = (parsed.hostname or "").lower().rstrip(".")
        path = parsed.path or ""
        if host in {"arxiv.org", "ar5iv.org"} and re.match(r"^/(?:abs|pdf|html)/", path):
            return URLType.ARXIV
        if host in {"biorxiv.org", "www.biorxiv.org"} and path.startswith("/content/"):
            return URLType.BIORXIV
        if host in {"medrxiv.org", "www.medrxiv.org"} and path.startswith("/content/"):
            return URLType.MEDRXIV
        if host in {"semanticscholar.org", "api.semanticscholar.org"} and path.startswith("/paper/"):
            return URLType.SEMANTIC_SCHOLAR
        if host in {"doi.org", "dx.doi.org"} and path.startswith("/10."):
            return URLType.DOI

        # Default to HTML for web pages
        return URLType.HTML

    @classmethod
    def _is_pdf_url(cls, url: str) -> bool:
        """Check if URL points directly to a PDF.

        Note: Academic source PDFs (arXiv, bioRxiv, etc.) are handled
        by their respective patterns, not as generic PDFs.
        """
        url_lower = url.lower()

        # Academic sources with PDF URLs should use their specialized downloaders
        academic_domains = {
            "arxiv.org", "ar5iv.org", "biorxiv.org", "www.biorxiv.org",
            "medrxiv.org", "www.medrxiv.org", "ncbi.nlm.nih.gov",
            "www.ncbi.nlm.nih.gov", "europepmc.org", "semanticscholar.org",
            "api.semanticscholar.org", "doi.org", "dx.doi.org",
        }
        if (urlparse(url_lower).hostname or "").lower().rstrip(".") in academic_domains:
            return False

        parsed = urlparse(url_lower)
        path = parsed.path

        # Check file extension
        if path.endswith(".pdf"):
            return True

        # Check common PDF URL patterns
        if "/pdf/" in path:
            return True

        return False

    @classmethod
    def extract_id(
        cls, url: str, url_type: Optional[URLType] = None
    ) -> Optional[str]:
        """
        Extract the identifier from a URL.

        Args:
            url: The URL to extract from
            url_type: Optional pre-classified type

        Returns:
            Extracted ID or None
        """
        if url_type is None:
            url_type = cls.classify(url)

        pmid, pmcid = academic_url_ids(url)
        if url_type == URLType.PUBMED and pmid:
            return pmid
        if url_type == URLType.PMC and pmcid:
            return pmcid

        if url_type == URLType.ARXIV:
            # Extract arXiv ID (e.g., 2301.12345 or cond-mat/0501234)
            match = re.fullmatch(r"/(?:abs|pdf|html)/(\d{4}\.\d{4,5}(?:v\d+)?)(?:\.pdf)?/?", urlparse(url).path,
                                 flags=re.IGNORECASE)
            if match:
                return match.group(1)
            # Old format
            match = re.fullmatch(r"/(?:abs|pdf|html)/([a-z-]+/\d{7}(?:v\d+)?)/?", urlparse(url).path,
                                 flags=re.IGNORECASE)
            if match:
                return match.group(1)

        elif url_type == URLType.PUBMED:
            match = re.fullmatch(r"/(?:pubmed/)?(\d+)/?", urlparse(url).path,
                                 flags=re.IGNORECASE)
            if match:return match.group(1)

        elif url_type == URLType.PMC:
            match = re.fullmatch(r"/(?:pmc/articles/|article/PMC/|articles/)?(PMC\d+)/?", urlparse(url).path,
                                 flags=re.IGNORECASE)
            if match:
                return f"PMC{match.group(1)}"

        elif url_type == URLType.SEMANTIC_SCHOLAR:
            # Extract paper ID (40-char hex)
            match = re.search(
                r"/paper/(?:[^/]+/)?([a-f0-9]{40})", url, re.IGNORECASE
            )
            if match:
                return match.group(1)

        elif url_type == URLType.DOI:
            match = re.fullmatch(r"/(10\.\d{4,}/[^\s?#]+?)/?", urlparse(url).path)
            if match:
                return match.group(1)

        return None

    @classmethod
    def get_source_name(cls, url_type: URLType) -> str:
        """Get human-readable source name."""
        names = {
            URLType.ARXIV: "arXiv",
            URLType.PUBMED: "PubMed",
            URLType.PMC: "PubMed Central",
            URLType.SEMANTIC_SCHOLAR: "Semantic Scholar",
            URLType.BIORXIV: "bioRxiv",
            URLType.MEDRXIV: "medRxiv",
            URLType.DOI: "DOI",
            URLType.PDF: "PDF",
            URLType.HTML: "Web Page",
            URLType.INVALID: "Invalid URL",
        }
        return names.get(url_type, "Unknown")
