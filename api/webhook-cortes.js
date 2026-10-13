// WEBHOOK "cortes prontos": quem termina os cortes (o robô, ou o Claude) avisa este endereço, e ele manda a
// notificação pra todo aparelho inscrito no app.
//   POST /api/webhook-cortes
//   Header:  x-webhook-secret: <senha do webhook>   (variável WEBHOOK_SECRET na Vercel)
//   Corpo:   { "culto": "Culto domingo noite 11/10", "cortes": 7, "titulo": "Quando Deus nos chama a confiar" }
const crypto = require('crypto');
const { KV_URL, KV_TOKEN, KEYS, kv, lerCorpo, parear } = require('./_util');

function igual(a, b) {             // comparação sem vazar a senha pelo tempo de resposta
  const ha = crypto.createHash('sha256').update(String(a)).digest(), hb = crypto.createHash('sha256').update(String(b)).digest();
  return crypto.timingSafeEqual(ha, hb);
}
const limpa = (s, max) => String(s == null ? '' : s).replace(/[\u0000-\u001f]/g, ' ').trim().slice(0, max);

module.exports = async (req, res) => {
  res.setHeader('Cache-Control', 'no-store');
  if (req.method !== 'POST') { res.status(405).json({ error: 'use_POST' }); return; }
  const segredo = process.env.WEBHOOK_SECRET || '';
  if (!segredo) { res.status(500).json({ error: 'webhook_nao_configurado' }); return; }
  if (!igual(req.headers['x-webhook-secret'] || '', segredo)) { res.status(401).json({ error: 'segredo_invalido' }); return; }
  if (!KV_URL || !KV_TOKEN) { res.status(500).json({ error: 'banco_nao_configurado' }); return; }
  const body = lerCorpo(req);
  if (!body) { res.status(400).json({ error: 'body_invalido' }); return; }
  const culto = limpa(body.culto, 120), titulo = limpa(body.titulo, 120), n = parseInt(body.cortes, 10);
  if (!culto) { res.status(400).json({ error: 'culto_obrigatorio' }); return; }
  if (!(n >= 1 && n <= 99)) { res.status(400).json({ error: 'cortes_deve_ser_de_1_a_99' }); return; }
  try {
    // o mesmo aviso repetido em 2 minutos (tentativa dupla de quem chama) não vira notificação em dobro
    const trava = await kv(['SET', KEYS.dedupe + crypto.createHash('sha1').update(culto + '|' + n).digest('hex'), '1', 'NX', 'EX', '120']);
    if (!trava.result) { res.status(200).json({ ok: true, duplicado: true, enviados: 0 }); return; }

    const evento = { id: Date.now(), tipo: 'cortes-prontos', quando: new Date().toISOString(), culto, titulo, cortes: n };
    await kv(['LPUSH', KEYS.avisos, JSON.stringify(evento)]);
    await kv(['LTRIM', KEYS.avisos, '0', '49']);

    const pub = process.env.VAPID_PUBLIC_KEY, priv = process.env.VAPID_PRIVATE_KEY;
    if (!pub || !priv) { res.status(200).json({ ok: true, enviados: 0, aviso: 'chaves_de_notificacao_nao_configuradas', registrado: true }); return; }
    const webpush = require('web-push');
    webpush.setVapidDetails(process.env.VAPID_SUBJECT || 'mailto:contato@pibn.org.br', pub, priv);

    const inscritos = parear((await kv(['HGETALL', KEYS.push])).result);
    const payload = JSON.stringify({ title: 'Cortes prontos ✂️', body: `${culto}: ${n} ${n === 1 ? 'corte pronto' : 'cortes prontos'} pra aprovar`, url: '/#cortes', tag: 'cortes-' + culto });
    let enviados = 0, removidos = 0, falhas = 0;
    await Promise.all(inscritos.map(async ([endpoint, valor]) => {
      try { await webpush.sendNotification(JSON.parse(valor), payload, { TTL: 86400 }); enviados++; }
      catch (e) {
        if (e && (e.statusCode === 404 || e.statusCode === 410)) { removidos++; await kv(['HDEL', KEYS.push, endpoint]).catch(() => {}); }   // aparelho que desinstalou
        else falhas++;
      }
    }));
    res.status(200).json({ ok: true, inscritos: inscritos.length, enviados, removidos, falhas });
  } catch (e) {
    res.status(500).json({ error: String((e && e.message) || e) });
  }
};
