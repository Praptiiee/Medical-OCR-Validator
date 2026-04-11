import re
from difflib import SequenceMatcher
from pathlib import Path

DATASET_DIR = Path(__file__).resolve().parent / "dataset"

# 1. Similarity Helper
def calculate_similarity(a, b):
    if not a or not b: return 0
    return SequenceMatcher(None, str(a).strip(), str(b).strip()).ratio()

# 2. Updated Extraction Logic (Ensuring it ALWAYS returns a dict)
def extract_medical_candidates(text_content):
    text = str(text_content).upper()
    
    # --- Date Extraction ---
    dates = []
    month_map = {"JAN": "01", "FEB": "02", "MAR": "03", "APR": "04", "MAY": "05", "JUN": "06",
                 "JUL": "07", "AUG": "08", "SEP": "09", "OCT": "10", "NOV": "11", "NOL": "11", "DEC": "12", "JULY": "07"}
    month_regex = "|".join(month_map.keys())
    
    for m in re.finditer(r'\b(\d{2})[\.\-\/]+(\d{4})\b', text):
        dates.append(f"{m.group(1)}/{m.group(2)}")
    for m in re.finditer(rf'\b({month_regex})[\.\-\/\s]*(\d{{4}})', text):
        dates.append(f"{month_map[m.group(1)]}/{m.group(2)}")

    # --- Batch & Price Masking ---
    clean_text = re.sub(r'\b\d{2}[\.\-\/]+\d{4}\b', '|', text)
    clean_text = re.sub(rf'({month_regex})[\.\-\/\s]*\d{{4}}', '|', clean_text)
    
    labels = [r'B\.?\s*N[O0]\.?:?', r'MFD\.?', r'EXP\.?', r'M\.?R\.?P\.?', r'RS\.?', 
              r'INCLUSIVE', r'OF\s*ALL\s*TAXES', r'TABS\.?', r'BATCH', r'DATE', r'MFG\.?']
    for label in labels:
        clean_text = re.sub(label, '|', clean_text)

    raw_chunks = clean_text.split('|')
    batch_candidates = []
    price_candidates = []

    for chunk in raw_chunks:
        chunk = chunk.strip()
        if not chunk: continue
        prices = re.findall(r'\d+\.\d{2}|\d+/\-', chunk)
        if prices:
            price_candidates.extend([p.replace('/-', '.00') for p in prices])
            chunk = re.sub(r'\d+\.\d{2}|\d+/\-', '', chunk)
        norm = chunk.strip(' :.-')
        if len(norm) >= 3 and not re.match(r'^(FOR|TABS|AND|THE)$', norm):
            if any(c.isalnum() for c in norm):
                batch_candidates.append(norm)

    # CRITICAL: Always return this structure to avoid 'NoneType' errors
    return {
        "batches": list(set(batch_candidates)),
        "dates": list(set(dates)),
        "prices": list(set(price_candidates))
    }

# 3. Load Truth Data (data.txt)
def load_ground_truth(filepath):
    truth_data = []
    try:
        with open(filepath, 'r') as f:
            for line in f:
                parts = line.strip().split(',')
                if len(parts) >= 2:
                    truth_data.append({"batch": parts[0].upper(), "date": parts[1]})
    except FileNotFoundError:
        print(f"Error: {filepath} not found!")
    return truth_data

# 4. Compare Logic
def compare_and_score(extracted, ground_truth_list):
    best_match = {"batch_score": 0, "date_score": 0, "overall": 0}
    
    for target in ground_truth_list:
        b_score = 0
        # Exact match check first (Score 1.0)
        if target['batch'] in extracted['batches']:
            b_score = 1.0
        else:
            # Fuzzy match
            for cand in extracted['batches']:
                b_score = max(b_score, calculate_similarity(cand, target['batch']))
        
        d_score = 1.0 if target['date'] in extracted['dates'] else 0.0
        
        overall = (b_score + d_score) / 2
        current_total = round(overall * 100, 2)
        
        if current_total > best_match['overall']:
            best_match = {
                "batch_score": round(b_score * 100, 2),
                "date_score": round(d_score * 100, 2),
                "overall": current_total
            }
    return best_match

# --- MAIN EXECUTION ---
ground_truth = load_ground_truth(DATASET_DIR / "data.txt")
input_file = DATASET_DIR / "extractcand.txt" # Reading from dataset folder
output_file = DATASET_DIR / "final.txt"

try:
    with open(input_file, "r") as f:
        ocr_lines = [line.strip() for line in f if line.strip()]

    total_score = 0
    with open(output_file, "w") as out:
        header = f"{'OCR TEXT':<40} | {'BATCH%':<7} | {'DATE%':<7} | {'OVERALL%':<9} | {'STATUS'}"
        out.write(header + "\n" + "="*80 + "\n")

        for line in ocr_lines:
            extracted = extract_medical_candidates(line)
            scores = compare_and_score(extracted, ground_truth)
            
            status = "ACCEPT" if scores['overall'] >= 75 else "REJECT"
            total_score += scores['overall']
            
            row = f"{line[:40]:<40} | {scores['batch_score']:<7} | {scores['date_score']:<7} | {scores['overall']:<9} | {status}"
            out.write(row + "\n")

        final_acc = round(total_score / len(ocr_lines), 2) if ocr_lines else 0
        out.write("="*80 + f"\nSYSTEM ACCURACY: {final_acc}%")
        
    print(f"Done! Check {output_file} for results. System Accuracy: {final_acc}%")

except FileNotFoundError:
    print(f"Error: Could not find {input_file}. Make sure it exists in the dataset folder.")