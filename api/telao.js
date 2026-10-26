// Apresentações no telão (assembleia): lista, slides e o slide atual, que o celular controla.
// Chaves próprias no KV (NÃO mexem na chave dos dados do app, controle-gravacoes:data):
//   controle-gravacoes:telao:lista        -> JSON [{ id, titulo, data, status, n, criado }]
//   controle-gravacoes:telao:apres:<id>   -> JSON { id, titulo, data, status, slides: [html...], texto, criado, montado }
//   controle-gravacoes:telao:atual:<id>   -> número do slide atual (0 = primeiro)
// Endpoints:
//   GET  /api/telao?lista=1              -> { lista }
//   GET  /api/telao?id=X                 -> { apresentacao, atual }
//   GET  /api/telao?id=X&atual=1         -> { atual }            (o telão consulta a cada segundo)
//   POST { acao:'ir', id, slide }        -> muda o slide atual   (controle no celular)
//   POST { acao:'pedir', titulo, data, texto, arquivo, slides? } -> cria apresentação "aguardando montagem" (texto, ou imagens pro robô ler: tipo 'ler-imagens')
//   POST { acao:'salvar', apresentacao } -> grava/atualiza uma apresentação pronta (slides em HTML) — usado pelo robô e pela importação
//   POST { acao:'anexar', id, slides }      -> acrescenta slides (envio em lotes)
//   POST { acao:'status', id, status, aviso } -> robô marca montando/erro
//   POST { acao:'converter', id }        -> cópia de uma apresentação de imagens pro robô montar no padrão
//   POST { acao:'apagar', id }            -> vai pra lixeira por 7 dias; { acao:'restaurar', id } traz de volta
//   GET  /api/telao?reconstruir=1        -> refaz a lista varrendo as chaves
const { KV_URL, KV_TOKEN, kv, acessoOk, lerCorpo } = require('./_util');

const K = { lista: 'controle-gravacoes:telao:lista', apres: 'controle-gravacoes:telao:apres:', atual: 'controle-gravacoes:telao:atual:', slide: 'controle-gravacoes:telao:slide:', lixo: 'controle-gravacoes:telao:lixeira:' };
const novoId = () => 'ap' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
const limpar = s => String(s || '').replace(/[<>]/g, '').trim().slice(0, 200);

async function lerLista() { const r = await kv(['GET', K.lista]); return r && r.result ? JSON.parse(r.result) : []; }
async function gravarLista(l) { await kv(['SET', K.lista, JSON.stringify(l)]); }
async function lerApres(id) {
  const r = await kv(['GET', K.apres + id]); if (!r || !r.result) return null; const a = JSON.parse(r.result);
  if (a.nSlides) {                                                   // slides guardados um por chave (apresentações grandes / de imagens)
    const ks = []; for (let i = 0; i < a.nSlides; i++) ks.push(K.slide + id + ':' + i);
    const m = await kv(['MGET', ...ks]); a.slides = (m && m.result ? m.result : []).map(x => x || '');
  }
  return a;
}
async function gravarApres(a) {
  const slides = a.slides || []; const copia = { ...a };
  copia.nSlides = slides.length; delete copia.slides;               // o corpo dos slides vai em chaves próprias
  for (let i = 0; i < slides.length; i++) await kv(['SET', K.slide + a.id + ':' + i, slides[i]]);
  await kv(['SET', K.apres + a.id, JSON.stringify(copia)]);
}
async function apagarSlides(id, n) { for (let i = 0; i < (n || 0); i++) await kv(['DEL', K.slide + id + ':' + i]); }
async function lerAtual(id) { const r = await kv(['GET', K.atual + id]); return r && r.result != null ? Number(r.result) || 0 : 0; }
function resumo(a) { return { id: a.id, titulo: a.titulo, data: a.data || '', status: a.status, n: (a.slides || []).length, criado: a.criado, montado: a.montado || '', aviso: a.aviso || '', tipo: a.tipo || 'texto' }; }
async function atualizarLista(a) {
  const l = (await lerLista()).filter(x => x.id !== a.id); l.unshift(resumo(a)); await gravarLista(l.slice(0, 200));
}

module.exports = async (req, res) => {
  if (!acessoOk(req, res)) return;
  if (!KV_URL || !KV_TOKEN) { res.status(500).json({ error: 'banco_nao_configurado' }); return; }
  res.setHeader('Cache-Control', 'no-store');
  try {
    if (req.method === 'GET') {
      const q = req.query || {};
      if (q.reconstruir) {                                       // refaz a lista varrendo as chaves das apresentações
        const sc = await kv(['KEYS', K.apres + '*']); const ids = (sc && sc.result ? sc.result : []).map(k => k.slice(K.apres.length));
        const l = []; for (const id of ids) { const a = await lerApres(id); if (a) l.push(resumo(a)); }
        l.sort((x, y) => (y.criado || '').localeCompare(x.criado || '')); await gravarLista(l); res.status(200).json({ lista: l, reconstruida: true }); return;
      }
      if (q.lista) { res.status(200).json({ lista: await lerLista() }); return; }
      const id = limpar(q.id); if (!id) { res.status(400).json({ error: 'sem_id' }); return; }
      if (q.atual) { res.status(200).json({ atual: await lerAtual(id) }); return; }
      const a = await lerApres(id); if (!a) { res.status(404).json({ error: 'nao_encontrada' }); return; }
      res.status(200).json({ apresentacao: a, atual: await lerAtual(id) }); return;
    }
    if (req.method !== 'POST') { res.status(405).json({ error: 'metodo_nao_suportado' }); return; }
    const b = lerCorpo(req); if (!b) { res.status(400).json({ error: 'body_invalido' }); return; }

    if (b.acao === 'ir') {
      const id = limpar(b.id); const a = await lerApres(id); if (!a) { res.status(404).json({ error: 'nao_encontrada' }); return; }
      const n = Math.max(0, Math.min((a.slides || []).length - 1, Number(b.slide) || 0));
      await kv(['SET', K.atual + id, String(n)]); res.status(200).json({ ok: true, atual: n }); return;
    }
    if (b.acao === 'pedir') {
      const titulo = limpar(b.titulo); if (!titulo) { res.status(400).json({ error: 'sem_titulo' }); return; }
      const texto = String(b.texto || '').slice(0, 900000);           // texto extraído dos arquivos (até ~900 KB; o KV aceita 1 MB por chave)
      const imgs = Array.isArray(b.slides) ? b.slides.map(s => String(s).slice(0, 450000)).slice(0, 120) : [];
      if (!texto.trim() && !imgs.length) { res.status(400).json({ error: 'sem_texto' }); return; }
      // tipo 'ler-imagens': o robô lê o texto das imagens e monta no padrão; até lá as imagens ficam guardadas como slides provisórios
      const a = { id: novoId(), titulo, data: limpar(b.data), status: 'aguardando', tipo: imgs.length ? 'ler-imagens' : 'texto', slides: imgs, texto, arquivo: limpar(b.arquivo), criado: new Date().toISOString() };
      await gravarApres(a); await kv(['SET', K.atual + a.id, '0']); await atualizarLista(a);
      res.status(200).json({ ok: true, id: a.id }); return;
    }
    if (b.acao === 'salvar') {
      const p = b.apresentacao; if (!p || !Array.isArray(p.slides) || !p.slides.length) { res.status(400).json({ error: 'sem_slides' }); return; }
      const id = limpar(p.id) || novoId(); const antes = await lerApres(id);
      const a = { ...(antes || {}), id, titulo: limpar(p.titulo) || (antes && antes.titulo) || 'Apresentação', data: limpar(p.data) || (antes && antes.data) || '',
        status: 'pronta', tipo: p.tipo === 'imagens' ? 'imagens' : 'texto', slides: p.slides.map(s => String(s).slice(0, 450000)).slice(0, 120), criado: (antes && antes.criado) || new Date().toISOString(), montado: new Date().toISOString() };
      if (antes && antes.texto && !a.texto) a.texto = antes.texto;
      if (antes && antes.nSlides > a.slides.length) await apagarSlides(id, antes.nSlides);
      await gravarApres(a); if (!antes) await kv(['SET', K.atual + id, '0']); await atualizarLista(a);
      res.status(200).json({ ok: true, id }); return;
    }
    if (b.acao === 'converter') {                               // apresentação de imagens -> cópia "· padrão PIBN" que o robô lê e monta
      const id = limpar(b.id); const a = await lerApres(id); if (!a || !a.slides.length) { res.status(404).json({ error: 'nao_encontrada' }); return; }
      const c = { id: novoId(), titulo: (a.titulo + ' · padrão PIBN').slice(0, 200), data: a.data || '', status: 'aguardando', tipo: 'ler-imagens', slides: a.slides, texto: '', arquivo: a.arquivo || '', origem: id, criado: new Date().toISOString() };
      await gravarApres(c); await kv(['SET', K.atual + c.id, '0']); await atualizarLista(c); res.status(200).json({ ok: true, id: c.id }); return;
    }
    if (b.acao === 'anexar') {                                  // acrescenta slides a uma apresentação (envio em lotes, ex.: imagens)
      const id = limpar(b.id); const a = await lerApres(id); if (!a || !Array.isArray(b.slides)) { res.status(404).json({ error: 'nao_encontrada' }); return; }
      const novos = b.slides.map(s => String(s).slice(0, 450000)); const base = a.slides.length;
      if (base + novos.length > 120) { res.status(400).json({ error: 'muitos_slides' }); return; }
      for (let i = 0; i < novos.length; i++) await kv(['SET', K.slide + id + ':' + (base + i), novos[i]]);
      a.nSlides = base + novos.length; a.montado = new Date().toISOString(); const copia = { ...a }; delete copia.slides;
      await kv(['SET', K.apres + id, JSON.stringify(copia)]); a.slides = a.slides.concat(novos); await atualizarLista(a);
      res.status(200).json({ ok: true, n: a.nSlides }); return;
    }
    if (b.acao === 'status') {                                  // robô marca "montando" / "erro" (com aviso) sem mexer nos slides
      const id = limpar(b.id); const a = await lerApres(id); if (!a) { res.status(404).json({ error: 'nao_encontrada' }); return; }
      const st = ['aguardando', 'montando', 'erro'].includes(b.status) ? b.status : a.status;
      a.status = st; a.aviso = String(b.aviso || '').slice(0, 500); a.tentativa = new Date().toISOString();
      await gravarApres(a); await atualizarLista(a); res.status(200).json({ ok: true }); return;
    }
    if (b.acao === 'apagar') {
      const id = limpar(b.id); const a = await lerApres(id);
      if (a) { a.apagadaEm = new Date().toISOString(); await kv(['SET', K.lixo + id, JSON.stringify(a), 'EX', String(7 * 24 * 3600)]); await apagarSlides(id, a.nSlides); }   // lixeira: 7 dias
      await kv(['DEL', K.apres + id]); await kv(['DEL', K.atual + id]);
      await gravarLista((await lerLista()).filter(x => x.id !== id)); res.status(200).json({ ok: true, lixeira: !!a }); return;
    }
    if (b.acao === 'restaurar') {
      const id = limpar(b.id); const r = await kv(['GET', K.lixo + id]); if (!r || !r.result) { res.status(404).json({ error: 'nao_esta_na_lixeira' }); return; }
      const a = JSON.parse(r.result); delete a.apagadaEm; await gravarApres(a); await kv(['SET', K.atual + id, '0']); await atualizarLista(a); await kv(['DEL', K.lixo + id]);
      res.status(200).json({ ok: true, id }); return;
    }
    res.status(400).json({ error: 'acao_desconhecida' });
  } catch (e) {
    res.status(500).json({ error: 'falha', detalhe: String(e.message || e) });
  }
};
