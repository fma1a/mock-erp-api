# ERP Fake API — para treinar extração via Python

Simula um ERP real: autenticação por token (client credentials), paginação,
token que expira e falhas intermitentes de servidor. O objetivo é você
escrever o script de extração em Python **contra isso**, como se fosse
um ERP de verdade (Bling, Omie, SAP B1, etc. seguem esse mesmo padrão).

## Como rodar

```bash
cd mock_erp_api
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Acesse **http://localhost:8000/docs** — é a documentação interativa
(Swagger) gerada automaticamente pelo FastAPI. Isso é *exatamente* o que
você abriria primeiro ao integrar com um ERP real: a doc da API é o seu
ponto de partida antes de escrever qualquer linha de código.

## Credenciais

```
client_id:     erp_demo_client
client_secret: erp_demo_secret_2026
```

## Autenticação

```
POST /auth/token?client_id=erp_demo_client&client_secret=erp_demo_secret_2026
```

Retorna:
```json
{"access_token": "...", "token_type": "bearer", "expires_in": 90}
```

O token **expira em 90 segundos**. Isso é de propósito — de novo, ERPs
reais fazem isso, e seu script precisa lidar com isso (ver checklist
abaixo).

## Endpoints de dados

Todos exigem header `Authorization: Bearer <token>` e aceitam paginação:

| Endpoint         | Parâmetros                                  |
|-------------------|----------------------------------------------|
| `GET /customers`   | `page`, `page_size`                          |
| `GET /products`    | `page`, `page_size`                          |
| `GET /orders`      | `page`, `page_size`, `updated_since` (ISO 8601) |
| `GET /order_items` | `page`, `page_size`, `updated_since` (ISO 8601) |

Formato de resposta (igual em todos):
```json
{
  "data": [ ... ],
  "pagination": {
    "page": 1,
    "page_size": 50,
    "total_pages": 10,
    "total_records": 500
  }
}
```

O parâmetro `updated_since` existe pra você simular **extração
incremental** — em vez de puxar toda a tabela de novo a cada execução,
você guarda o timestamp da última extração e só pede o que mudou desde
então. Isso é essencial em ERP de verdade: você não vai re-extrair 2 anos
de pedidos toda hora.

## Comportamentos "de propósito" pra você tratar no script

1. **Token expira em 90s.** Se sua extração demorar mais que isso (ou
   você rodar de novo depois), vai tomar `401 token_expired`. O script
   precisa saber pedir um token novo quando isso acontecer.
2. **~5% das chamadas autenticadas falham com `500`.** Simula
   instabilidade real de API. O script precisa ter lógica de retry
   (tentar de novo algumas vezes, idealmente com um pequeno backoff)
   em vez de quebrar na primeira falha.
3. **Paginação obrigatória.** Nenhum endpoint devolve tudo de uma vez —
   `page_size` máximo é 200. Seu script precisa iterar pelas páginas até
   `page == total_pages`.
