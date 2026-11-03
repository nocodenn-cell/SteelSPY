import os

# Testes não enviam X-API-KEY; desliga verificação salvo override explícito no teste.
os.environ.setdefault("SKIP_API_KEY", "1")

# Segredo usado para assinar cookies de sessão. Só para teste: em qualquer
# ambiente real, PWA_SESSION_SECRET vem do secret manager e nunca do repositório.
os.environ.setdefault("PWA_SESSION_SECRET", "test-only-secret-nao-usar-em-producao-0123456789")

# Cookie sem Secure por padrão nos testes (o TestClient fala http://, não https://).
os.environ.setdefault("PWA_COOKIE_SECURE", "0")
