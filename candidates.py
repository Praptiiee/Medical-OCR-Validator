import re
from pathlib import Path

DATASET_DIR = Path(__file__).resolve().parent / "dataset"

def extract_medical_candidates(text_content):
    # Flatten/Clean Input
    text = str(text_content).upper().replace('[', '').replace(']', '').replace('"', '').replace("'", "")
    
    # 1. DATE EXTRACTION
    dates = []
    month_map = {"JAN": "01", "FEB": "02", "MAR": "03", "APR": "04", "MAY": "05", "JUN": "06",
                 "JUL": "07", "AUG": "08", "SEP": "09", "OCT": "10", "NOV": "11", "NOL": "11", "DEC": "12"}
    month_regex = "|".join(month_map.keys())
    
    for m in re.finditer(r'\b(\d{2})[\.\-\/]+(\d{4})\b', text):
        dates.append(f"{m.group(1)}/{m.group(2)}")
    for m in re.finditer(rf'\b({month_regex})[\.\-\/\s]*(\d{{4}})', text):
        dates.append(f"{month_map[m.group(1)]}/{m.group(2)}")
    

    # 2. MASKING (Crucial to separate numeric batches from prices)
    # Mask dates and decimals (prices) so they aren't confused with short numeric batches
    clean_text = re.sub(r'\b\d{2}[\.\-\/]+\d{4}\b', ' | ', text)
   
    clean_text = re.sub(rf'\b({month_regex})[\.\-\/\s]*\d{{4}}', ' | ', clean_text)
   
    
    # Mask Prices with decimals (e.g., 120.00)
    clean_text = re.sub(r'\d+\.\d{2}', ' | ', clean_text)
    
    clean_text = re.sub(r'\d+/\-', ' | ', clean_text)
      # Debug: See the masked text before candidate extraction

    # Remove Labels
    labels = [r'B\.?\s*N[O0]\.?:?', r'MFD\.?', r'EXP\.?', r'M\.?R\.?P\.?', r'RS\.?', 
              r'INCLUSIVE', r'OF\s*ALL\s*TAXES', r'TABS\.?', r'BATCH', r'DATE', r'MFG\.?', 
              r'LETS', r'TABLETS', r'CAPSULES', r'RS', r'MRP']
    for label in labels:
        clean_text = re.sub(label, ' | ', clean_text)

    # 3. EXTRACT BATCH CANDIDATES
    raw_chunks = clean_text.split('|')
    batch_candidates = []

    for chunk in raw_chunks:
        # Remove extra noise around the chunk
        chunk = chunk.strip(' :.-_')
        if not chunk: continue
        
        parts = chunk.split()
        for p in parts:
            p = p.strip(' :.-_')
            
            # --- NEW BATCH LOGIC ---
            # 1. Matches Alphanumeric (like MNB/06 or DT6522)
            if len(p) >= 3 and any(c.isalpha() for c in p) and any(c.isdigit() for c in p):
                batch_candidates.append(p)
            
            # 2. Matches Numeric Only (like 18 or 718)
            # Must be purely digits and length 1 to 4
            elif p.isdigit() and 1 <= len(p) <= 4:
                batch_candidates.append(p)
                
            # 3. Matches pure alphanumeric length 5+ 
            elif len(p) >= 5 and p.isalnum():
                batch_candidates.append(p)

    return {
        "batches": list(set(batch_candidates)),
        "dates": list(set(dates))
    }

def process_ocr_file(input_path, output_path=None):
    """Reads raw OCR, extracts candidates, and saves to dataset/extractcand.txt by default"""
    if output_path is None:
        output_path = DATASET_DIR / "extractcand.txt"
    all_results = []
    try:
        # 1. Read the input file (cleaneed.txt or ocr_data.txt)
        with open(input_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]

        # 2. Open the output file to save the candidate report
        with open(output_path, 'w', encoding='utf-8') as out:
            out.write("MEDICAL CANDIDATE EXTRACTION REPORT\n")
            out.write("="*40 + "\n\n")
            
            for line in lines:
                # Use the extraction logic for each line
                res = extract_medical_candidates(line)
                all_results.append({"original_text": line, "extracted": res})
                
                # Write to the report file
                out.write(f"RAW TEXT: {line}\n")
                out.write(f"  > BATCHES: {res['batches']}\n")
                out.write(f"  > DATES:   {', '.join(res['dates']) if res['dates'] else 'None'}\n")
                out.write("-" * 30 + "\n")
        
        # Return the list so main.py can use it for scoring
        return all_results
        
    except Exception as e:
        print(f"Error in process_ocr_file: {e}")
        return []