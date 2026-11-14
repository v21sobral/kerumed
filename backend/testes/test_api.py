"""Testes da API REST (usam o cliente de testes do Flask e um banco temporário).

Execute, a partir da pasta backend:
    python -m unittest discover -s testes -v
"""
import os
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import create_app

AGORA = datetime(2026, 11, 10, 9, 0)   # terça-feira fixa para os testes
SEGUNDA, TERCA = "16/11/2026", "17/11/2026"


class BaseApi(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.app = create_app(os.path.join(self.pasta.name, "teste.db"), agora=lambda: AGORA,
                              chave_secreta="chave-de-teste", metodo_hash="pbkdf2:sha256:1000")
        self.anonimo = self.app.test_client()          # cliente sem login
        self.c = self.app.test_client()                # cliente autenticado
        token = self.anonimo.post("/api/login", json={"usuario": "admin", "senha": "admin123"}).json["token"]
        self.c.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        self.maria = self.post("/api/pacientes", nome="Maria Santos", cpf="123.456.789-00",
                               telefone="71999999999", data_nascimento="10/05/1990").json["paciente"]["id"]
        self.ana = self.post("/api/pacientes", nome="Ana Souza", cpf="98765432100",
                             telefone="7133334444", data_nascimento="01/02/1985").json["paciente"]["id"]
        self.joao = self.post("/api/profissionais", nome="Dr. João", especialidade="Cardiologia",
                              telefone="71988887777").json["profissional"]["id"]

    def tearDown(self):
        self.pasta.cleanup()

    def post(self, url, **corpo):
        return self.c.post(url, json=corpo)

    def agendar(self, paciente, data=SEGUNDA, horario="14:00", **extra):
        return self.post("/api/consultas", paciente_id=paciente, profissional_id=self.joao,
                         data=data, horario=horario, **extra)


class TestPacientesApi(BaseApi):
    def test_cadastro_e_listagem(self):
        r = self.c.get("/api/pacientes")
        self.assertEqual(r.status_code, 200)
        self.assertEqual([p["nome"] for p in r.json], ["Ana Souza", "Maria Santos"])

    def test_cadastro_retorna_201_e_mensagem(self):
        r = self.post("/api/pacientes", nome="Carlos Lima", cpf="11122233344",
                      telefone="71988887777", data_nascimento="23/11/2001")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json["mensagem"], "Paciente cadastrado com sucesso!")

    def test_nome_vazio_retorna_400(self):
        r = self.post("/api/pacientes", nome="", cpf="11122233344",
                      telefone="71988887777", data_nascimento="23/11/2001")
        self.assertEqual(r.status_code, 400)
        self.assertIn("nome", r.json["erro"].lower())

    def test_cpf_duplicado_retorna_409(self):
        r = self.post("/api/pacientes", nome="Outra", cpf="12345678900",
                      telefone="71988887777", data_nascimento="23/11/2001")
        self.assertEqual(r.status_code, 409)

    def test_corpo_invalido_retorna_400(self):
        r = self.c.post("/api/pacientes", data="isto não é json", content_type="text/plain")
        self.assertEqual(r.status_code, 400)

    def test_pesquisa_alteracao_e_remocao(self):
        self.assertEqual(len(self.c.get("/api/pacientes?busca=maria").json), 1)
        r = self.c.put(f"/api/pacientes/{self.ana}", json=dict(
            nome="Ana S. Souza", cpf="98765432100", telefone="7133334444", data_nascimento="01/02/1985"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json["paciente"]["nome"], "Ana S. Souza")
        self.assertEqual(self.c.delete(f"/api/pacientes/{self.ana}").status_code, 200)
        self.assertEqual(self.c.get(f"/api/pacientes/{self.ana}").status_code, 404)

    def test_remover_paciente_com_consulta_retorna_400(self):
        self.agendar(self.maria)
        self.assertEqual(self.c.delete(f"/api/pacientes/{self.maria}").status_code, 400)


class TestProfissionaisApi(BaseApi):
    def test_crud(self):
        self.assertEqual(self.c.get("/api/profissionais?busca=cardio").json[0]["nome"], "Dr. João")
        r = self.c.put(f"/api/profissionais/{self.joao}", json=dict(
            nome="Dr. João L.", especialidade="Clínico Geral", telefone="71988887777"))
        self.assertEqual(r.json["profissional"]["especialidade"], "Clínico Geral")
        self.assertEqual(self.post("/api/profissionais", nome="", especialidade="X",
                                   telefone="71988887777").status_code, 400)
        self.assertEqual(self.c.delete(f"/api/profissionais/{self.joao}").status_code, 200)


class TestConsultasApi(BaseApi):
    def test_agendar(self):
        r = self.agendar(self.maria, observacao="Primeira consulta")
        self.assertEqual(r.status_code, 201)
        c = r.json["consulta"]
        self.assertEqual((c["situacao"], c["especialidade"]), ("Agendada", "Cardiologia"))

    def test_sem_paciente_retorna_400(self):
        r = self.post("/api/consultas", profissional_id=self.joao, data=SEGUNDA, horario="14:00")
        self.assertEqual(r.status_code, 400)
        self.assertIn("paciente", r.json["erro"])

    def test_conflito_de_horario_retorna_409(self):
        self.agendar(self.maria)
        r = self.agendar(self.ana)
        self.assertEqual(r.status_code, 409)
        self.assertIn("Já existe uma consulta marcada para este profissional", r.json["erro"])

    def test_alterar_cancelar_e_situacao(self):
        cid = self.agendar(self.maria).json["consulta"]["id"]
        r = self.c.put(f"/api/consultas/{cid}", json=dict(
            paciente_id=self.maria, profissional_id=self.joao, data=TERCA, horario="15:00",
            observacao="Remarcada", situacao="Agendada"))
        self.assertEqual((r.status_code, r.json["consulta"]["data"]), (200, TERCA))
        r = self.c.patch(f"/api/consultas/{cid}/situacao", json={"situacao": "Realizada"})
        self.assertEqual(r.json["consulta"]["situacao"], "Realizada")
        self.assertEqual(self.c.post(f"/api/consultas/{cid}/cancelar").status_code, 400)

    def test_cancelar_mantem_registro(self):
        cid = self.agendar(self.maria).json["consulta"]["id"]
        r = self.c.post(f"/api/consultas/{cid}/cancelar")
        self.assertEqual(r.json["consulta"]["situacao"], "Cancelada")
        self.assertEqual(len(self.c.get("/api/consultas?situacao=Cancelada").json), 1)

    def test_pesquisa_e_filtro_invalido(self):
        self.agendar(self.maria)
        self.assertEqual(len(self.c.get("/api/consultas?paciente=maria").json), 1)
        self.assertEqual(len(self.c.get("/api/consultas?data=" + TERCA).json), 0)
        self.assertEqual(self.c.get("/api/consultas?data=99/99/2026").status_code, 400)

    def test_horarios_livres(self):
        self.agendar(self.maria)
        livres = self.c.get(f"/api/horarios-livres?profissional_id={self.joao}&data={SEGUNDA}").json
        self.assertNotIn("14:00", livres)
        self.assertIn("14:30", livres)

    def test_consulta_inexistente_retorna_404(self):
        self.assertEqual(self.c.get("/api/consultas/999").status_code, 404)


class TestAutenticacao(BaseApi):
    def test_login_sucesso_retorna_token_e_usuario(self):
        r = self.anonimo.post("/api/login", json={"usuario": "Admin", "senha": "admin123"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json["usuario"]["usuario"], "admin")
        self.assertTrue(r.json["token"])
        self.assertNotIn("senha_hash", r.json["usuario"])

    def test_login_invalido_retorna_401(self):
        r = self.anonimo.post("/api/login", json={"usuario": "admin", "senha": "senhaerrada"})
        self.assertEqual(r.status_code, 401)
        self.assertIn("usuário ou senha", r.json["erro"].lower())
        self.assertEqual(self.anonimo.post("/api/login", json={"usuario": "x", "senha": "y"}).status_code, 401)
        self.assertEqual(self.anonimo.post("/api/login", json={"usuario": "", "senha": ""}).status_code, 401)

    def test_rotas_exigem_token(self):
        for url in ("/api/pacientes", "/api/profissionais", "/api/consultas", "/api/config",
                    "/api/dashboard", "/api/me"):
            self.assertEqual(self.anonimo.get(url).status_code, 401, url)
        self.assertEqual(self.anonimo.post("/api/pacientes", json={"nome": "X"}).status_code, 401)
        self.assertEqual(self.anonimo.delete(f"/api/pacientes/{self.maria}").status_code, 401)
        self.assertEqual(len(self.c.get("/api/pacientes").json), 2)     # nada foi apagado

    def test_token_invalido_ou_adulterado(self):
        for cabecalho in ("Bearer lixo", "Bearer ", "Basic abc", "Bearer " + "a" * 40):
            r = self.anonimo.get("/api/pacientes", headers={"Authorization": cabecalho})
            self.assertEqual(r.status_code, 401, cabecalho)

    def test_token_expirado(self):
        import autenticacao
        original = autenticacao.VALIDADE_TOKEN_SEGUNDOS
        autenticacao.VALIDADE_TOKEN_SEGUNDOS = -1
        try:
            self.assertEqual(self.c.get("/api/pacientes").status_code, 401)
        finally:
            autenticacao.VALIDADE_TOKEN_SEGUNDOS = original

    def test_me(self):
        self.assertEqual(self.c.get("/api/me").json["usuario"]["usuario"], "admin")

    def test_preflight_cors_nao_exige_token(self):
        r = self.anonimo.options("/api/pacientes")
        self.assertIn(r.status_code, (200, 204))
        self.assertIn("Authorization", r.headers["Access-Control-Allow-Headers"])

    def test_bloqueio_apos_varias_senhas_erradas(self):
        for _ in range(5):
            self.assertEqual(self.anonimo.post(
                "/api/login", json={"usuario": "admin", "senha": "errada"}).status_code, 401)
        r = self.anonimo.post("/api/login", json={"usuario": "admin", "senha": "admin123"})
        self.assertEqual(r.status_code, 429)
        self.assertIn("tentativas", r.json["erro"])

    def test_sucesso_zera_contador_de_falhas(self):
        for _ in range(4):
            self.anonimo.post("/api/login", json={"usuario": "admin", "senha": "errada"})
        self.assertEqual(self.anonimo.post(
            "/api/login", json={"usuario": "admin", "senha": "admin123"}).status_code, 200)
        for _ in range(4):
            self.assertEqual(self.anonimo.post(
                "/api/login", json={"usuario": "admin", "senha": "errada"}).status_code, 401)


class TestDashboard(BaseApi):
    def test_totais(self):
        cid = self.agendar(self.maria).json["consulta"]["id"]
        self.agendar(self.ana, horario="15:00")
        self.c.post(f"/api/consultas/{cid}/cancelar")
        r = self.c.get("/api/dashboard").json
        self.assertEqual((r["pacientes"], r["profissionais"], r["consultas"]), (2, 1, 2))
        self.assertEqual((r["agendadas"], r["canceladas"], r["realizadas"], r["hoje"]), (1, 1, 0, 0))

    def test_consultas_de_hoje(self):
        # "hoje" nos testes é 10/11/2026 (terça): 08:30 já passou? não — agora são 09:00; usa 10:00
        self.post("/api/consultas", paciente_id=self.maria, profissional_id=self.joao,
                  data="10/11/2026", horario="10:00")
        self.assertEqual(self.c.get("/api/dashboard").json["hoje"], 1)


class TestPerfis(BaseApi):
    def cadastrar_recepcao(self, usuario="recepcao", senha="recep123"):
        r = self.post("/api/usuarios", nome="Joana Lima", usuario=usuario, senha=senha, perfil="recepcao")
        self.assertEqual(r.status_code, 201, r.json)
        return r

    def cliente_como(self, usuario, senha):
        cliente = self.app.test_client()
        r = self.anonimo.post("/api/login", json={"usuario": usuario, "senha": senha})
        self.assertEqual(r.status_code, 200, r.json)
        cliente.environ_base["HTTP_AUTHORIZATION"] = "Bearer " + r.json["token"]
        return cliente, r.json["usuario"]

    # ---- gestão de usuários (admin) ----
    def test_admin_lista_usuarios_com_perfil(self):
        r = self.c.get("/api/usuarios")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json[0]["usuario"], "admin")
        self.assertEqual((r.json[0]["perfil"], r.json[0]["perfil_rotulo"]), ("admin", "Administrador"))
        self.assertNotIn("senha_hash", r.json[0])

    def test_admin_cadastra_usuario_recepcao(self):
        r = self.cadastrar_recepcao()
        self.assertEqual(r.json["mensagem"], "Usuário cadastrado com sucesso!")
        self.assertEqual(r.json["usuario"]["perfil_rotulo"], "Recepção")
        self.assertEqual(len(self.c.get("/api/usuarios").json), 2)

    def test_cadastro_de_usuario_valida_dados(self):
        base = dict(nome="Joana Lima", usuario="joana", senha="senha123", perfil="recepcao")
        casos = {
            "nome": ("O nome do usuário", dict(base, nome="")),
            "acesso": ("nome de acesso", dict(base, usuario="a b")),
            "senha curta": ("pelo menos 6", dict(base, senha="123")),
            "senha vazia": ("obrigatória", dict(base, senha="")),
            "perfil": ("Perfil inválido", dict(base, perfil="dono")),
        }
        for rotulo, (trecho, dados) in casos.items():
            r = self.post("/api/usuarios", **dados)
            self.assertEqual(r.status_code, 400, rotulo)
            self.assertIn(trecho, r.json["erro"], rotulo)

    def test_usuario_duplicado_retorna_409(self):
        self.cadastrar_recepcao()
        r = self.post("/api/usuarios", nome="Outra", usuario="RECEPCAO", senha="outra123", perfil="recepcao")
        self.assertEqual(r.status_code, 409)
        self.assertIn("Já existe um usuário", r.json["erro"])

    def test_admin_remove_usuario_e_sessao_dele_deixa_de_valer(self):
        novo = self.cadastrar_recepcao().json["usuario"]["id"]
        recepcao, _ = self.cliente_como("recepcao", "recep123")
        self.assertEqual(recepcao.get("/api/pacientes").status_code, 200)
        self.assertEqual(self.c.delete(f"/api/usuarios/{novo}").status_code, 200)
        self.assertEqual(recepcao.get("/api/pacientes").status_code, 401)   # token antigo não vale mais
        self.assertEqual(self.c.delete(f"/api/usuarios/{novo}").status_code, 404)

    def test_admin_nao_remove_a_si_mesmo(self):
        meu_id = self.c.get("/api/me").json["usuario"]["id"]
        r = self.c.delete(f"/api/usuarios/{meu_id}")
        self.assertEqual(r.status_code, 400)
        self.assertIn("próprio usuário", r.json["erro"])

    def test_nao_remove_o_ultimo_administrador(self):
        import autenticacao, banco
        from validacoes import ValidacaoErro
        conexao = banco.conectar(os.path.join(self.pasta.name, "teste.db"))
        recep = self.cadastrar_recepcao().json["usuario"]["id"]
        admin = conexao.execute("SELECT id FROM usuarios WHERE usuario='admin'").fetchone()["id"]
        with self.assertRaises(ValidacaoErro) as ctx:
            autenticacao.remover_usuario(conexao, admin, id_logado=recep)
        self.assertIn("último administrador", str(ctx.exception))
        conexao.close()

    # ---- permissões da Recepção ----
    def test_recepcao_pode_cadastrar_agendar_e_pesquisar(self):
        self.cadastrar_recepcao()
        recepcao, usuario = self.cliente_como("recepcao", "recep123")
        self.assertEqual(usuario["perfil"], "recepcao")
        r = recepcao.post("/api/pacientes", json=dict(nome="Carlos Lima", cpf="111.222.333-44",
                          telefone="71988887777", data_nascimento="23/11/2001"))
        self.assertEqual(r.status_code, 201)
        carlos = r.json["paciente"]["id"]
        r = recepcao.post("/api/consultas", json=dict(paciente_id=carlos, profissional_id=self.joao,
                          data=SEGUNDA, horario="10:00"))
        self.assertEqual(r.status_code, 201)
        cid = r.json["consulta"]["id"]
        self.assertEqual(recepcao.put(f"/api/pacientes/{carlos}", json=dict(
            nome="Carlos Lima", cpf="111.222.333-44", telefone="71977776666",
            data_nascimento="23/11/2001")).status_code, 200)
        self.assertEqual(recepcao.post(f"/api/consultas/{cid}/cancelar").status_code, 200)
        self.assertEqual(len(recepcao.get("/api/consultas").json), 1)
        self.assertEqual(recepcao.get("/api/dashboard").status_code, 200)

    def test_recepcao_nao_remove_paciente_nem_profissional(self):
        self.cadastrar_recepcao()
        recepcao, _ = self.cliente_como("recepcao", "recep123")
        for url in (f"/api/pacientes/{self.ana}", f"/api/profissionais/{self.joao}"):
            r = recepcao.delete(url)
            self.assertEqual(r.status_code, 403, url)
            self.assertIn("não tem permissão", r.json["erro"])
        self.assertEqual(len(self.c.get("/api/pacientes").json), 2)          # nada foi removido
        self.assertEqual(len(self.c.get("/api/profissionais").json), 1)

    def test_recepcao_nao_acessa_gestao_de_usuarios(self):
        self.cadastrar_recepcao()
        recepcao, _ = self.cliente_como("recepcao", "recep123")
        self.assertEqual(recepcao.get("/api/usuarios").status_code, 403)
        r = recepcao.post("/api/usuarios", json=dict(nome="Hacker", usuario="hacker",
                          senha="hacker123", perfil="admin"))
        self.assertEqual(r.status_code, 403)
        self.assertEqual(recepcao.delete("/api/usuarios/1").status_code, 403)
        self.assertEqual(len(self.c.get("/api/usuarios").json), 2)           # ninguém foi criado

    def test_admin_continua_podendo_remover(self):
        self.assertEqual(self.c.delete(f"/api/pacientes/{self.ana}").status_code, 200)
        self.assertEqual(self.c.delete(f"/api/profissionais/{self.joao}").status_code, 200)

    def test_perfil_vem_sempre_do_banco(self):
        import banco
        self.cadastrar_recepcao()
        recepcao, _ = self.cliente_como("recepcao", "recep123")
        self.assertEqual(recepcao.delete(f"/api/pacientes/{self.ana}").status_code, 403)
        conexao = banco.conectar(os.path.join(self.pasta.name, "teste.db"))
        conexao.execute("UPDATE usuarios SET perfil='admin' WHERE usuario='recepcao'")
        conexao.commit(); conexao.close()
        self.assertEqual(recepcao.delete(f"/api/pacientes/{self.ana}").status_code, 200)   # mesmo token

    # ---- troca da própria senha ----
    def test_trocar_a_propria_senha(self):
        self.cadastrar_recepcao()
        recepcao, _ = self.cliente_como("recepcao", "recep123")
        casos = [("errada", "nova456", "senha atual está incorreta"), ("recep123", "123", "pelo menos 6"),
                 ("recep123", "recep123", "diferente da atual"), ("", "nova456", "senha atual está incorreta")]
        for atual, nova, trecho in casos:
            r = recepcao.post("/api/me/senha", json={"senha_atual": atual, "nova_senha": nova})
            self.assertEqual(r.status_code, 400)
            self.assertIn(trecho, r.json["erro"])
        r = recepcao.post("/api/me/senha", json={"senha_atual": "recep123", "nova_senha": "nova456"})
        self.assertEqual((r.status_code, r.json["mensagem"]), (200, "Senha alterada com sucesso!"))
        self.assertEqual(self.anonimo.post("/api/login", json={"usuario": "recepcao", "senha": "recep123"}).status_code, 401)
        self.assertEqual(self.anonimo.post("/api/login", json={"usuario": "recepcao", "senha": "nova456"}).status_code, 200)


class TestProfissionalDuplicadoApi(BaseApi):
    def test_duplicado_retorna_409_com_mensagem(self):
        r = self.post("/api/profissionais", nome="dr.  JOÃO", especialidade="CARDIOLOGIA", telefone="71955554444")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json["erro"], "Já existe um profissional cadastrado com este nome e esta especialidade.")
        self.assertEqual(len(self.c.get("/api/profissionais").json), 1)

    def test_mesmo_nome_outra_especialidade_funciona(self):
        r = self.post("/api/profissionais", nome="Dr. João", especialidade="Clínico Geral", telefone="71955554444")
        self.assertEqual(r.status_code, 201)

    def test_alterar_para_duplicado_retorna_409(self):
        outro = self.post("/api/profissionais", nome="Dra. Bia", especialidade="Pediatria",
                          telefone="71955554444").json["profissional"]["id"]
        r = self.c.put(f"/api/profissionais/{outro}", json=dict(nome="Dr. João", especialidade="Cardiologia",
                                                               telefone="71955554444"))
        self.assertEqual(r.status_code, 409)


class TestAuditoria(BaseApi):
    def registros(self, cliente=None, **filtros):
        consulta = "&".join(f"{k}={v}" for k, v in filtros.items())
        r = (cliente or self.c).get("/api/auditoria" + ("?" + consulta if consulta else ""))
        self.assertEqual(r.status_code, 200, r.json)
        return r.json

    def ultimo(self, **filtros):
        return self.registros(**filtros)["registros"][0]

    def criar_recepcao(self):
        self.post("/api/usuarios", nome="Joana Lima", usuario="recepcao", senha="recep123", perfil="recepcao")
        cliente = self.app.test_client()
        token = self.anonimo.post("/api/login", json={"usuario": "recepcao", "senha": "recep123"}).json["token"]
        cliente.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        return cliente

    def test_cadastros_do_setup_foram_registrados_com_data_e_usuario(self):
        r = self.registros()
        self.assertEqual(r["total"], 3)                         # 2 pacientes + 1 profissional
        mais_recente = r["registros"][0]
        self.assertEqual((mais_recente["usuario"], mais_recente["nome"], mais_recente["perfil"]),
                         ("admin", "Administrador", "admin"))
        self.assertEqual(mais_recente["data_hora"], "10/11/2026 09:00:00")
        self.assertEqual((mais_recente["acao"], mais_recente["entidade"]), ("criar", "profissional"))
        self.assertEqual(mais_recente["descricao"], "Cadastrou o profissional Dr. João (Cardiologia)")
        self.assertIn("Especialidade: Cardiologia", mais_recente["detalhes"])

    def test_alteracao_mostra_antes_e_depois(self):
        self.c.put(f"/api/pacientes/{self.maria}", json=dict(
            nome="Maria Santos", cpf="123.456.789-00", telefone="71988887777", data_nascimento="10/05/1990"))
        reg = self.ultimo()
        self.assertEqual((reg["acao"], reg["acao_rotulo"], reg["entidade"]), ("alterar", "Alteração", "paciente"))
        self.assertEqual(reg["detalhes"], ["Telefone: (71) 99999-9999 → (71) 98888-7777"])
        self.assertEqual(reg["registro_id"], self.maria)

    def test_alteracao_sem_mudanca_nao_gera_registro(self):
        antes = self.registros()["total"]
        self.c.put(f"/api/pacientes/{self.maria}", json=dict(
            nome="Maria Santos", cpf="123.456.789-00", telefone="71999999999", data_nascimento="10/05/1990"))
        self.assertEqual(self.registros()["total"], antes)

    def test_operacao_que_falha_nao_gera_registro(self):
        antes = self.registros()["total"]
        self.post("/api/pacientes", nome="", cpf="1", telefone="", data_nascimento="")          # 400
        self.post("/api/pacientes", nome="Outra", cpf="12345678900", telefone="71999999999",
                  data_nascimento="10/05/1990")                                                   # 409 CPF
        self.c.delete("/api/pacientes/9999")                                                      # 404
        self.assertEqual(self.registros()["total"], antes)

    def test_consultas_cadastro_alteracao_situacao_e_cancelamento(self):
        cid = self.agendar(self.maria, observacao="Primeira").json["consulta"]["id"]
        reg = self.ultimo()
        self.assertEqual(reg["descricao"], f"Agendou a consulta {cid}: Maria Santos com Dr. João em 16/11/2026 às 14:00")
        self.c.put(f"/api/consultas/{cid}", json=dict(paciente_id=self.maria, profissional_id=self.joao,
                   data=TERCA, horario="15:00", observacao="Primeira", situacao="Agendada"))
        reg = self.ultimo()
        self.assertEqual(reg["acao"], "alterar")
        self.assertEqual(sorted(reg["detalhes"]), ["Data: 16/11/2026 → 17/11/2026", "Horário: 14:00 → 15:00"])
        self.c.patch(f"/api/consultas/{cid}/situacao", json={"situacao": "Realizada"})
        reg = self.ultimo()
        self.assertEqual((reg["acao"], reg["acao_rotulo"]), ("situacao", "Mudança de situação"))
        self.assertEqual(reg["detalhes"], ["Situação: Agendada → Realizada"])
        outra = self.agendar(self.ana, horario="10:00").json["consulta"]["id"]
        self.c.post(f"/api/consultas/{outra}/cancelar")
        reg = self.ultimo()
        self.assertEqual((reg["acao"], reg["acao_rotulo"]), ("cancelar", "Cancelamento"))
        self.assertIn("Cancelou a consulta", reg["descricao"])
        self.assertEqual(reg["detalhes"], ["Situação: Agendada → Cancelada"])

    def test_remocao_guarda_os_dados_do_item_removido(self):
        self.c.delete(f"/api/pacientes/{self.ana}")
        reg = self.ultimo()
        self.assertEqual((reg["acao"], reg["descricao"]), ("remover", "Removeu o paciente Ana Souza"))
        self.assertIn("Nome: Ana Souza", reg["detalhes"])
        self.assertEqual(self.c.get(f"/api/pacientes/{self.ana}").status_code, 404)   # sumiu, mas o registro fica

    def test_acoes_da_recepcao_ficam_registradas_com_o_nome_dela(self):
        recepcao = self.criar_recepcao()
        recepcao.post("/api/pacientes", json=dict(nome="Carlos Lima", cpf="111.222.333-44",
                      telefone="71988887777", data_nascimento="23/11/2001"))
        reg = self.ultimo(usuario="recepcao")
        self.assertEqual((reg["usuario"], reg["nome"], reg["perfil"]), ("recepcao", "Joana Lima", "recepcao"))
        self.assertEqual(reg["descricao"], "Cadastrou o paciente Carlos Lima")
        self.assertEqual(self.registros(usuario="Joana")["total"], 1)           # filtro também por nome
        self.assertEqual(self.registros(usuario="admin")["total"], 4)           # 3 do setup + cadastro do usuário

    def test_somente_admin_consulta_a_auditoria(self):
        recepcao = self.criar_recepcao()
        self.assertEqual(recepcao.get("/api/auditoria").status_code, 403)
        self.assertEqual(self.anonimo.get("/api/auditoria").status_code, 401)

    def test_usuarios_senha_e_remocao_sao_registrados_sem_expor_senhas(self):
        recepcao = self.criar_recepcao()
        recepcao.post("/api/me/senha", json={"senha_atual": "recep123", "nova_senha": "nova456"})
        reg = self.ultimo(acao="senha")
        self.assertEqual((reg["usuario"], reg["descricao"]), ("recepcao", "Alterou a própria senha"))
        uid = self.c.get("/api/usuarios").json[1]["id"]
        self.c.delete(f"/api/usuarios/{uid}")
        reg = self.ultimo(entidade="usuario", acao="remover")
        self.assertEqual(reg["descricao"], "Removeu o usuário recepcao")
        bruto = str(self.registros()["registros"])
        for segredo in ("recep123", "nova456", "scrypt", "pbkdf2"):
            self.assertNotIn(segredo, bruto)
        # os registros do usuário removido continuam existindo
        self.assertGreaterEqual(self.registros(usuario="recepcao")["total"], 1)

    def test_filtros(self):
        self.c.put(f"/api/pacientes/{self.maria}", json=dict(
            nome="Maria Santos", cpf="123.456.789-00", telefone="71988887777", data_nascimento="10/05/1990"))
        self.assertEqual(self.registros(entidade="paciente")["total"], 3)
        self.assertEqual(self.registros(entidade="profissional")["total"], 1)
        self.assertEqual(self.registros(acao="alterar")["total"], 1)
        self.assertEqual(self.registros(data_inicial="10/11/2026", data_final="10/11/2026")["total"], 4)
        self.assertEqual(self.registros(data_inicial="11/11/2026")["total"], 0)
        self.assertEqual(self.registros(data_final="09/11/2026")["total"], 0)
        self.assertEqual(self.registros(entidade="paciente", acao="criar", usuario="admin")["total"], 2)

    def test_filtros_invalidos_retornam_400(self):
        for filtro in ("entidade=xyz", "acao=xyz", "data_inicial=31/02/2026", "data_final=abc",
                       "data_inicial=10/11/2026&data_final=01/11/2026"):
            self.assertEqual(self.c.get("/api/auditoria?" + filtro).status_code, 400, filtro)

    def test_paginacao(self):
        for i in range(4):
            self.post("/api/pacientes", nome=f"Paciente {i}", cpf=f"5555555550{i}", telefone="71999999999",
                      data_nascimento="10/05/1990")
        p1 = self.registros(por_pagina=3)
        self.assertEqual((p1["total"], p1["paginas"], p1["pagina"], len(p1["registros"])), (7, 3, 1, 3))
        p3 = self.registros(por_pagina=3, pagina=3)
        self.assertEqual((p3["pagina"], len(p3["registros"])), (3, 1))
        self.assertEqual(self.registros(por_pagina=3, pagina=99)["pagina"], 3)    # limitado ao máximo
        self.assertEqual(self.registros(por_pagina="abc", pagina="x")["pagina"], 1)
        datas = [r["id"] for r in p1["registros"]]
        self.assertEqual(datas, sorted(datas, reverse=True))                      # mais recente primeiro

    def test_consultar_a_auditoria_nao_gera_registro(self):
        antes = self.registros()["total"]
        self.c.get("/api/pacientes"); self.c.get("/api/consultas"); self.c.get("/api/dashboard")
        self.assertEqual(self.registros()["total"], antes)

    def test_registros_nao_podem_ser_alterados_nem_apagados_nem_pelo_banco(self):
        import banco
        import sqlite3
        conexao = banco.conectar(os.path.join(self.pasta.name, "teste.db"))
        with self.assertRaises(sqlite3.IntegrityError):
            conexao.execute("UPDATE auditoria SET descricao = 'adulterado'")
        with self.assertRaises(sqlite3.IntegrityError):
            conexao.execute("DELETE FROM auditoria")
        conexao.close()
        for metodo in ("put", "delete", "patch", "post"):
            r = getattr(self.c, metodo)("/api/auditoria/1")
            self.assertIn(r.status_code, (404, 405))


class TestInfra(BaseApi):
    def test_config(self):
        r = self.c.get("/api/config")
        self.assertEqual(r.json["situacoes"], ["Agendada", "Realizada", "Cancelada"])

    def test_rota_inexistente_e_cors(self):
        r = self.c.get("/api/nada")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self.c.get("/api/config").headers["Access-Control-Allow-Origin"], "*")


if __name__ == "__main__":
    unittest.main(verbosity=2)
