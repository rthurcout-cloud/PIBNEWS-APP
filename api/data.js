// Função serverless do Vercel: lê e grava os dados compartilhados no Vercel KV (Upstash Redis).
// Endpoints:
//   GET  /api/data  -> retorna { gravacoes, pessoas, cortes, cultos }
//   POST /api/data  -> salva  { gravacoes, pessoas, cortes, cultos }
// Segurança: se a variável de ambiente ACCESS_CODE estiver definida, exige o header x-access-code.

const KV_URL = process.env.KV_REST_API_URL || process.env.UPSTASH_REDIS_REST_URL;
const KV_TOKEN = process.env.KV_REST_API_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN;
const DATA_KEY = 'controle-gravacoes:data';

async function kv(command) {
  const res = await fetch(KV_URL, {
    method: 'POST',
    headers: { Authorization: 'Bearer ' + KV_TOKEN, 'Content-Type': 'application/json' },
    body: JSON.stringify(command)
  });
  if (!res.ok) throw new Error('KV ' + res.status + ': ' + (await res.text()));
  return res.json();
}

module.exports = async (req, res) => {
  const required = process.env.ACCESS_CODE || '';
  const sent = req.headers['x-access-code'] || '';
  if (required && sent !== required) {
    res.status(401).json({ error: 'codigo_invalido' });
    return;
  }
  if (!KV_URL || !KV_TOKEN) {
    res.status(500).json({ error: 'banco_nao_configurado', dica: 'Crie um Vercel KV e conecte ao projeto.' });
    return;
  }
  try {
    if (req.method === 'GET') {
      const out = await kv(['GET', DATA_KEY]);
      const data = out && out.result ? JSON.parse(out.result) : { gravacoes: [], pessoas: [] };
      res.setHeader('Cache-Control', 'no-store');
      res.status(200).json(data);
      return;
    }
    if (req.method === 'POST') {
      let body = req.body;
      if (typeof body === 'string') { try { body = JSON.parse(body); } catch (e) { body = null; } }
      if (!body || typeof body !== 'object') { res.status(400).json({ error: 'body_invalido' }); return; }
      // envio sem nenhuma lista (ex.: um {} por engano) apagaria o banco inteiro: recusa
      const CHAVES = ['gravacoes', 'pessoas', 'cortes', 'cultos'];
      if (!CHAVES.some(k => Array.isArray(body[k]))) { res.status(409).json({ error: 'envio_vazio_recusado' }); return; }
      // lista que não veio no envio (versão antiga do app, robô) fica como já estava guardada
      const safe = {};
      CHAVES.forEach(k => { safe[k] = Array.isArray(body[k]) ? body[k] : null; });
      if (CHAVES.some(k => !safe[k])) {
        const atual = await kv(['GET', DATA_KEY]);
        const d = atual && atual.result ? JSON.parse(atual.result) : {};
        CHAVES.forEach(k => { if (!safe[k]) safe[k] = Array.isArray(d[k]) ? d[k] : []; });
      }
      await kv(['SET', DATA_KEY, JSON.stringify(safe)]);
      res.status(200).json({ ok: true });
      return;
    }
    res.status(405).json({ error: 'metodo_nao_suportado' });
  } catch (e) {
    res.status(500).json({ error: String((e && e.message) || e) });
  }
};
