// Endereço base da API. Se o frontend for aberto pelo próprio backend (porta 5000),
// usa caminho relativo; se for servido à parte, aponta para o backend local.
const API_BASE = window.location.port === "5000" ? "/api" : "http://127.0.0.1:5000/api";
