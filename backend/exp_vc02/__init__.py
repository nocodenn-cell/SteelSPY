"""Preparação da Sprint 5 (visão) — ferramentas agnósticas de modelo.

Nada aqui importa detector, GPU ou rede. São dois contratos executáveis:

* `dataset`: o que um dataset de vergalhões precisa provar antes do treino
  (hashes, dimensões, rótulos COCO e ausência de vazamento entre divisões);
* `metricas`: como uma predição é medida e barrada (AP/AR, precisão/recall e
  portão de validação humana) — o mesmo contrato para qualquer modelo futuro.
"""
