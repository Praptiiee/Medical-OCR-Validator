import re
from difflib import SequenceMatcher
from pathlib import Path
# Importing from your specific file: candidates.py
from candidates import extract_medical_candidates, process_ocr_file 

DATASET_DIR = Path(__file__).resolve().parent / "dataset"

# --- 1. Scoring Helpers ---
def calculate_similarity(a, b):
    if not a or not b: return 0
    return SequenceMatcher(None, str(a).strip(), str(b).strip()).ratio()

def normalize_date(date_str):
    """Converts YYYY-MM-DD to MM/YYYY to match OCR extraction"""
    # Handles "2021-08-01" -> "08/2021"
    match = re.search(r'(\d{4})-(\d{2})-\d{2}', date_str)
    if match:
        return f"{match.group(2)}/{match.group(1)}"
    return date_str

def load_ground_truth(filepath):
    truth_data = []
    try:
        with open(filepath, 'r') as f:
            for line in f:
                # Cleaning the tuple-like strings in your data.txt
                line = line.replace('(', '').replace(')', '').replace('"', '').strip()
                parts = line.split(',')
                if len(parts) >= 3:
                    # parts[0] is Batch, parts[1] is MFD, parts[2] is EXP
                    truth_data.append({
                        "batch": parts[0].strip().upper(),
                        "mfd": normalize_date(parts[1].strip()),
                        "exp": normalize_date(parts[2].strip())
                    })
    except Exception as e:
        print(f"Error loading truth data: {e}")
    return truth_data

# --- 1. Updated Compare Logic ---
def compare_and_score(extracted, ground_truth_list):
    """Compares extracted data against the dataset and identifies the BEST matching entry"""
    best_match = {
        "batch_score": 0, 
        "date_score": 0, 
        "overall": 0, 
        "matched_batch": "N/A" # New field to track which batch matched
    }
    
    for target in ground_truth_list:
        # Batch Scoring
        b_score = 0
        current_best_cand = ""
        
        if target['batch'] in extracted['batches']:
            b_score = 1.0
        else:
            for cand in extracted['batches']:
                score = calculate_similarity(cand, target['batch'])
                if score > b_score:
                    b_score = score

        # Date Scoring
        d_score = 1.0 if (target['mfd'] in extracted['dates'] or target['exp'] in extracted['dates']) else 0.0
        
        overall = (b_score + d_score) / 2
        current_overall_pct = round(overall * 100, 2)
        
        # If this dataset entry is a better match than previous ones, save it
        if current_overall_pct > best_match['overall']:
            best_match = {
                "batch_score": round(b_score * 100, 2),
                "date_score": round(d_score * 100, 2),
                "overall": current_overall_pct,
                "matched_batch": target['batch'] # Keep track of the dataset batch name
            }
            
    return best_match

# --- 2. Updated Execution Logic ---
def run_pipeline():
    source_file = DATASET_DIR / "cleaneed.txt"
    truth_file = DATASET_DIR / "data.txt"
    output_file = DATASET_DIR / "final.txt"
    
    print("Step 1: Extracting candidates...")
    ocr_results = process_ocr_file(source_file)
    
    print(f"Step 2: Comparing and generating {output_file}...")
    ground_truth = load_ground_truth(truth_file)
    
    total_accuracy = 0
    with open(output_file, "w") as out:
        # Updated Header to include "DATASET MATCH"
        header = f"{'OCR RAW TEXT':<35} | {'DATASET MATCH':<15} | {'BATCH%':<7} | {'DATE%':<7} | {'OVERALL%':<9} | {'STATUS'}"
        out.write(header + "\n")
        out.write("="*105 + "\n")

        for entry in ocr_results:
            raw_text = entry['original_text']
            extracted = entry['extracted']
            
            # Get the best match details
            scores = compare_and_score(extracted, ground_truth)
            
            status = "ACCEPT" if scores['overall'] >= 75 else "REJECT"
            total_accuracy += scores['overall']
            
            # Format the row with the Matched Batch name
            row = (f"{raw_text[:35]:<35} | "
                   f"{scores['matched_batch']:<15} | "
                   f"{scores['batch_score']:<7} | "
                   f"{scores['date_score']:<7} | "
                   f"{scores['overall']:<9} | "
                   f"{status}")
            out.write(row + "\n")

        final_val = round(total_accuracy / len(ocr_results), 2) if ocr_results else 0
        out.write("="*105 + f"\nTOTAL SYSTEM ACCURACY: {final_val}%")
    
    print(f"Complete! Accuracy: {final_val}%")

if __name__ == "__main__":
    run_pipeline()