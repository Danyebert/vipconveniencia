# Convenience Manager v1.0.0

Sistema web para gestão de uma conveniência, desenvolvido em Flask/Python, com PostgreSQL no Supabase e preparado para Vercel.

## Funcionalidades

- Catálogo público com busca, categorias e somente produtos em estoque.
- Login administrativo.
- Dashboard com vendas do dia/mês e estoque baixo.
- Categorias.
- Produtos: compra, margem, preço sugerido, preço de venda, estoque mínimo, imagem e status.
- Clientes: nome, CPF, telefone e endereço.
- Entrada e histórico de estoque.
- PDV / venda com cliente opcional e forma de pagamento.
- Baixa transacional de estoque no PostgreSQL.
- Formas de pagamento iniciais: PIX, Espécie, Crédito e Débito.
- Abertura/fechamento de caixa, sangria e suprimento.
- Relatórios por período, faturamento, custo, lucro estimado e pagamentos.
- Layout responsivo para desktop e celular.
- Endpoint `/health` para teste.

## 1. Criar o banco no Supabase

1. Crie um projeto no Supabase.
2. Abra **SQL Editor**.
3. Copie e execute todo o conteúdo de `sql/schema.sql`.
4. Em **Project Settings > API**, copie a URL do projeto e a chave de servidor/secret. Nunca coloque a chave secret no navegador ou no Git.

O SQL cria as tabelas, índices, dados iniciais e a função transacional `finalizar_venda`.

## 2. Configurar variáveis

Copie `.env.example` para `.env` e preencha:

```env
FLASK_SECRET_KEY=uma-chave-longa-e-aleatoria
SUPABASE_URL=https://SEU-PROJETO.supabase.co
SUPABASE_KEY=SUA_CHAVE_SECRET_DO_SUPABASE
ADMIN_EMAIL=seu-email@dominio.com
ADMIN_PASSWORD=uma-senha-forte
STORE_NAME=Nome da sua Conveniência
```

Para gerar uma `FLASK_SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## 3. Rodar localmente

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

### Linux / WSL

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app main.py run --host=0.0.0.0 --port=5000 --debug --no-reload
```

Acesse `http://127.0.0.1:5000`.

## 4. Publicar no GitHub

```bash
git init
git add .
git commit -m "feat: Convenience Manager v1.0.0"
git branch -M main
git remote add origin URL_DO_SEU_REPOSITORIO
git push -u origin main
```

O `.env` já está no `.gitignore` e não será enviado.

## 5. Publicar na Vercel

1. Entre na Vercel e importe o repositório do GitHub.
2. Não precisa definir framework manualmente; o projeto contém `api/index.py` expondo a aplicação WSGI Flask.
3. Em **Project > Settings > Environment Variables**, cadastre:
   - `FLASK_SECRET_KEY`
   - `SUPABASE_URL`
   - `SUPABASE_KEY`
   - `ADMIN_EMAIL`
   - `ADMIN_PASSWORD`
   - `STORE_NAME`
4. Faça o deploy.
5. Abra `https://SEU-DOMINIO.vercel.app/health`. O retorno esperado é:

```json
{"status":"ok","version":"1.0.0"}
```

6. Depois acesse `/login` com `ADMIN_EMAIL` e `ADMIN_PASSWORD`.

## Primeiros passos após publicar

1. Cadastre/ajuste as categorias.
2. Cadastre os produtos.
3. Registre entradas de estoque.
4. Abra o caixa.
5. Faça uma venda teste.
6. Confira estoque, caixa e relatório.

## Fotos dos produtos

Nesta v1.0.0 o cadastro recebe uma URL de imagem. Você pode usar URLs públicas do Supabase Storage. Assim os arquivos não dependem do filesystem efêmero da Vercel.

## Segurança

- `SUPABASE_KEY` deve ser uma chave **de servidor/secret**, nunca uma chave pública exposta no JavaScript.
- O RLS está habilitado nas tabelas e não há policies públicas de escrita.
- A função de venda é executável somente pelo `service_role`.
- Troque imediatamente a senha administrativa de exemplo.
- Use HTTPS (a Vercel fornece HTTPS por padrão no domínio publicado).

## Estrutura

```text
conveniencia_manager_v1/
├── api/
│   └── index.py
├── sql/
│   └── schema.sql
├── static/
│   ├── css/app.css
│   └── js/app.js
├── templates/
├── app.py
├── main.py
├── requirements.txt
├── vercel.json
├── .env.example
└── README.md
```

## Observação sobre caixa

Uma venda pode ser realizada mesmo sem um caixa aberto, mas só entra no relatório de movimentação do caixa quando houver um caixa aberto. O relatório geral de vendas continua registrando a venda normalmente.
