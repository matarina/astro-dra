#!/usr/bin/env python3
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
D=ROOT/'evaluation/scholar-strategy-20261112/pilot-assessment-v2-20261113'
def main():
 p=json.loads((D/'summary-private.json').read_text())
 p['calibration'].pop('known_labels_private',None)
 p['status']='valid_blinded_assessment_complete_public_summary'
 (D/'summary.json').write_text(json.dumps(p,ensure_ascii=False,indent=2)+'\n')
 print(p['reports'],p['calibration'])
if __name__=='__main__':main()
