// Aba Pacientes: cadastro, listagem, pesquisa, alteração e remoção.
const Pacientes = (() => {
  const { $, el } = UI;
  let selecionadoId = null;
  let f, corpo;

  function init() {
    f = { nome: $("#pac-nome"), cpf: $("#pac-cpf"), telefone: $("#pac-telefone"), nascimento: $("#pac-nascimento") };
    corpo = $("#pac-tabela");
    UI.aplicarMascara(f.cpf, "cpf");
    UI.aplicarMascara(f.telefone, "telefone");
    UI.aplicarMascara(f.nascimento, "data");
    $("#form-paciente").addEventListener("submit", (e) => { e.preventDefault(); cadastrar(); });
    $("#pac-alterar").addEventListener("click", alterar);
    $("#pac-remover").addEventListener("click", remover);
    $("#pac-limpar").addEventListener("click", limpar);
    $("#form-busca-paciente").addEventListener("submit", (e) => { e.preventDefault(); listar(); });
    $("#pac-todos").addEventListener("click", () => { $("#pac-busca").value = ""; listar(); });
  }

  const dadosDoForm = () => ({
    nome: f.nome.value, cpf: f.cpf.value, telefone: f.telefone.value, data_nascimento: f.nascimento.value,
  });

  async function listar() {
    const r = await UI.tentar(() => Api.pacientes.listar($("#pac-busca").value));
    if (!r.ok) return;
    const linhas = r.valor.map((p) => ({
      ...p,
      celulas: [p.id, p.nome, p.cpf, p.telefone, p.data_nascimento].map((v) => el("td", {}, String(v))),
    }));
    UI.preencherTabela(corpo, linhas, 5, selecionar);
    if (selecionadoId !== null) UI.marcarLinha(corpo, selecionadoId);
    $("#pac-total").textContent = `${linhas.length} paciente(s) encontrado(s).`;
  }

  function selecionar(p) {
    selecionadoId = p.id;
    f.nome.value = p.nome; f.cpf.value = p.cpf;
    f.telefone.value = p.telefone; f.nascimento.value = p.data_nascimento;
    UI.marcarLinha(corpo, p.id);
  }

  function limpar() {
    selecionadoId = null;
    for (const campo of Object.values(f)) campo.value = "";
    UI.marcarLinha(corpo, null);
  }

  async function cadastrar() {
    const r = await UI.tentar(() => Api.pacientes.criar(dadosDoForm()));
    if (!r.ok) return;
    UI.toast(r.valor.mensagem);
    limpar(); listar();
  }

  async function alterar() {
    if (selecionadoId === null) return UI.toast("Selecione um paciente na lista para alterar.", "aviso");
    const r = await UI.tentar(() => Api.pacientes.alterar(selecionadoId, dadosDoForm()));
    if (!r.ok) return;
    UI.toast(r.valor.mensagem);
    limpar(); listar();
  }

  async function remover() {
    if (selecionadoId === null) return UI.toast("Selecione um paciente na lista para remover.", "aviso");
    if (!(await UI.confirmar(`Remover o paciente "${f.nome.value}"?`))) return;
    const r = await UI.tentar(() => Api.pacientes.remover(selecionadoId));
    if (!r.ok) return;
    UI.toast(r.valor.mensagem);
    limpar(); listar();
  }

  return { init, atualizar: listar };
})();
