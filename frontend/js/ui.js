// Utilitários de interface: criação de elementos, mensagens, confirmação e máscaras.
const UI = (() => {
  const $ = (seletor, raiz = document) => raiz.querySelector(seletor);

  // Cria elementos sem usar innerHTML (evita injeção de HTML pelos dados digitados).
  function el(tag, props = {}, ...filhos) {
    const e = document.createElement(tag);
    for (const [chave, valor] of Object.entries(props)) {
      if (chave === "class") e.className = valor;
      else if (chave.startsWith("on")) e.addEventListener(chave.slice(2), valor);
      else e.setAttribute(chave, valor);
    }
    for (const filho of filhos.flat()) e.append(filho instanceof Node ? filho : document.createTextNode(filho ?? ""));
    return e;
  }

  function toast(mensagem, tipo = "sucesso") {
    const aviso = el("div", { class: `toast ${tipo}`, role: tipo === "erro" ? "alert" : "status" }, mensagem);
    $("#toasts").append(aviso);
    setTimeout(() => aviso.remove(), tipo === "sucesso" ? 3500 : 6500);
  }

  function confirmar(mensagem) {
    return new Promise((resolver) => {
      const dialogo = $("#dialogo");
      $("#dialogo-texto").textContent = mensagem;
      const fechar = (resposta) => { dialogo.close(); resolver(resposta); };
      $("#dialogo-sim").onclick = () => fechar(true);
      $("#dialogo-nao").onclick = () => fechar(false);
      dialogo.oncancel = () => resolver(false);
      dialogo.showModal();
    });
  }

  // Executa uma ação assíncrona mostrando erros ao usuário. Retorna {ok, valor}.
  async function tentar(acao) {
    try {
      return { ok: true, valor: await acao() };
    } catch (erro) {
      toast(erro.message, "erro");
      return { ok: false };
    }
  }

  function preencherSelect(select, itens, rotulo, vazio) {
    const anterior = select.value;
    select.replaceChildren(el("option", { value: "" }, vazio));
    for (const item of itens) select.append(el("option", { value: String(item.valor) }, rotulo(item)));
    if ([...select.options].some((o) => o.value === anterior)) select.value = anterior;
  }

  function preencherTabela(corpo, linhas, colunas, aoClicar) {
    corpo.replaceChildren();
    if (!linhas.length) {
      corpo.append(el("tr", {}, el("td", { class: "vazio", colspan: String(colunas) }, "Nenhum registro encontrado.")));
      return;
    }
    for (const linha of linhas) {
      const tr = el("tr", { "data-id": String(linha.id), onclick: () => aoClicar(linha, tr) }, linha.celulas);
      corpo.append(tr);
    }
  }

  function marcarLinha(corpo, id) {
    for (const tr of corpo.querySelectorAll("tr")) tr.classList.toggle("selecionada", tr.dataset.id === String(id));
  }

  // ---- máscaras de digitação ----
  const apenasDigitos = (t) => t.replace(/\D/g, "");
  const formatadores = {
    cpf(t) {
      const d = apenasDigitos(t).slice(0, 11);
      return d.replace(/^(\d{3})(\d)/, "$1.$2").replace(/^(\d{3})\.(\d{3})(\d)/, "$1.$2.$3")
              .replace(/\.(\d{3})(\d)/, ".$1-$2");
    },
    telefone(t) {
      const d = apenasDigitos(t).slice(0, 11);
      if (d.length <= 2) return d ? `(${d}` : "";
      const meio = d.length > 10 ? 7 : 6;
      return `(${d.slice(0, 2)}) ${d.slice(2, meio)}${d.length > meio ? "-" + d.slice(meio) : ""}`;
    },
    data(t) {
      const d = apenasDigitos(t).slice(0, 8);
      return d.replace(/^(\d{2})(\d)/, "$1/$2").replace(/^(\d{2})\/(\d{2})(\d)/, "$1/$2/$3");
    },
  };
  function aplicarMascara(input, tipo) {
    input.addEventListener("input", () => { input.value = formatadores[tipo](input.value); });
  }

  return { $, el, toast, confirmar, tentar, preencherSelect, preencherTabela, marcarLinha, aplicarMascara, formatadores };
})();
