// Aba Usuários (somente administrador) e janela "Minha senha" (todos os perfis).
const Usuarios = (() => {
  const { $, el } = UI;
  let selecionado = null;   // { id, usuario }
  let f, corpo;

  function init() {
    f = { nome: $("#usu-nome"), usuario: $("#usu-usuario"), senha: $("#usu-senha"), perfil: $("#usu-perfil") };
    corpo = $("#usu-tabela");
    $("#form-usuario").addEventListener("submit", (e) => { e.preventDefault(); cadastrar(); });
    $("#usu-remover").addEventListener("click", remover);
    $("#usu-limpar").addEventListener("click", limpar);
  }

  async function listar() {
    const r = await UI.tentar(() => Api.usuarios.listar());
    if (!r.ok) return;
    const linhas = r.valor.map((u) => ({
      ...u,
      celulas: [u.id, u.nome, u.usuario, u.perfil_rotulo].map((v) => el("td", {}, String(v))),
    }));
    UI.preencherTabela(corpo, linhas, 4, (u) => { selecionado = u; UI.marcarLinha(corpo, u.id); });
    if (selecionado) UI.marcarLinha(corpo, selecionado.id);
    $("#usu-total").textContent = `${linhas.length} usuário(s) cadastrado(s).`;
  }

  function limpar() {
    selecionado = null;
    f.nome.value = ""; f.usuario.value = ""; f.senha.value = ""; f.perfil.value = "recepcao";
    UI.marcarLinha(corpo, null);
  }

  async function cadastrar() {
    const dados = { nome: f.nome.value, usuario: f.usuario.value, senha: f.senha.value, perfil: f.perfil.value };
    const r = await UI.tentar(() => Api.usuarios.criar(dados));
    if (!r.ok) return;
    UI.toast(r.valor.mensagem);
    limpar(); listar();
  }

  async function remover() {
    if (!selecionado) return UI.toast("Selecione um usuário na lista para remover.", "aviso");
    if (!(await UI.confirmar(`Remover o usuário "${selecionado.usuario}"? Ele perderá o acesso ao sistema.`))) return;
    const id = selecionado.id;
    const r = await UI.tentar(() => Api.usuarios.remover(id));
    if (!r.ok) return;
    UI.toast(r.valor.mensagem);
    limpar(); listar();
  }

  return { init, atualizar: listar };
})();

const MinhaSenha = (() => {
  const { $ } = UI;

  function init() {
    const dialogo = $("#dialogo-senha");
    const campos = ["#senha-atual", "#senha-nova", "#senha-confirmar"].map((s) => $(s));
    const limpar = () => campos.forEach((c) => { c.value = ""; });
    $("#senha-btn").addEventListener("click", () => { limpar(); dialogo.showModal(); campos[0].focus(); });
    $("#senha-cancelar").addEventListener("click", () => { limpar(); dialogo.close(); });
    $("#form-senha").addEventListener("submit", async (e) => {
      e.preventDefault();
      const [atual, nova, confirmar] = campos.map((c) => c.value);
      if (nova !== confirmar) return UI.toast("A confirmação não confere com a nova senha.", "erro");
      const r = await UI.tentar(() => Api.trocarSenha(atual, nova));
      if (!r.ok) return;
      UI.toast(r.valor.mensagem);
      limpar(); dialogo.close();
    });
  }

  return { init };
})();
