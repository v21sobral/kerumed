"""Funções de validação e conversão de dados do Sistema de Marcação de Consultas.

Todas as funções lançam ValidacaoErro com uma mensagem clara para o usuário
quando o dado é inválido.
"""
import re
import unicodedata
from datetime import date, datetime, time

# ---- Regras de negócio definidas pela equipe ------------------------------
HORA_ABERTURA = time(8, 0)       # primeiro horário de atendimento
HORA_FECHAMENTO = time(18, 0)    # o último horário possível é 17:30
INTERVALO_MINUTOS = 30           # consultas de 30 em 30 minutos
DIAS_MAX_ANTECEDENCIA = 365      # não agenda além de 1 ano
DIAS_UTEIS = (0, 1, 2, 3, 4)     # segunda (0) a sexta (4)

SITUACOES = ("Agendada", "Realizada", "Cancelada")
ESPECIALIDADES_SUGERIDAS = (
    "Clínico Geral", "Cardiologia", "Pediatria", "Dermatologia", "Ortopedia",
)


class ValidacaoErro(Exception):
    """Erro de validação/regra de negócio com mensagem amigável (HTTP 400)."""


class NaoEncontradoErro(ValidacaoErro):
    """Registro inexistente (HTTP 404)."""


class NaoAutorizadoErro(ValidacaoErro):
    """Login inválido ou sessão ausente/expirada (HTTP 401)."""


class AcessoNegadoErro(ValidacaoErro):
    """Usuário autenticado sem permissão para a operação (HTTP 403)."""


class LimiteExcedidoErro(ValidacaoErro):
    """Muitas tentativas de login seguidas (HTTP 429)."""


class ConflitoErro(ValidacaoErro):
    """Conflito com dados existentes: CPF repetido, horário ocupado... (HTTP 409)."""


def apenas_digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")


def validar_nome(nome: str, rotulo: str = "O nome") -> str:
    nome = " ".join((nome or "").split())
    if not nome:
        raise ValidacaoErro(f"{rotulo} é obrigatório e não pode ficar vazio.")
    if len(nome) < 3:
        raise ValidacaoErro(f"{rotulo} deve ter pelo menos 3 caracteres.")
    if len(nome) > 100:
        raise ValidacaoErro(f"{rotulo} deve ter no máximo 100 caracteres.")
    return nome


def validar_cpf(cpf: str) -> str:
    """Valida o CPF (obrigatório, 11 dígitos) e devolve só os números.

    Obs.: não conferimos os dígitos verificadores para permitir CPFs de
    exemplo/teste (ex.: 12345678900). Para produção, bastaria acrescentar
    o cálculo dos dígitos aqui.
    """
    if not (cpf or "").strip():
        raise ValidacaoErro("O CPF é obrigatório e não pode ficar vazio.")
    digitos = apenas_digitos(cpf)
    if len(digitos) != 11:
        raise ValidacaoErro("CPF inválido: informe 11 dígitos (ex.: 123.456.789-00).")
    if len(set(digitos)) == 1:
        raise ValidacaoErro("CPF inválido: não pode ter todos os dígitos iguais.")
    return digitos


def formatar_cpf(digitos: str) -> str:
    return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"


def validar_telefone(telefone: str) -> str:
    if not (telefone or "").strip():
        raise ValidacaoErro("O telefone é obrigatório e não pode ficar vazio.")
    digitos = apenas_digitos(telefone)
    if len(digitos) not in (10, 11):
        raise ValidacaoErro("Telefone inválido: informe DDD + número (10 ou 11 dígitos).")
    return digitos


def formatar_telefone(digitos: str) -> str:
    if len(digitos) == 11:
        return f"({digitos[:2]}) {digitos[2:7]}-{digitos[7:]}"
    return f"({digitos[:2]}) {digitos[2:6]}-{digitos[6:]}"


_TITULOS = {"dr", "dra", "doutor", "doutora", "prof", "profa", "professor", "professora"}


def chave_texto(texto: str) -> str:
    """Forma normalizada para comparar textos: sem acentos, sem diferença de caixa e de espaços."""
    sem_acento = "".join(c for c in unicodedata.normalize("NFKD", texto or "") if not unicodedata.combining(c))
    return " ".join(sem_acento.casefold().split())


def chave_nome_profissional(nome: str) -> str:
    """Como chave_texto, mas ignora título e pontuação ('Dr. João Pereira' == 'joao pereira')."""
    palavras = chave_texto(nome).replace(".", " ").split()
    while palavras and palavras[0] in _TITULOS:
        palavras.pop(0)
    return " ".join(palavras) or chave_texto(nome)


def validar_especialidade(especialidade: str) -> str:
    especialidade = " ".join((especialidade or "").split())
    if not especialidade:
        raise ValidacaoErro("A especialidade é obrigatória e não pode ficar vazia.")
    if len(especialidade) > 60:
        raise ValidacaoErro("A especialidade deve ter no máximo 60 caracteres.")
    return especialidade


def converter_data(texto: str, rotulo: str = "A data") -> date:
    """Converte 'dd/mm/aaaa' em date."""
    texto = (texto or "").strip()
    if not texto:
        raise ValidacaoErro(f"{rotulo} é obrigatória e não pode ficar vazia.")
    try:
        return datetime.strptime(texto, "%d/%m/%Y").date()
    except ValueError:
        raise ValidacaoErro(f"{rotulo} é inválida. Use o formato dd/mm/aaaa (ex.: 15/09/2026).")


def validar_nascimento(texto: str, hoje: date) -> date:
    nascimento = converter_data(texto, "A data de nascimento")
    if nascimento > hoje:
        raise ValidacaoErro("A data de nascimento não pode ser no futuro.")
    if nascimento.year < 1900:
        raise ValidacaoErro("A data de nascimento é inválida (anterior a 1900).")
    return nascimento


def converter_horario(texto: str) -> time:
    """Converte 'HH:MM' em time e confere a grade de atendimento."""
    texto = (texto or "").strip()
    if not texto:
        raise ValidacaoErro("O horário é obrigatório e não pode ficar vazio.")
    try:
        horario = datetime.strptime(texto, "%H:%M").time()
    except ValueError:
        raise ValidacaoErro("O horário é inválido. Use o formato HH:MM (ex.: 14:30).")
    if not (HORA_ABERTURA <= horario < HORA_FECHAMENTO):
        raise ValidacaoErro(
            f"Horário fora do atendimento da clínica ({HORA_ABERTURA:%H:%M} às "
            f"{HORA_FECHAMENTO:%H:%M})."
        )
    if horario.minute % INTERVALO_MINUTOS != 0:
        raise ValidacaoErro(
            f"As consultas são marcadas de {INTERVALO_MINUTOS} em {INTERVALO_MINUTOS} minutos "
            "(ex.: 14:00 ou 14:30)."
        )
    return horario


def horarios_disponiveis_na_grade() -> list[str]:
    """Todos os horários da grade de atendimento ('08:00', '08:30', ...)."""
    horarios, minutos = [], HORA_ABERTURA.hour * 60
    fim = HORA_FECHAMENTO.hour * 60
    while minutos < fim:
        horarios.append(f"{minutos // 60:02d}:{minutos % 60:02d}")
        minutos += INTERVALO_MINUTOS
    return horarios


def validar_data_consulta(data_consulta: date, horario: time, agora: datetime) -> None:
    """Regras de data para uma consulta Agendada."""
    if data_consulta.weekday() not in DIAS_UTEIS:
        raise ValidacaoErro("A clínica não atende aos sábados e domingos. Escolha um dia útil.")
    if datetime.combine(data_consulta, horario) <= agora:
        raise ValidacaoErro("Não é possível agendar uma consulta em data/horário que já passou.")
    if (data_consulta - agora.date()).days > DIAS_MAX_ANTECEDENCIA:
        raise ValidacaoErro(
            f"A data é muito distante: agende com no máximo {DIAS_MAX_ANTECEDENCIA} dias de antecedência."
        )


def validar_situacao(situacao: str) -> str:
    if situacao not in SITUACOES:
        raise ValidacaoErro("Situação inválida. Use: " + ", ".join(SITUACOES) + ".")
    return situacao
