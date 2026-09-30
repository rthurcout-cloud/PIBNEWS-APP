"""Funções comuns do robô de cortes (só biblioteca padrão do Python)."""
import html, json, os, re, urllib.request

APP_URL = os.environ.get('APP_URL', 'https://pibnews-app.vercel.app')
PASTA_DRIVE = os.environ.get('PASTA_DRIVE', '1rEWdoYDcdlfo19mXGauTbNQkUDGNEcAc')
EXTENSOES = ('.mp4', '.mov', '.mkv', '.m4v', '.webm', '.avi', '.ts')


def http(url, dados=None, cab=None, metodo=None, tempo=120):
    req = urllib.request.Request(url, data=dados, headers=cab or {'User-Agent': 'Mozilla/5.0'}, method=metodo)
    with urllib.request.urlopen(req, timeout=tempo) as r:
        return r.read()


def ler_app():
    return json.loads(http(APP_URL + '/api/data'))


def gravar_app(mudar):
    """Lê o banco na hora, aplica a mudança e grava (pra não atropelar o que foi salvo no app)."""
    d = ler_app()
    mudar(d)
    http(APP_URL + '/api/data', json.dumps(d, ensure_ascii=False).encode('utf-8'),
         {'Content-Type': 'application/json', 'User-Agent': 'robo-cortes'}, 'POST')
    return d


def listar_drive(pasta=PASTA_DRIVE):
    """Arquivos de vídeo da pasta compartilhada do Drive (qualquer pessoa com o link): [(id, nome)]."""
    s = http(f'https://drive.google.com/embeddedfolderview?id={pasta}').decode('utf-8', 'replace')
    out = []
    for m in re.finditer(r'<a href="https://drive\.google\.com/file/d/([^/"]+)/[^"]*"[^>]*>.*?<div class="flip-entry-title">(.*?)</div>', s, re.S):
        nome = html.unescape(m.group(2)).strip()
        if nome.lower().endswith(EXTENSOES):
            out.append((m.group(1), nome))
    return out


def pendentes(d, arquivos):
    feitos = {c.get('driveId') for c in d.get('cultos', []) if c.get('driveId')}
    return [a for a in arquivos if a[0] not in feitos]
