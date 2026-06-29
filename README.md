# Controle de Gravações — versão online (compartilhada)

App de agenda, roteiros e pessoas para gravações, com **dados compartilhados** entre duas
ou mais pessoas. Hospedado no **Vercel**, dados guardados no **Vercel KV** (banco grátis).

Tudo pode ser feito pelo **navegador**, sem terminal.

---

## Passo 1 — Subir no GitHub

1. Acesse https://github.com/new
2. **Repository name:** `controle-gravacoes-online` → deixe **Public** ou **Private** (tanto faz) → **Create repository**
3. Na página do repositório, clique em **"uploading an existing file"** (ou aba *Add file → Upload files*)
4. **Arraste TODOS os arquivos desta pasta** para a área de upload, incluindo a pasta `api`:
   - `index.html`
   - `api/data.js`  (mantenha dentro da pasta `api`)
   - `package.json`
   - `manifest.webmanifest`
   - `apple-touch-icon.png`, `icon-192.png`, `icon-512.png`
   - `README.md`
5. Clique em **Commit changes**

## Passo 2 — Importar no Vercel

1. Acesse https://vercel.com/new
2. **Import** o repositório `controle-gravacoes-online` que você acabou de criar
3. **Framework Preset:** deixe **Other** · não preencha *Build Command* · **Deploy**
4. Espere terminar. Vai gerar um link tipo `https://controle-gravacoes-online.vercel.app`
   - (Nesse momento o app abre, mas ainda mostra erro de banco — falta o Passo 3.)

## Passo 3 — Criar o banco (Vercel KV)

1. No projeto do Vercel, abra a aba **Storage**
2. **Create Database** → escolha **KV** (Redis / Upstash) → dê um nome → **Create**
3. **Connect** o banco ao projeto `controle-gravacoes-online` (marque todos os ambientes:
   Production, Preview, Development)
   - Isso adiciona sozinho as variáveis `KV_REST_API_URL` e `KV_REST_API_TOKEN`.

## Passo 4 — Definir o código de acesso (recomendado)

Para ninguém de fora bisbilhotar caso o link vaze:

1. Projeto → **Settings** → **Environment Variables**
2. Adicione:
   - **Key:** `ACCESS_CODE`
   - **Value:** uma senha à sua escolha (ex: `estudio2026`)
   - Marque os 3 ambientes → **Save**

## Passo 5 — Republicar (importante)

Depois de conectar o banco e/ou adicionar o código:

1. Aba **Deployments** → no deploy mais recente, clique no menu **⋯** → **Redeploy** → **Redeploy**

Pronto! Agora o link está funcionando com dados compartilhados. ✅

---

## Usar no iPhone (atalho na tela inicial)

1. Abra o link do app no **Safari**
2. Digite o **código de acesso** (o mesmo `ACCESS_CODE` que você definiu)
3. Toque no botão **Compartilhar** (quadrado com seta para cima)
4. **Adicionar à Tela de Início** → **Adicionar**

O ícone aparece como um app. Faça o mesmo no celular da outra pessoa, com o **mesmo link
e mesmo código** — os dois verão e editarão a **mesma lista**.

---

## Como funciona / observações

- Os dados ficam num único registro no Vercel KV e são **sincronizados a cada ~7 segundos**.
- O canto superior mostra o status: **✓ Sincronizado**, **Salvando…**, **Sem conexão**.
- Para evitar perda de dados, **evitem editar exatamente a mesma coisa no mesmo segundo**
  (vale o último que salvar). Para o uso normal de duas pessoas, é tranquilo.
- O botão **Backup** baixa um arquivo `.json` com tudo — bom para guardar uma cópia.
- O app local antigo (`app-gravacoes.html`) continua existindo e é independente desta versão.
