// Função serverless do Vercel: lê e grava os dados compartilhados no Vercel KV (Upstash Redis).
// Endpoints:
//   GET  /api/data  -> retorna { gravacoes, pessoas }
//   POST /api/data  -> salva  { gravacoes, pessoas }
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
      const safe = {
        gravacoes: Array.isArray(body.gravacoes) ? body.gravacoes : [],
        pessoas: Array.isArray(body.pessoas) ? body.pessoas : []
      };
      await kv(['SET', DATA_KEY, JSON.stringify(safe)]);
      res.status(200).json({ ok: true });
      return;
    }
    res.status(405).json({ error: 'metodo_nao_suportado' });
  } catch (e) {
    res.status(500).json({ error: String((e && e.message) || e) });
  }
};
