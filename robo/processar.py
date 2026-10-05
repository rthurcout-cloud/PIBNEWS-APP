"""Robô de cortes do PIB News (roda no GitHub Actions, sem depender de computador).

1. Pega o vídeo mais antigo ainda não processado da pasta do Drive e marca o culto como "Em produção" no app.
2. Transcreve o culto inteiro (rápido) e pede à API do Claude: onde começa e termina a mensagem,
   de 5 a 7 cortes de até 60 s e a descrição do YouTube no formato da PIBN.
3. Transcreve os trechos dos cortes com precisão de palavra, gera os cortes verticais e a mensagem na íntegra.
4. Publica os vídeos como anexos (release) no GitHub e deixa o culto "Pra aprovar" no app.
Se algo der errado, o culto fica como "Deu erro" com o motivo, e nada do que já existe é apagado.
"""
import datetime, json, os, re, subprocess, sys, time, traceback, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comum import ler_app, gravar_app, listar_drive, pendentes, http
import reels

REPO = os.environ.get('GITHUB_REPOSITORY', 'rthurcout-cloud/PIBNEWS-APP')
GH_TOKEN = os.environ.get('GITHUB_TOKEN', '')
CHAVE = os.environ.get('ANTHROPIC_API_KEY', '')
MODELO = os.environ.get('MODELO_CLAUDE', 'claude-sonnet-5-5')
TRAB = os.path.abspath(os.environ.get('PASTA_TRABALHO', 'trabalho'))
os.makedirs(TRAB, exist_ok=True)

RODAPE = """━━━━━━━━━━━━━━━
📱 Acesse nossas redes sociais:

🌐 Site: https://pibn.org.br/
📸 Instagram: https://www.instagram.com/pibniteroi/
📸 Soul Jovem: https://www.instagram.com/souljovem_pibn/
📸 Classe A: https://www.instagram.com/classea_pibn/
▶️ YouTube: https://www.youtube.com/@PIBNiteroi
👍 Facebook: https://www.facebook.com/pib.niteroi1892"""


def hms(t):
    t = int(round(t)); return f'{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}'


def seg(s):
    p = [float(x) for x in str(s).strip().split(':')]
    while len(p) < 3: p.insert(0, 0)
    return p[0] * 3600 + p[1] * 60 + p[2]


def run(*cmd):
    subprocess.run(list(cmd), check=True)


def duracao(arq):
    return float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', arq],
                                capture_output=True, check=True).stdout.strip() or 0)


def baixar_drive(fid, destino):
    url = f'https://drive.usercontent.google.com/download?id={fid}&export=download&confirm=t'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=600) as r, open(destino, 'wb') as f:
        if 'text/html' in (r.headers.get('Content-Type') or ''):
            raise RuntimeError('O Drive não liberou o arquivo. Confira se a pasta está compartilhada como "qualquer pessoa com o link".')
        while True:
            b = r.read(8 * 1024 * 1024)
            if not b: break
            f.write(b)
    if os.path.getsize(destino) < 1_000_000:
        raise RuntimeError('O arquivo baixado do Drive veio vazio ou muito pequeno.')


def whisper(audio, modelo, palavras=False, desloc=0.0):
    from faster_whisper import WhisperModel
    m = WhisperModel(modelo, device='cpu', compute_type='int8', cpu_threads=os.cpu_count() or 4)
    segs, _ = m.transcribe(audio, language='pt', vad_filter=True, beam_size=5 if palavras else 1, word_timestamps=palavras)
    out = []
    for s in segs:
        out.append({'start': s.start + desloc, 'end': s.end + desloc, 'text': s.text.strip(),
                    'words': [{'w': w.word, 's': w.start + desloc, 'e': w.end + desloc} for w in (s.words or [])]})
    return out


def claude(prompt):
    if not CHAVE:
        raise RuntimeError('Falta a chave da API do Claude (segredo ANTHROPIC_API_KEY no GitHub).')
    corpo = json.dumps({'model': MODELO, 'max_tokens': 8000, 'messages': [{'role': 'user', 'content': prompt}]}).encode('utf-8')
    for tent in range(3):
        try:
            r = json.loads(http('https://api.anthropic.com/v1/messages', corpo,
                                {'x-api-key': CHAVE, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'}, 'POST', 300))
            txt = ''.join(b.get('text', '') for b in r.get('content', []))
            return json.loads(txt[txt.index('{'): txt.rindex('}') + 1])
        except Exception as e:
            if tent == 2: raise RuntimeError(f'A API do Claude não respondeu direito: {e}')
            time.sleep(10)


PROMPT = """Você trabalha na mídia da Primeira Igreja Batista de Niterói (PIBN). Abaixo está a transcrição automática (pode ter erros de palavra) de um culto, com o tempo de cada trecho no formato [HH:MM:SS]. Nome do arquivo do vídeo: "{arquivo}".

Tarefas:
1. Ache a MENSAGEM (a pregação): "inicio" = quando o pregador começa a falar, depois que a música acabou; "fim" = quando ele termina de falar, antes de qualquer música. Regra do Arthur: a mensagem NÃO pode ter nada de música, nem no começo, nem no fim, nem no apelo ou na oração (se tocar música por baixo da oração ou do apelo, termine antes dela). Não inclua louvor, avisos nem ofertas.
2. Escolha de 5 a 7 CORTES da mensagem para Instagram e YouTube Shorts. Cada corte: trecho contínuo de 30 a 58 segundos, que faça sentido sozinho, começando no início de uma frase e terminando no fim de uma frase. Prefira frases fortes, histórias e aplicações. Não repita o mesmo trecho. Nenhum corte pode ter música (nem cantada nem tocada por baixo).
3. Escreva a DESCRIÇÃO do YouTube da mensagem no formato abaixo (sem o rodapé; ele é colocado depois).
4. Liste correções de palavras que a transcrição errou dentro dos cortes (ex.: nomes bíblicos, "PIV" -> "PIB").

Regras de escrita: português do Brasil, direto. Sem promessa de resultado, sem linguagem de coach. NÃO invente nome, número ou fato: o nome do pregador só se aparecer no nome do arquivo ou for dito no vídeo; se não souber, deixe "".

Formato da descrição:
{link}[Título da mensagem] | [Referência bíblica]{pregador_titulo}

📖 Tema: [tema] — [referência]

[1 parágrafo de contexto]

1️⃣ [primeiro ponto] ([versículo, se houver])
[1 ou 2 frases]

2️⃣ ... (quantos pontos a mensagem tiver)

✨ "[frase marcante da mensagem, fiel ao que foi dito]"

🙏 [chamada curta pra curtir, comentar e compartilhar]

#PIBNiteroi [3 a 5 hashtags do tema]

Responda SÓ com um JSON válido, sem texto antes ou depois:
{{"mensagem": {{"inicio": "HH:MM:SS", "fim": "HH:MM:SS"}},
  "titulo": "título curto da mensagem", "referencia": "livro cap.vers", "pregador": "Pr. Nome ou vazio",
  "data_culto": "AAAA-MM-DD ou vazio", "culto": "ex.: Culto domingo noite, ou vazio",
  "cortes": [{{"titulo": "título curto", "inicio": "HH:MM:SS", "fim": "HH:MM:SS", "legenda_post": "1 ou 2 frases pro post, fiéis ao que foi dito"}}],
  "descricao": "texto completo da descrição", "correcoes": {{"palavra errada": "palavra certa"}}}}

TRANSCRIÇÃO:
{transcricao}"""


def slug(t):
    import unicodedata
    t = unicodedata.normalize('NFD', t).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', t).strip('-')[:50] or 'corte'


def github(metodo, url, dados=None, cab=None):
    h = {'Authorization': 'Bearer ' + GH_TOKEN, 'Accept': 'application/vnd.github+json', 'User-Agent': 'robo-cortes'}
    h.update(cab or {})
    return json.loads(http(url, dados, h, metodo, 1800) or b'{}')


def publicar(tag, nome, arquivos):
    rel = github('POST', f'https://api.github.com/repos/{REPO}/releases',
                 json.dumps({'tag_name': tag, 'target_commitish': 'main', 'name': nome,
                             'body': 'Vídeos gerados pelo robô de cortes do PIB News (mensagem na íntegra e cortes).'}).encode('utf-8'),
                 {'Content-Type': 'application/json'})
    urls = {}
    for chave, caminho, nome_arq in arquivos:
        with open(caminho, 'rb') as f:
            a = github('POST', f'https://uploads.github.com/repos/{REPO}/releases/{rel["id"]}/assets?name={nome_arq}', f.read(),
                       {'Content-Type': 'video/mp4'})
        urls[chave] = a['browser_download_url']
        print('publicado:', nome_arq, flush=True)
    return urls


TESTE_URL = os.environ.get('TESTE_VIDEO_URL', '')  # modo teste: baixa deste link, não grava no app nem publica


def processar():
    if TESTE_URL:
        return teste()
    d = ler_app()
    novos = pendentes(d, listar_drive())
    if not novos:
        print('nada novo'); return
    fid, fnome = novos[0]
    print('processando:', fnome, flush=True)
    hoje = datetime.date.today().isoformat()

    # culto no app: usa um "aguardando" (link colado no app) ou cria um novo
    alvo = {}
    def marcar(db):
        cs = db.setdefault('cultos', [])
        c = next((x for x in sorted(cs, key=lambda x: x.get('criado', '')) if x.get('status') == 'aguardando' and not x.get('driveId')), None)
        if not c:
            c = {'id': 'cu' + format(int(time.time() * 1000), 'x'), 'link': '', 'yt': '', 'criado': hoje}
            cs.append(c)
        c.update({'status': 'producao', 'driveId': fid, 'driveNome': fnome, 'erro': '', 'inicioProducao': datetime.datetime.utcnow().isoformat() + 'Z'})
        if not c.get('titulo'): c['titulo'] = re.sub(r'\.\w+$', '', fnome)
        alvo.update(c)
    gravar_app(marcar)
    cid = alvo['id']

    def atualizar(campos):
        def f(db):
            for c in db.get('cultos', []):
                if c['id'] == cid: c.update(campos)
        gravar_app(f)

    try:
        video = os.path.join(TRAB, 'culto' + (os.path.splitext(fnome)[1].lower() or '.mp4'))
        baixar_drive(fid, video)
        print('baixado:', round(os.path.getsize(video) / 1e6), 'MB', flush=True)
        audio = os.path.join(TRAB, 'audio.wav')
        run('ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', video, '-vn', '-ac', '1', '-ar', '16000', audio)

        t0 = time.time()
        rapido = whisper(audio, os.environ.get('MODELO_RAPIDO', 'small'))
        print(f'transcrição geral: {len(rapido)} trechos em {time.time() - t0:.0f}s', flush=True)
        transcricao = '\n'.join(f'[{hms(s["start"])}] {s["text"]}' for s in rapido)
        open(os.path.join(TRAB, 'transcricao.txt'), 'w', encoding='utf-8').write(transcricao)

        yt = alvo.get('yt') or ''
        link = f'🔴 Assista: https://youtu.be/{yt}\n\n' if yt else ''
        plano = claude(PROMPT.format(arquivo=fnome, link=link, pregador_titulo=' | [Pregador, se souber]', transcricao=transcricao))
        print('plano:', json.dumps(plano, ensure_ascii=False)[:1500], flush=True)
        ini, fim = seg(plano['mensagem']['inicio']), seg(plano['mensagem']['fim'])
        if not (0 <= ini < fim <= duracao(video) + 5): raise RuntimeError('Início/fim da mensagem fora do vídeo.')

        # palavras exatas só nos trechos dos cortes (modelo mais preciso)
        cortes, todas = [], []
        for i, c in enumerate(plano.get('cortes', [])[:7], 1):
            a, b = seg(c['inicio']), seg(c['fim'])
            if b - a < 10: continue
            b = min(b, a + 62)
            jan = os.path.join(TRAB, f'j{i}.wav')
            run('ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-ss', str(max(0, a - 3)), '-to', str(b + 3), '-i', audio, jan)
            ws = whisper(jan, os.environ.get('MODELO_PRECISO', 'medium'), palavras=True, desloc=max(0, a - 3))
            todas += [w for s in ws for w in s['words'] if a - 0.3 <= w['s'] <= b + 0.5]
            cortes.append((f'{i:02d}-{slug(c["titulo"])}', a, b, c))
        if not cortes: raise RuntimeError('Nenhum corte válido saiu da escolha.')
        todas.sort(key=lambda w: w['s'])

        feitos = reels.gerar(video, todas, [(n, a, b) for n, a, b, _ in cortes], os.path.join(TRAB, 'cortes'),
                             os.path.join(TRAB, 'tmp'), plano.get('correcoes') or {})

        # mensagem na íntegra em Full HD (H.264, abre em qualquer lugar), sem folga (nada de música) e com fade do preto no começo e pro preto no fim
        msg = os.path.join(TRAB, 'mensagem-1080p.mp4')
        dur, FD = fim - ini, 1.5
        run('ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-ss', str(ini), '-to', str(fim), '-i', video,
            '-vf', f"scale='min(1920,iw)':-2,fade=t=in:st=0:d={FD},fade=t=out:st={dur - FD:.3f}:d={FD}",
            '-af', f"afade=t=in:st=0:d={FD},afade=t=out:st={dur - FD:.3f}:d={FD}",
            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', msg)
        leves = []
        for nome, final, _, _ in feitos:
            leve = os.path.join(TRAB, 'cortes', nome + '-720p.mp4')
            run('ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', final, '-vf', 'scale=720:1280:flags=lanczos', '-c:v', 'libx264',
                '-preset', 'slow', '-crf', '27', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', leve)
            leves.append(leve)

        data = plano.get('data_culto') or ''
        tag = f'culto-{data or hoje}-{cid}'
        arqs = [('msg', msg, 'mensagem-1080p.mp4')]
        for (nome, final, _, _), leve in zip(feitos, leves):
            arqs += [(nome + '-hd', final, nome + '.mp4'), (nome, leve, nome + '-720p.mp4')]
        urls = publicar(tag, f'{plano.get("culto") or "Culto"} {data} · {plano.get("titulo", "")}'.strip(), arqs)

        descricao = (plano.get('descricao') or '').strip() + '\n\n' + RODAPE
        pastor = plano.get('pregador') or ''
        ref = plano.get('referencia') or ''
        novos_cortes = []
        for k, ((nome, final, a, b), (_, _, _, c)) in enumerate(zip(feitos, cortes), 1):
            novos_cortes.append({'id': f'co{cid}{k:02d}', 'culto': cid, 'titulo': c['titulo'],
                                 'mensagem': ' · '.join(x for x in [plano.get('culto') or '', plano.get('titulo') or '', f'({ref})' if ref else ''] if x),
                                 'pastor': pastor, 'link': alvo.get('link') or '', 'inicio': hms(a), 'fim': hms(b), 'plataforma': 'ambos',
                                 'status': 'aprovar', 'postado': '', 'video': urls[nome], 'videoHD': urls[nome + '-hd'],
                                 'notas': 'Legenda sugerida: ' + (c.get('legenda_post') or '').strip(), 'criado': hoje, 'ordem': k})

        def concluir(db):
            db['cortes'] = [x for x in db.get('cortes', []) if x.get('culto') != cid] + novos_cortes
            for c in db.get('cultos', []):
                if c['id'] == cid:
                    c.update({'status': 'pronto', 'titulo': plano.get('titulo') or c.get('titulo'), 'pastor': pastor, 'data': data,
                              'culto': plano.get('culto') or '', 'inicio': hms(ini), 'fim': hms(fim), 'ytInicio': '',
                              'descricao': descricao, 'video': urls['msg'], 'erro': '',
                              'fimProducao': datetime.datetime.utcnow().isoformat() + 'Z'})
        gravar_app(concluir)
        print('PRONTO:', plano.get('titulo'), '-', len(novos_cortes), 'cortes', flush=True)
    except Exception as e:
        traceback.print_exc()
        atualizar({'status': 'erro', 'erro': str(e)[:300]})
        raise


def teste():
    video = os.path.join(TRAB, 'culto.mp4')
    with urllib.request.urlopen(urllib.request.Request(TESTE_URL, headers={'User-Agent': 'Mozilla/5.0'}), timeout=600) as r, open(video, 'wb') as f:
        f.write(r.read())
    audio = os.path.join(TRAB, 'audio.wav')
    run('ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', video, '-vn', '-ac', '1', '-ar', '16000', audio)
    t0 = time.time(); rapido = whisper(audio, os.environ.get('MODELO_RAPIDO', 'small'))
    print(f'teste: transcrição geral {len(rapido)} trechos em {time.time() - t0:.0f}s (vídeo de {duracao(video):.0f}s)', flush=True)
    open(os.path.join(TRAB, 'transcricao.txt'), 'w', encoding='utf-8').write('\n'.join(f'[{hms(s["start"])}] {s["text"]}' for s in rapido))
    plano = json.loads(os.environ['TESTE_PLANO']) if os.environ.get('TESTE_PLANO') else claude(PROMPT.format(
        arquivo='teste.mp4', link='', pregador_titulo='', transcricao='\n'.join(f'[{hms(s["start"])}] {s["text"]}' for s in rapido)))
    cortes, todas = [], []
    for i, c in enumerate(plano['cortes'], 1):
        a, b = seg(c['inicio']), seg(c['fim'])
        jan = os.path.join(TRAB, f'j{i}.wav')
        run('ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-ss', str(max(0, a - 3)), '-to', str(b + 3), '-i', audio, jan)
        t0 = time.time(); ws = whisper(jan, os.environ.get('MODELO_PRECISO', 'medium'), palavras=True, desloc=max(0, a - 3))
        print(f'teste: palavras do corte {i} em {time.time() - t0:.0f}s', flush=True)
        todas += [w for s in ws for w in s['words'] if a - 0.3 <= w['s'] <= b + 0.5]
        cortes.append((f'{i:02d}-{slug(c["titulo"])}', a, b))
    todas.sort(key=lambda w: w['s'])
    t0 = time.time(); reels.gerar(video, todas, cortes, os.path.join(TRAB, 'cortes'), os.path.join(TRAB, 'tmp'), plano.get('correcoes') or {})
    print(f'teste: cortes gerados em {time.time() - t0:.0f}s', flush=True)


if __name__ == '__main__':
    processar()
