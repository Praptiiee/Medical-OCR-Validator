# Medical-OCR-Validator
A robust post-processing pipeline for validating noisy OCR outputs from pharmaceutical packaging using regex-based extraction and fuzzy matching.

📌 Problem Statement

OCR systems often produce noisy and inconsistent text, especially in real-world environments like medicine packaging.

Key challenges:

Misread characters (e.g., O vs 0, S vs 5)
Broken formatting
Mixed text segments
Inconsistent date formats

This project builds a data validation pipeline to reliably extract and validate:

Batch Numbers
Expiry Dates
⚙️ Approach

The pipeline consists of 4 main stages:

1. Text Normalization
Converts OCR input into uppercase
Removes noise and unwanted symbols
2. Information Extraction
Regex-based extraction of:
Dates (MM/YYYY, MMM YYYY)
Batch numbers
3. Fuzzy Matching
Uses RapidFuzz for similarity scoring
Handles OCR distortions and partial matches
4. Decision Engine
Weighted scoring:
Batch match → 70–80%
Date match → 20–30%
Outputs:
✅ ACCEPT
❌ REJECT
🧠 Tech Stack
Python
Regex (re)
RapidFuzz (Fuzzy Matching)
📊 Example
Input (OCR Output)
B.NO.TT 25114 M.D.SEP.2025 E.D.AUG.2027
Output
Matched Batch: TT25114
Expiry: 08/2027
Final Score: 0.95
Decision: ACCEPT


📈 Use Cases
Pharmaceutical packaging validation
Supply chain verification
OCR post-processing systems
Compliance automation
