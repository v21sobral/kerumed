"""Camada de acesso ao banco de dados (SQLite)."""
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


def _migrar_profissionais(conexao: sqlite3.Connection) -> None:
    """Garante as colunas-chave e o índice único (nome + especialidade) dos profissionais.

    Funciona também em bancos criados antes desta regra. Se já houver duplicados antigos,
    o índice não é criado, mas o serviço continua impedindo novos duplicados.
    """
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
    except sqlite3.IntegrityError:
        pass
    conexao.commit()


def conectar(caminho=CAMINHO_PADRAO) -> sqlite3.Connection:
    """Abre (e cria, se necessário) o banco de dados. Use ':memory:' nos testes."""
    conexao = sqlite3.connect(str(caminho))
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    conexao.executescript(ESQUEMA)
    _migrar_profissionais(conexao)
    return conexao
