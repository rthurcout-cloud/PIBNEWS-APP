// Inscrição nas notificações do celular (Web Push) e lista dos últimos avisos.
//   GET    /api/push            -> { publicKey }  (chave pública pro navegador se inscrever)
//   GET    /api/push?avisos=1   -> { avisos: [...] } últimos avisos de "cortes prontos"
//   POST   /api/push            -> { subscription } guarda a inscrição deste aparelho
//   DELETE /api/push            -> { endpoint } remove a inscrição
const { KV_URL, KV_TOKEN, KEYS, kv, acessoOk, lerCorpo } = require('./_util');

module.exports = async (req, res) => {
  res.setHeader('Cache-Control', 'no-store');
  if (!KV_URL || !KV_TOKEN) { res.status(500).json({ error: 'banco_nao_configurado' }); return; }
  try {
    if (req.method === 'GET') {
      const q = new URL(req.url, 'http://x').searchParams;
      if (q.get('avisos')) {
        if (!acessoOk(req, res)) return;
        const r = await kv(['LRANGE', KEYS.avisos, '0', '19']);
        const avisos = (r.result || []).map(s => { try { return JSON.parse(s); } catch (e) { return null; } }).filter(Boolean);
        res.status(200).json({ avisos }); return;
      }
      res.status(200).json({ publicKey: process.env.VAPID_PUBLIC_KEY || '' }); return;
    }
    if (req.method === 'POST' || req.method === 'DELETE') {
      if (!acessoOk(req, res)) return;
      const body = lerCorpo(req);
      if (!body) { res.status(400).json({ error: 'body_invalido' }); return; }
      if (req.method === 'DELETE') {
        if (typeof body.endpoint !== 'string') { res.status(400).json({ error: 'endpoint_invalido' }); return; }
        await kv(['HDEL', KEYS.push, body.endpoint]);
        res.status(200).json({ ok: true }); return;
      }
      const sub = body.subscription;
      const ok = sub && typeof sub.endpoint === 'string' && /^https:\/\//.test(sub.endpoint) && sub.endpoint.length < 1000 &&
                 sub.keys && typeof sub.keys.p256dh === 'string' && typeof sub.keys.auth === 'string';
      if (!ok) { res.status(400).json({ error: 'inscricao_invalida' }); return; }
      await kv(['HSET', KEYS.push, sub.endpoint, JSON.stringify({ endpoint: sub.endpoint, keys: { p256dh: sub.keys.p256dh, auth: sub.keys.auth }, criado: new Date().toISOString() })]);
      const n = await kv(['HLEN', KEYS.push]);
      res.status(200).json({ ok: true, inscritos: n.result });
      return;
    }
    res.status(405).json({ error: 'metodo_nao_suportado' });
  } catch (e) {
    res.status(500).json({ error: String((e && e.message) || e) });
  }
};
