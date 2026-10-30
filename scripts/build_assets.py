"""Rebuild reproducible assets using pure-Python minifiers."""
from pathlib import Path
import rjsmin
import rcssmin

root=Path(__file__).resolve().parents[1]/'app'/'static'
(root/'dist').mkdir(exist_ok=True)
(root/'dist'/'app.min.js').write_text(rjsmin.jsmin((root/'app.js').read_text(encoding='utf-8')),encoding='utf-8')
(root/'dist'/'style.min.css').write_text(rcssmin.cssmin((root/'style.css').read_text(encoding='utf-8')),encoding='utf-8')
for name,target in [('app.js','app.min.js'),('style.css','style.min.css')]:
    before=(root/name).stat().st_size; after=(root/'dist'/target).stat().st_size
    print(f'{name}: {before} -> {after} bytes ({(1-after/before)*100:.1f}% smaller)')
