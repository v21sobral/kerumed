"""(Opcional) Carrega dados de exemplo para demonstração e capturas de tela.

Uso:  python dados_exemplo.py
As consultas são criadas em dias úteis futuros, a partir de hoje.
"""
from datetime import date, timedelta

import banco
from servicos import ClinicaService


def proximo_dia_util(a_partir_de: date, dias: int) -> str:
    dia = a_partir_de
    while dias > 0 or dia.weekday() > 4:
        dia += timedelta(days=1)
        if dia.weekday() <= 4:
            dias -= 1
    return dia.strftime("%d/%m/%Y")


def main():
    s = ClinicaService(banco.conectar())
    if s.listar_pacientes() or s.listar_profissionais():
        print("O banco já possui dados; nada foi alterado.")
        return
    maria = s.cadastrar_paciente("Maria Santos", "123.456.789-00", "(71) 99999-9999", "10/05/1990")
    ana = s.cadastrar_paciente("Ana Souza", "987.654.321-00", "(71) 3333-4444", "01/02/1985")
    carlos = s.cadastrar_paciente("Carlos Lima", "111.222.333-44", "(71) 98888-7777", "23/11/2001")
    joao = s.cadastrar_profissional("Dr. João Pereira", "Cardiologia", "(71) 98777-6666")
    bia = s.cadastrar_profissional("Dra. Beatriz Rocha", "Pediatria", "(71) 97666-5555")
    s.cadastrar_profissional("Dr. Paulo Mendes", "Clínico Geral", "(71) 96555-4444")

    hoje = date.today()
    s.agendar_consulta(maria, joao, proximo_dia_util(hoje, 2), "14:00", "Retorno - exames")
    s.agendar_consulta(ana, bia, proximo_dia_util(hoje, 3), "09:30", "Primeira consulta")
    cancelada = s.agendar_consulta(carlos, joao, proximo_dia_util(hoje, 4), "10:00")
    s.cancelar_consulta(cancelada)
    print("Dados de exemplo carregados.")


if __name__ == "__main__":
    main()
