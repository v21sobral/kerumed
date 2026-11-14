const Login = (() => {
  const tela = document.getElementById("login-screen");
  const appShell = document.getElementById("app-shell");
  const form = document.getElementById("form-login");
  const usuarioInput = document.getElementById("login-usuario");
  const senhaInput = document.getElementById("login-senha");
  const logoutBtn = document.getElementById("logout-btn");
  const campos = [usuarioInput, senhaInput];

  // Impede que o navegador (ou o HTML) preencha usuário e senha sozinhos
  form.setAttribute("autocomplete", "off");
  usuarioInput.setAttribute("autocomplete", "off");
  senhaInput.setAttribute("autocomplete", "new-password");
  for (const campo of campos) {
    campo.addEventListener("focus", () => { campo.readOnly = false; });
  }

  function limparCampos() {
    usuarioInput.value = "";
    senhaInput.value = "";
  }

  function mostrar() {
    tela.hidden = false;
    appShell.hidden = true;
    limparCampos();
    for (const campo of campos) campo.readOnly = true;   // só libera quando a pessoa clicar no campo
    // limpa de novo caso o navegador tente autopreencher logo depois
    for (const ms of [50, 300, 1000]) {
      setTimeout(() => {
        if (!tela.hidden && !campos.includes(document.activeElement)) limparCampos();
      }, ms);
    }
  }

  function esconder() {
    tela.hidden = true;
    appShell.hidden = false;
  }

  const usuarioLogado = () => Api.usuario();

  async function entrar(event) {
    event.preventDefault();
    const usuario = usuarioInput.value.trim();
    const senha = senhaInput.value;
    if (!usuario || !senha) {
      UI.toast("Informe usuário e senha para continuar.", "erro");
      return;
    }

    const resultado = await UI.tentar(() => Api.login({ usuario, senha }));
    if (!resultado.ok) return;

    Api.salvarSessao(resultado.valor.token, resultado.valor.usuario);
    limparCampos();
    esconder();
    UI.toast(`Bem-vindo, ${resultado.valor.usuario.nome}!`, "sucesso");
    if (window.__inicializarSistema) window.__inicializarSistema();
  }

  function sair() {
    Api.limparSessao();
    mostrar();
  }

  // Ao voltar para a página pelo histórico do navegador, os campos também ficam vazios
  window.addEventListener("pageshow", () => { if (!tela.hidden) limparCampos(); });

  form.addEventListener("submit", entrar);
  logoutBtn.addEventListener("click", sair);

  return { mostrar, esconder, usuarioLogado, sair };
})();