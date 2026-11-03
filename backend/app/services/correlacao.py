"""Motor de correlação pedido × NF-e.

Por que este módulo existe separado da conciliação
--------------------------------------------------

A conciliação antiga casava linha de pedido com item de NF-e **por bitola**. Duas
linhas de pedido com a mesma bitola apontavam para o mesmo item faturado, e o
mesmo ferro era contado duas vezes: o resultado parecia conferido e estava
errado.

Aqui a associação é feita antes de qualquer conta, com uma regra só:

    uma quantidade faturada pode ser consumida por uma única linha do pedido.

E por uma regra de honestidade:

    quando a evidência não decide entre duas leituras, não se escolhe uma.
    Marca-se para revisão humana.

Confianças, da mais forte para a mais fraca
-------------------------------------------

1. `manual` — um responsável confirmou a correlação. Vale mais que qualquer heurística.
2. `codigo_produto` — o código do fornecedor no pedido e o `cProd` da NF-e coincidem.
3. `bitola_unica` — só existe uma linha do pedido disputando aquele item. A
   exclusividade é o que torna o casamento determinístico; se duas linhas têm a
   mesma bitola, ele deixa de existir.

Fora isso, nada é casado. Itens sobram como *faturado sem pedido* e linhas como
*pedido não faturado* — os dois casos que a conciliação anterior escondia.

O módulo é puro: não conhece banco, HTTP nem tenant. Recebe dados, devolve
decisões. É assim que se consegue testar ambiguidade sem montar um mundo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from app.domain.conferente import converter_para_metros

# ---------------------------------------------------------------------------
# Normalização de unidades
# ---------------------------------------------------------------------------

_POR_EXTENSO = {"M", "METRO", "METROS", "ML", "MT", "M1"}
_QUILO = {"KG", "KILO", "QUILOGRAMA", "QUILOGRAMAS", "KGS"}
_BARRA = {"BARRA", "BARRAS", "UN", "UNID", "UNIDADE", "PC", "PCS", "PCT"}
_SACO = {"SACO", "SACOS", "SC", "SAC"}
_M3 = {"M3", "M³", "METRO CUBICO", "METROS CUBICOS", "M_CUBO"}
_TON = {"TON", "TONELADA", "TONELADAS", "T"}

METROS_POR_BARRA_PADRAO = 12.0


def normalizar_unidade(unidade: Any) -> str:
    return str(unidade or "").strip().upper()


def chave_base(quantidade: Any, unidade: Any, bitola_mm: Any, metros_por_barra: float | None = None) -> tuple[str, float] | None:
    """
    Converte `(quantidade, unidade)` para uma base comparável.

    Devolve `(nome_da_base, valor)` ou `None` quando não há base conhecida —
    e ausência de base é o que impede comparar 1000 m com 40 t sem inventar.

    Aço com bitola converge para metros: é a única grandeza em que barra, quilo
    e metro descrevem o mesmo material. Sem bitola, não há como converter —
    um "UN" de cimento e um "UN" de vergalhão não são a mesma coisa.
    """
    try:
        q = float(quantidade)
    except (TypeError, ValueError):
        return None

    u = normalizar_unidade(unidade)
    try:
        b = float(bitola_mm) if bitola_mm is not None else None
    except (TypeError, ValueError):
        b = None

    if u in _POR_EXTENSO:
        return ("m", q)
    if u in _QUILO:
        if b and b > 0:
            return ("m", converter_para_metros(q, b))
        return ("kg", q)
    if u in _BARRA:
        if b and b > 0:
            mpb = metros_por_barra or METROS_POR_BARRA_PADRAO
            return ("m", q * float(mpb))
        return ("un", q)
    if u in _SACO:
        return ("saco", q)
    if u in _M3:
        return ("m3", q)
    if u in _TON:
        return ("ton", q)
    if not u:
        return None
    return (u.lower(), q)


def normalizar_codigo(codigo: Any) -> str:
    """Código de produto comparável: maiúsculo, sem pontuação nem espaços."""
    if codigo is None:
        return ""
    return "".join(c for c in str(codigo).strip().upper() if c.isalnum())


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LinhaPedido:
    pedido_item_id: str
    linha: int
    quantidade: float
    unidade: str
    codigo_produto: str | None = None
    material_tipo: str = "material"
    categoria_material: str = "aco"
    bitola_mm: float | None = None
    marca_exigida: str | None = None
    metros_por_barra: float | None = None

    @classmethod
    def de_dict(cls, d: dict[str, Any]) -> "LinhaPedido":
        return cls(
            pedido_item_id=str(d.get("id") or d["pedido_item_id"]),
            linha=int(d.get("linha") or 0),
            quantidade=float(d.get("quantidade") or 0),
            unidade=str(d.get("unidade") or ""),
            codigo_produto=d.get("codigo_produto_fornecedor") or d.get("codigo_produto"),
            material_tipo=str(d.get("material_tipo") or "material"),
            categoria_material=str(d.get("categoria_material") or "aco"),
            bitola_mm=float(d["bitola_mm"]) if d.get("bitola_mm") is not None else None,
            marca_exigida=d.get("marca_exigida") or d.get("marca"),
            metros_por_barra=d.get("metros_por_barra"),
        )

    @property
    def base(self) -> tuple[str, float] | None:
        return chave_base(
            self.quantidade, self.unidade, self.bitola_mm, self.metros_por_barra
        )


@dataclass(frozen=True)
class ItemFaturado:
    referencia: str
    nfe_log_id: str
    n_item: int
    quantidade: float | None
    unidade: str | None
    codigo_produto: str | None = None
    descricao: str | None = None
    bitola_mm: float | None = None
    marca: str | None = None
    metros_por_barra: float | None = None

    @classmethod
    def de_dict(cls, d: dict[str, Any], *, nfe_log_id: str, posicao: int) -> "ItemFaturado":
        n_item = d.get("nItem") or d.get("n_item") or d.get("item_numero") or posicao
        try:
            n_item_int = int(str(n_item))
        except (TypeError, ValueError):
            n_item_int = posicao
        return cls(
            referencia=f"{nfe_log_id}:{n_item_int}",
            nfe_log_id=nfe_log_id,
            n_item=n_item_int,
            quantidade=float(d["quantidade"]) if d.get("quantidade") is not None else None,
            unidade=d.get("unidade"),
            codigo_produto=d.get("codigo_produto") or d.get("cProd") or d.get("codigo"),
            descricao=d.get("descricao"),
            bitola_mm=float(d["bitola_mm"]) if d.get("bitola_mm") is not None else None,
            marca=d.get("marca"),
            metros_por_barra=d.get("metros_por_barra"),
        )

    @property
    def base(self) -> tuple[str, float] | None:
        return chave_base(
            self.quantidade, self.unidade, self.bitola_mm, self.metros_por_barra
        )


@dataclass(frozen=True)
class CorrelacaoHumana:
    """Correlação confirmada por responsável. Vence qualquer heurística."""

    pedido_item_id: str
    nfe_log_id: str
    n_item: int
    quantidade: float | None = None
    observacao: str | None = None

    @property
    def referencia(self) -> str:
        return f"{self.nfe_log_id}:{self.n_item}"


# ---------------------------------------------------------------------------
# Saída
# ---------------------------------------------------------------------------


@dataclass
class Atribuicao:
    pedido_item_id: str
    linha: int
    referencia: str
    nfe_log_id: str
    n_item: int
    confianca: str
    quantidade_faturada: float
    quantidade_faturada_base: float
    base: str
    quantidade_consumida_base: float
    origem: str = "automatica"


@dataclass
class Ambiguidade:
    pedido_item_id: str
    linha: int
    motivo: str
    candidatos: list[dict[str, Any]] = field(default_factory=list)
    disputado_por: list[int] = field(default_factory=list)


@dataclass
class ResultadoCorrelacao:
    atribuicoes: list[Atribuicao]
    ambiguidades: list[Ambiguidade]
    linhas_sem_fatura: list[dict[str, Any]]
    faturados_sem_pedido: list[dict[str, Any]]

    def por_linha(self) -> dict[str, list[Atribuicao]]:
        agrupado: dict[str, list[Atribuicao]] = {}
        for a in self.atribuicoes:
            agrupado.setdefault(a.pedido_item_id, []).append(a)
        return agrupado


# ---------------------------------------------------------------------------
# Motor
# ---------------------------------------------------------------------------

CONFIANCA_MANUAL = "manual"
CONFIANCA_CODIGO = "codigo_produto"
CONFIANCA_BITOLA_UNICA = "bitola_unica"

_MOTIVO_AMBIGUIDADE = (
    "Mais de uma linha do pedido disputa o mesmo item faturado. "
    "Sem evidência para decidir, nenhuma correlação é aplicada."
)
_MOTIVO_CODIGO_DUPLICADO = (
    "Duas linhas do pedido trazem o mesmo código de produto do fornecedor. "
    "O código não identifica a linha: precisa de revisão humana."
)


def _compativel_por_atributo(linha: LinhaPedido, item: ItemFaturado) -> bool:
    """
    Casamento por atributo só quando as grandezas são comparáveis e a bitola bate.

    Bitola de um lado só não gera casamento: é justamente o caso em que o
    sistema antigo adivinhou, e adivinhação não é auditoria. Cimento e bloco,
    que não têm bitola de nenhum lado, casam pela unidade — a exclusividade do
    componente é o que continua tornando a associação determinística.
    """
    if linha.base is None or item.base is None:
        return False
    if linha.base[0] != item.base[0]:
        return False
    if linha.bitola_mm is not None and item.bitola_mm is not None:
        return abs(float(linha.bitola_mm) - float(item.bitola_mm)) <= 0.5
    return linha.bitola_mm is None and item.bitola_mm is None


def correlacionar(
    linhas: Iterable[LinhaPedido],
    itens: Iterable[ItemFaturado],
    *,
    manuais: Iterable[CorrelacaoHumana] = (),
) -> ResultadoCorrelacao:
    """
    Determina quais itens faturados pertencem a quais linhas do pedido.

    Ordem de decisão — a primeira que resolve, resolve:

    1. correlações humanas confirmadas;
    2. código de produto do fornecedor == código do item na NF-e;
    3. bitola, quando a linha é a **única** candidata daquele grupo de itens.

    Itens sem qualquer correspondência viram `faturados_sem_pedido`. Linhas sem
    item viram `linhas_sem_fatura`. Grupos em que duas linhas disputam o mesmo
    item viram `ambiguidades` — e ficam fora das outras três listas, para o
    relatório não contar o mesmo problema duas vezes.
    """
    linhas = list(linhas)
    itens = list(itens)
    por_ref = {i.referencia: i for i in itens}
    linha_por_id = {l.pedido_item_id: l for l in linhas}

    saldo = {i.referencia: (float(i.quantidade) if i.quantidade is not None else 0.0) for i in itens}
    sem_quantidade = {i.referencia for i in itens if i.quantidade is None or float(i.quantidade) <= 0}
    for ref in sem_quantidade:
        saldo[ref] = 0.0

    atribuicoes: list[Atribuicao] = []
    consumido_por: dict[str, list[str]] = {i.referencia: [] for i in itens}
    resolvidas: set[str] = set()
    ambiguidades: list[Ambiguidade] = []

    def _registrar(linha: LinhaPedido, item: ItemFaturado, confianca: str, origem: str, quantidade: float) -> None:
        base_item = item.base or ("", 0.0)
        atribuicoes.append(
            Atribuicao(
                pedido_item_id=linha.pedido_item_id,
                linha=linha.linha,
                referencia=item.referencia,
                nfe_log_id=item.nfe_log_id,
                n_item=item.n_item,
                confianca=confianca,
                quantidade_faturada=float(item.quantidade or 0),
                quantidade_faturada_base=base_item[1],
                base=base_item[0],
                quantidade_consumida_base=quantidade,
                origem=origem,
            )
        )
        consumido_por[item.referencia].append(linha.pedido_item_id)

    # --- 1. humana -----------------------------------------------------------
    for m in manuais:
        linha = linha_por_id.get(m.pedido_item_id)
        item = por_ref.get(m.referencia)
        if linha is None or item is None:
            continue
        disponível = saldo[item.referencia]
        if disponível <= 0:
            continue
        pedido_base = chave_base(m.quantidade, item.unidade, item.bitola_mm, item.metros_por_barra)
        valor = pedido_base[1] if pedido_base else disponível
        consumir = min(valor, disponível)
        _registrar(linha, item, CONFIANCA_MANUAL, "humana", consumir)
        saldo[item.referencia] = disponível - consumir
        resolvidas.add(linha.pedido_item_id)

    # --- 2. código de produto ------------------------------------------------
    linhas_por_codigo: dict[str, list[LinhaPedido]] = {}
    for l in linhas:
        if l.pedido_item_id in resolvidas:
            continue
        cod = normalizar_codigo(l.codigo_produto)
        if cod:
            linhas_por_codigo.setdefault(cod, []).append(l)

    itens_por_codigo: dict[str, list[ItemFaturado]] = {}
    for i in itens:
        cod = normalizar_codigo(i.codigo_produto)
        if cod:
            itens_por_codigo.setdefault(cod, []).append(i)

    for cod, candidatas in linhas_por_codigo.items():
        grupo_itens = [
            i for i in itens_por_codigo.get(cod, []) if saldo[i.referencia] > 0
        ]
        if not grupo_itens:
            continue
        if len(candidatas) > 1:
            # O código repete no pedido: ele deixou de identificar a linha.
            for l in candidatas:
                ambiguidades.append(
                    Ambiguidade(
                        pedido_item_id=l.pedido_item_id,
                        linha=l.linha,
                        motivo=_MOTIVO_CODIGO_DUPLICADO,
                        candidatos=[_resumo_item(i, saldo[i.referencia]) for i in grupo_itens],
                        disputado_por=[o.linha for o in candidatas if o is not l],
                    )
                )
                resolvidas.add(l.pedido_item_id)
            for i in grupo_itens:
                saldo[i.referencia] = 0.0
            continue

        linha = candidatas[0]
        for item in grupo_itens:
            _registrar(linha, item, CONFIANCA_CODIGO, "automatica", saldo[item.referencia])
            saldo[item.referencia] = 0.0
        resolvidas.add(linha.pedido_item_id)

    # --- 3. atributo com exclusividade ---------------------------------------
    restantes = [l for l in linhas if l.pedido_item_id not in resolvidas]
    candidatos_por_linha = {
        l.pedido_item_id: [i for i in itens if saldo[i.referencia] > 0 and _compativel_por_atributo(l, i)]
        for l in restantes
    }

    # Componentes conexos: duas linhas estão no mesmo componente se disputam um
    # mesmo item. Componente com uma única linha é determinístico; com duas, não.
    visitados: set[str] = set()
    for linha in restantes:
        inicio = linha.pedido_item_id
        if inicio in visitados:
            continue
        pilha = [inicio]
        componente_linhas: set[str] = set()
        componente_itens: set[str] = set()
        while pilha:
            atual = pilha.pop()
            if atual in componente_linhas:
                continue
            componente_linhas.add(atual)
            for item in candidatos_por_linha.get(atual, []):
                if item.referencia in componente_itens:
                    continue
                componente_itens.add(item.referencia)
                for outra, cands in candidatos_por_linha.items():
                    if outra != atual and any(c.referencia == item.referencia for c in cands):
                        pilha.append(outra)

        if len(componente_linhas) == 1:
            pid = next(iter(componente_linhas))
            l = linha_por_id[pid]
            for ref in sorted(componente_itens):
                item = por_ref[ref]
                if saldo[ref] <= 0:
                    continue
                _registrar(l, item, CONFIANCA_BITOLA_UNICA, "automatica", saldo[ref])
                saldo[ref] = 0.0
            if componente_itens:
                resolvidas.add(pid)
        else:
            numeradas = sorted(linha_por_id[pid].linha for pid in componente_linhas)
            for pid in sorted(componente_linhas):
                l = linha_por_id[pid]
                concorrentes = [x for x in numeradas if x != l.linha]
                ambiguidades.append(
                    Ambiguidade(
                        pedido_item_id=pid,
                        linha=l.linha,
                        motivo=_MOTIVO_AMBIGUIDADE,
                        candidatos=[
                            _resumo_item(por_ref[ref], saldo[ref])
                            for ref in sorted(componente_itens)
                        ],
                        disputado_por=concorrentes,
                    )
                )
            for ref in componente_itens:
                saldo[ref] = 0.0
        visitados |= componente_linhas

    # --- sobras ---------------------------------------------------------------
    resolvidas_ids = {a.pedido_item_id for a in atribuicoes} | {
        am.pedido_item_id for am in ambiguidades
    }
    linhas_sem_fatura = [
        {
            "pedido_item_id": l.pedido_item_id,
            "linha": l.linha,
            "quantidade": l.quantidade,
            "unidade": l.unidade,
            "base": (l.base[0] if l.base else None),
        }
        for l in linhas
        if l.pedido_item_id not in resolvidas_ids
    ]

    refs_em_ambiguidade = {
        c["referencia"] for am in ambiguidades for c in am.candidatos
    }
    faturados_sem_pedido = [
        _resumo_item(i, saldo[i.referencia])
        for i in itens
        if not consumido_por[i.referencia] and i.referencia not in refs_em_ambiguidade
    ]

    return ResultadoCorrelacao(
        atribuicoes=atribuicoes,
        ambiguidades=ambiguidades,
        linhas_sem_fatura=linhas_sem_fatura,
        faturados_sem_pedido=faturados_sem_pedido,
    )


def _resumo_item(item: ItemFaturado, saldo_atual: float) -> dict[str, Any]:
    base = item.base
    return {
        "referencia": item.referencia,
        "nfe_log_id": item.nfe_log_id,
        "n_item": item.n_item,
        "descricao": item.descricao,
        "codigo_produto": item.codigo_produto,
        "bitola_mm": item.bitola_mm,
        "marca": item.marca,
        "quantidade": item.quantidade,
        "unidade": item.unidade,
        "quantidade_base": (base[1] if base else None),
        "base": (base[0] if base else None),
        "saldo": saldo_atual,
    }
