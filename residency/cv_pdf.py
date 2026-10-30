"""Read uploaded CV PDFs in a bounded subprocess; never retain the binary file."""
import base64
import binascii
import json
import subprocess
import sys

from .config import APP_ROOT
from .store import AppError

MAX_PDF_BYTES = 3 * 1024 * 1024
MAX_ENCODED = 4 * ((MAX_PDF_BYTES + 2) // 3)
MAX_CV_TEXT = 16000
MAX_PAGES = 20


def pdf_text(encoded):
    if not isinstance(encoded, str) or len(encoded) > MAX_ENCODED:
        raise AppError('Choose a PDF no larger than 3 MB', 413)
    try: raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error): raise AppError('The PDF upload is invalid') from None
    if not raw.startswith(b'%PDF-') or len(raw) > MAX_PDF_BYTES:
        raise AppError('Upload a valid PDF no larger than 3 MB')
    try:
        result = subprocess.run([sys.executable, '-I', '-B', str(APP_ROOT/'scripts/pdf_text.py')],
            input=raw, capture_output=True, timeout=20, env={'LANG':'C.UTF-8'})
        value = json.loads(result.stdout) if result.returncode == 0 else {'error':'invalid'}
    except subprocess.TimeoutExpired:
        raise AppError('This PDF took too long to read. Try a simpler text PDF', 422) from None
    except (OSError, ValueError):
        raise AppError('The PDF reader is unavailable. Install requirements-pdf.txt for this app', 503) from None
    errors = {
        'encrypted': 'Upload an unlocked PDF; password-protected PDFs are not supported',
        'pages': 'Use a CV PDF with at most 20 pages',
        'length': 'This CV contains more than 16,000 characters. Upload a shorter CV',
        'empty': 'No readable text was found. Export a text PDF; scanned images need OCR first',
        'dependency': 'The PDF reader is unavailable. Install requirements-pdf.txt for this app',
        'invalid': 'This PDF could not be read. Try exporting it again as a text PDF',
    }
    if value.get('error'):
        code = value['error']
        raise AppError(errors.get(code, errors['invalid']), 503 if code == 'dependency' else 422)
    text = value.get('text')
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_CV_TEXT:
        raise AppError(errors['invalid'], 422)
    return text


def worker():
    import io
    import logging
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    sys.path.insert(0, str(APP_ROOT/'.tools/pdf-libs'))
    try: from pypdf import PdfReader
    except ImportError: return {'error':'dependency'}
    logging.disable(logging.CRITICAL)
    try:
        reader = PdfReader(io.BytesIO(sys.stdin.buffer.read(MAX_PDF_BYTES + 1)))
        if reader.is_encrypted: return {'error':'encrypted'}
        if not 1 <= len(reader.pages) <= MAX_PAGES: return {'error':'pages'}
        parts = []
        for page in reader.pages:
            parts.append((page.extract_text() or '').replace('\x00', '').strip())
            if sum(len(part) + 2 for part in parts) > MAX_CV_TEXT: return {'error':'length'}
        text = '\n\n'.join(parts).strip()
        return {'text': text} if text else {'error':'empty'}
    except Exception: return {'error':'invalid'}
