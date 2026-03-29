import re
from rapidfuzz import fuzz 

class MedicalOCRValidator:
    def __init__(self, reference_data, threshold=0.80):
        self.reference_data = reference_data
        self.threshold = threshold

    def extract_dates(self, text):
        dates = []
        # Match MM/YYYY formats
        for m in re.finditer(r'\b(\d{2})[\.\-\/]+(\d{4})\b', text):
            dates.append(f"{m.group(1)}/{m.group(2)}")
        
        # Match MMM YYYY formats
        months = {"JAN":"01","FEB":"02","MAR":"03","APR":"04","MAY":"05","JUN":"06",
                  "JUL":"07","AUG":"08","SEP":"09","OCT":"10","NOV":"11","DEC":"12"}
        for m in re.finditer(r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[\.\-\/\s]*(\d{4})', text):
            dates.append(f"{months[m.group(1)]}/{m.group(2)}")
            
        return list(set(dates))

    def extract_batches(self, text):
        clean_text = re.sub(r'\b\d{2}[\.\-\/]+\d{4}\b', '|', text)
        clean_text = re.sub(r'(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[\.\-\/\s]*\d{4}', '|', clean_text)
        clean_text = re.sub(r'\b\d+\.\d{2}\b', '|', clean_text)
        
        # INCLUSIVE is now before INCL to prevent word-splitting
        labels = [
            r'B\.?\s*N[O0]\.?:?', r'BATCH\s*N[O0]\.?:?', r'LOT', 
            r'M\.?F\.?G\.?\s*D\.?T\.?:?', r'M\.?F\.?G\.?:?', r'M\.?D\.?:?', 
            r'E\.?X\.?P\.?\s*D\.?T\.?:?', r'E\.?X\.?P\.?:?', r'E\.?D\.?:?', 
            r'M\.?R\.?P\.?:?', r'R\.?S\.?:?', r'INCLUSIVE', r'INCL\.?',
            r'OF\s*ALL\s*TAXES', r'TAXES', r'TABS\.?', r'TABLETS', r'\bFOR\b', r'\bPER\b'
        ]
        for label in labels:
            clean_text = re.sub(label, '|', clean_text)

        raw_chunks = clean_text.split('|')
        
        candidates = []
        for chunk in raw_chunks:
            # Just remove spaces and punctuation, no character swapping
            norm = re.sub(r'[\s\W_]+', '', chunk)  
            if len(norm) >= 4 and not norm.isalpha():
                candidates.append(norm)
                
        return list(set(candidates))

    def get_similarity(self, a, b):
        # CHANGED: Using RapidFuzz. Divided by 100 to maintain your 0.0 to 1.0 scoring scale
        return fuzz.ratio(a, b) / 100.0

    def validate(self, raw_ocr):
        # 1. Handle single string vs list
        if not isinstance(raw_ocr, (tuple, list)):
            raw_ocr_list = [raw_ocr]
        else:
            raw_ocr_list = raw_ocr

        date_cands = []
        batch_cands = []

        # 2. EXTRACT SEPARATELY
        # We loop through the list and extract BEFORE joining anything
        for segment in raw_ocr_list:
            segment_str = str(segment).upper()
            date_cands.extend(self.extract_dates(segment_str))
            batch_cands.extend(self.extract_batches(segment_str))

        date_cands = list(set(date_cands))
        batch_cands = list(set(batch_cands))

        # 3. Join for the giant exact match string fallback only
        text = " ".join(map(str, raw_ocr_list)).upper()

        if not text:
            return "REJECT: No valid OCR text provided.\n"

        candidates_str = f"Extracted Batches: {batch_cands}\nExtracted Dates: {date_cands}"
        
        # Giant string for exact match, no translation applied
        giant_string = re.sub(r'[\s\W_]+', '', text)
        
        best_match = None
        highest_score = 0.0

        for ref in self.reference_data:
            if isinstance(ref, tuple):
                r_batch_raw = str(ref[0])
                r_expiry = str(ref[1])
            else:
                r_batch_raw = str(ref.get('batch_number', ''))
                r_expiry = str(ref.get('expiry_date', ''))

            ref_batch_norm = r_batch_raw.upper()

            # Exact Match
            if ref_batch_norm in giant_string:
                batch_score = 1.0
                date_score = 1.0 if r_expiry in date_cands else 0.0
                final_score = (batch_score * 0.7) + (date_score * 0.3)
                
                # EARLY EXIT: If batch is 1.0, accept immediately and skip the threshold check entirely!
                return f"{candidates_str}\n" + self.format_result(
                    r_batch_raw, r_expiry, 1.0, date_score, round(final_score, 2), "ACCEPT"
                )

            # Fuzzy Match
            for cand in batch_cands:
                batch_score = self.get_similarity(cand, ref_batch_norm)
                date_score = 1.0 if r_expiry in date_cands else 0.0
                final_score = (batch_score * 0.8) + (date_score * 0.2)

                # EARLY EXIT: If fuzzy matching hits exactly 1.0 for the batch, accept immediately!
                if batch_score == 1.0:
                    return f"{candidates_str}\n" + self.format_result(
                        r_batch_raw, r_expiry, 1.0, date_score, round(final_score, 2), "ACCEPT"
                    )

                if final_score > highest_score:
                    highest_score = final_score
                    best_match = {
                        "batch": r_batch_raw, "expiry": r_expiry,
                        "b_score": round(batch_score, 2), "d_score": date_score, "f_score": round(final_score, 2)
                    }

        decision = "ACCEPT" if highest_score >= self.threshold else "REJECT"
        
        if not best_match:
            return f"{candidates_str}\nREJECT: No matching candidates found.\n"

        return f"{candidates_str}\n" + self.format_result(
            best_match["batch"], best_match["expiry"], 
            best_match["b_score"], best_match["d_score"], 
            best_match["f_score"], decision
        )

    def format_result(self, batch, expiry, b_s, d_s, f_s, decision):
        return (f"Matched Batch: {batch} | Reference Expiry: {expiry}\n"
                f"Batch Score: {b_s} | Date Score: {d_s} | Final Score: {f_s}\n"
                f"Decision: {decision}\n")

# --- EXECUTION BLOCK ---
if __name__ == "__main__":
    ref_db = [
        ("TT25114","08/2027","84.38"),
        ("TT25133","10/2027","97.97"),
        ("250210135","01/2027","69.00"),
        ("GTG0584A","01/2027","175.00"),
        ("250910968","08/2027","58.88"),
        ("GT25177","12/2023","43.00"),
        ("251011092","09/2027","61.78"),
        ("250910946","08/2028","11.44"),
        ("GTG1825A","05/2027","125.00"),
        ("2510110255","09/2027","40.50"),
        ("2510110256","09/2027","40.50"),
        ("T12Y005","04/2027","65.87"),
        ("GTG2584A","02/2028","368.44"),
        ("6RA08007C","07/2028","258.00"),
        ("25AJ0030","01/2027","356.00"),
        ("K6C25002","06/2028","162.04"),
        ("2HV7M014","06/2027","184.60"),
        ("AC925029","07/2028","234.09"),
        ("722500196","06/2027","165.00"),
        ("RF1325034","06/2027","182.80"),
        ("2509109899","08/2028","37.88"),
        ("IQU12518","02/2027","90.00"),
        ("250930021","08/2028","25.93"),
        ("251011034","09/2027","37.50"),
        ("250911012","08/2028","40.78"),
        ("251011072","03/2027","77.25"),
        ("DBMY0954","09/2027","17.00"),
        ("250911006","08/2028","17.74"),
        ("AKG2500T","01/2028","77.44"),
        ("FND0725076BH","02/2028","139.69"),
        ("FT2502","09/2027","554.00"),
        ("P75Y006","06/2027","412.21"),
        ("250910956","08/2027","26.61"),
        ("5SD0219","03/2027","48.38"),
        ("5SN1451","06/2028","78.90"),
        ("GEJF0006","05/2027","174.70"),
        ("80250294A","07/2027","189.00"),
        ("G55Y032","06/2028","25.26"),
        ("I501123","02/2028","72.16"),
        ("GESF0002","06/2028","210.10"),
        ("ATS14ABA","07/2027","444.27"),
        ("D150R122","06/2029","139.15"),
        ("SPF250767","11/2027","170.00"),
        ("BRF09101A","08/2028","245.63"),
        ("E2501270","04/2027","266.00"),
        ("250910996","08/2027","16.30"),
        ("GTG2320A","07/2027","72.57"),
        ("250710788","06/2027","7.42"),
        ("48020678","08/2027","78.52"),
        ("250810859","07/2027","74.44"),
        ("250911003","08/2027","54.28"),
        ("250910947","08/2028","66.56"),
        ("250710690","06/2027","21.60"),
        ("D2250177","01/2028","80.50"),
        ("J12090","09/2027","181.22"),
        ("2523016N","01/2027","66.53")
    ]

    # FIXED: Wrapped ALL entries inside ONE master list.
    ocr_inputs = [
        ['B.NO.TT 25114 M.D.SEP.2025 E.D.AUG.2027', 'M.R.P.7.84.38', 'INCLUSIVE OFALLTAXES/IOTABS'],
        ['B.NO.25C', 'B.N0250910909', 'MFG.DTISEP.2025', 'M.R.PiRS43.13', 'EXP.DT.A', 'EXP.DTAUG.', '2027', 'FOR', '10', 'FOR#10', 'TABS.', 'INCL. OF ALLITAXES'],
        ['B.No.GT25177 MFG.07 /2025 EXP.12/2023', 'M.R.P.Rs.43.OPER1OTABS.I.A.T.'],
        ['B.NO.25C', 'B.N0250910909', 'MFG.DTISEP.2025', 'M.R.PiRS43.13', 'EXP.DT.A', 'EXP.DTAUG.', '2027', 'FOR', '10', 'FOR#10', 'TABS.', 'INCL. OF ALLITAXES'],
        ['M.L.N0.:KTK/25A301/95', 'MFD.BY:USV PVTLTD.', 'AT:B249/250.IND', 'STAGE,', 'PEENYA INDUSTRIAL ESTATE.', 'BANGALORE-56C058'],
        ['M.LN0.:KTK/25A/301/95', 'MFD.BY:USVPVT.LTD.', 'ATHB-249/250.IND STAGE,', 'PEENYA INDUSTHIAL ESTATE.', 'BANGALORE-56O 058'],
        ['M.L.N0WKTK/25A/301/95', 'MFD.BYEUSV PVT. LTD.', 'AT:B-249/250, IND 5TAGE', 'PEENYAHNDUSTRIAL ESTATE.', 'BANGALORE-560 G58'],
        ['B.N0.2250710788', 'MFG.DT.JUL:2025', 'EXP.DT.3UN.2027', 'M.R. P.RS.7.42', 'FOR', '10', 'TABS.', 'INCL.OFALL TAXES'],
        ['B.NO.:GTG0S28A', 'M69UDt10R72O25', 'EXO.DLOU20217', 'M.R.P.REMEOO', '(Incl.ofalfitakes)', 'per 10 Tablets'],
        ['for', '20', 'capsules', 'Roter br', '(inclusive of ah taxes)', 'Max.', 'Rotall'],
        ['B.NO. 250910989 , MG.DT.SEP.2025', 'EXP.DT.AUG.202&', 'MR.P.RS.37.88', 'FOR', '10', 'TABS.INCEOF ALL TAXES'],
        ['MFGDT.OCT.2O2E', 'B.NO.25101104MFG.DT.OCT.2025', 'B.NO', 'M.R.P.RS.37.50', 'EXP.DT.SEP.202EM.R.P.RS.3750', 'EXP.', 'INCLOF ALL', 'TAXES', 'FOR 10', 'TASINCLOFALL TAXES', 'FOR'],
        ['B.NO.251011034MFG.DT.OCT.2025', 'EXP.DT.SEP2O7', 'M.R.P.RS.37.50', 'FOR', '10', 'TASINCL OF ALL TAXES'],
        ['25', 'BN0.251011072MFG.DT.OCT.202S', '25', 'EXPDT.MAR.', '2027', 'M.R.P.RS.77#', 'ES', 'FOR', '10', 'CAPS.INCL.OFALLTAXES'],
        ['T.OCT.', '2025', 'B.NO.2510110FGDT.OCT.205', 'P.RS.37.50', 'EXP.DT.SEP.2027M.R.P.RS.3750', 'FALL TAXES', 'FOR', '10', 'TASSHINCL OF ALL TAXEE'],
        ['B.NO.AKG25OOT MAX.RETAIL PRICE', 'MFD.FEB.25', 'RS.77.44INCL.', 'EXPJAN.28', 'OF ALLTAXES'],
        ['B.NO.P75Y09GM.R.P. 412-21', 'MFG.07/2025NER 10 TABS.', 'EXP.06/2027NCL.OF ALL TAXES'],
        ['B.NO.P75Y006-M.R.P.FF.412-21', 'MFG.07/2025 PER90 TABS.', 'EXP.06/2C27 INCE OF ALL TAXES'],
        ['B.NO:P75YOOG:M.R.P.P412-21', 'MFG.07/2025PER 10 TABS.', 'EXP.06/202%INCL.OF ALL TAXES'],
        ['RS.78.90 FOR', '15', 'TABS.', 'B.NO.5SN1451MFDJUL25EXPJUN.28'],
        ['R18880G5B003', 'MF11IHPEnS262', 'EXPR0ATE O4202', 'M.R.RRs.51.15X15 TABS', 'INCL OE ALL TAXES'],
        ['B.No. GEJFO006', 'M.R.P.RS.174.70', 'MFG.DATEJUN.2025', 'PER STUPOF 10 TABS.', 'EXPIRYDATE MAY', '2027', 'INCLUS.IE OF ALL TAXES'],
        ['B:N0:i80250Z94A', 'M:PG.:0872025', 'EXP.:07/2037', 'M.R.P.Rs.X189.00', 'FOR IO TABS.', 'INCLUSIVE.OFALL TAXES'],
        ['Tablets D', 'Rivaroxaban', 'Rivaflo"2.5', '2.5mg', 'Composition:', 'Each film coated tabjet coptains:', 'Q.S.', 'Rwaroxaban EP', 'Excibients', 'Colours: Ferric Dxide Vellaw USP-NF.', 'Titanium Dioxide IP.', 'As ded by the Cardologist.', 'Dosage', 'Do not store above 30nC.', 'Kicine ', 'Swallow complete tablet. Do not crush or che', 'Refer encosed pcnsert furhr infor'],
        ['ECE', 'Rac', 'I1.', '8.N0.:B025029', 'MF.G.:08/2025', 'EXP.:07/202.7', 'M.R.P.RS::I89.0', 'FOR 10 TABS.', 'INCLUSIVE OF ALL TA'],
        ['TXTIESS', 'FOR10TABS.M.R.P.76.39', 'MEG.DATE04-2025 EXPIRY DATE 03-2027', 'MRP8M002', "'ONg"],
        ['B.NO.2RE8M002', '.2025', 'EXP.AUG.2027', 'MFG.SEP', 'PACK', 'OF 15 TABS.', 'M.R.P.', 'PER', 'BLISTER', 'OF', 'ALL', 'TAXES', 'H', '272-30', 'INCLUSIVE'],
        ['220510948', 'MFG. OXT.SEP.2025', 'EXP. DT.AUG. 2028', 'M.R.P.RS.11.44', 'FOR', '20', 'TABS.', 'INCL.OF ALL TAXES'],
        ['B.NO.', 'MFG. DT.SEP.2025', '290580346', 'EXP. DT.AUG.2028', 'M.R.P.RS.1L.44', 'FOR', 'COLOFALLTAY', '10', 'TABS'],
        ['M.R.P. Rs.125.00', 'Incl. of all taxes)', 'per 7 Tablets'],
        ['2202/50:2023', 'Mfg.Dt.: 06/2025', 'BAA GA'],
        ['025', 'BINO.251011025MFG.DT.OCT.2025', '50', 'EXP. DT. SEP.', '2027MR.P.RS.40.50', 'KES', 'FOR', '10', 'TABS. INCLOF ALL TAXES'],
        # ['B.NO. 251O11025MFG.DT.OCT.2025', 'EXP.DT. SEP.2027 M. R. P. RS', '.40.50', 'FOR', '10', 'TABSINCL. OF', 'ALL', 'TAXES'],
        # ['B.NO. 25101025 MFG.DT. OCT:2025', '0', 'EXP.DT.SEP#2027', 'M.R.P.RS.4050', 'FOR', '10', 'TABS', 'INCL.OF ALL TAXIES', 'S'],
        ['B.N0.25AJ0030MFG.AUG.2025', 'EXPIRY DATE:JAN.2O27', 'M.R.P.RS.356.OOFOR20CABS.I.A.T.'],
        ['B.NO.AC925O29 MAX.RETAILPRICE', 'MFD.AUG.25', 'RS.234.09INCL.', 'EXP.JUL.28', 'OF ALL TAXES']
    ]

    validator = MedicalOCRValidator(ref_db) 

    # FIXED: Added a loop to iterate over all entries
    for idx, ocr in enumerate(ocr_inputs):
        print(f"Processing Entry {ocr} ")
        print(validator.validate(ocr))