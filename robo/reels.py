"""Cortes verticais (Reels/Shorts) de uma mensagem: trecho inteiro sem cortar pausa, até 60 s,
enquadramento no rosto do pregador por plano de câmera, slide/plano aberto inteiro com fundo desfocado,
legenda palavra a palavra (fonte Archivo Black) e volume no padrão dos reels (-14 LUFS). Sem título."""
import os, subprocess, json
import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
FONTES = os.path.join(AQUI, 'fontes')
W, H, FPS = 1080, 1920, 30
PASSO = 0.25  # amostra 4 vezes por segundo


def probe(video):
    out = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height',
                          '-of', 'json', video], capture_output=True, check=True).stdout
    s = json.loads(out)['streams'][0]
    return int(s['width']), int(s['height'])


def intervalo(todas, a, b):
    ws = [w for w in todas if w['s'] >= a - 0.05 and w['e'] <= b + 0.05]
    if not ws:
        return [], a, min(b, a + 60)
    ini = max(a, ws[0]['s'] - 0.25)
    ws = [w for w in ws if w['e'] + 0.4 - ini <= 60.0]
    fim = min(b + 0.4, ws[-1]['e'] + 0.4)
    return ws, ini, fim


def amostras(video, a, b):
    import cv2
    raw = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-ss', f'{a:.3f}', '-to', f'{b:.3f}', '-i', video,
                          '-vf', 'fps=4,scale=480:270', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True, check=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, 270, 480, 3)
    frente = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    perfil = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_profileface.xml')
    out = []
    for f in fr:
        hsv = cv2.cvtColor(f, cv2.COLOR_RGB2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [18, 8], [0, 180, 0, 256]); cv2.normalize(hist, hist)
        g = cv2.cvtColor(f, cv2.COLOR_RGB2GRAY)
        faces = list(frente.detectMultiScale(g, 1.1, 5, minSize=(16, 16)))
        if not faces:
            faces = list(perfil.detectMultiScale(g, 1.1, 5, minSize=(16, 16))) + \
                    [(480 - fx - fw, fy, fw, fh) for fx, fy, fw, fh in perfil.detectMultiScale(cv2.flip(g, 1), 1.1, 5, minSize=(16, 16))]
        ycc = cv2.cvtColor(f, cv2.COLOR_RGB2YCrCb)
        pele = (ycc[:, :, 1] > 133) & (ycc[:, :, 1] < 175) & (ycc[:, :, 2] > 75) & (ycc[:, :, 2] < 130)
        faces = [r for r in faces if pele[r[1]:r[1] + r[3], r[0]:r[0] + r[2]].mean() > 0.30]
        cx = None
        if faces:
            fx, fy, fw, fh = max(faces, key=lambda r: r[2] * r[3])
            cx = (fx + fw / 2) / 480.0  # posição do rosto de 0 a 1 na largura
        out.append((hist, cx))
    return out


def pedacos(video, a, b):
    """Divide nas trocas de câmera; com rosto = corte 9:16 no rosto; sem rosto = imagem inteira."""
    import cv2
    am = amostras(video, a, b)
    if not am:
        return [(a, b, True, 0.5)]
    cortes = [0] + [i for i in range(1, len(am)) if cv2.compareHist(am[i - 1][0], am[i][0], cv2.HISTCMP_BHATTACHARYYA) > 0.35] + [len(am)]
    out = []
    for i0, i1 in zip(cortes, cortes[1:]):
        if i1 <= i0:
            continue
        t0, t1 = a + i0 * PASSO, min(b, a + i1 * PASSO)
        xs = [c for _, c in am[i0:i1] if c is not None]
        if len(xs) < max(1, 0.3 * (i1 - i0)):
            out.append([t0, t1, True, 0.5]); continue
        ref, ini, grupo = float(np.median(xs[:4])), t0, []
        for k in range(i0, i1):
            c = am[k][1]
            if c is not None and abs(c - ref) > 0.105 and grupo and (a + k * PASSO) - ini >= 1.0:
                out.append([ini, a + k * PASSO, False, float(np.median(grupo))])
                ini, grupo, ref = a + k * PASSO, [], c
            if c is not None:
                grupo.append(c)
        out.append([ini, t1, False, float(np.median(grupo)) if grupo else ref])
    final = []
    for p in out:
        if final and p[1] - p[0] < 0.75:
            final[-1][1] = p[1]
        else:
            final.append(p)
    return [tuple(p) for p in final]


def _t(x):
    return f'{int(x // 3600)}:{int(x % 3600 // 60):02d}:{x % 60:05.2f}'


def legenda(ws, ini, dur, caminho, corrige):
    pal = []
    for w in ws:
        s, e = w['s'] - ini, w['e'] - ini
        txt = corrige.get(w['w'].strip(), w['w'].strip())
        if txt and s >= -0.01:
            pal.append((max(0, s), e, txt))
    grupos, g = [], []
    for item in pal:
        g.append(item)
        if len(g) == 3 or item[2][-1:] in '.?!':
            grupos.append(g); g = []
    if g:
        grupos.append(g)
    linhas = []
    for k, g in enumerate(grupos):
        i0, f0 = g[0][0], (grupos[k + 1][0][0] if k + 1 < len(grupos) else g[-1][1] + 0.3)
        linhas.append(f'Dialogue: 0,{_t(i0)},{_t(min(f0, dur))},Leg,,0,0,0,,' + ' '.join(t for _, _, t in g).upper())
    ass = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Leg,Archivo Black,70,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,6,2,2,70,70,560,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + '\n'.join(linhas) + '\n'
    open(caminho, 'w', encoding='utf-8').write(ass)


def gerar(video, todas, cortes, saida, tmp, corrige=None):
    """cortes: lista de (nome, inicio_s, fim_s). Devolve lista de (nome, arquivo_final, inicio_real, fim_real)."""
    corrige = corrige or {}
    os.makedirs(saida, exist_ok=True); os.makedirs(tmp, exist_ok=True)
    W0, H0 = probe(video)
    cw = int(H0 * 9 / 16) // 2 * 2
    feitos = []
    for nome, a, b in cortes:
        ws, ini, fim = intervalo(todas, a, b)
        arqs = []
        for i, (x, y, sl, cx) in enumerate(pedacos(video, ini, fim)):
            o = os.path.join(tmp, f'{nome}-{i:03d}.mp4')
            if sl:
                vf = (f'[0:v]split[p][q];[p]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=30:3,eq=brightness=-0.08[bg];'
                      f'[q]scale={W}:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,fps={FPS},setsar=1[v]')
            else:
                x0 = int(min(max(cx * W0 - cw / 2, 0), W0 - cw)) // 2 * 2
                vf = f'[0:v]crop={cw}:{H0}:{x0}:0,scale={W}:{H}:flags=lanczos,fps={FPS},setsar=1[v]'
            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-ss', f'{x:.3f}', '-to', f'{y:.3f}', '-i', video,
                            '-filter_complex', vf, '-map', '[v]', '-map', '0:a', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18',
                            '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ar', '48000', '-b:a', '192k', o], check=True)
            arqs.append(o)
        lista = os.path.join(tmp, nome + '-lista.txt')
        open(lista, 'w', encoding='utf-8').write(''.join(f"file '{p}'\n" for p in arqs))
        bruto = os.path.join(tmp, nome + '-bruto.mp4')
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lista, '-c', 'copy', bruto], check=True)
        ass = os.path.join(tmp, nome + '.ass')
        legenda(ws, ini, fim - ini, ass, corrige)
        final = os.path.join(saida, nome + '.mp4')
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', bruto, '-vf', f"ass={ass}:fontsdir={FONTES}",
                        '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11', '-c:v', 'libx264', '-preset', 'medium', '-crf', '19', '-pix_fmt', 'yuv420p',
                        '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', final], check=True)
        feitos.append((nome, final, ini, fim))
        print('corte pronto:', nome, f'{fim - ini:.1f}s', flush=True)
    return feitos
