"""Isolated PDF parser worker: stdin PDF bytes, stdout JSON, no model calls."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from residency.cv_pdf import worker

if __name__ == '__main__':
    print(json.dumps(worker(), ensure_ascii=False))
