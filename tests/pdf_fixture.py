"""Tiny synthetic text PDF used by upload tests; no personal data."""
def make_pdf(text='Built Python tools for water monitoring.', pages=1):
    escaped=text.replace('\\','\\\\').replace('(','\\(').replace(')','\\)')
    stream=f'BT /F1 12 Tf 40 760 Td ({escaped}) Tj ET'.encode('ascii')
    font_id=3+2*pages
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',
        f'<< /Type /Pages /Count {pages} /Kids ['.encode()+b' '.join(f'{3+2*i} 0 R'.encode() for i in range(pages))+b'] >>']
    for index in range(pages):
        objects.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {4+2*index} 0 R >>'.encode())
        objects.append(f'<< /Length {len(stream)} >>\nstream\n'.encode()+stream+b'\nendstream')
    objects.append(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')
    result=b'%PDF-1.4\n';offsets=[0]
    for index,body in enumerate(objects,1):
        offsets.append(len(result));result+=f'{index} 0 obj\n'.encode()+body+b'\nendobj\n'
    start=len(result)
    result+=f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode()
    result+=b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets[1:])
    return result+f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode()
