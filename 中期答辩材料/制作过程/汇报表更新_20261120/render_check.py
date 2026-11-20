"""Native Word PDF raster QA using the bundled PDFium runtime."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pypdfium2 as pdfium
from pypdf import PdfReader

root = Path(__file__).resolve().parent
results, images, page_texts = {}, {}, {}
for name in ('docx', 'doc'):
    doc = pdfium.PdfDocument(root / f'report_{name}.pdf')
    out = root / f'pages_{name}'
    out.mkdir(exist_ok=True)
    hashes, texts, pixels = [], [], []
    for i in range(len(doc)):
        page = doc[i]
        pil = page.render(scale=1.6).to_pil().convert('RGB')
        pil.save(out / f'page-{i+1}.png')
        hashes.append(hashlib.sha256(pil.tobytes()).hexdigest())
        pixels.append(np.asarray(pil))
        texts.append(page.get_textpage().get_text_range())
    (root / f'page_text_{name}.txt').write_text('\n'.join(f'PAGE {i+1}\n{v}' for i, v in enumerate(texts)), encoding='utf-8')
    results[name], images[name], page_texts[name] = hashes, pixels, texts
differences = []
for i, (a, b) in enumerate(zip(images['docx'], images['doc']), 1):
    diff = np.any(a != b, axis=2)
    ys, xs = np.where(diff)
    differences.append({'page': i, 'pixel_difference_fraction': float(diff.mean()),
                        'bounds': [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())] if len(xs) else None,
                        'text_equal': page_texts['docx'][i-1] == page_texts['doc'][i-1]})
assert len(results['doc']) == len(results['docx']) == 6
assert all(len(t.strip()) > 100 for t in page_texts['docx'])
(root / 'render_comparison.json').write_text(json.dumps({'page_hashes': results, 'differences': differences}, indent=2), encoding='utf-8')
print(json.dumps(differences, indent=2))
for i, page in enumerate(PdfReader(root / 'report_docx.pdf').pages, 1):
    text = page.extract_text()
    print(i, 'CHARS', len(text), 'FIRST', text[:45].replace('\n', ' '), 'LAST', text[-70:].replace('\n', ' '))
