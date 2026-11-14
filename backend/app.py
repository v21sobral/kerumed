"""API REST (Flask) do Sistema de Marcação de Consultas.

Execute:  python app.py   →  http://127.0.0.1:5000
O backend também entrega os arquivos da pasta ../frontend, então um único
comando sobe o sistema completo. (O frontend também pode ser servido à parte:
a API aceita requisições de outras origens — CORS.)
"""
import os
from datetime import datetime
from pathlib import Path

from flask import Flask, g, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

import auditoria
import autenticacao
import banco
import validacoes as v
from servicos import ClinicaService
from validacoes import (AcessoNegadoErro, ConflitoErro, LimiteExcedidoErro, NaoAutorizadoErro,
                        NaoEncontradoErro, ValidacaoErro)

PASTA_FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


def create_app(caminho_banco=banco.CAMINHO_PADRAO, agora=None, chave_secreta=None,
               metodo_hash="scrypt") -> Flask:
    """Fábrica da aplicação.

    'agora' fixa o relógio e 'chave_secreta'/'metodo_hash' permitem testes rápidos.
    """
    app = Flask(__name__, static_folder=None)
    app.json.ensure_ascii = False
    app.config["CAMINHO_BANCO"] = str(caminho_banco)
    app.config["AGORA"] = agora

    autenticador = autenticacao.Autenticador(
        chave_secreta or autenticacao.carregar_chave_secreta(caminho_banco))
    inicial = banco.conectar(caminho_banco)     # cria as tabelas e o admin inicial (uma única vez)
    autenticacao.garantir_admin(inicial, metodo_hash)
    inicial.close()

    # ------------------------------------------------------------------
    # Infraestrutura: uma conexão/serviço por requisição
    # ------------------------------------------------------------------
    def conexao():
        if "conexao" not in g:
            g.conexao = banco.conectar(app.config["CAMINHO_BANCO"])
        return g.conexao

    def servico() -> ClinicaService:
        if "servico" not in g:
            extra = {"agora": app.config["AGORA"]} if app.config["AGORA"] else {}
            g.servico = ClinicaService(conexao(), **extra)
        return g.servico

    def auditar(acao, entidade, registro_id, descricao, antes=None, depois=None, campos=()):
        """Registra na auditoria uma operação JÁ concluída com sucesso pelo usuário logado."""
        try:
            auditoria.registrar(conexao(), g.usuario, acao, entidade, registro_id, descricao,
                                (app.config["AGORA"] or datetime.now)(), antes, depois, campos)
        except Exception:   # falha ao auditar não desfaz a operação já gravada
            app.logger.exception("Falha ao gravar o registro de auditoria")

    @app.teardown_appcontext
    def fechar_conexao(_erro):
        conexao = g.pop("conexao", None)
        if conexao is not None:
            conexao.close()

    @app.after_request
    def liberar_cors(resposta):
        if request.path.startswith("/api/"):
            resposta.headers["Access-Control-Allow-Origin"] = "*"
            resposta.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            resposta.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        return resposta

    def corpo() -> dict:
        dados = request.get_json(silent=True)
        if not isinstance(dados, dict):
            raise ValidacaoErro("Requisição inválida: envie os dados em formato JSON.")
        return dados

    def texto(dados: dict, chave: str) -> str:
        valor = dados.get(chave)
        return "" if valor is None else str(valor)

    @app.before_request
    def exigir_login():
        """Toda rota /api/ (exceto o login) exige um token válido no cabeçalho Authorization."""
        if (request.method == "OPTIONS" or not request.path.startswith("/api/")
                or request.path == "/api/login"):
            return
        cabecalho = request.headers.get("Authorization", "")
        if not cabecalho.startswith("Bearer ") or len(cabecalho) <= 7:
            raise NaoAutorizadoErro("Faça login para acessar o sistema.")
        g.usuario = autenticador.validar_token(cabecalho[7:], conexao())
        if not autenticacao.permitido(g.usuario["perfil"], request.method, request.path):
            raise AcessoNegadoErro("Você não tem permissão para realizar esta operação.")

    @app.post("/api/login")
    def login():
        d = corpo()
        conexao = banco.conectar(app.config["CAMINHO_BANCO"])
        try:
            resultado = autenticador.entrar(
                conexao, texto(d, "usuario"), texto(d, "senha"), request.remote_addr or "")
        finally:
            conexao.close()
        return jsonify(mensagem="Login realizado com sucesso!", **resultado)

    @app.get("/api/me")
    def usuario_atual():
        return jsonify(usuario=g.usuario)

    @app.post("/api/me/senha")
    def trocar_minha_senha():
        d = corpo()
        autenticacao.alterar_senha(conexao(), g.usuario["id"], texto(d, "senha_atual"),
                                   texto(d, "nova_senha"), metodo_hash)
        auditar("senha", "usuario", g.usuario["id"], "Alterou a própria senha")
        return jsonify(mensagem="Senha alterada com sucesso!")

    @app.get("/api/usuarios")
    def listar_usuarios():
        return jsonify(autenticacao.listar_usuarios(conexao()))

    @app.post("/api/usuarios")
    def cadastrar_usuario():
        d = corpo()
        novo = autenticacao.criar_usuario(conexao(), texto(d, "nome"), texto(d, "usuario"),
                                          texto(d, "senha"), texto(d, "perfil"), metodo_hash)
        auditar("criar", "usuario", novo["id"],
                f"Cadastrou o usuário {novo['usuario']} (perfil {novo['perfil_rotulo']})",
                depois=novo, campos=("nome", "usuario", "perfil_rotulo"))
        return jsonify(mensagem="Usuário cadastrado com sucesso!", usuario=novo), 201

    @app.delete("/api/usuarios/<int:usuario_id>")
    def remover_usuario(usuario_id):
        antes = autenticacao.obter_usuario(conexao(), usuario_id)
        autenticacao.remover_usuario(conexao(), usuario_id, g.usuario["id"])
        auditar("remover", "usuario", usuario_id, f"Removeu o usuário {antes['usuario']}",
                antes=antes, campos=("nome", "usuario", "perfil_rotulo"))
        return jsonify(mensagem="Usuário removido com sucesso!")

    @app.get("/api/auditoria")
    def consultar_auditoria():
        a = request.args
        return jsonify(auditoria.listar(
            conexao(), a.get("usuario", ""), a.get("entidade", ""), a.get("acao", ""),
            a.get("data_inicial", ""), a.get("data_final", ""), a.get("pagina", 1),
            a.get("por_pagina", auditoria.POR_PAGINA_PADRAO)))

    @app.get("/api/dashboard")
    def dashboard():
        return jsonify(servico().resumo())

    # ------------------------------------------------------------------
    # Tratamento de erros → JSON {"erro": "mensagem"}
    # ------------------------------------------------------------------
    @app.errorhandler(NaoEncontradoErro)
    def erro_nao_encontrado(e):
        return jsonify(erro=str(e)), 404

    @app.errorhandler(NaoAutorizadoErro)
    def erro_nao_autorizado(e):
        return jsonify(erro=str(e)), 401

    @app.errorhandler(AcessoNegadoErro)
    def erro_acesso_negado(e):
        return jsonify(erro=str(e)), 403

    @app.errorhandler(LimiteExcedidoErro)
    def erro_limite(e):
        return jsonify(erro=str(e)), 429

    @app.errorhandler(ConflitoErro)
    def erro_conflito(e):
        return jsonify(erro=str(e)), 409

    @app.errorhandler(ValidacaoErro)
    def erro_validacao(e):
        return jsonify(erro=str(e)), 400

    @app.errorhandler(404)
    def rota_inexistente(_e):
        if request.path.startswith("/api/"):
            return jsonify(erro="Rota não encontrada."), 404
        return "Página não encontrada.", 404

    @app.errorhandler(405)
    def metodo_nao_permitido(_e):
        return jsonify(erro="Método não permitido para esta rota."), 405

    @app.errorhandler(Exception)
    def erro_inesperado(e):
        if isinstance(e, HTTPException):
            return jsonify(erro=e.description), e.code
        app.logger.exception(e)
        return jsonify(erro="Erro interno inesperado no servidor."), 500

    # ------------------------------------------------------------------
    # Configurações para o frontend
    # ------------------------------------------------------------------
    @app.get("/api/config")
    def config():
        return jsonify(
            especialidades=list(v.ESPECIALIDADES_SUGERIDAS),
            situacoes=list(v.SITUACOES),
            horarios=v.horarios_disponiveis_na_grade(),
        )

    # ------------------------------------------------------------------
    # Pacientes
    # ------------------------------------------------------------------
    @app.get("/api/pacientes")
    def listar_pacientes():
        return jsonify(servico().listar_pacientes(request.args.get("busca", "")))

    @app.get("/api/pacientes/<int:paciente_id>")
    def obter_paciente(paciente_id):
        return jsonify(servico().obter_paciente(paciente_id))

    @app.post("/api/pacientes")
    def cadastrar_paciente():
        d = corpo()
        novo_id = servico().cadastrar_paciente(
            texto(d, "nome"), texto(d, "cpf"), texto(d, "telefone"), texto(d, "data_nascimento"))
        paciente = servico().obter_paciente(novo_id)
        auditar("criar", "paciente", novo_id, f"Cadastrou o paciente {paciente['nome']}",
                depois=paciente, campos=("nome", "cpf", "telefone", "data_nascimento"))
        return jsonify(mensagem="Paciente cadastrado com sucesso!", paciente=paciente), 201

    @app.put("/api/pacientes/<int:paciente_id>")
    def alterar_paciente(paciente_id):
        d = corpo()
        antes = servico().obter_paciente(paciente_id)
        servico().alterar_paciente(
            paciente_id, texto(d, "nome"), texto(d, "cpf"), texto(d, "telefone"),
            texto(d, "data_nascimento"))
        depois = servico().obter_paciente(paciente_id)
        auditar("alterar", "paciente", paciente_id, f"Alterou o paciente {depois['nome']}",
                antes, depois, ("nome", "cpf", "telefone", "data_nascimento"))
        return jsonify(mensagem="Dados do paciente atualizados com sucesso!", paciente=depois)

    @app.delete("/api/pacientes/<int:paciente_id>")
    def remover_paciente(paciente_id):
        antes = servico().obter_paciente(paciente_id)
        servico().remover_paciente(paciente_id)
        auditar("remover", "paciente", paciente_id, f"Removeu o paciente {antes['nome']}",
                antes=antes, campos=("nome", "cpf", "telefone", "data_nascimento"))
        return jsonify(mensagem="Paciente removido com sucesso!")

    # ------------------------------------------------------------------
    # Profissionais
    # ------------------------------------------------------------------
    @app.get("/api/profissionais")
    def listar_profissionais():
        return jsonify(servico().listar_profissionais(request.args.get("busca", "")))

    @app.get("/api/profissionais/<int:profissional_id>")
    def obter_profissional(profissional_id):
        return jsonify(servico().obter_profissional(profissional_id))

    @app.post("/api/profissionais")
    def cadastrar_profissional():
        d = corpo()
        novo_id = servico().cadastrar_profissional(
            texto(d, "nome"), texto(d, "especialidade"), texto(d, "telefone"))
        profissional = servico().obter_profissional(novo_id)
        auditar("criar", "profissional", novo_id,
                f"Cadastrou o profissional {profissional['nome']} ({profissional['especialidade']})",
                depois=profissional, campos=("nome", "especialidade", "telefone"))
        return jsonify(mensagem="Profissional cadastrado com sucesso!", profissional=profissional), 201

    @app.put("/api/profissionais/<int:profissional_id>")
    def alterar_profissional(profissional_id):
        d = corpo()
        antes = servico().obter_profissional(profissional_id)
        servico().alterar_profissional(
            profissional_id, texto(d, "nome"), texto(d, "especialidade"), texto(d, "telefone"))
        depois = servico().obter_profissional(profissional_id)
        auditar("alterar", "profissional", profissional_id,
                f"Alterou o profissional {depois['nome']}", antes, depois, ("nome", "especialidade", "telefone"))
        return jsonify(mensagem="Dados do profissional atualizados com sucesso!", profissional=depois)

    @app.delete("/api/profissionais/<int:profissional_id>")
    def remover_profissional(profissional_id):
        antes = servico().obter_profissional(profissional_id)
        servico().remover_profissional(profissional_id)
        auditar("remover", "profissional", profissional_id,
                f"Removeu o profissional {antes['nome']} ({antes['especialidade']})",
                antes=antes, campos=("nome", "especialidade", "telefone"))
        return jsonify(mensagem="Profissional removido com sucesso!")

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------
    @app.get("/api/consultas")
    def pesquisar_consultas():
        a = request.args
        return jsonify(servico().pesquisar_consultas(
            a.get("paciente", ""), a.get("profissional", ""), a.get("data", ""),
            a.get("especialidade", ""), a.get("situacao", "")))

    @app.get("/api/consultas/<int:consulta_id>")
    def obter_consulta(consulta_id):
        return jsonify(servico().obter_consulta(consulta_id))

    @app.post("/api/consultas")
    def agendar_consulta():
        d = corpo()
        novo_id = servico().agendar_consulta(
            d.get("paciente_id"), d.get("profissional_id"),
            texto(d, "data"), texto(d, "horario"), texto(d, "observacao"))
        c = servico().obter_consulta(novo_id)
        auditar("criar", "consulta", novo_id,
                f"Agendou a consulta {novo_id}: {c['paciente']} com {c['profissional']} "
                f"em {c['data']} às {c['horario']}", depois=c, campos=("paciente", "profissional", "especialidade", "data", "horario", "situacao", "observacao"))
        return jsonify(mensagem=f"Consulta agendada com sucesso! Código: {novo_id}", consulta=c), 201

    @app.put("/api/consultas/<int:consulta_id>")
    def alterar_consulta(consulta_id):
        d = corpo()
        antes = servico().obter_consulta(consulta_id)
        servico().alterar_consulta(
            consulta_id, d.get("paciente_id"), d.get("profissional_id"),
            texto(d, "data"), texto(d, "horario"), texto(d, "observacao"),
            texto(d, "situacao") or "Agendada")
        depois = servico().obter_consulta(consulta_id)
        auditar("alterar", "consulta", consulta_id,
                f"Alterou a consulta {consulta_id} de {depois['paciente']}", antes, depois, ("paciente", "profissional", "especialidade", "data", "horario", "situacao", "observacao"))
        return jsonify(mensagem="Consulta alterada com sucesso!", consulta=depois)

    @app.post("/api/consultas/<int:consulta_id>/cancelar")
    def cancelar_consulta(consulta_id):
        antes = servico().obter_consulta(consulta_id)
        servico().cancelar_consulta(consulta_id)
        depois = servico().obter_consulta(consulta_id)
        auditar("cancelar", "consulta", consulta_id,
                f"Cancelou a consulta {consulta_id} de {depois['paciente']} "
                f"({depois['data']} às {depois['horario']})", antes, depois, ("paciente", "profissional", "especialidade", "data", "horario", "situacao", "observacao"))
        return jsonify(mensagem="Consulta cancelada com sucesso!", consulta=depois)

    @app.patch("/api/consultas/<int:consulta_id>/situacao")
    def alterar_situacao(consulta_id):
        d = corpo()
        antes = servico().obter_consulta(consulta_id)
        servico().alterar_situacao(consulta_id, texto(d, "situacao"))
        depois = servico().obter_consulta(consulta_id)
        auditar("situacao", "consulta", consulta_id,
                f"Alterou a situação da consulta {consulta_id} de {depois['paciente']} "
                f"para {depois['situacao']}", antes, depois, ("paciente", "profissional", "especialidade", "data", "horario", "situacao", "observacao"))
        return jsonify(mensagem="Situação da consulta atualizada com sucesso!", consulta=depois)

    @app.get("/api/horarios-livres")
    def horarios_livres():
        return jsonify(servico().horarios_livres(
            request.args.get("profissional_id"), request.args.get("data", "")))

    # ------------------------------------------------------------------
    # Frontend estático
    # ------------------------------------------------------------------
    @app.get("/")
    def pagina_inicial():
        return send_from_directory(PASTA_FRONTEND, "index.html")

    @app.get("/<path:caminho>")
    def arquivos_do_frontend(caminho):
        if caminho.startswith("api/"):
            return jsonify(erro="Rota não encontrada."), 404
        return send_from_directory(PASTA_FRONTEND, caminho)

    return app


if __name__ == "__main__":
    porta = int(os.environ.get("PORT", 5000))
    # debug só quando FLASK_DEBUG=1 (o modo debug expõe um console de execução de código)
    create_app().run(host="127.0.0.1", port=porta, debug=os.environ.get("FLASK_DEBUG") == "1")
