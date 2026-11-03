import os

# Testes não enviam X-API-KEY; desliga verificação salvo override explícito no teste.
os.environ.setdefault("SKIP_API_KEY", "1")
