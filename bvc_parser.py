#!/usr/bin/env python3
"""
BVC (Buget Venituri Cheltuieli) parser for Romanian listed company reports.

Extracts budget projections from Excel (.xlsx) and PDF files published on
company investor relations pages. The output is a normalized dict with yearly
projected revenue, expenses, gross profit, and net income.

Usage as module:
    from bvc_parser import parse_bvc_excel, parse_bvc_pdf, extract_bvc_from_url

Usage as script:
    python3 bvc_parser.py /path/to/bvc_file.xlsx
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from typing import Any, Dict, Optional
from urllib.parse import urlparse
from urllib.request import urlopen


# ---------------------------------------------------------------------------
# Romanian keyword matching
# ---------------------------------------------------------------------------

# Keywords that signal a BVC document (budget, projections)
_BVC_SIGNAL_KEYWORDS: list[str] = [
    "buget",
    "bvc",
    "venituri",
    "cheltuieli",
    "profit",
    "estimari",
    "proiectii",
    "proiectii",
]

# Label → normalized key mapping.  Patterns are case-insensitive and the
# first match wins.  Order matters: more specific patterns first.
_LABEL_PATTERNS: list[tuple[str, str]] = [
    # Revenue / income labels
    (r"venituri\s*totale", "revenue"),
    (r"venituri\s*din\s*exploatare", "revenue"),
    (r"venituri\s*operationale", "revenue"),
    (r"venituri", "revenue"),
    (r"cifra\s*de\s*afaceri\s*neta", "revenue"),
    (r"cifra\s*de\s*afaceri", "revenue"),
    (r"total\s*venituri", "revenue"),
    (r"total\s*revenue", "revenue"),
    # Expenses / cost labels
    (r"cheltuieli\s*totale", "expenses"),
    (r"cheltuieli\s*din\s*exploatare", "expenses"),
    (r"cheltuieli\s*operationale", "expenses"),
    (r"cheltuieli", "expenses"),
    (r"total\s*cheltuieli", "expenses"),
    (r"total\s*expenses", "expenses"),
    # Gross profit labels
    (r"profit\s*brut", "gross_profit"),
    (r"rezultat\s*brut", "gross_profit"),
    (r"profit\s*inainte\s*de\s*impozit", "gross_profit"),
    (r"ebitda", "gross_profit"),
    # Net income labels
    (r"profit\s*net", "net_income"),
    (r"rezultat\s*net", "net_income"),
    (r"profit\s*de\s*repartizat", "net_income"),
    (r"net\s*income", "net_income"),
    (r"net\s*profit", "net_income"),
]

# Year detection: 4-digit numbers between 2020–2099
_YEAR_RE = re.compile(r"\b(20[2-9]\d)\b")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_bvc(data: Any) -> bool:
    """Check whether *data* likely represents a BVC document.

    *data* can be a string (raw text), a list of strings (rows), or a list of
    lists/dicts (tabular data).  Returns ``True`` when at least one of the
    Romanian BVC-signalling keywords is found (case-insensitive).

    Args:
        data: Text, list of text lines, or tabular data to scan.

    Returns:
        True if BVC content detected, False otherwise.
    """
    text = _flatten_to_text(data)
    if not text:
        return False
    lower = text.lower()
    return any(kw in lower for kw in _BVC_SIGNAL_KEYWORDS)


def parse_bvc_excel(filepath: str) -> Optional[dict[str, Any]]:
    """Parse an Excel file (.xlsx) containing a BVC budget.

    Opens every sheet whose name contains ``Buget`` or ``BVC``
    (case-insensitive) and scans rows for known Romanian labels.
    Returns the first coherent set of projections found.

    Args:
        filepath: Path to the ``.xlsx`` file.

    Returns:
        ``{"year": int, "revenue": float, "expenses": float,
          "gross_profit": float, "net_income": float}``, or ``None``
          if no BVC data could be identified.

    Raises:
        ImportError: If ``openpyxl`` is not installed.
        FileNotFoundError: If *filepath* does not exist.
    """
    try:
        import openpyxl  # type: ignore[import-untyped]
    except ImportError:
        raise ImportError(
            "openpyxl not installed. Install with: pip install openpyxl"
        ) from None

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")

    wb = openpyxl.load_workbook(filepath, data_only=True)

    # Prefer sheets whose name suggests BVC content
    candidate_sheets: list[str] = []
    for name in wb.sheetnames:
        lower = name.lower()
        if "buget" in lower or "bvc" in lower:
            candidate_sheets.append(name)

    # Fallback: try all sheets
    sheets_to_try = candidate_sheets if candidate_sheets else wb.sheetnames

    for sheet_name in sheets_to_try:
        ws = wb[sheet_name]
        rows: list[list[Any]] = []
        for row in ws.iter_rows(min_row=1, values_only=True):
            rows.append(list(row))

        result = _parse_tabular_data(rows)
        if result is not None:
            wb.close()
            return result

    wb.close()
    return None


def parse_bvc_pdf(filepath: str) -> Optional[dict[str, Any]]:
    """Parse a PDF file containing a BVC budget.

    Tries ``pymupdf`` (fitz) first, then falls back to ``pdfplumber``.
    Extracts text from all pages, searches for Romanian labels, and
    returns normalized projections.

    Args:
        filepath: Path to the ``.pdf`` file.

    Returns:
        Same dict format as :func:`parse_bvc_excel`, or ``None``.

    Raises:
        ImportError: If neither ``pymupdf`` (fitz) nor ``pdfplumber``
                     is installed.
        FileNotFoundError: If *filepath* does not exist.
    """
    # Check for PDF library availability *before* checking file existence,
    # so callers get a clear ImportError rather than an unrelated FileNotFoundError.
    _check_pdf_library()

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")

    text = _extract_pdf_text(filepath)
    if text is None:
        return None

    # Split into lines and try tabular parsing
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    rows: list[list[str]] = []
    for line in lines:
        # Try to split on 2+ spaces (common in PDF text extraction)
        parts = re.split(r"\s{2,}", line)
        if parts:
            rows.append(parts)

    result = _parse_tabular_data(rows)
    if result is not None:
        return result

    # Last resort: scan the raw text more loosely
    return _parse_loose_text(text)


def extract_bvc_from_url(
    url: str,
    download_dir: str,
    timeout: int = 30,
) -> Optional[dict[str, Any]]:
    """Download a BVC file from *url* and parse it with the appropriate parser.

    The file extension (``.xlsx`` or ``.pdf``) determines the parser used.
    If the URL has no recognisable extension, both parsers are tried.

    Args:
        url: Public URL to the BVC document.
        download_dir: Local directory in which to save the downloaded file.
        timeout: HTTP read timeout in seconds (default 30).

    Returns:
        Parsed BVC dict, or ``None`` if the file could not be downloaded
        or parsed.

    Raises:
        RuntimeError: If the HTTP request fails (non-200 status or network error).
    """
    os.makedirs(download_dir, exist_ok=True)

    parsed_url = urlparse(url)
    filename = os.path.basename(parsed_url.path)
    if not filename:
        # Generate a name from the URL
        filename = "bvc_download"

    # Determine extension
    _, ext = os.path.splitext(filename)
    ext = ext.lower()

    # Download
    filepath = os.path.join(download_dir, filename)

    try:
        with urlopen(url, timeout=timeout) as resp:
            status = getattr(resp, "status", None) or getattr(resp, "code", 200)
            if hasattr(status, "__int__"):
                status = int(status)
            if status != 200:
                raise RuntimeError(
                    f"HTTP {status} when downloading {url}"
                )
            content = resp.read()

        with open(filepath, "wb") as f:
            f.write(content)

    except Exception as exc:
        raise RuntimeError(
            f"Failed to download {url}: {exc}"
        ) from exc

    # Parse based on extension
    if ext in (".xlsx", ".xls"):
        return parse_bvc_excel(filepath)

    if ext == ".pdf":
        return parse_bvc_pdf(filepath)

    # Unknown extension — try both
    for parser in (parse_bvc_excel, parse_bvc_pdf):
        try:
            result = parser(filepath)
            if result is not None:
                return result
        except Exception:
            continue

    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _check_pdf_library() -> None:
    """Raise ImportError early if no PDF library is available."""
    # Try pymupdf first
    try:
        import fitz  # type: ignore[import-untyped,import-not-found]  # noqa: F401
        return
    except ImportError:
        pass

    # Try pdfplumber
    try:
        import pdfplumber  # type: ignore[import-untyped,import-not-found]  # noqa: F401
        return
    except ImportError:
        pass

    raise ImportError(
        "Neither pymupdf (fitz) nor pdfplumber is installed. "
        "Install one with: pip install pymupdf  OR  pip install pdfplumber"
    )


def _flatten_to_text(data: Any) -> str:
    """Convert arbitrary *data* to a single lowercased string for keyword scan."""
    if isinstance(data, str):
        return data
    if isinstance(data, (list, tuple)):
        parts: list[str] = []
        for item in data:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, (list, tuple)):
                parts.append(" ".join(str(c) for c in item))
            elif isinstance(item, dict):
                parts.append(" ".join(str(v) for v in item.values()))
            else:
                parts.append(str(item))
        return " ".join(parts)
    if isinstance(data, dict):
        return " ".join(str(v) for v in data.values())
    return str(data)


def _extract_pdf_text(filepath: str) -> Optional[str]:
    """Extract raw text from a PDF, trying pymupdf first, then pdfplumber.

    Returns the combined text of all pages, or None if no library is available.
    """
    # --- pymupdf (fitz) ---
    try:
        import fitz  # type: ignore[import-untyped]
    except ImportError:
        pass
    else:
        doc = fitz.open(filepath)
        try:
            pages: list[str] = []
            for page in doc:
                pages.append(page.get_text())
            return "\n".join(pages)
        finally:
            doc.close()

    # --- pdfplumber ---
    try:
        import pdfplumber  # type: ignore[import-untyped]
    except ImportError:
        pass
    else:
        pages = []
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
        if pages:
            return "\n".join(pages)

    # Neither library available
    raise ImportError(
        "Neither pymupdf (fitz) nor pdfplumber is installed. "
        "Install one with: pip install pymupdf  OR  pip install pdfplumber"
    )


def _find_year(cells: list[str]) -> Optional[int]:
    """Return the first 4-digit year (2020–2099) found across *cells*."""
    for cell in cells:
        m = _YEAR_RE.search(str(cell))
        if m:
            return int(m.group(1))
    return None


def _parse_number(value: Any) -> Optional[float]:
    """Try to convert *value* to a float, handling Romanian/European formatting.

    Handles:
    - Strings like ``"12.345,67"`` (RO locale: ``.`` as thousands, ``,`` as decimal)
    - Strings like ``"12,345.67"`` (US locale)
    - Plain numbers, ints, floats.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    raw = str(value).strip()
    if not raw:
        return None

    # Remove common suffixes
    raw = re.sub(r"\s*(RON|LEI|lei|RON|€|EUR|%)\s*$", "", raw, flags=re.IGNORECASE)

    # Detect pattern: if comma is followed by exactly two digits → RO decimal
    # Otherwise treat comma as thousands separator.
    has_comma = "," in raw
    has_dot = "." in raw
    has_both = has_comma and has_dot

    if has_both:
        # Both present — decide by position
        dot_pos = raw.rfind(".")
        comma_pos = raw.rfind(",")
        if comma_pos > dot_pos:
            # Rightmost is comma → RO: dot=thousands, comma=decimal
            raw = raw.replace(".", "").replace(",", ".")
        else:
            # Rightmost is dot → US: comma=thousands, dot=decimal
            raw = raw.replace(",", "")
    elif has_comma:
        # Only comma present — check if it looks like decimal (exactly 2 digits after)
        comma_idx = raw.rfind(",")
        after_comma = raw[comma_idx + 1:]
        if len(after_comma) == 2 and after_comma.isdigit():
            raw = raw.replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif has_dot and raw.count(".") > 1:
        # Multiple dots and no comma → Romanian thousands separators
        # e.g. "69.965.000" → 69965000
        raw = raw.replace(".", "")
    # else: only one dot or no separator → US format, pass through

    try:
        return float(raw)
    except (ValueError, TypeError):
        return None


def _parse_tabular_data(rows: list[list[Any]]) -> Optional[dict[str, Any]]:
    """Attempt to extract BVC projections from tabular data (list of rows).

    Each row is a sequence of cell values.  We search for a label in the
    first column (or first few columns) and take the first numeric value
    in the remaining columns as the amount.

    Returns a normalized dict or None.
    """
    if not rows:
        return None

    extracted: dict[str, Optional[float]] = {
        "revenue": None,
        "expenses": None,
        "gross_profit": None,
        "net_income": None,
    }
    year: Optional[int] = None

    for row in rows:
        if not row:
            continue

        # Build a single label string from the first few text-ish cells
        label_parts: list[str] = []
        value_idx: Optional[int] = None
        for idx, cell in enumerate(row):
            if cell is None:
                continue
            s = str(cell).strip()
            if not s:
                continue
            if re.match(r"^[-]?\d", s) or s in ("-", "—", "–", "n/a", "N/A"):
                # Looks like a number or placeholder — this is the value column
                if value_idx is None:
                    value_idx = idx
                continue
            # Heuristic: if we haven't found a value column yet and the cell
            # has mixed text+digits, it might still be a label.
            if value_idx is None:
                label_parts.append(s)

        label = " ".join(label_parts).strip()
        if not label:
            continue

        # Try to find the year early
        if year is None:
            y = _find_year(label_parts)
            if y is not None:
                year = y
            elif value_idx is not None and value_idx < len(row):
                y = _find_year([str(row[value_idx])])
                if y is not None:
                    year = y

        # Match label against known patterns
        label_lower = label.lower()
        matched_key: Optional[str] = None
        for pattern, key in _LABEL_PATTERNS:
            if re.search(pattern, label_lower):
                matched_key = key
                break

        if matched_key is None:
            continue

        # Extract the numeric value from the remaining cells in this row
        if value_idx is not None:
            candidates = row[value_idx:]
        else:
            candidates = row[len(label_parts):]

        for cell in candidates:
            val = _parse_number(cell)
            if val is not None:
                # If we already have this key and the new value is smaller,
                # it might be a sub-item — prefer the larger (total) value.
                existing = extracted[matched_key]
                if existing is None or abs(val) > abs(existing):
                    extracted[matched_key] = val
                break

    # Also scan for a standalone year if not yet found
    if year is None:
        for row in rows:
            for cell in row:
                y = _find_year([str(cell)])
                if y is not None:
                    year = y
                    break
            if year is not None:
                break

    # Require at least revenue or net_income to consider this a valid parse
    if extracted["revenue"] is None and extracted["net_income"] is None:
        return None

    # Fill year default if still missing
    if year is None:
        year = 0  # unknown

    return {
        "year": year,
        "revenue": extracted["revenue"] or 0.0,
        "expenses": extracted["expenses"] or 0.0,
        "gross_profit": extracted["gross_profit"] or 0.0,
        "net_income": extracted["net_income"] or 0.0,
    }


def _parse_loose_text(text: str) -> Optional[dict[str, Any]]:
    """Fallback parser for PDF text that didn't parse cleanly as tabular data.

    Scans the text for known label patterns followed by a number on the same
    or next line.
    """
    lines = text.splitlines()
    year: Optional[int] = None
    extracted: dict[str, Optional[float]] = {
        "revenue": None,
        "expenses": None,
        "gross_profit": None,
        "net_income": None,
    }

    # Try to find year early
    for line in lines:
        y = _find_year([line])
        if y is not None:
            year = y
            break

    for i, line in enumerate(lines):
        line_lower = line.strip().lower()
        if not line_lower:
            continue

        matched_key: Optional[str] = None
        for pattern, key in _LABEL_PATTERNS:
            if re.search(pattern, line_lower):
                matched_key = key
                break

        if matched_key is None:
            continue

        # Look for a number on this line
        found_on_line = False
        numbers = re.findall(r"[-]?\d[\d.,]*\d", line)
        for num_str in numbers:
            val = _parse_number(num_str)
            if val is not None:
                found_on_line = True
                existing = extracted[matched_key]
                if existing is None or abs(val) > abs(existing):
                    extracted[matched_key] = val
                break

        # If no number on this line, try the next line
        if not found_on_line and i + 1 < len(lines):
            numbers = re.findall(r"[-]?\d[\d.,]*\d", lines[i + 1])
            for num_str in numbers:
                val = _parse_number(num_str)
                if val is not None:
                    existing = extracted[matched_key]
                    if existing is None or abs(val) > abs(existing):
                        extracted[matched_key] = val
                    break

    if extracted["revenue"] is None and extracted["net_income"] is None:
        return None

    if year is None:
        year = 0

    return {
        "year": year,
        "revenue": extracted["revenue"] or 0.0,
        "expenses": extracted["expenses"] or 0.0,
        "gross_profit": extracted["gross_profit"] or 0.0,
        "net_income": extracted["net_income"] or 0.0,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python3 bvc_parser.py <filepath>", file=sys.stderr)
        sys.exit(1)

    filepath = sys.argv[1]
    ext = os.path.splitext(filepath)[1].lower()

    if ext in (".xlsx", ".xls"):
        result = parse_bvc_excel(filepath)
    elif ext == ".pdf":
        result = parse_bvc_pdf(filepath)
    else:
        # Try both
        result = parse_bvc_excel(filepath) or parse_bvc_pdf(filepath)

    if result is None:
        print(json.dumps({"error": "Could not parse BVC data"}, ensure_ascii=False))
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, indent=2))
