"""
API fake de um ERP, para você treinar extração de dados via API real
(autenticação, paginação, expiração de token, falhas intermitentes).

Rodar:
    uvicorn main:app --reload --port 8000

Depois acesse http://localhost:8000/docs para ver a documentação
interativa (Swagger) gerada automaticamente -- é assim que você vai
descobrir os endpoints de um ERP real também, então já é treino disso.
"""

import random
import secrets
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Query
from faker import Faker

app = FastAPI(
    title="ERP Fake API",
    description="Simula um ERP para treino de extração de dados via API.",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# "Credenciais" do cliente -- documentadas no README, não escondidas de
# propósito (num ERP real, você receberia isso do time de TI/fornecedor).
# ---------------------------------------------------------------------------
CLIENT_ID = "erp_demo_client"
CLIENT_SECRET = "erp_demo_secret_2026"
TOKEN_TTL_SECONDS = 90  # curto de propósito: força você a tratar expiração/refresh

# access_token -> expires_at (epoch)
active_tokens: dict[str, float] = {}

# ---------------------------------------------------------------------------
# Geração de dados em memória (mesma "cara" do case anterior, mas agora
# servida via HTTP em vez de CSV pronto)
# ---------------------------------------------------------------------------
random.seed(7)
Faker.seed(7)
fake = Faker("pt_BR")

CATEGORIES = [
    "Eletrônicos", "Moda", "Casa e Decoração", "Esporte e Lazer",
    "Livros", "Beleza", "Brinquedos", "Pet Shop",
]
PAYMENT_METHODS = ["credit_card", "pix", "boleto", "debit_card"]
ORDER_STATUS = ["completed", "completed", "completed", "cancelled", "refunded"]


def _gen_customers(n=500):
    rows = []
    for i in range(1, n + 1):
        created = fake.date_time_between(start_date="-2y", end_date="-6M")
        updated = created + timedelta(days=random.randint(0, 400))
        rows.append({
            "customer_id": i,
            "customer_name": fake.name(),
            "email": fake.email(),
            "state": fake.estado_sigla(),
            "city": fake.city(),
            "created_at": created.isoformat(),
            "updated_at": min(updated, datetime.now()).isoformat(),
        })
    return rows


def _gen_products(n=120):
    rows = []
    for i in range(1, n + 1):
        category = random.choice(CATEGORIES)
        cost = round(random.uniform(10, 800), 2)
        margin = random.uniform(1.2, 2.8)
        rows.append({
            "product_id": i,
            "product_name": f"{fake.word().capitalize()} {category[:4]}-{i}",
            "category": category,
            "cost_price": cost,
            "list_price": round(cost * margin, 2),
            "active": random.random() > 0.05,
        })
    return rows


def _gen_orders_and_items(customers, products, n_orders=2000):
    orders, items = [], []
    item_id_seq = 1
    active_products = [p for p in products if p["active"]]

    for order_id in range(1, n_orders + 1):
        customer = random.choice(customers)
        days_ago = random.randint(0, 180)
        order_ts = datetime.now() - timedelta(
            days=days_ago, hours=random.randint(0, 23), minutes=random.randint(0, 59)
        )
        status = random.choice(ORDER_STATUS)
        payment_method = random.choice(PAYMENT_METHODS)

        n_items = random.randint(1, 5)
        chosen = random.sample(active_products, k=min(n_items, len(active_products)))

        order_total = 0.0
        for prod in chosen:
            qty = random.randint(1, 3)
            unit_price = prod["list_price"]
            discount_pct = random.choice([0, 0, 0, 0.05, 0.1, 0.15])
            line_total = round(qty * unit_price * (1 - discount_pct), 2)
            order_total += line_total

            items.append({
                "order_item_id": item_id_seq,
                "order_id": order_id,
                "product_id": prod["product_id"],
                "quantity": qty,
                "unit_price": unit_price,
                "discount_pct": discount_pct,
                "line_total": line_total,
                "updated_at": order_ts.isoformat(),
            })
            item_id_seq += 1

        orders.append({
            "order_id": order_id,
            "customer_id": customer["customer_id"],
            "order_ts": order_ts.isoformat(),
            "status": status,
            "payment_method": payment_method,
            "order_total": round(order_total, 2),
            "updated_at": order_ts.isoformat(),
        })

    return orders, items


_CUSTOMERS = _gen_customers()
_PRODUCTS = _gen_products()
_ORDERS, _ORDER_ITEMS = _gen_orders_and_items(_CUSTOMERS, _PRODUCTS)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
@app.post("/auth/token")
def get_token(client_id: str, client_secret: str):
    """
    Fluxo tipo OAuth2 client-credentials, comum em ERPs (Bling, Omie, SAP
    B1, etc). Troque client_id + client_secret por um access_token.
    O token expira em TOKEN_TTL_SECONDS -- seu script vai precisar pedir
    um novo quando ele vencer.
    """
    if client_id != CLIENT_ID or client_secret != CLIENT_SECRET:
        raise HTTPException(status_code=401, detail="invalid_client")

    token = secrets.token_hex(16)
    active_tokens[token] = time.time() + TOKEN_TTL_SECONDS

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": TOKEN_TTL_SECONDS,
    }


def require_auth(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing_bearer_token")

    token = authorization.removeprefix("Bearer ").strip()
    expires_at = active_tokens.get(token)

    if expires_at is None:
        raise HTTPException(status_code=401, detail="invalid_token")
    if time.time() > expires_at:
        del active_tokens[token]
        raise HTTPException(status_code=401, detail="token_expired")

    # 5% de chance de simular uma falha transiente do servidor -- seu
    # script de extração precisa saber tentar de novo (com backoff) em
    # vez de quebrar na primeira falha.
    if random.random() < 0.05:
        raise HTTPException(status_code=500, detail="internal_server_error")


# ---------------------------------------------------------------------------
# Paginação genérica
# ---------------------------------------------------------------------------
def _paginate(records, page: int, page_size: int, updated_since: Optional[str] = None):
    if updated_since:
        try:
            cutoff = datetime.fromisoformat(updated_since)
        except ValueError:
            raise HTTPException(status_code=400, detail="updated_since deve ser ISO 8601, ex: 2026-09-01T00:00:00")
        records = [r for r in records if datetime.fromisoformat(r["updated_at"]) >= cutoff]

    total_records = len(records)
    total_pages = max(1, (total_records + page_size - 1) // page_size)
    start = (page - 1) * page_size
    end = start + page_size

    return {
        "data": records[start:end],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "total_records": total_records,
        },
    }


# ---------------------------------------------------------------------------
# Endpoints de dados
# ---------------------------------------------------------------------------
@app.get("/customers")
def get_customers(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
                   _auth=None, authorization: Optional[str] = Header(None)):
    require_auth(authorization)
    return _paginate(_CUSTOMERS, page, page_size)


@app.get("/products")
def get_products(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
                  authorization: Optional[str] = Header(None)):
    require_auth(authorization)
    return _paginate(_PRODUCTS, page, page_size)


@app.get("/orders")
def get_orders(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
                updated_since: Optional[str] = Query(None, description="ISO 8601, ex: 2026-09-01T00:00:00"),
                authorization: Optional[str] = Header(None)):
    require_auth(authorization)
    return _paginate(_ORDERS, page, page_size, updated_since)


@app.get("/order_items")
def get_order_items(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
                     updated_since: Optional[str] = Query(None, description="ISO 8601, ex: 2026-09-01T00:00:00"),
                     authorization: Optional[str] = Header(None)):
    require_auth(authorization)
    return _paginate(_ORDER_ITEMS, page, page_size, updated_since)


@app.get("/")
def root():
    return {
        "message": "ERP Fake API rodando. Veja /docs para a documentação interativa.",
        "auth": "POST /auth/token com client_id e client_secret (veja README.md)",
        "endpoints": ["/customers", "/products", "/orders", "/order_items"],
    }
