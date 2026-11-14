// Aba Auditoria (somente administrador): consulta paginada do histórico de modificações.
const Auditoria = (() => {
  const { $, el } = UI;
  let f, corpo;
  let pagina = 1, paginas = 1;

  function init() {
    f = {
      usuario: $("#aud-usuario"), entidade: $("#aud-entidade"), acao: $("#aud-acao"),
      dataInicial: $("#aud-data-inicial"), dataFinal: $("#aud-data-final"),
    };
    corpo = $("#aud-tabela");
    UI.aplicarMascara(f.dataInicial, "data");
    UI.aplicarMascara(f.dataFinal, "data");
    $("#form-auditoria").addEventListener("submit", (e) => { e.preventDefault(); buscar(1); });
    $("#aud-limpar").addEventListener("click", limparFiltros);
    $("#aud-atualizar").addEventListener("click", () => buscar(pagina));
    $("#aud-anterior").addEventListener("click", () => buscar(pagina - 1));
    $("#aud-proxima").addEventListener("click", () => buscar(pagina + 1));
  }

  function limparFiltros() {
    for (const campo of Object.values(f)) campo.value = "";
    buscar(1);
  }

  function linha(r) {
    const detalhes = r.detalhes.length
      ? el("div", { class: "detalhes" }, r.detalhes.map((d) => el("div", {}, d)))
      : "";
    return el("tr", {},
      el("td", {}, r.data_hora),
      el("td", {}, el("strong", {}, r.nome), el("div", { class: "sub" }, `${r.usuario} · ${r.perfil === "admin" ? "Administrador" : "Recepção"}`)),
      el("td", {}, el("span", { class: `selo-acao ${r.acao}` }, r.acao_rotulo)),
      el("td", {}, `${r.entidade_rotulo}${r.registro_id ? " #" + r.registro_id : ""}`),
      el("td", { class: "desc" }, r.descricao, detalhes),
    );
  }

  async function buscar(numero = 1) {
    const r = await UI.tentar(() => Api.auditoria({
      usuario: f.usuario.value, entidade: f.entidade.value, acao: f.acao.value,
      data_inicial: f.dataInicial.value, data_final: f.dataFinal.value, pagina: Math.max(1, numero),
    }));
    if (!r.ok) return;
    const { registros, total } = r.valor;
    pagina = r.valor.pagina; paginas = r.valor.paginas;
    corpo.replaceChildren();
    if (!registros.length) {
      corpo.append(el("tr", {}, el("td", { class: "vazio", colspan: "5" }, "Nenhum registro encontrado.")));
    } else {
      for (const reg of registros) corpo.append(linha(reg));
    }
    $("#aud-total").textContent = total
      ? `Página ${pagina} de ${paginas} — ${total} registro(s)` : "0 registro(s) encontrado(s).";
    $("#aud-anterior").disabled = pagina <= 1;
    $("#aud-proxima").disabled = pagina >= paginas;
  }

  return { init, atualizar: () => buscar(1) };
})();
