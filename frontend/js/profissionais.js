// Aba Profissionais: cadastro, listagem, pesquisa, alteração e remoção.
const Profissionais = (() => {
  const { $, el } = UI;
  let selecionadoId = null;
  let f, corpo;

  function init() {
    f = { nome: $("#prof-nome"), especialidade: $("#prof-especialidade"), telefone: $("#prof-telefone") };
    corpo = $("#prof-tabela");
    UI.aplicarMascara(f.telefone, "telefone");
    $("#form-profissional").addEventListener("submit", (e) => { e.preventDefault(); cadastrar(); });
    $("#prof-alterar").addEventListener("click", alterar);
    $("#prof-remover").addEventListener("click", remover);
    $("#prof-limpar").addEventListener("click", limpar);
    $("#form-busca-profissional").addEventListener("submit", (e) => { e.preventDefault(); listar(); });
    $("#prof-todos").addEventListener("click", () => { $("#prof-busca").value = ""; listar(); });
  }

  const dadosDoForm = () => ({
    nome: f.nome.value, especialidade: f.especialidade.value, telefone: f.telefone.value,
  });

  async function listar() {
    const r = await UI.tentar(() => Api.profissionais.listar($("#prof-busca").value));
    if (!r.ok) return;
    const linhas = r.valor.map((p) => ({
      ...p,
      celulas: [p.id, p.nome, p.especialidade, p.telefone].map((v) => el("td", {}, String(v))),
    }));
    UI.preencherTabela(corpo, linhas, 4, selecionar);
    if (selecionadoId !== null) UI.marcarLinha(corpo, selecionadoId);
    $("#prof-total").textContent = `${linhas.length} profissional(is) encontrado(s).`;
  }

  function selecionar(p) {
    selecionadoId = p.id;
    f.nome.value = p.nome; f.especialidade.value = p.especialidade; f.telefone.value = p.telefone;
    UI.marcarLinha(corpo, p.id);
  }

  function limpar() {
    selecionadoId = null;
    for (const campo of Object.values(f)) campo.value = "";
    UI.marcarLinha(corpo, null);
  }

  async function cadastrar() {
    const r = await UI.tentar(() => Api.profissionais.criar(dadosDoForm()));
    if (!r.ok) return;
    UI.toast(r.valor.mensagem);
    limpar(); listar();
  }

  async function alterar() {
    if (selecionadoId === null) return UI.toast("Selecione um profissional na lista para alterar.", "aviso");
    const r = await UI.tentar(() => Api.profissionais.alterar(selecionadoId, dadosDoForm()));
    if (!r.ok) return;
    UI.toast(r.valor.mensagem);
    limpar(); listar();
  }

  async function remover() {
    if (selecionadoId === null) return UI.toast("Selecione um profissional na lista para remover.", "aviso");
    if (!(await UI.confirmar(`Remover o profissional "${f.nome.value}"?`))) return;
    const r = await UI.tentar(() => Api.profissionais.remover(selecionadoId));
    if (!r.ok) return;
    UI.toast(r.valor.mensagem);
    limpar(); listar();
  }

  return { init, atualizar: listar };
})();
