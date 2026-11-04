"""Protótipo experimental de contagem visual de vergalhões (Sprint VC-01).

Módulo isolado: nenhuma rota do produto o importa e nenhuma decisão daqui entra
no recebimento. A única ligação com o SteelSPY real é a reutilização da validação
de fotografia já existente em `app.services.evidencias`, para que o experimento
não reinventasse verificação de assinatura, normalização e hash.

O pacote depende de bibliotecas de visão computacional que **não** estão no
`requirements.txt` da aplicação. Por isso os importadores pesados (`cv2`, `numpy`,
`torch`) aparecem só dentro das funções que precisam deles: assim a suíte de
testes do produto continua rodando no venv de sempre, sem o stack de inferência.
"""
