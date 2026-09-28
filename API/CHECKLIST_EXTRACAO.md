# Checklist — Etapa 1: script de extração (extract.py)

Não é receita de bolo — é o que o script precisa resolver, na ordem que
faz sentido resolver. Escreva, rode, e me chama quando travar ou quando
quiser revisão.

## 1. Autenticação
- [ ] Fazer `POST /auth/token` com `client_id`/`client_secret`
- [ ] Guardar o `access_token` e calcular quando ele expira
      (`time.time() + expires_in`, por exemplo)
- [ ] Criar uma função tipo `get_valid_token()` que só pede um token novo
      se o atual estiver perto de expirar (ou já expirado) — não peça um
      token novo a cada request, só quando precisar

## 2. Uma chamada simples
- [ ] Fazer `GET /customers` com o header `Authorization: Bearer <token>`
- [ ] Conferir que recebeu `200` e conseguiu ler o JSON

## 3. Paginação
- [ ] Ler `pagination.total_pages` da primeira resposta
- [ ] Iterar de `page=1` até `total_pages`, acumulando os `data` de cada
      página numa lista só
- [ ] Repetir esse padrão pra `products`, `orders` e `order_items`
      (dica: vale a pena escrever uma função genérica `fetch_all(endpoint,
      params={})` que qualquer um dos 4 endpoints usa, em vez de duplicar
      o loop 4 vezes)

## 4. Tratamento de erro / retry
- [ ] Se a resposta vier `401` com `token_expired`, pedir um token novo
      e repetir a chamada (só essa, não recomeçar tudo do zero)
- [ ] Se vier `500`, tentar de novo até N vezes (ex: 3) antes de desistir
      — pode usar um `time.sleep()` pequeno entre tentativas
- [ ] Se estourar as tentativas, decidir o que fazer: abortar o pipeline
      inteiro, ou seguir sem aquele lote e logar o que faltou? (pensa
      nisso e me conta sua decisão — não tem resposta única certa, depende
      do caso de uso)

## 5. Extração incremental (opcional nessa primeira passada)
- [ ] Usar `updated_since` em `orders`/`order_items` pra só buscar o que
      mudou desde a última execução
- [ ] Pensar em onde guardar esse "timestamp da última execução" (um
      arquivo local simples resolve por agora; depois, numa versão mais
      madura, isso viraria uma tabela de controle no próprio Snowflake)

## 6. Saída
- [ ] Salvar cada entidade (`customers`, `products`, `orders`,
      `order_items`) como CSV ou Parquet numa pasta `data/raw/`
- [ ] Não precisa limpar/transformar nada aqui — isso é o próximo passo,
      já dentro do Snowflake

---

**Bibliotecas que você vai precisar:** `requests` (chamadas HTTP) e
`pandas` (estruturar e salvar). Não precisa de mais nada além disso pra
essa etapa.

Quando terminar (ou travar em algum ponto), me manda o que você escreveu
que eu reviso com você.
