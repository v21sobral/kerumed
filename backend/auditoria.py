"""Registro de auditoria: quem fez o quê e quando (somente inclusão).

Toda criação, alteração, remoção, cancelamento, mudança de situação de consulta e
operação de usuários concluída com sucesso gera um registro. Os registros não podem
ser editados nem apagados (nem pela API, nem pelo banco: há triggers).
"""
import json
import math
from datetime import datetime

import validacoes as v
from validacoes import ValidacaoErro

ACOES = {
    "criar": "Cadastro", "alterar": "Alteração", "remover": "Remoção",
    "cancelar": "Cancelamento", "situacao": "Mudança de situação", "senha": "Troca de senha",
}
ENTIDADES = {"paciente": "Paciente", "profissional": "Profissional", "consulta": "Consulta", "usuario": "Usuário"}
ROTULOS = {
    "nome": "Nome", "cpf": "CPF", "telefone": "Telefone", "data_nascimento": "Nascimento",
    "especialidade": "Especialidade", "paciente": "Paciente", "profissional": "Profissional",
    "data": "Data", "horario": "Horário", "observacao": "Observação", "situacao": "Situação",
    "usuario": "Usuário", "perfil_rotulo": "Perfil",
}
POR_PAGINA_PADRAO, POR_PAGINA_MAX = 20, 100


def _vazio(valor) -> str:
    return "(vazio)" if valor in (None, "") else str(valor)


def diferencas(antes: dict, depois: dict) -> dict:
    """Campos que mudaram: {campo: [valor_antes, valor_depois]}."""
    return {c: [antes.get(c), depois.get(c)] for c in depois if antes.get(c) != depois.get(c)}


def registrar(conexao, usuario: dict, acao: str, entidade: str, registro_id, descricao: str,
              quando: datetime, antes: dict = None, depois: dict = None, campos=()):
    """Grava um registro. 'antes'/'depois' são os dados do item (dicionários) e 'campos' diz
    quais campos interessam. Alteração sem nenhuma mudança real não gera registro."""
    detalhes = None
    if antes is not None and depois is not None:
        dif = {c: par for c, par in diferencas(
            {c: antes.get(c) for c in campos}, {c: depois.get(c) for c in campos}).items()}
        if not dif and acao in ("alterar", "situacao"):
            return None
        detalhes = {"alteracoes": dif}
    elif depois is not None:
        detalhes = {"dados": {c: depois.get(c) for c in campos}}
    elif antes is not None:
        detalhes = {"dados": {c: antes.get(c) for c in campos}}
    cur = conexao.execute(
        "INSERT INTO auditoria (data_hora, usuario_id, usuario, nome, perfil, acao, entidade, "
        "registro_id, descricao, detalhes) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (quando.strftime("%Y-%m-%d %H:%M:%S"), usuario["id"], usuario["usuario"], usuario["nome"],
         usuario["perfil"], acao, entidade, registro_id, descricao,
         json.dumps(detalhes, ensure_ascii=False) if detalhes else None))
    conexao.commit()
    return cur.lastrowid


def _linhas_detalhe(detalhes_json) -> list[str]:
    if not detalhes_json:
        return []
    detalhes = json.loads(detalhes_json)
    if "alteracoes" in detalhes:
        return [f"{ROTULOS.get(c, c)}: {_vazio(a)} → {_vazio(b)}" for c, (a, b) in detalhes["alteracoes"].items()]
    return [f"{ROTULOS.get(c, c)}: {_vazio(x)}" for c, x in detalhes.get("dados", {}).items()]


def _para_dict(l) -> dict:
    return {
        "id": l["id"],
        "data_hora": datetime.strptime(l["data_hora"], "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y %H:%M:%S"),
        "usuario_id": l["usuario_id"], "usuario": l["usuario"], "nome": l["nome"],
        "perfil": l["perfil"], "acao": l["acao"], "acao_rotulo": ACOES.get(l["acao"], l["acao"]),
        "entidade": l["entidade"], "entidade_rotulo": ENTIDADES.get(l["entidade"], l["entidade"]),
        "registro_id": l["registro_id"], "descricao": l["descricao"],
        "detalhes": _linhas_detalhe(l["detalhes"]),
    }


def _inteiro(valor, padrao: int, minimo: int, maximo: int) -> int:
    try:
        return max(minimo, min(maximo, int(valor)))
    except (TypeError, ValueError):
        return padrao


def listar(conexao, usuario="", entidade="", acao="", data_inicial="", data_final="",
           pagina=1, por_pagina=POR_PAGINA_PADRAO) -> dict:
    """Consulta paginada, do registro mais recente para o mais antigo."""
    onde, params = [], []
    if (usuario or "").strip():
        onde.append("(usuario LIKE ? OR nome LIKE ?)")
        params += [f"%{usuario.strip()}%"] * 2
    if (entidade or "").strip():
        if entidade not in ENTIDADES:
            raise ValidacaoErro("Tipo de registro inválido para o filtro.")
        onde.append("entidade = ?")
        params.append(entidade)
    if (acao or "").strip():
        if acao not in ACOES:
            raise ValidacaoErro("Ação inválida para o filtro.")
        onde.append("acao = ?")
        params.append(acao)
    inicio = fim = None
    if (data_inicial or "").strip():
        inicio = v.converter_data(data_inicial, "A data inicial")
        onde.append("data_hora >= ?")
        params.append(f"{inicio.isoformat()} 00:00:00")
    if (data_final or "").strip():
        fim = v.converter_data(data_final, "A data final")
        onde.append("data_hora <= ?")
        params.append(f"{fim.isoformat()} 23:59:59")
    if inicio and fim and inicio > fim:
        raise ValidacaoErro("A data inicial não pode ser posterior à data final.")

    filtro = (" WHERE " + " AND ".join(onde)) if onde else ""
    total = conexao.execute(f"SELECT COUNT(*) FROM auditoria{filtro}", params).fetchone()[0]
    por_pagina = _inteiro(por_pagina, POR_PAGINA_PADRAO, 1, POR_PAGINA_MAX)
    paginas = max(1, math.ceil(total / por_pagina))
    pagina = _inteiro(pagina, 1, 1, paginas)
    linhas = conexao.execute(
        f"SELECT * FROM auditoria{filtro} ORDER BY data_hora DESC, id DESC LIMIT ? OFFSET ?",
        [*params, por_pagina, (pagina - 1) * por_pagina]).fetchall()
    return {"registros": [_para_dict(l) for l in linhas], "total": total,
            "pagina": pagina, "paginas": paginas, "por_pagina": por_pagina}
