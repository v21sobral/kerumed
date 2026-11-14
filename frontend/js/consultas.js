// Aba Consultas: marcação, alteração, cancelamento, mudança de situação e pesquisa.
const Consultas = (() => {
  const { $, el } = UI;
  let config, f, filtros, corpo;
  let pacientes = [], profissionais = [], lista = [];
  let selecionada = null;
  let versaoHorarios = 0;

  function init(cfg) {
    config = cfg;
    f = {
      paciente: $("#con-paciente"), profissional: $("#con-profissional"),
      especialidade: $("#con-especialidade"), data: $("#con-data"), horario: $("#con-horario"),
      situacao: $("#con-situacao"), observacao: $("#con-observacao"),
    };
    filtros = {
      paciente: $("#fil-paciente"), profissional: $("#fil-profissional"), data: $("#fil-data"),
      especialidade: $("#fil-especialidade"), situacao: $("#fil-situacao"),
    };
    corpo = $("#con-tabela");

    UI.aplicarMascara(f.data, "data");
    UI.aplicarMascara(filtros.data, "data");
    UI.preencherSelect(f.horario, config.horarios.map((h) => ({ valor: h, h })), (i) => i.h, "Selecione...");
    UI.preencherSelect(f.situacao, config.situacoes.map((s) => ({ valor: s })), (i) => i.valor, "Selecione...");
    f.situacao.value = "Agendada";
    UI.preencherSelect(filtros.situacao, config.situacoes.map((s) => ({ valor: s })), (i) => i.valor, "Todas");

    f.profissional.addEventListener("change", aoMudarProfissionalOuData);
    f.data.addEventListener("input", aoMudarProfissionalOuData);
    $("#form-consulta").addEventListener("submit", (e) => { e.preventDefault(); agendar(); });
    $("#con-alterar").addEventListener("click", alterar);
    $("#con-cancelar").addEventListener("click", cancelar);
    $("#con-realizar").addEventListener("click", realizar);
    $("#con-limpar").addEventListener("click", limpar);
    $("#form-filtros").addEventListener("submit", (e) => { e.preventDefault(); buscar(); });
    $("#fil-limpar").addEventListener("click", limparFiltros);
    $("#fil-hoje").addEventListener("click", () => {
      const hoje = new Date();
      const dois = (n) => String(n).padStart(2, "0");
      filtros.data.value = `${dois(hoje.getDate())}/${dois(hoje.getMonth() + 1)}/${hoje.getFullYear()}`;
      buscar();
    });
  }

  // ---- listas de apoio (pacientes e profissionais) -------------------------
  async function atualizar() {
    const r = await UI.tentar(async () => {
      [pacientes, profissionais] = await Promise.all([Api.pacientes.listar(), Api.profissionais.listar()]);
    });
    if (r.ok) {
      UI.preencherSelect(f.paciente, pacientes.map((p) => ({ valor: p.id, ...p })),
        (p) => `${p.id} - ${p.nome}`, "Selecione o paciente...");
      UI.preencherSelect(f.profissional, profissionais.map((p) => ({ valor: p.id, ...p })),
        (p) => `${p.id} - ${p.nome} (${p.especialidade})`, "Selecione o profissional...");
      mostrarEspecialidade();
    }
    await buscar();
  }

  function mostrarEspecialidade() {
    const prof = profissionais.find((p) => String(p.id) === f.profissional.value);
    f.especialidade.value = prof ? prof.especialidade : "";
  }

  // Marca na lista de horários os que já estão ocupados para o profissional/data escolhidos.
  async function aoMudarProfissionalOuData() {
    mostrarEspecialidade();
    const versao = ++versaoHorarios;
    let ocupados = new Set();
    if (f.profissional.value && f.data.value.length === 10) {
      try {
        const livres = new Set(await Api.consultas.horariosLivres(f.profissional.value, f.data.value));
        ocupados = new Set(config.horarios.filter((h) => !livres.has(h)));
        // a própria consulta em edição não deve aparecer como "ocupado"
        if (selecionada && String(selecionada.profissional_id) === f.profissional.value
            && selecionada.data === f.data.value) ocupados.delete(selecionada.horario);
      } catch (_) { /* data inválida: apenas não marca nada */ }
    }
    if (versao !== versaoHorarios) return;
    for (const opcao of f.horario.options) {
      if (opcao.value) opcao.textContent = ocupados.has(opcao.value) ? `${opcao.value} — ocupado` : opcao.value;
    }
  }

  // ---- formulário ----------------------------------------------------------
  const numeroOuNulo = (valor) => (valor ? Number(valor) : null);

  const dadosDoForm = () => ({
    paciente_id: numeroOuNulo(f.paciente.value), profissional_id: numeroOuNulo(f.profissional.value),
    data: f.data.value, horario: f.horario.value, observacao: f.observacao.value, situacao: f.situacao.value,
  });

  function selecionar(c) {
    selecionada = c;
    f.paciente.value = String(c.paciente_id);
    f.profissional.value = String(c.profissional_id);
    f.especialidade.value = c.especialidade;
    f.data.value = c.data; f.horario.value = c.horario;
    f.situacao.value = c.situacao; f.observacao.value = c.observacao;
    UI.marcarLinha(corpo, c.id);
    aoMudarProfissionalOuData();
  }

  function limpar() {
    selecionada = null;
    for (const campo of [f.paciente, f.profissional, f.especialidade, f.data, f.horario, f.observacao]) campo.value = "";
    f.situacao.value = "Agendada";
    UI.marcarLinha(corpo, null);
    aoMudarProfissionalOuData();
  }

  // ---- pesquisa e listagem -------------------------------------------------
  async function buscar() {
    const r = await UI.tentar(() => Api.consultas.listar({
      paciente: filtros.paciente.value, profissional: filtros.profissional.value, data: filtros.data.value,
      especialidade: filtros.especialidade.value, situacao: filtros.situacao.value,
    }));
    if (!r.ok) return;
    lista = r.valor;
    const linhas = lista.map((c) => ({
      ...c,
      celulas: [
        el("td", {}, String(c.id)), el("td", {}, c.paciente), el("td", {}, c.profissional),
        el("td", {}, c.especialidade), el("td", {}, c.data), el("td", {}, c.horario),
        el("td", {}, el("span", { class: `selo ${c.situacao}` }, c.situacao)), el("td", {}, c.observacao),
      ],
    }));
    UI.preencherTabela(corpo, linhas, 8, selecionar);
    if (selecionada) UI.marcarLinha(corpo, selecionada.id);
    $("#con-total").textContent = `${lista.length} consulta(s) encontrada(s).`;
  }

  function limparFiltros() {
    for (const campo of Object.values(filtros)) campo.value = "";
    buscar();
  }

  // ---- ações ---------------------------------------------------------------
  async function concluir(acao) {
    const r = await UI.tentar(acao);
    if (!r.ok) return;
    UI.toast(r.valor.mensagem);
    limpar();
    await buscar();
  }

  const exigirSelecao = (texto) => {
    if (selecionada) return true;
    UI.toast(texto, "aviso");
    return false;
  };

  const agendar = () => concluir(() => Api.consultas.criar(dadosDoForm()));

  function alterar() {
    if (exigirSelecao("Selecione uma consulta na lista para alterar."))
      concluir(() => Api.consultas.alterar(selecionada.id, dadosDoForm()));
  }

  async function cancelar() {
    if (!exigirSelecao("Selecione uma consulta na lista para cancelar.")) return;
    const id = selecionada.id;
    if (!(await UI.confirmar("Cancelar esta consulta? O registro será mantido com a situação \"Cancelada\"."))) return;
    concluir(() => Api.consultas.cancelar(id));
  }

  function realizar() {
    if (exigirSelecao("Selecione uma consulta na lista para marcar como realizada."))
      concluir(() => Api.consultas.situacao(selecionada.id, "Realizada"));
  }

  return { init, atualizar };
})();
