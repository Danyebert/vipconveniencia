import os
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps
from werkzeug.exceptions import HTTPException

from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, session, url_for
from supabase import create_client
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-change-me")
app.config["STORE_NAME"] = os.getenv("STORE_NAME", "Minha Conveniência")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@conveniencia.local")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")


def db():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Configure SUPABASE_URL e SUPABASE_KEY no ambiente.")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def money(value):
    try:
        value = Decimal(str(value or 0))
    except Exception:
        value = Decimal("0")
    s = f"{value:,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")

app.jinja_env.filters["money"] = money


def parse_decimal(value, default="0"):
    if value is None:
        return Decimal(default)
    try:
        raw = str(value).replace("R$", "").replace(" ", "").strip()
        if "," in raw:
            raw = raw.replace(".", "").replace(",", ".")
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return Decimal(default)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@app.context_processor
def globals_ctx():
    return {"store_name": app.config["STORE_NAME"], "app_version": "1.0.0", "today": date.today()}


@app.errorhandler(404)
def page_not_found(exc):
    return render_template(
        "error.html",
        error="Página não encontrada."
    ), 404


@app.errorhandler(Exception)
def handle_exception(exc):

    # Se for erro HTTP normal, mantém o código correto
    if isinstance(exc, HTTPException):
        return render_template(
            "error.html",
            error=exc.description
        ), exc.code

    # Só registra traceback para erro interno real
    app.logger.exception(exc)

    if request.path.startswith("/admin"):
        flash(f"Erro: {exc}", "danger")

    return render_template(
        "error.html",
        error="Ocorreu um erro interno no sistema."
    ), 500
    
@app.route("/")
def catalog():
    client = db()
    cats = client.table("categorias").select("*").eq("ativo", True).order("nome").execute().data or []
    products = client.table("produtos").select("*,categorias(nome)").eq("ativo", True).gt("estoque_atual", 0).order("nome").execute().data or []
    q = (request.args.get("q") or "").strip().lower()
    category_id = request.args.get("categoria")
    if q:
        products = [p for p in products if q in (p.get("nome") or "").lower()]
    if category_id:
        products = [p for p in products if str(p.get("categoria_id")) == str(category_id)]
    return render_template("catalog.html", categories=cats, products=products, selected_category=category_id, q=q)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if email == ADMIN_EMAIL.lower() and password == ADMIN_PASSWORD:
            session.clear()
            session["admin"] = True
            session["email"] = email
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("E-mail ou senha inválidos.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("catalog"))


@app.route("/admin")
@login_required
def dashboard():
    client = db()
    start_today = datetime.combine(date.today(), datetime.min.time()).isoformat()
    month_start = date.today().replace(day=1).isoformat()
    sales_today = client.table("vendas").select("id,total,status,created_at").gte("created_at", start_today).eq("status", "finalizada").execute().data or []
    sales_month = client.table("vendas").select("id,total,status,created_at").gte("created_at", month_start).eq("status", "finalizada").execute().data or []
    low_stock = client.table("produtos").select("id,nome,estoque_atual,estoque_minimo").eq("ativo", True).execute().data or []
    low_stock = [p for p in low_stock if Decimal(str(p.get("estoque_atual") or 0)) <= Decimal(str(p.get("estoque_minimo") or 0))]
    latest = client.table("vendas").select("id,total,created_at,clientes(nome)").eq("status", "finalizada").order("created_at", desc=True).limit(8).execute().data or []
    return render_template(
        "dashboard.html",
        sales_today=sum(Decimal(str(s.get("total") or 0)) for s in sales_today),
        sales_month=sum(Decimal(str(s.get("total") or 0)) for s in sales_month),
        count_today=len(sales_today), low_stock=low_stock, latest=latest
    )


@app.route("/admin/categorias", methods=["GET", "POST"])
@login_required
def categories():
    client = db()
    if request.method == "POST":
        name = request.form.get("nome", "").strip()
        if name:
            client.table("categorias").insert({"nome": name, "ativo": True}).execute()
            flash("Categoria cadastrada.", "success")
        return redirect(url_for("categories"))
    rows = client.table("categorias").select("*").order("nome").execute().data or []
    return render_template("categories.html", categories=rows)


@app.post("/admin/categorias/<int:item_id>/toggle")
@login_required
def category_toggle(item_id):
    client = db()
    row = client.table("categorias").select("ativo").eq("id", item_id).single().execute().data
    client.table("categorias").update({"ativo": not bool(row.get("ativo"))}).eq("id", item_id).execute()
    return redirect(url_for("categories"))


@app.route("/admin/produtos")
@login_required
def products():
    rows = db().table("produtos").select("*,categorias(nome)").order("nome").execute().data or []
    return render_template("products.html", products=rows)


@app.route("/admin/produtos/novo", methods=["GET", "POST"])
@app.route("/admin/produtos/<int:item_id>/editar", methods=["GET", "POST"])
@login_required
def product_form(item_id=None):
    client = db()
    cats = client.table("categorias").select("*").eq("ativo", True).order("nome").execute().data or []
    product = None
    if item_id:
        product = client.table("produtos").select("*").eq("id", item_id).single().execute().data
    if request.method == "POST":
        purchase = parse_decimal(request.form.get("preco_compra"))
        margin = parse_decimal(request.form.get("margem"))
        suggested = purchase * (Decimal("1") + margin / Decimal("100"))
        payload = {
            "categoria_id": int(request.form["categoria_id"]),
            "nome": request.form["nome"].strip(),
            "descricao": request.form.get("descricao", "").strip(),
            "preco_compra": float(purchase), "margem": float(margin), "preco_sugerido": float(suggested),
            "preco_venda": float(parse_decimal(request.form.get("preco_venda"))),
            "estoque_minimo": float(parse_decimal(request.form.get("estoque_minimo"))),
            "imagem_url": request.form.get("imagem_url", "").strip() or None,
            "ativo": request.form.get("ativo") == "on",
            "updated_at": datetime.utcnow().isoformat()
        }
        if item_id:
            client.table("produtos").update(payload).eq("id", item_id).execute()
            flash("Produto atualizado.", "success")
        else:
            payload["estoque_atual"] = 0
            client.table("produtos").insert(payload).execute()
            flash("Produto cadastrado.", "success")
        return redirect(url_for("products"))
    return render_template("product_form.html", categories=cats, product=product)


@app.post("/admin/produtos/<int:item_id>/toggle")
@login_required
def product_toggle(item_id):
    client = db()
    row = client.table("produtos").select("ativo").eq("id", item_id).single().execute().data
    client.table("produtos").update({"ativo": not bool(row.get("ativo"))}).eq("id", item_id).execute()
    return redirect(url_for("products"))


@app.route("/admin/clientes")
@login_required
def clients():
    rows = db().table("clientes").select("*").order("nome").execute().data or []
    return render_template("clients.html", clients=rows)


@app.route("/admin/clientes/novo", methods=["GET", "POST"])
@app.route("/admin/clientes/<int:item_id>/editar", methods=["GET", "POST"])
@login_required
def client_form(item_id=None):
    client = db()
    customer = None
    if item_id:
        customer = client.table("clientes").select("*").eq("id", item_id).single().execute().data
    if request.method == "POST":
        payload = {k: request.form.get(k, "").strip() or None for k in ["nome", "cpf", "telefone", "cep", "endereco", "numero", "bairro", "cidade", "uf"]}
        if item_id:
            client.table("clientes").update(payload).eq("id", item_id).execute()
        else:
            client.table("clientes").insert(payload).execute()
        flash("Cliente salvo.", "success")
        return redirect(url_for("clients"))
    return render_template("client_form.html", customer=customer)


@app.route("/admin/estoque", methods=["GET", "POST"])
@login_required
def stock():
    client = db()
    if request.method == "POST":
        product_id = int(request.form["produto_id"])
        qty = parse_decimal(request.form["quantidade"])
        cost = parse_decimal(request.form.get("custo_unitario"))
        prod = client.table("produtos").select("*").eq("id", product_id).single().execute().data
        before = Decimal(str(prod.get("estoque_atual") or 0))
        after = before + qty
        client.table("produtos").update({"estoque_atual": float(after), "preco_compra": float(cost) if cost > 0 else prod.get("preco_compra")}).eq("id", product_id).execute()
        client.table("movimentacoes_estoque").insert({
            "produto_id": product_id, "tipo": "ENTRADA", "quantidade": float(qty),
            "estoque_anterior": float(before), "estoque_posterior": float(after), "custo_unitario": float(cost),
            "observacao": request.form.get("observacao", "").strip() or "Entrada manual"
        }).execute()
        flash("Entrada de estoque registrada.", "success")
        return redirect(url_for("stock"))
    products = client.table("produtos").select("id,nome,estoque_atual,preco_compra").eq("ativo", True).order("nome").execute().data or []
    moves = client.table("movimentacoes_estoque").select("*,produtos(nome)").order("created_at", desc=True).limit(50).execute().data or []
    return render_template("stock.html", products=products, moves=moves)


@app.route("/admin/vendas", methods=["GET", "POST"])
@login_required
def sales():
    client = db()
    if request.method == "POST":
        product_ids = request.form.getlist("produto_id[]")
        qtys = request.form.getlist("quantidade[]")
        if not product_ids:
            flash("Adicione pelo menos um produto.", "danger")
            return redirect(url_for("sales"))
        items = []
        for pid, qty_raw in zip(product_ids, qtys):
            qty = parse_decimal(qty_raw)
            if pid and qty > 0:
                items.append({"produto_id": int(pid), "quantidade": float(qty)})
        if not items:
            flash("Informe ao menos um item válido.", "danger")
            return redirect(url_for("sales"))
        customer_id = request.form.get("cliente_id") or None
        payment_id = int(request.form["forma_pagamento_id"])
        result = client.rpc("finalizar_venda", {
            "p_cliente_id": int(customer_id) if customer_id else None,
            "p_forma_pagamento_id": payment_id,
            "p_itens": items
        }).execute().data
        if isinstance(result, list):
            result = result[0] if result else {}
        flash(f"Venda #{result.get('venda_id')} finalizada no valor de {money(result.get('total'))}.", "success")
        return redirect(url_for("sales"))
    products = client.table("produtos").select("id,nome,preco_venda,estoque_atual").eq("ativo", True).gt("estoque_atual", 0).order("nome").execute().data or []
    customers = client.table("clientes").select("id,nome,cpf").order("nome").execute().data or []
    payments = client.table("formas_pagamento").select("*").eq("ativo", True).order("nome").execute().data or []
    latest = client.table("vendas").select("id,total,created_at,clientes(nome)").eq("status", "finalizada").order("created_at", desc=True).limit(20).execute().data or []
    return render_template("sales.html", products=products, customers=customers, payments=payments, latest=latest)


@app.route("/admin/caixa", methods=["GET", "POST"])
@login_required
def cash():
    client = db()
    open_rows = client.table("caixas").select("*").eq("status", "aberto").order("aberto_em", desc=True).limit(1).execute().data or []
    current = open_rows[0] if open_rows else None
    if request.method == "POST":
        action = request.form.get("action")
        if action == "open" and not current:
            initial = parse_decimal(request.form.get("valor_inicial"))
            client.table("caixas").insert({"valor_inicial": float(initial), "status": "aberto"}).execute()
            flash("Caixa aberto.", "success")
        elif action == "close" and current:
            informed = parse_decimal(request.form.get("valor_informado"))
            moves = client.table("movimentacoes_caixa").select("tipo,valor").eq("caixa_id", current["id"]).execute().data or []
            expected = Decimal(str(current.get("valor_inicial") or 0)) + sum((Decimal(str(m.get("valor") or 0)) for m in moves if m.get("tipo") in ["VENDA", "SUPRIMENTO"]), Decimal("0")) - sum((Decimal(str(m.get("valor") or 0)) for m in moves if m.get("tipo") == "SANGRIA"), Decimal("0"))
            client.table("caixas").update({"status": "fechado", "fechado_em": datetime.utcnow().isoformat(), "valor_final_esperado": float(expected), "valor_final_informado": float(informed), "diferenca": float(informed - expected)}).eq("id", current["id"]).execute()
            flash("Caixa fechado.", "success")
        return redirect(url_for("cash"))
    moves = []
    by_payment = {}
    if current:
        moves = client.table("movimentacoes_caixa").select("*,formas_pagamento(nome)").eq("caixa_id", current["id"]).order("created_at", desc=True).execute().data or []
        for m in moves:
            name = ((m.get("formas_pagamento") or {}).get("nome")) or m.get("tipo")
            by_payment[name] = by_payment.get(name, Decimal("0")) + Decimal(str(m.get("valor") or 0))
    return render_template("cash.html", current=current, moves=moves, by_payment=by_payment)


@app.post("/admin/caixa/movimento")
@login_required
def cash_movement():
    client = db()
    open_rows = client.table("caixas").select("id").eq("status", "aberto").limit(1).execute().data or []
    if not open_rows:
        flash("Abra o caixa primeiro.", "danger")
        return redirect(url_for("cash"))
    kind = request.form.get("tipo")
    if kind not in ["SANGRIA", "SUPRIMENTO"]:
        flash("Tipo de movimento inválido.", "danger")
        return redirect(url_for("cash"))
    client.table("movimentacoes_caixa").insert({"caixa_id": open_rows[0]["id"], "tipo": kind, "valor": float(parse_decimal(request.form.get("valor"))), "descricao": request.form.get("descricao", "").strip()}).execute()
    flash("Movimento de caixa registrado.", "success")
    return redirect(url_for("cash"))


@app.route("/admin/relatorios")
@login_required
def reports():
    client = db()
    start = request.args.get("inicio") or (date.today() - timedelta(days=30)).isoformat()
    end = request.args.get("fim") or date.today().isoformat()
    end_dt = (datetime.fromisoformat(end) + timedelta(days=1)).isoformat()
    rows = client.table("vendas").select("id,total,created_at,clientes(nome),venda_itens(quantidade,preco_custo,subtotal),venda_pagamentos(valor,formas_pagamento(nome))").gte("created_at", start).lt("created_at", end_dt).eq("status", "finalizada").order("created_at", desc=True).execute().data or []
    revenue = sum((Decimal(str(r.get("total") or 0)) for r in rows), Decimal("0"))
    cost = Decimal("0")
    payments = {}
    for r in rows:
        for item in r.get("venda_itens") or []:
            cost += Decimal(str(item.get("preco_custo") or 0)) * Decimal(str(item.get("quantidade") or 0))
        for p in r.get("venda_pagamentos") or []:
            name = ((p.get("formas_pagamento") or {}).get("nome")) or "Não informado"
            payments[name] = payments.get(name, Decimal("0")) + Decimal(str(p.get("valor") or 0))
    return render_template("reports.html", rows=rows, start=start, end=end, revenue=revenue, cost=cost, profit=revenue-cost, payments=payments)


@app.route("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}
