# Sistema de Marcação de Consultas (versão web)

Aplicação web com **backend em Python (Flask + SQLite)** e **frontend em HTML/CSS/JavaScript puro**.

```
01_Sistema/
├─ backend/                 API REST em Python
│  ├─ app.py                rotas da API (+ entrega o frontend)
│  ├─ servicos.py           regras de negócio e CRUD
│  ├─ validacoes.py         validações e regras da clínica
│  ├─ banco.py              criação do banco SQLite
│  ├─ autenticacao.py       login, hash de senha, token, perfis e usuários
│  ├─ auditoria.py          registro e consulta do histórico de modificações
│  ├─ dados_exemplo.py      (opcional) dados para demonstração
│  ├─ requirements.txt
│  └─ testes/               testes automatizados (serviço + API)
└─ frontend/                interface no navegador
   ├─ index.html
   ├─ css/estilo.css
   └─ js/                   config, api, ui, login, pacientes, profissionais, usuarios, auditoria, consultas, app
```

## Como executar
Requer Python 3.10+.
```
cd 01_Sistema/backend
python -m venv .venv                 # opcional, recomendado
.venv\Scripts\activate               # Windows   (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
python app.py
```
Abra **http://127.0.0.1:5000** no navegador. O banco `clinica.db` é criado sozinho na primeira execução.

**Login inicial:** usuário `admin`, senha `admin123`. Para usar outra senha, defina `ADMIN_USER` e `ADMIN_PASSWORD` **antes da primeira execução** (o administrador só é criado quando o banco ainda não tem usuários).

- Dados de exemplo (opcional, útil para as capturas de tela): `python dados_exemplo.py`
- Outra porta: defina a variável `PORT` (ex.: `set PORT=8000` no Windows).
- Modo de desenvolvimento com recarga automática: `set FLASK_DEBUG=1` (desligado por padrão).
- Frontend separado (opcional): com o backend rodando, sirva a pasta `frontend` com
  `python -m http.server 8080` e abra http://127.0.0.1:8080 — o `js/config.js` já aponta para a API em `:5000`.

## Testes automatizados (107 testes)
```
cd backend
python -m unittest discover -s testes -v
```

## API REST
Erros retornam JSON `{"erro": "mensagem"}`: **400** validação, **401** sem login/sessão inválida, **403** sem permissão para o perfil, **404** não encontrado, **409** conflito (CPF repetido, horário ocupado), **429** muitas tentativas de login.

Todas as rotas, exceto `POST /api/login`, exigem o cabeçalho `Authorization: Bearer <token>` (o token vale 8 horas).

| Método | Rota | Descrição |
|---|---|---|
| GET / POST | `/api/pacientes` | listar (`?busca=`) / cadastrar |
| GET / PUT / DELETE | `/api/pacientes/<id>` | consultar / alterar / remover |
| GET / POST | `/api/profissionais` | listar (`?busca=`) / cadastrar (**409** se já existir o mesmo nome com a mesma especialidade) |
| GET / PUT / DELETE | `/api/profissionais/<id>` | consultar / alterar / remover |
| GET / POST | `/api/consultas` | pesquisar (`?paciente=&profissional=&data=&especialidade=&situacao=`) / agendar |
| GET / PUT | `/api/consultas/<id>` | consultar / alterar (inclusive data e horário) |
| POST | `/api/consultas/<id>/cancelar` | cancelar (mantém o registro) |
| PATCH | `/api/consultas/<id>/situacao` | Agendada / Realizada / Cancelada |
| GET | `/api/horarios-livres?profissional_id=&data=` | horários livres do profissional |
| GET | `/api/config` | especialidades, situações e grade de horários |
| POST | `/api/login` | autentica (`usuario`, `senha`) e devolve o token |
| GET | `/api/me` | usuário da sessão atual (com perfil) |
| POST | `/api/me/senha` | troca a própria senha (`senha_atual`, `nova_senha`) |
| GET / POST | `/api/usuarios` | listar / cadastrar usuário *(somente admin)* |
| DELETE | `/api/usuarios/<id>` | remover usuário *(somente admin)* |
| GET | `/api/auditoria` | histórico de modificações *(somente admin)*; filtros `usuario`, `entidade`, `acao`, `data_inicial`, `data_final` (dd/mm/aaaa), `pagina`, `por_pagina` |
| GET | `/api/dashboard` | totais do painel (pacientes, profissionais, consultas, agendadas, realizadas, canceladas, hoje) |

## Regras definidas pela equipe
- Atendimento de **segunda a sexta, das 08:00 às 18:00**, de **30 em 30 minutos** (último horário: 17:30).
- Não agenda em data/horário passado nem com mais de 365 dias de antecedência.
- Um profissional não pode ter duas consultas no mesmo dia e horário; o paciente também não.
- Consulta cancelada **permanece registrada** como "Cancelada" e libera o horário.
- Consulta cancelada não pode ser editada (para remarcar, faça novo agendamento); consulta realizada não pode ser cancelada.
- Paciente/profissional com consultas registradas não podem ser removidos (preserva o histórico).
- CPF: 11 dígitos e único por paciente (dígitos verificadores não são conferidos, para aceitar CPFs de exemplo).
- Telefone: DDD + número (10 ou 11 dígitos). Nascimento: dd/mm/aaaa, não pode ser futuro.

## Perfis de acesso
| Perfil | Pode | Não pode |
|---|---|---|
| **Administrador** (`admin`) | Tudo: cadastros, consultas, remover pacientes/profissionais, gerenciar usuários (aba **Usuários**) e consultar a **Auditoria** | Remover o próprio usuário ou o último administrador |
| **Recepção** (`recepcao`) | Cadastrar/alterar pacientes e profissionais, marcar/alterar/cancelar consultas, pesquisar, ver o painel e trocar a própria senha | Remover pacientes e profissionais; acessar a gestão de usuários e a auditoria |

- O usuário inicial é o `admin` (senha `admin123`, ou o definido em `ADMIN_USER` / `ADMIN_PASSWORD`). Ele cria os demais na aba **Usuários**.
- As permissões são conferidas **no backend** em toda requisição (o perfil é lido do banco, então remover um usuário ou mudar seu perfil vale na hora); esconder botões na tela é só conveniência.
- Qualquer usuário troca a própria senha em **Minha senha** (mínimo de 6 caracteres).

## Auditoria
A aba **Auditoria** (somente administrador) lista, do mais recente para o mais antigo, tudo o que foi **cadastrado, alterado, cancelado ou removido** por qualquer usuário (inclusive o administrador): usuário responsável (nome, acesso e perfil), data e hora, ação, tipo/código do registro e descrição, com o **valor anterior e o novo** nas alterações. Há filtros por usuário, tipo, ação e período, e paginação.

- Só operações **concluídas com sucesso** geram registro; consultas, erros de validação e alterações sem nenhuma mudança real não geram.
- Senhas nunca são gravadas (nem as novas, nem os hashes).
- Os registros são somente de inclusão: a API não tem rota para alterá-los ou apagá-los e o banco bloqueia `UPDATE` e `DELETE` na tabela (triggers). Eles também sobrevivem à remoção do usuário ou do item auditado.
- O registro é gravado logo depois da operação; se a gravação falhar, o erro vai para o log do servidor e a operação já concluída não é desfeita.

## Profissionais duplicados
Não é possível cadastrar (nem alterar para) um profissional com o **mesmo nome e a mesma especialidade** de outro. A comparação ignora maiúsculas/minúsculas, acentos, espaços extras e o título (Dr./Dra.): `Dr. João Pereira` e `joao  pereira` na mesma especialidade são o mesmo profissional. O mesmo nome com especialidade diferente é permitido. A regra existe no serviço e como índice único no banco; bancos antigos são migrados automaticamente (se já tiverem duplicados, eles são mantidos, mas novos duplicados continuam bloqueados).

## Segurança
- Senhas guardadas apenas como hash (scrypt); o token é assinado com uma chave secreta gerada na primeira execução (`backend/.secret_key`) ou definida em `CLINICA_SECRET_KEY`.
- 5 senhas erradas seguidas em 5 minutos bloqueiam o login temporariamente.
- Não versione `clinica.db` nem `.secret_key` (já estão no `.gitignore`).
