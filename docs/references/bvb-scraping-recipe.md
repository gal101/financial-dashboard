# BVB Financial Data Scraping Recipe

## Overview

Extract quarterly (last 12) and annual (last 5 years) financial data from Romanian company investor relations pages. Sources: Excel files (.xlsx) preferred, PDF annual reports as fallback.

## Steps

### 1. Discover Excel/PDF links
- Navigate to company IR page with Playwright CDP on `ws://localhost:3000`
- Look for pages: "Rezultate Financiare", "Rapoarte", "Investitori", "Relatii Investitori"
- Collect all `.xlsx` and PDF links containing financial keywords (T1, S1, T3, Annual, preliminar)

### 2. Download and parse Excel files
- Use `curl` + `openpyxl` (data_only=True)
- **Column layout detection (Pitfall #35):**
  - Format A (RO-only, 4 cols): Col 0=RO label, Col 1=prev year, **Col 2=current**, Col 3=Δ%
  - Format B (bilingual, 5+ cols): Col 0=RO label, Col 1=EN label, Col 2=prev year, **Col 3=current**, Col 4=Δ%
  - Detection: check if col 1 contains English text → Format B
- **Always print raw column headers and first 5 rows before extracting**
- Revenue labels: "Venituri din exploatare", "Cifra de afaceri", "Total Revenue"
- NI labels: "Rezultat net", "Profit net", "Net income"
- Handle European comma decimals (e.g., "30,05" → 30.05)

### 3. Derive individual quarters from cumulative reports
Romanian semi-annual reporting:
- T1 = Q1 only
- S1 = Q1+Q2 (H1, cumulative)
- T3 = Q1+Q2+Q3 (9M, cumulative)
- Annual = Q1+Q2+Q3+Q4 (FY)

Derivation:
```
Q1 = T1
Q2 = S1 - T1
Q3 = T3 - S1
Q4 = Annual - T3
```

### 4. Fill Q4 gaps from PDF annual reports
- Download annual PDF (`pymupdf` / `fitz`)
- Search for "venituri din exploatare de X milioane" and "profit net de X milioane"
- Also extract growth percentages (e.g., "creștere cu 64%") to derive prior year if exact number not stated
- Cross-reference: `Annual = 9M_cumulative + Q4_derived`

### 5. Write to SQLite
- RED ZONE tables: `quarterly`, `annual` — use `db.upsert_quarterly()` / `db.upsert_annual()`
- Source field MUST contain actual document URL (not text label):
  - Excel: `https://company.ro/.../T3_2025.xlsx`
  - PDF: `https://company.ro/.../Annual_2024.pdf (p5: 84.4M rev, 16.4M NI)`
  - Derived: `https://company.ro/.../Annual_2023.pdf (derived from 64% growth vs 2022)`
- After writing, run `db.export_to_json()` to regenerate `company_data.json`

### 6. Frontend: always show last 12 quarters
```javascript
var qs = comp.quarterly.slice(-12);  // NOT slice(0, 12)
```

## Pitfalls
- DO NOT trust Yahoo Finance P/E ratios for BVB stocks — calculate from raw data
- "Venituri din exploatare" ≠ "Cifra de afaceri" — former includes capitalized production
- Q4 is rarely in Excel files — must derive from annual PDF
- Earlier quarters (before company had Excel downloads) may be in prev-year columns of later reports
- Per-sheet format detection needed — same workbook can mix Format A and B across sheets
- Always backup DB before writing: `db.backup()`
