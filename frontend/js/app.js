// Inicialização: sessão, tema, dashboard, abas e módulos.
let sistemaInicializado = false;
let abaAtual = "consultas";
let modulos = {};

const Dashboard = {
  async atualizar() {
    if (!Api.usuario()) return;
    try {
      const r = await Api.dashboard();
      for (const [chave, valor] of Object.entries(r)) {
        const campo = document.getElementById(`dash-${chave}`);
        if (campo) campo.textContent = String(valor);
      }
    } catch (_) {
      // o painel é só informativo; erros reais já aparecem nas telas principais
    }
  },
};

function aplicarTema(tema) {
  const resolved = tema === "dark" ? "dark" : "light";
  document.body.setAttribute("data-theme", resolved);
  localStorage.setItem("clinica.theme", resolved);
  const toggle = document.getElementById("theme-toggle");
  if (toggle) toggle.textContent = resolved === "dark" ? "☀️" : "🌙";
}

// Mostra/esconde o que o perfil logado pode usar (o backend também confere cada requisição).
function aplicarPerfil() {
  const usuario = Api.usuario();
  const admin = !!usuario && usuario.perfil === "admin";
  const rotulo = usuario ? (usuario.perfil_rotulo || usuario.perfil) : "";
  const etiqueta = document.getElementById("usuario-perfil");
  if (etiqueta) etiqueta.textContent = rotulo ? `Sessão · ${rotulo}` : "Sessão";
  document.getElementById("aba-usuarios-botao").hidden = !admin;
  document.getElementById("aba-auditoria-botao").hidden = !admin;
  for (const id of ["pac-remover", "prof-remover"]) document.getElementById(id).hidden = !admin;
  if (!admin && (abaAtual === "usuarios" || abaAtual === "auditoria")) abaAtual = "consultas";
}

function abrirAba(nome) {
  abaAtual = nome;
  for (const botao of document.querySelectorAll(".aba")) {
    botao.setAttribute("aria-selected", String(botao.dataset.aba === nome));
  }
  for (const chave of Object.keys(modulos)) UI.$(`#aba-${chave}`).hidden = chave !== nome;
  modulos[nome].atualizar();   // recarrega os dados ao abrir a aba
  Dashboard.atualizar();
}

async function inicializarSistema() {
  const chip = document.getElementById("usuario-logado");
  const usuario = Api.usuario();
  if (chip && usuario) chip.textContent = usuario.nome || usuario.usuario;
  aplicarPerfil();

  if (!sistemaInicializado) {            // só monta os módulos na primeira vez
    sistemaInicializado = true;
    let config = { especialidades: [], situacoes: ["Agendada", "Realizada", "Cancelada"], horarios: [] };
    const r = await UI.tentar(() => Api.config());
    if (r.ok) config = r.valor;

    const lista = UI.$("#lista-especialidades");
    for (const nome of config.especialidades) lista.append(UI.el("option", { value: nome }));

    Pacientes.init();
    Profissionais.init();
    Usuarios.init();
    Auditoria.init();
    MinhaSenha.init();
    Consultas.init(config);
    modulos = { consultas: Consultas, pacientes: Pacientes, profissionais: Profissionais, usuarios: Usuarios, auditoria: Auditoria };

    for (const botao of document.querySelectorAll(".aba")) {
      botao.addEventListener("click", () => abrirAba(botao.dataset.aba));
    }
  }
  abrirAba(abaAtual);                    // em novos logins, apenas recarrega os dados
}

window.__inicializarSistema = inicializarSistema;

document.addEventListener("DOMContentLoaded", async () => {
  aplicarTema(localStorage.getItem("clinica.theme") || "dark");
  document.getElementById("theme-toggle")?.addEventListener("click", () => {
    aplicarTema(document.body.getAttribute("data-theme") === "dark" ? "light" : "dark");
  });

  // O dashboard acompanha qualquer cadastro/alteração/remoção feita nas telas.
  document.addEventListener("dados-alterados", () => Dashboard.atualizar());
  // Token vencido ou inválido: volta para a tela de login.
  document.addEventListener("sessao-expirada", () => Login.mostrar());

  if (!Api.usuario()) {
    Login.mostrar();
    return;
  }
  // Confere com o servidor se a sessão guardada ainda vale.
  const sessao = await UI.tentar(() => Api.me());
  if (!sessao.ok) {
    Api.limparSessao();
    Login.mostrar();
    return;
  }
  Api.salvarSessao(Api.token(), sessao.valor.usuario);   // perfil atualizado pelo servidor
  Login.esconder();
  inicializarSistema();
});
