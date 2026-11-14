"""Autenticação: usuários, senhas com hash, tokens assinados e limite de tentativas."""
import os
import secrets
import sqlite3
import time
from pathlib import Path

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

import re

from validacoes import (ConflitoErro, LimiteExcedidoErro, NaoAutorizadoErro,
                        NaoEncontradoErro, ValidacaoErro)

PERFIS = {"admin": "Administrador", "recepcao": "Recepção"}


def permitido(perfil: str, metodo: str, caminho: str) -> bool:
    """Regras de acesso por perfil.

    - admin: tudo.
    - recepcao: cadastra, altera, agenda, cancela e pesquisa; NÃO remove pacientes/profissionais
      e NÃO acessa a gestão de usuários nem a auditoria.
    """
    if perfil == "admin":
        return True
    if caminho.startswith(("/api/usuarios", "/api/auditoria")):
        return False
    if metodo == "DELETE" and re.match(r"^/api/(pacientes|profissionais)/", caminho):
        return False
    return True


VALIDADE_TOKEN_SEGUNDOS = 8 * 60 * 60      # sessão de 8 horas
MAX_FALHAS = 5                             # tentativas erradas seguidas...
JANELA_SEGUNDOS = 5 * 60                   # ...dentro desta janela bloqueiam o login


def _usuario_dict(linha) -> dict:
    return {"id": linha["id"], "nome": linha["nome"], "usuario": linha["usuario"],
            "perfil": linha["perfil"], "perfil_rotulo": PERFIS.get(linha["perfil"], linha["perfil"])}


def garantir_admin(conexao: sqlite3.Connection, metodo_hash: str = "scrypt") -> None:
    """Cria o administrador inicial se ainda não existir nenhum usuário.

    Usuário e senha vêm de ADMIN_USER / ADMIN_PASSWORD (padrão: admin / admin123).
    Para uso real, defina uma senha própria antes da primeira execução.
    """
    if conexao.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]:
        return
    usuario = os.environ.get("ADMIN_USER", "admin").strip().lower()
    senha = os.environ.get("ADMIN_PASSWORD", "admin123")
    conexao.execute(
        "INSERT INTO usuarios (nome, usuario, senha_hash, perfil) VALUES (?, ?, ?, 'admin')",
        ("Administrador", usuario, generate_password_hash(senha, method=metodo_hash)),
    )
    conexao.commit()


def carregar_chave_secreta(caminho_banco) -> str:
    """Chave que assina os tokens: variável de ambiente ou arquivo local gerado uma vez."""
    if os.environ.get("CLINICA_SECRET_KEY"):
        return os.environ["CLINICA_SECRET_KEY"]
    arquivo = Path(str(caminho_banco)).with_name(".secret_key")
    if arquivo.exists():
        return arquivo.read_text().strip()
    chave = secrets.token_hex(32)
    arquivo.write_text(chave)
    try:
        arquivo.chmod(0o600)
    except OSError:
        pass
    return chave


class Autenticador:
    def __init__(self, chave_secreta: str, relogio=time.monotonic):
        self._token = URLSafeTimedSerializer(chave_secreta, salt="clinica-auth")
        self._falhas: dict[str, list[float]] = {}
        self._relogio = relogio

    # ---- limite de tentativas ------------------------------------------
    def _falhas_recentes(self, chave: str) -> list[float]:
        agora = self._relogio()
        recentes = [t for t in self._falhas.get(chave, []) if agora - t < JANELA_SEGUNDOS]
        self._falhas[chave] = recentes
        return recentes

    # ---- login / token ---------------------------------------------------
    def entrar(self, conexao, usuario: str, senha: str, origem: str = "") -> dict:
        usuario = (usuario or "").strip().lower()
        if not usuario or not senha:
            raise NaoAutorizadoErro("Informe o usuário e a senha.")
        chave = f"{origem}|{usuario}"
        if len(self._falhas_recentes(chave)) >= MAX_FALHAS:
            raise LimiteExcedidoErro(
                "Muitas tentativas de login. Aguarde alguns minutos e tente novamente.")

        linha = conexao.execute(
            "SELECT id, nome, usuario, senha_hash, perfil FROM usuarios WHERE usuario = ?",
            (usuario,),
        ).fetchone()
        if not linha or not check_password_hash(linha["senha_hash"], senha):
            self._falhas[chave].append(self._relogio())
            raise NaoAutorizadoErro("Usuário ou senha inválidos.")

        self._falhas.pop(chave, None)
        dados = _usuario_dict(linha)
        return {"token": self._token.dumps({"id": dados["id"]}), "usuario": dados}

    def validar_token(self, token: str, conexao) -> dict:
        """Confere a assinatura/validade do token e carrega o usuário ATUAL do banco."""
        try:
            dados = self._token.loads(token, max_age=VALIDADE_TOKEN_SEGUNDOS)
        except (SignatureExpired, BadSignature):
            raise NaoAutorizadoErro("Sessão expirada ou inválida. Faça login novamente.")
        linha = conexao.execute(
            "SELECT id, nome, usuario, perfil FROM usuarios WHERE id = ?", (dados.get("id"),)
        ).fetchone()
        if not linha:                       # usuário removido depois do login
            raise NaoAutorizadoErro("Sessão expirada ou inválida. Faça login novamente.")
        return _usuario_dict(linha)


# ----------------------------------------------------------------------
# Gestão de usuários (somente perfil admin — ver permitido())
# ----------------------------------------------------------------------
def _validar_senha(senha: str, rotulo: str = "A senha") -> str:
    if not senha:
        raise ValidacaoErro(f"{rotulo} é obrigatória e não pode ficar vazia.")
    if len(senha) < 6:
        raise ValidacaoErro(f"{rotulo} deve ter pelo menos 6 caracteres.")
    if len(senha) > 72:
        raise ValidacaoErro(f"{rotulo} deve ter no máximo 72 caracteres.")
    return senha


def listar_usuarios(conexao) -> list[dict]:
    linhas = conexao.execute(
        "SELECT id, nome, usuario, perfil FROM usuarios ORDER BY nome COLLATE NOCASE")
    return [_usuario_dict(l) for l in linhas]


def criar_usuario(conexao, nome, usuario, senha, perfil, metodo_hash="scrypt") -> dict:
    from validacoes import validar_nome
    nome = validar_nome(nome, "O nome do usuário")
    usuario = (usuario or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9._-]{3,30}", usuario):
        raise ValidacaoErro("O nome de acesso deve ter de 3 a 30 caracteres "
                            "(letras, números, ponto, hífen ou sublinhado, sem espaços).")
    _validar_senha(senha)
    if perfil not in PERFIS:
        raise ValidacaoErro("Perfil inválido. Escolha Administrador ou Recepção.")
    try:
        cur = conexao.execute(
            "INSERT INTO usuarios (nome, usuario, senha_hash, perfil) VALUES (?, ?, ?, ?)",
            (nome, usuario, generate_password_hash(senha, method=metodo_hash), perfil))
        conexao.commit()
    except sqlite3.IntegrityError:
        raise ConflitoErro("Já existe um usuário com este nome de acesso.")
    return _usuario_dict(conexao.execute(
        "SELECT id, nome, usuario, perfil FROM usuarios WHERE id = ?", (cur.lastrowid,)).fetchone())


def obter_usuario(conexao, usuario_id: int) -> dict:
    linha = conexao.execute(
        "SELECT id, nome, usuario, perfil FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
    if not linha:
        raise NaoEncontradoErro("Usuário não encontrado.")
    return _usuario_dict(linha)


def remover_usuario(conexao, usuario_id: int, id_logado: int) -> None:
    linha = conexao.execute("SELECT id, perfil FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
    if not linha:
        raise NaoEncontradoErro("Usuário não encontrado.")
    if usuario_id == id_logado:
        raise ValidacaoErro("Você não pode remover o seu próprio usuário.")
    if linha["perfil"] == "admin" and conexao.execute(
            "SELECT COUNT(*) FROM usuarios WHERE perfil = 'admin'").fetchone()[0] <= 1:
        raise ValidacaoErro("Não é possível remover o último administrador do sistema.")
    conexao.execute("DELETE FROM usuarios WHERE id = ?", (usuario_id,))
    conexao.commit()


def alterar_senha(conexao, usuario_id: int, senha_atual: str, nova_senha: str,
                  metodo_hash="scrypt") -> None:
    linha = conexao.execute("SELECT senha_hash FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
    if not linha:
        raise NaoEncontradoErro("Usuário não encontrado.")
    if not senha_atual or not check_password_hash(linha["senha_hash"], senha_atual):
        raise ValidacaoErro("A senha atual está incorreta.")
    _validar_senha(nova_senha, "A nova senha")
    if nova_senha == senha_atual:
        raise ValidacaoErro("A nova senha deve ser diferente da atual.")
    conexao.execute("UPDATE usuarios SET senha_hash = ? WHERE id = ?",
                    (generate_password_hash(nova_senha, method=metodo_hash), usuario_id))
    conexao.commit()
