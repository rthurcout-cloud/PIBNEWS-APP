// Ajudantes das funções de aviso (o "_" no nome faz a Vercel não tratar este arquivo como endereço).
const KV_URL = process.env.KV_REST_API_URL || process.env.UPSTASH_REDIS_REST_URL;
const KV_TOKEN = process.env.KV_REST_API_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN;

// Chaves próprias dos avisos: NÃO mexem na chave dos dados do app (controle-gravacoes:data).
const KEYS = { push: 'controle-gravacoes:push', avisos: 'controle-gravacoes:avisos', dedupe: 'controle-gravacoes:avisado:' };

async function kv(command) {
  const res = await fetch(KV_URL, {
    method: 'POST',
    headers: { Authorization: 'Bearer ' + KV_TOKEN, 'Content-Type': 'application/json' },
    body: JSON.stringify(command)
  });
  if (!res.ok) throw new Error('KV ' + res.status + ': ' + (await res.text()));
  return res.json();
}

// Mesma regra do /api/data: se ACCESS_CODE existir, exige o header x-access-code.
function acessoOk(req, res) {
  const required = process.env.ACCESS_CODE || '';
  const sent = req.headers['x-access-code'] || '';
  if (required && sent !== required) { res.status(401).json({ error: 'codigo_invalido' }); return false; }
  return true;
}

function lerCorpo(req) {
  let body = req.body;
  if (typeof body === 'string') { try { body = JSON.parse(body); } catch (e) { body = null; } }
  return body && typeof body === 'object' ? body : null;
}

function parear(flat) {            // HGETALL do Upstash vem como [campo, valor, campo, valor...]
  const out = [];
  for (let i = 0; i + 1 < (flat || []).length; i += 2) out.push([flat[i], flat[i + 1]]);
  return out;
}

module.exports = { KV_URL, KV_TOKEN, KEYS, kv, acessoOk, lerCorpo, parear };
