"""Regras de negócio do Sistema de Marcação de Consultas.

A interface (Tkinter) só conversa com esta classe; ela valida os dados,
aplica as regras e acessa o banco. Erros de uso viram ValidacaoErro.
"""
import sqlite3
from datetime import date, datetime
from typing import Callable, Optional

import validacoes as v
from validacoes import ConflitoErro, NaoEncontradoErro, ValidacaoErro


class ClinicaService:
    def __init__(self, conexao: sqlite3.Connection,
                 agora: Callable[[], datetime] = datetime.now):
        self.db = conexao
        self._agora = agora  # injetável para facilitar os testes

    # ------------------------------------------------------------------
    # Pacientes
    # ------------------------------------------------------------------
    @staticmethod
    def _paciente_dict(linha: sqlite3.Row) -> dict:
        return {
            "id": linha["id"],
            "nome": linha["nome"],
            "cpf": v.formatar_cpf(linha["cpf"]),
            "telefone": v.formatar_telefone(linha["telefone"]),
            "data_nascimento": date.fromisoformat(linha["data_nascimento"]).strftime("%d/%m/%Y"),
        }

    def _dados_paciente(self, nome, cpf, telefone, nascimento):
        return (
            v.validar_nome(nome, "O nome do paciente"),
            v.validar_cpf(cpf),
            v.validar_telefone(telefone),
            v.validar_nascimento(nascimento, self._agora().date()).isoformat(),
        )

    def cadastrar_paciente(self, nome, cpf, telefone, nascimento) -> int:
        dados = self._dados_paciente(nome, cpf, telefone, nascimento)
        try:
            cur = self.db.execute(
                "INSERT INTO pacientes (nome, cpf, telefone, data_nascimento) VALUES (?,?,?,?)",
                dados,
            )
            self.db.commit()
        except sqlite3.IntegrityError:
            raise ConflitoErro("Já existe um paciente cadastrado com este CPF.")
        return cur.lastrowid

    def alterar_paciente(self, paciente_id, nome, cpf, telefone, nascimento) -> None:
        self.obter_paciente(paciente_id)
        dados = self._dados_paciente(nome, cpf, telefone, nascimento)
        try:
            self.db.execute(
                "UPDATE pacientes SET nome=?, cpf=?, telefone=?, data_nascimento=? WHERE id=?",
                (*dados, paciente_id),
            )
            self.db.commit()
        except sqlite3.IntegrityError:
            raise ConflitoErro("Já existe outro paciente cadastrado com este CPF.")

    def remover_paciente(self, paciente_id) -> None:
        self.obter_paciente(paciente_id)
        total = self.db.execute(
            "SELECT COUNT(*) FROM consultas WHERE paciente_id=?", (paciente_id,)
        ).fetchone()[0]
        if total:
            raise ValidacaoErro(
                "Não é possível remover o paciente: ele possui consultas registradas "
                "(o histórico de atendimentos deve ser preservado)."
            )
        self.db.execute("DELETE FROM pacientes WHERE id=?", (paciente_id,))
        self.db.commit()

    def obter_paciente(self, paciente_id) -> dict:
        if paciente_id in (None, ""):
            raise ValidacaoErro("Selecione um paciente.")
        linha = self.db.execute("SELECT * FROM pacientes WHERE id=?", (paciente_id,)).fetchone()
        if not linha:
            raise NaoEncontradoErro("Paciente não encontrado.")
        return self._paciente_dict(linha)

    def listar_pacientes(self, busca: str = "") -> list[dict]:
        """Lista pacientes; 'busca' procura por código, nome ou CPF."""
        busca = (busca or "").strip()
        sql, params = "SELECT * FROM pacientes", []
        if busca:
            sql += " WHERE nome LIKE ? OR cpf LIKE ? OR CAST(id AS TEXT) = ?"
            digitos = v.apenas_digitos(busca)
            params = [f"%{busca}%", f"%{digitos}%" if digitos else "\0", busca]
        sql += " ORDER BY nome COLLATE NOCASE"
        return [self._paciente_dict(l) for l in self.db.execute(sql, params)]

    # ------------------------------------------------------------------
    # Profissionais
    # ------------------------------------------------------------------
    @staticmethod
    def _profissional_dict(linha: sqlite3.Row) -> dict:
        return {
            "id": linha["id"],
            "nome": linha["nome"],
            "especialidade": linha["especialidade"],
            "telefone": v.formatar_telefone(linha["telefone"]),
        }

    @staticmethod
    def _dados_profissional(nome, especialidade, telefone):
        return (
            v.validar_nome(nome, "O nome do profissional"),
            v.validar_especialidade(especialidade),
            v.validar_telefone(telefone),
        )

    def _checar_profissional_duplicado(self, nome, especialidade, ignorar_id=None) -> None:
        """Não permite dois profissionais com o mesmo nome E a mesma especialidade.

        A comparação ignora maiúsculas/minúsculas, acentos, espaços extras e título (Dr./Dra.).
        O mesmo nome com especialidade diferente é permitido.
        """
        igual = self.db.execute(
            "SELECT 1 FROM profissionais WHERE nome_chave=? AND especialidade_chave=? AND id<>?",
            (v.chave_nome_profissional(nome), v.chave_texto(especialidade),
             ignorar_id if ignorar_id is not None else -1),
        ).fetchone()
        if igual:
            raise ConflitoErro(
                "Já existe um profissional cadastrado com este nome e esta especialidade.")

    def cadastrar_profissional(self, nome, especialidade, telefone) -> int:
        nome, especialidade, telefone = self._dados_profissional(nome, especialidade, telefone)
        self._checar_profissional_duplicado(nome, especialidade)
        try:
            cur = self.db.execute(
                "INSERT INTO profissionais (nome, especialidade, telefone, nome_chave, "
                "especialidade_chave) VALUES (?,?,?,?,?)",
                (nome, especialidade, telefone, v.chave_nome_profissional(nome),
                 v.chave_texto(especialidade)),
            )
            self.db.commit()
        except sqlite3.IntegrityError:
            raise ConflitoErro(
                "Já existe um profissional cadastrado com este nome e esta especialidade.")
        return cur.lastrowid

    def alterar_profissional(self, profissional_id, nome, especialidade, telefone) -> None:
        self.obter_profissional(profissional_id)
        nome, especialidade, telefone = self._dados_profissional(nome, especialidade, telefone)
        self._checar_profissional_duplicado(nome, especialidade, ignorar_id=profissional_id)
        try:
            self.db.execute(
                "UPDATE profissionais SET nome=?, especialidade=?, telefone=?, nome_chave=?, "
                "especialidade_chave=? WHERE id=?",
                (nome, especialidade, telefone, v.chave_nome_profissional(nome),
                 v.chave_texto(especialidade), profissional_id),
            )
            self.db.commit()
        except sqlite3.IntegrityError:
            raise ConflitoErro(
                "Já existe um profissional cadastrado com este nome e esta especialidade.")

    def remover_profissional(self, profissional_id) -> None:
        self.obter_profissional(profissional_id)
        total = self.db.execute(
            "SELECT COUNT(*) FROM consultas WHERE profissional_id=?", (profissional_id,)
        ).fetchone()[0]
        if total:
            raise ValidacaoErro(
                "Não é possível remover o profissional: ele possui consultas registradas "
                "(o histórico de atendimentos deve ser preservado)."
            )
        self.db.execute("DELETE FROM profissionais WHERE id=?", (profissional_id,))
        self.db.commit()

    def obter_profissional(self, profissional_id) -> dict:
        if profissional_id in (None, ""):
            raise ValidacaoErro("Selecione um profissional.")
        linha = self.db.execute(
            "SELECT * FROM profissionais WHERE id=?", (profissional_id,)
        ).fetchone()
        if not linha:
            raise NaoEncontradoErro("Profissional não encontrado.")
        return self._profissional_dict(linha)

    def listar_profissionais(self, busca: str = "") -> list[dict]:
        """Lista profissionais; 'busca' procura por código, nome ou especialidade."""
        busca = (busca or "").strip()
        sql, params = "SELECT * FROM profissionais", []
        if busca:
            sql += " WHERE nome LIKE ? OR especialidade LIKE ? OR CAST(id AS TEXT) = ?"
            params = [f"%{busca}%", f"%{busca}%", busca]
        sql += " ORDER BY nome COLLATE NOCASE"
        return [self._profissional_dict(l) for l in self.db.execute(sql, params)]

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------
    _SELECT_CONSULTA = """
        SELECT c.*, p.nome AS paciente_nome, pr.nome AS profissional_nome
        FROM consultas c
        JOIN pacientes p ON p.id = c.paciente_id
        JOIN profissionais pr ON pr.id = c.profissional_id
    """

    @staticmethod
    def _consulta_dict(l: sqlite3.Row) -> dict:
        return {
            "id": l["id"],
            "paciente_id": l["paciente_id"],
            "paciente": l["paciente_nome"],
            "profissional_id": l["profissional_id"],
            "profissional": l["profissional_nome"],
            "especialidade": l["especialidade"],
            "data": date.fromisoformat(l["data"]).strftime("%d/%m/%Y"),
            "horario": l["horario"],
            "observacao": l["observacao"],
            "situacao": l["situacao"],
        }

    def obter_consulta(self, consulta_id) -> dict:
        if consulta_id in (None, ""):
            raise ValidacaoErro("Selecione uma consulta.")
        linha = self.db.execute(
            self._SELECT_CONSULTA + " WHERE c.id=?", (consulta_id,)
        ).fetchone()
        if not linha:
            raise NaoEncontradoErro("Consulta não encontrada.")
        return self._consulta_dict(linha)

    def _checar_conflitos(self, paciente_id, profissional_id, data_iso, horario,
                          ignorar_id: Optional[int] = None) -> None:
        ignorar = ignorar_id if ignorar_id is not None else -1
        if self.db.execute(
            "SELECT 1 FROM consultas WHERE profissional_id=? AND data=? AND horario=? "
            "AND situacao<>'Cancelada' AND id<>?",
            (profissional_id, data_iso, horario, ignorar),
        ).fetchone():
            raise ConflitoErro(
                "Não foi possível realizar o agendamento. Já existe uma consulta "
                "marcada para este profissional nesse horário."
            )
        if self.db.execute(
            "SELECT 1 FROM consultas WHERE paciente_id=? AND data=? AND horario=? "
            "AND situacao<>'Cancelada' AND id<>?",
            (paciente_id, data_iso, horario, ignorar),
        ).fetchone():
            raise ConflitoErro(
                "Não foi possível realizar o agendamento. Este paciente já possui "
                "outra consulta marcada nesse mesmo horário."
            )

    def _validar_consulta(self, paciente_id, profissional_id, data_txt, horario_txt,
                          situacao, consulta_atual: Optional[dict] = None):
        """Valida e devolve (paciente, profissional, data_iso, horario)."""
        if paciente_id in (None, ""):
            raise ValidacaoErro("Selecione um paciente para a consulta.")
        if profissional_id in (None, ""):
            raise ValidacaoErro("Selecione um profissional para a consulta.")
        paciente = self.obter_paciente(paciente_id)
        profissional = self.obter_profissional(profissional_id)
        v.validar_situacao(situacao)
        data_consulta = v.converter_data(data_txt, "A data da consulta")
        horario = v.converter_horario(horario_txt).strftime("%H:%M")

        if situacao == "Agendada":
            mudou = (
                consulta_atual is None
                or consulta_atual["data"] != data_consulta.strftime("%d/%m/%Y")
                or consulta_atual["horario"] != horario
                or consulta_atual["situacao"] != "Agendada"
            )
            if mudou:  # alterar só a observação de algo já marcado não revalida a data
                v.validar_data_consulta(
                    data_consulta, datetime.strptime(horario, "%H:%M").time(), self._agora()
                )
            self._checar_conflitos(
                paciente_id, profissional_id, data_consulta.isoformat(), horario,
                ignorar_id=consulta_atual["id"] if consulta_atual else None,
            )
        return paciente, profissional, data_consulta.isoformat(), horario

    def agendar_consulta(self, paciente_id, profissional_id, data, horario,
                         observacao: str = "") -> int:
        paciente, profissional, data_iso, hora = self._validar_consulta(
            paciente_id, profissional_id, data, horario, "Agendada"
        )
        observacao = (observacao or "").strip()
        if len(observacao) > 300:
            raise ValidacaoErro("A observação deve ter no máximo 300 caracteres.")
        try:
            cur = self.db.execute(
                "INSERT INTO consultas (paciente_id, profissional_id, especialidade, data, "
                "horario, observacao, situacao) VALUES (?,?,?,?,?,?, 'Agendada')",
                (paciente["id"], profissional["id"], profissional["especialidade"],
                 data_iso, hora, observacao),
            )
            self.db.commit()
        except sqlite3.IntegrityError:
            raise ConflitoErro(
                "Não foi possível realizar o agendamento. Já existe uma consulta "
                "marcada para este horário."
            )
        return cur.lastrowid

    def alterar_consulta(self, consulta_id, paciente_id, profissional_id, data, horario,
                         observacao: str = "", situacao: str = "Agendada") -> None:
        atual = self.obter_consulta(consulta_id)
        if atual["situacao"] == "Cancelada" and situacao == "Cancelada":
            raise ValidacaoErro(
                "Esta consulta está cancelada e não pode ser alterada. "
                "Para remarcar, faça um novo agendamento."
            )
        paciente, profissional, data_iso, hora = self._validar_consulta(
            paciente_id, profissional_id, data, horario, situacao, consulta_atual=atual
        )
        observacao = (observacao or "").strip()
        if len(observacao) > 300:
            raise ValidacaoErro("A observação deve ter no máximo 300 caracteres.")
        try:
            self.db.execute(
                "UPDATE consultas SET paciente_id=?, profissional_id=?, especialidade=?, "
                "data=?, horario=?, observacao=?, situacao=? WHERE id=?",
                (paciente["id"], profissional["id"], profissional["especialidade"],
                 data_iso, hora, observacao, situacao, consulta_id),
            )
            self.db.commit()
        except sqlite3.IntegrityError:
            raise ConflitoErro(
                "Não foi possível alterar a consulta. Já existe uma consulta "
                "marcada para este horário."
            )

    def alterar_situacao(self, consulta_id, nova_situacao: str) -> None:
        """Muda só a situação (Agendada / Realizada / Cancelada), mantendo os demais dados."""
        atual = self.obter_consulta(consulta_id)
        v.validar_situacao(nova_situacao)
        if atual["situacao"] == nova_situacao:
            raise ValidacaoErro(f"A consulta já está com a situação '{nova_situacao}'.")
        if nova_situacao == "Agendada":
            self._validar_consulta(
                atual["paciente_id"], atual["profissional_id"], atual["data"],
                atual["horario"], "Agendada", consulta_atual=atual,
            )
        self.db.execute("UPDATE consultas SET situacao=? WHERE id=?", (nova_situacao, consulta_id))
        self.db.commit()

    def cancelar_consulta(self, consulta_id) -> None:
        """Cancela mantendo o registro (histórico) e liberando o horário."""
        atual = self.obter_consulta(consulta_id)
        if atual["situacao"] == "Cancelada":
            raise ValidacaoErro("Esta consulta já está cancelada.")
        if atual["situacao"] == "Realizada":
            raise ValidacaoErro("Não é possível cancelar uma consulta que já foi realizada.")
        self.alterar_situacao(consulta_id, "Cancelada")

    def pesquisar_consultas(self, paciente: str = "", profissional: str = "", data: str = "",
                            especialidade: str = "", situacao: str = "") -> list[dict]:
        """Lista consultas aplicando (em conjunto) os filtros informados."""
        where, params = [], []
        if (paciente or "").strip():
            where.append("p.nome LIKE ?")
            params.append(f"%{paciente.strip()}%")
        if (profissional or "").strip():
            where.append("pr.nome LIKE ?")
            params.append(f"%{profissional.strip()}%")
        if (data or "").strip():
            where.append("c.data = ?")
            params.append(v.converter_data(data, "A data de pesquisa").isoformat())
        if (especialidade or "").strip():
            where.append("c.especialidade LIKE ?")
            params.append(f"%{especialidade.strip()}%")
        if (situacao or "").strip():
            where.append("c.situacao = ?")
            params.append(v.validar_situacao(situacao.strip()))
        sql = self._SELECT_CONSULTA
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY c.data, c.horario, c.id"
        return [self._consulta_dict(l) for l in self.db.execute(sql, params)]

    def horarios_livres(self, profissional_id, data: str) -> list[str]:
        """Horários da grade ainda livres para o profissional na data informada."""
        self.obter_profissional(profissional_id)
        data_iso = v.converter_data(data, "A data").isoformat()
        ocupados = {
            l[0] for l in self.db.execute(
                "SELECT horario FROM consultas WHERE profissional_id=? AND data=? "
                "AND situacao<>'Cancelada'", (profissional_id, data_iso))
        }
        return [h for h in v.horarios_disponiveis_na_grade() if h not in ocupados]

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------
    def resumo(self) -> dict:
        """Totais para o painel inicial (calculados no banco)."""
        def total(sql, *params):
            return self.db.execute(sql, params).fetchone()[0]

        hoje = self._agora().date().isoformat()
        return {
            "pacientes": total("SELECT COUNT(*) FROM pacientes"),
            "profissionais": total("SELECT COUNT(*) FROM profissionais"),
            "consultas": total("SELECT COUNT(*) FROM consultas"),
            "agendadas": total("SELECT COUNT(*) FROM consultas WHERE situacao='Agendada'"),
            "realizadas": total("SELECT COUNT(*) FROM consultas WHERE situacao='Realizada'"),
            "canceladas": total("SELECT COUNT(*) FROM consultas WHERE situacao='Cancelada'"),
            "hoje": total("SELECT COUNT(*) FROM consultas WHERE data=? AND situacao='Agendada'", hoje),
        }
