"""Camada de acesso ao banco de dados (SQLite local e Turso/libSQL na nuvem)."""
import os
import sqlite3
from pathlib import Path

from validacoes import chave_nome_profissional, chave_texto

CAMINHO_PADRAO = Path(__file__).with_name("clinica.db")

ESQUEMA = """
CREATE TABLE IF NOT EXISTS pacientes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nome            TEXT NOT NULL,
    cpf             TEXT NOT NULL UNIQUE,
    telefone        TEXT NOT NULL,
    data_nascimento TEXT NOT NULL            -- ISO: aaaa-mm-dd
);

CREATE TABLE IF NOT EXISTS profissionais (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    nome          TEXT NOT NULL,
    especialidade TEXT NOT NULL,
    telefone      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS consultas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_id     INTEGER NOT NULL REFERENCES pacientes(id),
    profissional_id INTEGER NOT NULL REFERENCES profissionais(id),
    especialidade   TEXT NOT NULL,           -- guardada no momento da marcação
    data            TEXT NOT NULL,           -- ISO: aaaa-mm-dd
    horario         TEXT NOT NULL,           -- HH:MM
    observacao      TEXT NOT NULL DEFAULT '',
    situacao        TEXT NOT NULL DEFAULT 'Agendada'
                    CHECK (situacao IN ('Agendada', 'Realizada', 'Cancelada'))
);

CREATE TABLE IF NOT EXISTS usuarios (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nome        TEXT NOT NULL,
    usuario     TEXT NOT NULL UNIQUE,
    senha_hash  TEXT NOT NULL,
    perfil      TEXT NOT NULL DEFAULT 'admin'
);

-- Registro de auditoria: somente inclusão (triggers impedem alterar ou apagar registros).
CREATE TABLE IF NOT EXISTS auditoria (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    data_hora   TEXT NOT NULL,               -- aaaa-mm-dd HH:MM:SS
    usuario_id  INTEGER,                     -- sem chave estrangeira: o registro sobrevive ao usuário
    usuario     TEXT NOT NULL,
    nome        TEXT NOT NULL,
    perfil      TEXT NOT NULL,
    acao        TEXT NOT NULL,
    entidade    TEXT NOT NULL,
    registro_id INTEGER,
    descricao   TEXT NOT NULL,
    detalhes    TEXT                         -- JSON com os campos alterados/criados/removidos
);
CREATE INDEX IF NOT EXISTS ix_auditoria_data ON auditoria (data_hora);
CREATE TRIGGER IF NOT EXISTS trg_auditoria_sem_update BEFORE UPDATE ON auditoria
BEGIN SELECT RAISE(ABORT, 'Registros de auditoria não podem ser alterados.'); END;
CREATE TRIGGER IF NOT EXISTS trg_auditoria_sem_delete BEFORE DELETE ON auditoria
BEGIN SELECT RAISE(ABORT, 'Registros de auditoria não podem ser apagados.'); END;

-- Segunda linha de defesa: o banco também impede conflitos de horário
-- (consultas canceladas não ocupam o horário).
CREATE UNIQUE INDEX IF NOT EXISTS ux_profissional_horario
    ON consultas (profissional_id, data, horario) WHERE situacao <> 'Cancelada';
CREATE UNIQUE INDEX IF NOT EXISTS ux_paciente_horario
    ON consultas (paciente_id, data, horario) WHERE situacao <> 'Cancelada';
"""


# ----------------------------------------------------------------------
# Adaptador para que o Turso (libsql) se comporte exatamente como sqlite3.Row
# ----------------------------------------------------------------------
class _LinhaDict(dict):
    """Permite acessar colunas tanto por nome (linha['id']) quanto por índice (linha[0])."""
    def __init__(self, colunas, valores):
        super().__init__(zip(colunas, valores))
        self._valores = tuple(valores)

    def __getitem__(self, chave):
        if isinstance(chave, int):
            return self._valores[chave]
        return super().__getitem__(chave)


class _CursorTurso:
    def __init__(self, cursor):
        self._cur = cursor
        self._linhas = None

    @property
    def lastrowid(self):
        return self._cur.lastrowid

    @property
    def rowcount(self):
        return self._cur.rowcount

    def _converter(self, tupla):
        if tupla is None:
            return None
        colunas = [col[0] for col in (self._cur.description or [])]
        return _LinhaDict(colunas, tupla)

    def fetchone(self):
        return self._converter(self._cur.fetchone())

    def fetchall(self):
        return [self._converter(r) for r in self._cur.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


class _ConexaoTurso:
    """Envolve a conexão libsql-experimental garantindo compatibilidade total com sqlite3."""
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql: str, params=()):
        cur = self._conn.cursor()
        cur.execute(sql, tuple(params))
        return _CursorTurso(cur)

    def executescript(self, script: str):
        for comando in script.split(";"):
            # Remove comentários de linha e espaços
            linhas = [l for l in comando.splitlines() if not l.strip().startswith("--")]
            stmt = "\n".join(linhas).strip()
            if stmt:
                self._conn.execute(stmt)
        self._conn.commit()

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def _migrar_profissionais(conexao) -> None:
    """Garante as colunas-chave e o índice único (nome + especialidade) dos profissionais."""
    colunas = {l["name"] for l in conexao.execute("PRAGMA table_info(profissionais)")}
    for coluna in ("nome_chave", "especialidade_chave"):
        if coluna not in colunas:
            conexao.execute(f"ALTER TABLE profissionais ADD COLUMN {coluna} TEXT")
    pendentes = conexao.execute(
        "SELECT id, nome, especialidade FROM profissionais "
        "WHERE nome_chave IS NULL OR especialidade_chave IS NULL").fetchall()
    for l in pendentes:
        conexao.execute("UPDATE profissionais SET nome_chave=?, especialidade_chave=? WHERE id=?",
                        (chave_nome_profissional(l["nome"]), chave_texto(l["especialidade"]), l["id"]))
    try:
        conexao.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_profissional_nome_especialidade "
                        "ON profissionais (nome_chave, especialidade_chave)")
    except Exception:
        pass
    conexao.commit()


def _dividir_esquema(esquema: str) -> list[str]:
    """Separa comandos SQL respeitando blocos BEGIN ... END de triggers."""
    comandos = []
    atual = []
    dentro_trigger = False
    for linha in esquema.splitlines():
        limpa = linha.strip()
        if not limpa or limpa.startswith("--"):
            continue
        atual.append(linha)
        maiuscula = limpa.upper()
        if maiuscula.startswith("CREATE TRIGGER"):
            dentro_trigger = True
        if dentro_trigger and maiuscula.endswith("END;"):
            comandos.append("\n".join(atual))
            atual = []
            dentro_trigger = False
        elif not dentro_trigger and maiuscula.endswith(";"):
            comandos.append("\n".join(atual))
            atual = []
    return comandos


def conectar(caminho=CAMINHO_PADRAO):
    """Abre (e cria, se necessário) o banco de dados.

    Usa Turso na nuvem se TURSO_DATABASE_URL estiver definida e o caminho não for ':memory:'.
    """
    turso_url = os.environ.get("TURSO_DATABASE_URL", "").strip()
    turso_token = os.environ.get("TURSO_AUTH_TOKEN", "").strip()

    if turso_url and str(caminho) != ":memory:":
        import libsql_experimental as libsql
        # Converte wss:// para libsql:// se necessário
        url_formatada = turso_url.replace("wss://", "libsql://").replace("https://", "libsql://")
        conn_bruta = libsql.connect(database=url_formatada, auth_token=turso_token)
        conexao = _ConexaoTurso(conn_bruta)
        conexao.execute("PRAGMA foreign_keys = ON")
        for stmt in _dividir_esquema(ESQUEMA):
            conexao.execute(stmt)
        conexao.commit()
        _migrar_profissionais(conexao)
        return conexao

    conexao = sqlite3.connect(str(caminho))
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    conexao.executescript(ESQUEMA)
    _migrar_profissionais(conexao)
    return conexao
