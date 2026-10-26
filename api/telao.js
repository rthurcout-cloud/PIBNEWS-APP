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
//   POST { acao:'pedir', titulo, data, texto, arquivo } -> cria apresentação "aguardando montagem" com o texto enviado
//   POST { acao:'salvar', apresentacao } -> grava/atualiza uma apresentação pronta (slides em HTML) — usado pelo robô e pela importação
//   POST { acao:'apagar', id }
const { KV_URL, KV_TOKEN, kv, acessoOk, lerCorpo } = require('./_util');

const K = { lista: 'controle-gravacoes:telao:lista', apres: 'controle-gravacoes:telao:apres:', atual: 'controle-gravacoes:telao:atual:' };
const novoId = () => 'ap' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
const limpar = s => String(s || '').replace(/[<>]/g, '').trim().slice(0, 200);

async function lerLista() { const r = await kv(['GET', K.lista]); return r && r.result ? JSON.parse(r.result) : []; }
async function gravarLista(l) { await kv(['SET', K.lista, JSON.stringify(l)]); }
async function lerApres(id) { const r = await kv(['GET', K.apres + id]); return r && r.result ? JSON.parse(r.result) : null; }
async function lerAtual(id) { const r = await kv(['GET', K.atual + id]); return r && r.result != null ? Number(r.result) || 0 : 0; }
function resumo(a) { return { id: a.id, titulo: a.titulo, data: a.data || '', status: a.status, n: (a.slides || []).length, criado: a.criado, montado: a.montado || '' }; }
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
      if (!texto.trim()) { res.status(400).json({ error: 'sem_texto' }); return; }
      const a = { id: novoId(), titulo, data: limpar(b.data), status: 'aguardando', slides: [], texto, arquivo: limpar(b.arquivo), criado: new Date().toISOString() };
      await kv(['SET', K.apres + a.id, JSON.stringify(a)]); await kv(['SET', K.atual + a.id, '0']); await atualizarLista(a);
      res.status(200).json({ ok: true, id: a.id }); return;
    }
    if (b.acao === 'salvar') {
      const p = b.apresentacao; if (!p || !Array.isArray(p.slides) || !p.slides.length) { res.status(400).json({ error: 'sem_slides' }); return; }
      const id = limpar(p.id) || novoId(); const antes = await lerApres(id);
      const a = { ...(antes || {}), id, titulo: limpar(p.titulo) || (antes && antes.titulo) || 'Apresentação', data: limpar(p.data) || (antes && antes.data) || '',
        status: 'pronta', slides: p.slides.map(s => String(s).slice(0, 60000)).slice(0, 80), criado: (antes && antes.criado) || new Date().toISOString(), montado: new Date().toISOString() };
      if (antes && antes.texto && !a.texto) a.texto = antes.texto;
      await kv(['SET', K.apres + id, JSON.stringify(a)]); if (!antes) await kv(['SET', K.atual + id, '0']); await atualizarLista(a);
      res.status(200).json({ ok: true, id }); return;
    }
    if (b.acao === 'apagar') {
      const id = limpar(b.id); await kv(['DEL', K.apres + id]); await kv(['DEL', K.atual + id]);
      await gravarLista((await lerLista()).filter(x => x.id !== id)); res.status(200).json({ ok: true }); return;
    }
    res.status(400).json({ error: 'acao_desconhecida' });
  } catch (e) {
    res.status(500).json({ error: 'falha', detalhe: String(e.message || e) });
  }
};
