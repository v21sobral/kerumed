// Camada de comunicação com o backend (fetch → JSON).
const Api = (() => {
  const CHAVE_TOKEN = "clinica.token";
  const CHAVE_USUARIO = "clinica.usuario";

  // ---- sessão (token devolvido pelo /login e enviado em todas as requisições) ----
  const token = () => localStorage.getItem(CHAVE_TOKEN);
  function salvarSessao(novoToken, usuario) {
    localStorage.setItem(CHAVE_TOKEN, novoToken);
    localStorage.setItem(CHAVE_USUARIO, JSON.stringify(usuario));
  }
  function limparSessao() {
    localStorage.removeItem(CHAVE_TOKEN);
    localStorage.removeItem(CHAVE_USUARIO);
  }
  function usuario() {
    try {
      const u = JSON.parse(localStorage.getItem(CHAVE_USUARIO) || "null");
      return token() && u && u.usuario ? u : null;
    } catch (_) {
      return null;
    }
  }

  async function requisicao(metodo, caminho, corpo) {
    let resposta;
    const cabecalhos = {};
    if (corpo) cabecalhos["Content-Type"] = "application/json";
    if (token()) cabecalhos["Authorization"] = `Bearer ${token()}`;
    try {
      resposta = await fetch(API_BASE + caminho, {
        method: metodo,
        headers: cabecalhos,
        body: corpo ? JSON.stringify(corpo) : undefined,
      });
    } catch (_) {
      throw new Error("Não foi possível conectar ao servidor. Verifique se o backend está em execução.");
    }
    let dados = {};
    try { dados = await resposta.json(); } catch (_) { /* resposta sem JSON */ }
    if (!resposta.ok) {
      if (resposta.status === 401 && caminho !== "/login") {
        limparSessao();                                       // sessão expirada/inválida
        document.dispatchEvent(new CustomEvent("sessao-expirada"));
      }
      const erro = new Error(dados.erro || "Ocorreu um erro inesperado. Tente novamente.");
      erro.status = resposta.status;
      throw erro;
    }
    if (metodo !== "GET" && caminho !== "/login") {
      document.dispatchEvent(new CustomEvent("dados-alterados"));   // atualiza o dashboard
    }
    return dados;
  }

  function consulta(params) {
    const p = new URLSearchParams();
    for (const [k, v] of Object.entries(params || {})) if (v) p.set(k, v);
    const texto = p.toString();
    return texto ? "?" + texto : "";
  }

  return {
    token, usuario, salvarSessao, limparSessao,
    login: (d) => requisicao("POST", "/login", d),
    me: () => requisicao("GET", "/me"),
    trocarSenha: (senhaAtual, novaSenha) =>
      requisicao("POST", "/me/senha", { senha_atual: senhaAtual, nova_senha: novaSenha }),
    auditoria: (filtros) => requisicao("GET", "/auditoria" + consulta(filtros)),
    usuarios: {
      listar: () => requisicao("GET", "/usuarios"),
      criar: (d) => requisicao("POST", "/usuarios", d),
      remover: (id) => requisicao("DELETE", `/usuarios/${id}`),
    },
    dashboard: () => requisicao("GET", "/dashboard"),
    config: () => requisicao("GET", "/config"),
    pacientes: {
      listar: (busca) => requisicao("GET", "/pacientes" + consulta({ busca })),
      criar: (d) => requisicao("POST", "/pacientes", d),
      alterar: (id, d) => requisicao("PUT", `/pacientes/${id}`, d),
      remover: (id) => requisicao("DELETE", `/pacientes/${id}`),
    },
    profissionais: {
      listar: (busca) => requisicao("GET", "/profissionais" + consulta({ busca })),
      criar: (d) => requisicao("POST", "/profissionais", d),
      alterar: (id, d) => requisicao("PUT", `/profissionais/${id}`, d),
      remover: (id) => requisicao("DELETE", `/profissionais/${id}`),
    },
    consultas: {
      listar: (filtros) => requisicao("GET", "/consultas" + consulta(filtros)),
      criar: (d) => requisicao("POST", "/consultas", d),
      alterar: (id, d) => requisicao("PUT", `/consultas/${id}`, d),
      cancelar: (id) => requisicao("POST", `/consultas/${id}/cancelar`),
      situacao: (id, situacao) => requisicao("PATCH", `/consultas/${id}/situacao`, { situacao }),
      horariosLivres: (profissionalId, data) =>
        requisicao("GET", "/horarios-livres" + consulta({ profissional_id: profissionalId, data })),
    },
  };
})();
