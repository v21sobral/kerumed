"""Testes automatizados das regras de negócio (rodam sem interface gráfica).

Execute, a partir da pasta 01_Sistema:
    python -m unittest discover -s testes -v
"""
import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import banco
from servicos import ClinicaService
from validacoes import ConflitoErro, ValidacaoErro

AGORA = datetime(2026, 11, 10, 9, 0)   # terça-feira, "hoje" fixo dos testes
SEGUNDA, TERCA, QUARTA = "16/11/2026", "17/11/2026", "18/11/2026"
SABADO, DOMINGO = "21/11/2026", "22/11/2026"


class BaseTeste(unittest.TestCase):
    def setUp(self):
        self.s = ClinicaService(banco.conectar(":memory:"), agora=lambda: AGORA)
        self.maria = self.s.cadastrar_paciente("Maria Santos", "123.456.789-00", "71999999999", "10/05/1990")
        self.ana = self.s.cadastrar_paciente("Ana Souza", "98765432100", "7133334444", "01/02/1985")
        self.dr_joao = self.s.cadastrar_profissional("Dr. João Lima", "Cardiologia", "71988887777")
        self.dra_bia = self.s.cadastrar_profissional("Dra. Bia Rocha", "Pediatria", "71977776666")

    def erro(self, funcao, *args, **kwargs):
        with self.assertRaises(ValidacaoErro) as ctx:
            funcao(*args, **kwargs)
        return str(ctx.exception)


class TestPacientes(BaseTeste):
    def test_cadastrar_e_listar(self):
        pacientes = self.s.listar_pacientes()
        self.assertEqual([p["nome"] for p in pacientes], ["Ana Souza", "Maria Santos"])
        maria = self.s.obter_paciente(self.maria)
        self.assertEqual(maria["cpf"], "123.456.789-00")
        self.assertEqual(maria["telefone"], "(71) 99999-9999")
        self.assertEqual(maria["data_nascimento"], "10/05/1990")

    def test_nome_vazio(self):
        msg = self.erro(self.s.cadastrar_paciente, "  ", "11122233344", "71999999999", "10/05/1990")
        self.assertIn("nome", msg.lower())

    def test_cpf_vazio_e_invalido(self):
        self.assertIn("CPF", self.erro(self.s.cadastrar_paciente, "Fulano", "", "71999999999", "10/05/1990"))
        self.assertIn("CPF", self.erro(self.s.cadastrar_paciente, "Fulano", "123", "71999999999", "10/05/1990"))

    def test_telefone_vazio_e_invalido(self):
        self.assertIn("telefone", self.erro(self.s.cadastrar_paciente, "Fulano", "11122233344", "", "10/05/1990").lower())
        self.assertIn("telefone", self.erro(self.s.cadastrar_paciente, "Fulano", "11122233344", "123", "10/05/1990").lower())

    def test_nascimento_invalido_e_futuro(self):
        self.erro(self.s.cadastrar_paciente, "Fulano", "11122233344", "71999999999", "31/02/1990")
        self.erro(self.s.cadastrar_paciente, "Fulano", "11122233344", "71999999999", "01/01/2030")
        self.erro(self.s.cadastrar_paciente, "Fulano", "11122233344", "71999999999", "")

    def test_cpf_duplicado(self):
        msg = self.erro(self.s.cadastrar_paciente, "Outra Maria", "12345678900", "71999999999", "10/05/1990")
        self.assertIn("CPF", msg)

    def test_alterar_paciente(self):
        self.s.alterar_paciente(self.maria, "Maria S. Santos", "12345678900", "71911112222", "10/05/1990")
        self.assertEqual(self.s.obter_paciente(self.maria)["nome"], "Maria S. Santos")

    def test_alterar_paciente_com_cpf_de_outro(self):
        self.erro(self.s.alterar_paciente, self.maria, "Maria", "98765432100", "71911112222", "10/05/1990")

    def test_pesquisar_paciente(self):
        self.assertEqual(len(self.s.listar_pacientes("maria")), 1)
        self.assertEqual(len(self.s.listar_pacientes("987.654")), 1)
        self.assertEqual(len(self.s.listar_pacientes("zzz")), 0)

    def test_remover_paciente_sem_consultas(self):
        self.s.remover_paciente(self.ana)
        self.assertEqual(len(self.s.listar_pacientes()), 1)

    def test_remover_paciente_com_consulta_e_bloqueado(self):
        self.s.agendar_consulta(self.maria, self.dr_joao, SEGUNDA, "14:00")
        self.assertIn("consultas", self.erro(self.s.remover_paciente, self.maria))


class TestProfissionais(BaseTeste):
    def test_cadastrar_listar_pesquisar(self):
        self.assertEqual(len(self.s.listar_profissionais()), 2)
        self.assertEqual(self.s.listar_profissionais("cardio")[0]["nome"], "Dr. João Lima")

    def test_campos_obrigatorios(self):
        self.erro(self.s.cadastrar_profissional, "", "Cardiologia", "71988887777")
        self.erro(self.s.cadastrar_profissional, "Dr. X", "", "71988887777")
        self.erro(self.s.cadastrar_profissional, "Dr. X", "Cardiologia", "")

    def test_alterar_e_remover(self):
        self.s.alterar_profissional(self.dr_joao, "Dr. João L. Lima", "Clínico Geral", "71988887777")
        self.assertEqual(self.s.obter_profissional(self.dr_joao)["especialidade"], "Clínico Geral")
        self.s.remover_profissional(self.dr_joao)
        self.assertEqual(len(self.s.listar_profissionais()), 1)

    def test_remover_profissional_com_consulta_e_bloqueado(self):
        self.s.agendar_consulta(self.maria, self.dr_joao, SEGUNDA, "14:00")
        self.erro(self.s.remover_profissional, self.dr_joao)


class TestMarcacao(BaseTeste):
    def test_agendar_com_sucesso(self):
        cid = self.s.agendar_consulta(self.maria, self.dr_joao, SEGUNDA, "14:00", "Primeira consulta")
        c = self.s.obter_consulta(cid)
        self.assertEqual(c["situacao"], "Agendada")
        self.assertEqual(c["especialidade"], "Cardiologia")   # vem do profissional
        self.assertEqual((c["data"], c["horario"]), (SEGUNDA, "14:00"))

    def test_sem_paciente_ou_profissional(self):
        self.assertIn("paciente", self.erro(self.s.agendar_consulta, None, self.dr_joao, SEGUNDA, "14:00"))
        self.assertIn("profissional", self.erro(self.s.agendar_consulta, self.maria, "", SEGUNDA, "14:00"))

    def test_sem_data_ou_horario(self):
        self.erro(self.s.agendar_consulta, self.maria, self.dr_joao, "", "14:00")
        self.erro(self.s.agendar_consulta, self.maria, self.dr_joao, SEGUNDA, "")

    def test_datas_e_horarios_invalidos(self):
        self.erro(self.s.agendar_consulta, self.maria, self.dr_joao, "32/13/2026", "14:00")
        self.erro(self.s.agendar_consulta, self.maria, self.dr_joao, SEGUNDA, "25:00")
        self.erro(self.s.agendar_consulta, self.maria, self.dr_joao, SEGUNDA, "14:10")   # fora da grade de 30 min
        self.erro(self.s.agendar_consulta, self.maria, self.dr_joao, SEGUNDA, "07:30")   # antes da abertura
        self.erro(self.s.agendar_consulta, self.maria, self.dr_joao, SEGUNDA, "18:00")   # depois do último horário

    def test_data_passada_e_fim_de_semana(self):
        self.assertIn("passou", self.erro(self.s.agendar_consulta, self.maria, self.dr_joao, "09/11/2026", "14:00"))
        self.assertIn("passou", self.erro(self.s.agendar_consulta, self.maria, self.dr_joao, "10/11/2026", "08:30"))
        self.assertIn("sábados", self.erro(self.s.agendar_consulta, self.maria, self.dr_joao, SABADO, "14:00"))
        self.erro(self.s.agendar_consulta, self.maria, self.dr_joao, DOMINGO, "14:00")

    def test_data_muito_distante(self):
        self.erro(self.s.agendar_consulta, self.maria, self.dr_joao, "16/11/2028", "14:00")

    def test_conflito_de_horario_do_profissional(self):
        self.s.agendar_consulta(self.maria, self.dr_joao, SEGUNDA, "14:00")
        msg = self.erro(self.s.agendar_consulta, self.ana, self.dr_joao, SEGUNDA, "14:00")
        self.assertIn("Já existe uma consulta marcada para este profissional", msg)
        self.assertEqual(len(self.s.pesquisar_consultas()), 1)

    def test_paciente_nao_pode_ter_duas_consultas_no_mesmo_horario(self):
        self.s.agendar_consulta(self.ana, self.dr_joao, SEGUNDA, "14:00")
        msg = self.erro(self.s.agendar_consulta, self.ana, self.dra_bia, SEGUNDA, "14:00")
        self.assertIn("paciente", msg)

    def test_mesmo_horario_com_outro_profissional_e_permitido(self):
        self.s.agendar_consulta(self.maria, self.dr_joao, SEGUNDA, "14:00")
        self.s.agendar_consulta(self.ana, self.dra_bia, SEGUNDA, "14:00")
        self.assertEqual(len(self.s.pesquisar_consultas()), 2)

    def test_horarios_livres(self):
        self.s.agendar_consulta(self.maria, self.dr_joao, SEGUNDA, "14:00")
        livres = self.s.horarios_livres(self.dr_joao, SEGUNDA)
        self.assertNotIn("14:00", livres)
        self.assertIn("14:30", livres)
        self.assertIn("14:00", self.s.horarios_livres(self.dra_bia, SEGUNDA))


class TestAlteracaoECancelamento(BaseTeste):
    def setUp(self):
        super().setUp()
        self.cid = self.s.agendar_consulta(self.maria, self.dr_joao, SEGUNDA, "14:00")

    def alterar(self, data, horario, **kw):
        self.s.alterar_consulta(self.cid, self.maria, self.dr_joao, data, horario, **kw)

    def test_alterar_data_e_horario(self):
        self.alterar(TERCA, "15:00", observacao="Remarcada")
        c = self.s.obter_consulta(self.cid)
        self.assertEqual((c["data"], c["horario"], c["observacao"]), (TERCA, "15:00", "Remarcada"))

    def test_alterar_para_horario_ocupado(self):
        self.s.agendar_consulta(self.ana, self.dr_joao, TERCA, "15:00")
        self.assertIn("Já existe", self.erro(self.alterar, TERCA, "15:00"))

    def test_alterar_mantendo_horario_nao_conflita_consigo_mesma(self):
        self.alterar(SEGUNDA, "14:00", observacao="Só a observação mudou")
        self.assertEqual(self.s.obter_consulta(self.cid)["observacao"], "Só a observação mudou")

    def test_alterar_para_data_invalida(self):
        self.erro(self.alterar, "09/11/2026", "14:00")
        self.erro(self.alterar, SEGUNDA, "")

    def test_cancelar_mantem_registro(self):
        self.s.cancelar_consulta(self.cid)
        c = self.s.obter_consulta(self.cid)
        self.assertEqual(c["situacao"], "Cancelada")
        self.assertEqual(len(self.s.pesquisar_consultas(situacao="Cancelada")), 1)

    def test_cancelar_libera_o_horario(self):
        self.s.cancelar_consulta(self.cid)
        self.s.agendar_consulta(self.ana, self.dr_joao, SEGUNDA, "14:00")   # agora é possível

    def test_cancelar_duas_vezes_e_alterar_cancelada(self):
        self.s.cancelar_consulta(self.cid)
        self.assertIn("já está cancelada", self.erro(self.s.cancelar_consulta, self.cid))
        self.erro(self.alterar, TERCA, "10:00", situacao="Cancelada")

    def test_nao_cancela_realizada(self):
        self.s.alterar_situacao(self.cid, "Realizada")
        self.assertIn("realizada", self.erro(self.s.cancelar_consulta, self.cid))

    def test_situacoes(self):
        self.s.alterar_situacao(self.cid, "Realizada")
        self.assertEqual(self.s.obter_consulta(self.cid)["situacao"], "Realizada")
        self.erro(self.s.alterar_situacao, self.cid, "Realizada")      # já estava
        self.erro(self.s.alterar_situacao, self.cid, "Inexistente")    # situação inválida

    def test_reativar_cancelada_respeita_conflito(self):
        self.s.cancelar_consulta(self.cid)
        self.s.agendar_consulta(self.ana, self.dr_joao, SEGUNDA, "14:00")  # ocupa o horário liberado
        self.assertIn("Já existe", self.erro(self.s.alterar_situacao, self.cid, "Agendada"))


class TestPesquisa(BaseTeste):
    def setUp(self):
        super().setUp()
        self.c1 = self.s.agendar_consulta(self.maria, self.dr_joao, SEGUNDA, "09:00")
        self.c2 = self.s.agendar_consulta(self.ana, self.dra_bia, TERCA, "10:00")
        self.c3 = self.s.agendar_consulta(self.maria, self.dra_bia, QUARTA, "11:00")
        self.s.cancelar_consulta(self.c3)

    def ids(self, **filtros):
        return [c["id"] for c in self.s.pesquisar_consultas(**filtros)]

    def test_sem_filtro_lista_tudo_ordenado(self):
        self.assertEqual(self.ids(), [self.c1, self.c2, self.c3])

    def test_por_cada_criterio(self):
        self.assertEqual(self.ids(paciente="ana"), [self.c2])
        self.assertEqual(self.ids(profissional="joão"), [self.c1])
        self.assertEqual(self.ids(data=TERCA), [self.c2])
        self.assertEqual(self.ids(especialidade="pedia"), [self.c2, self.c3])
        self.assertEqual(self.ids(situacao="Cancelada"), [self.c3])

    def test_filtros_combinados_e_sem_resultado(self):
        self.assertEqual(self.ids(paciente="maria", especialidade="Pediatria"), [self.c3])
        self.assertEqual(self.ids(paciente="zzz"), [])

    def test_filtro_invalido(self):
        self.erro(self.s.pesquisar_consultas, data="31/31/2026")
        self.erro(self.s.pesquisar_consultas, situacao="Qualquer")


class TestProfissionalDuplicado(BaseTeste):
    MSG = "Já existe um profissional cadastrado com este nome e esta especialidade."

    def cadastrar(self, nome, esp, tel="71955554444"):
        return self.s.cadastrar_profissional(nome, esp, tel)

    def test_mesmo_nome_e_mesma_especialidade_e_bloqueado(self):
        with self.assertRaises(ConflitoErro) as ctx:
            self.cadastrar("Dr. João Lima", "Cardiologia")
        self.assertEqual(str(ctx.exception), self.MSG)
        self.assertEqual(len(self.s.listar_profissionais()), 2)

    def test_variacoes_de_escrita_tambem_sao_duplicados(self):
        for nome, esp in [("dr. joao lima", "cardiologia"), ("  DR.  JOÃO   LIMA ", "CARDIOLOGIA"),
                          ("João Lima", "Cardiologia"), ("Dra. Joao Lima", "Cardiología"),
                          ("Doutor João Lima", "  Cardiologia  ")]:
            with self.assertRaises(ConflitoErro, msg=f"{nome} / {esp}"):
                self.cadastrar(nome, esp)

    def test_mesmo_nome_com_outra_especialidade_e_permitido(self):
        self.cadastrar("Dr. João Lima", "Clínico Geral")
        self.assertEqual(len(self.s.listar_profissionais("João")), 2)

    def test_outro_nome_na_mesma_especialidade_e_permitido(self):
        self.cadastrar("Dr. Paulo Mendes", "Cardiologia")
        self.assertEqual(len(self.s.listar_profissionais("Cardiologia")), 2)

    def test_alterar_para_ficar_igual_a_outro_e_bloqueado(self):
        with self.assertRaises(ConflitoErro) as ctx:
            self.s.alterar_profissional(self.dra_bia, "Dr. João Lima", "Cardiologia", "71977776666")
        self.assertEqual(str(ctx.exception), self.MSG)
        self.assertEqual(self.s.obter_profissional(self.dra_bia)["nome"], "Dra. Bia Rocha")   # nada mudou

    def test_alterar_sem_mudar_nome_e_especialidade_e_permitido(self):
        self.s.alterar_profissional(self.dr_joao, "Dr. João Lima", "Cardiologia", "71911112222")
        self.assertEqual(self.s.obter_profissional(self.dr_joao)["telefone"], "(71) 91111-2222")
        self.s.alterar_profissional(self.dr_joao, "DR. JOÃO LIMA", "cardiologia", "71911112222")  # só a grafia

    def test_alterar_especialidade_para_outra_livre_e_permitido(self):
        self.s.alterar_profissional(self.dra_bia, "Dr. João Lima", "Pediatria", "71977776666")

    def test_remover_libera_o_cadastro_novamente(self):
        self.s.remover_profissional(self.dr_joao)
        self.cadastrar("Dr. João Lima", "Cardiologia")

    def test_banco_antigo_sem_colunas_e_com_duplicados_e_migrado(self):
        import sqlite3
        import tempfile
        pasta = tempfile.TemporaryDirectory()
        caminho = os.path.join(pasta.name, "antigo.db")
        bruto = sqlite3.connect(caminho)
        bruto.executescript("""
            CREATE TABLE profissionais (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL,
                especialidade TEXT NOT NULL, telefone TEXT NOT NULL);
            INSERT INTO profissionais (nome, especialidade, telefone) VALUES
                ('Dr. Ana Dias', 'Pediatria', '71999990000'), ('ana dias', 'pediatria', '71999990001');
        """)
        bruto.commit(); bruto.close()
        conexao = banco.conectar(caminho)                       # não pode quebrar com duplicados antigos
        service = ClinicaService(conexao, agora=lambda: AGORA)
        self.assertEqual(len(service.listar_profissionais()), 2)
        with self.assertRaises(ConflitoErro):                   # mas novos duplicados continuam barrados
            service.cadastrar_profissional("DRA. ANA DIAS", "Pediatria", "71999990002")
        service.cadastrar_profissional("Dra. Ana Dias", "Dermatologia", "71999990002")
        conexao.close(); pasta.cleanup()


if __name__ == "__main__":
    unittest.main(verbosity=2)
