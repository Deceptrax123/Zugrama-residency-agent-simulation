import base64
import subprocess
import unittest
from unittest.mock import patch

from residency.cv_pdf import MAX_ENCODED, pdf_text
from residency.store import AppError
from tests.pdf_fixture import make_pdf


def encoded(raw):return base64.b64encode(raw).decode()


class CVPDFTests(unittest.TestCase):
    def test_real_pdf_reader_preserves_supporting_quote_across_pages(self):
        text=pdf_text(encoded(make_pdf(pages=2)))
        self.assertEqual(text.count('Built Python tools for water monitoring.'),2)

    def test_reject_bad_oversized_empty_and_too_many_pages(self):
        for value in ('not base64',encoded(b'not a PDF'),'x'*(MAX_ENCODED+1),
                      encoded(b'%PDF-broken'),encoded(make_pdf('')),encoded(make_pdf(pages=21)),
                      encoded(make_pdf('x'*16001))):
            with self.assertRaises(AppError):pdf_text(value)

    def test_parser_timeout_is_bounded_and_does_not_leak_document(self):
        with patch('residency.cv_pdf.subprocess.run',side_effect=subprocess.TimeoutExpired('parser',20)):
            with self.assertRaises(AppError) as error:pdf_text(encoded(make_pdf()))
        self.assertEqual(error.exception.status,422)
        self.assertNotIn('Python',str(error.exception))
