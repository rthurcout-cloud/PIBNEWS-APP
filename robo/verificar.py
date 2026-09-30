"""Checagem rápida (a cada 15 min): tem vídeo novo na pasta do Drive? Escreve tem=1 pro GitHub Actions."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comum import ler_app, listar_drive, pendentes

arquivos = listar_drive()
novos = pendentes(ler_app(), arquivos)
print(f'{len(arquivos)} vídeo(s) na pasta, {len(novos)} novo(s)')
for a in novos:
    print(' -', a[1])
with open(os.environ.get('GITHUB_OUTPUT', os.devnull), 'a', encoding='utf-8') as f:
    f.write(f"tem={'1' if novos else '0'}\n")
