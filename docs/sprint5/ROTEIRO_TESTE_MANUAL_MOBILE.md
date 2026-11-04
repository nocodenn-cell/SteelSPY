# Roteiro de teste manual em celular real — recebimento de ponta a ponta

**Estado:** pendente de execução física. Nada aqui foi validado em aparelho real
até que alguém execute este roteiro e registre as evidências. Os testes
automatizados cobrem a API, o isolamento e o contrato do PWA; eles não provam
câmera, permissão do navegador nem comportamento de rede do celular.

**Objetivo:** provar, no portão, que o operador consegue receber uma carga,
fotografar, ver a divergência e que a construtora vizinha não acessa nada.

**Banco:** `stellspy_demo` local, criado por `backend/scripts/seed_demo.py`.
Não use o projeto Supabase oficial para este roteiro e não altere dados reais.

---

## 1. Preparação (PC, Windows/PowerShell)

```powershell
# 1. Banco local descartável com duas construtoras sintéticas
docker start stellspy-pg
cd backend
..\.venv\Scripts\python.exe scripts\seed_demo.py
```

O script imprime os logins e a senha de demonstração. São sintéticos:

| Papel | Login | Pode |
|-------|-------|------|
| Engenharia/admin | `eng@alfa.demo` | pedido, vínculo NF-e, dossiê |
| Fiscal (portão) | `almox@alfa.demo` | receber, contar, fotografar |
| Auditoria | `auditor@alfa.demo` | ler tudo, baixar foto, exportar dossiê |
| Outra construtora | `outra@beta.demo` | somente a obra Beta |

Senha padrão: `SenhaForte#123`.

```powershell
# 2. API apontando para o banco de demonstração
#    (a senha da role de app é a mesma que o seed_demo usou)
$env:DATABASE_URL="postgresql+psycopg2://stellspy_app:dev-local-app-password@localhost:55432/stellspy_demo"
$env:PWA_COOKIE_SECURE="0"          # HTTP local: o cookie não pode exigir TLS
$env:CORS_ALLOW_ORIGINS="http://localhost:8080"
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

```powershell
# 3. PWA em outra janela, na raiz do repositório
cd ..
.venv\Scripts\python.exe -m http.server 8080 --directory pwa
```

Antes de abrir no celular, edite `pwa/index.html` e preencha:

```json
{"apiBaseUrl": "http://localhost:8000"}
```

**Reverta essa linha ao final** (`"apiBaseUrl": ""`) para não deixar configuração
de teste no repositório.

### Celular Android por USB (câmera funciona)

```powershell
adb devices                 # aparelho autorizado
adb reverse tcp:8080 tcp:8080
adb reverse tcp:8000 tcp:8000
```

Abra no Chrome do celular: `http://localhost:8080`.

Por que assim: navegador só libera câmera e service worker em `https://` ou
`localhost`. O `adb reverse` faz o celular enxergar o PC como `localhost`, sem
certificado, sem túnel e sem custo.

### iPhone

Não há caminho equivalente por USB. Em HTTP na rede local o Safari bloqueia a
câmera (contexto inseguro) e o service worker. **Teste em iPhone permanece
pendente** até existir HTTPS interno ou domínio de homologação.

---

## 2. Casos de teste

Registre para cada caso: hora, modelo do aparelho, versão do Chrome/Safari,
tipo de rede (Wi-Fi/4G) e captura de tela. "Passou" sem captura não conta.

### CT-01 — Login e escopo

1. Abra o app e entre com `almox@alfa.demo`.
2. **Esperado:** lista mostra apenas `Residencial Aurora — Torre Norte`.
3. Saia e entre com `outra@beta.demo`.
4. **Esperado:** lista mostra apenas `Obra Beta 1`; a obra Alfa não aparece.

### CT-02 — Recebimento parcial (contagem por linha)

1. Como `almox@alfa.demo`, abra **Receber** e escolha o pedido `PC-2026-0117`.
2. Informe apenas a linha 1 (`1000 M`) e registre.
3. **Esperado:** resultado `PARCIAL`, com o saldo das linhas 2 e 3 visível.
4. Abra **Histórico**.
5. **Esperado:** a entrada aparece uma única vez, com status parcial.

### CT-03 — Queda de rede no registro (não duplicar)

1. Inicie uma nova entrada e preencha a contagem.
2. Ative o modo avião **antes** de tocar em `REGISTRAR ENTRADA`.
3. Toque no botão.
4. **Esperado:** mensagem clara de "Sem conexão… a operação não foi confirmada".
   Nada é marcado como concluído.
5. Desligue o modo avião e toque novamente.
6. **Esperado:** a entrada é criada **uma vez**. O histórico não mostra duplicata.

> O app guarda o identificador daquela entrada na sessão do navegador. Recarregar
> a tela não cria uma segunda carga; "REGISTRAR OUTRA ENTRADA" cria.

### CT-04 — Câmera e evidência

1. Na tela de fotos da entrega, toque em `TIRAR FOTO`.
2. **Esperado:** o navegador pede permissão de câmera; a captura abre a câmera
   traseira (não a galeria).
3. Tire a foto do material e envie.
4. **Esperado:** a foto aparece na lista da entrega, com horário.
5. Abra a foto.
6. **Esperado:** a imagem carrega; a URL não é pública e não exibe caminho de
   armazenamento.

### CT-05 — Queda de rede no upload (não duplicar foto)

1. Selecione outra foto e toque em enviar.
2. Ative o modo avião durante o envio.
3. **Esperado:** erro claro; a foto **não** entra como enviada.
4. Desligue o modo avião e toque em enviar novamente.
5. **Esperado:** existe **uma** foto nova, não duas.

### CT-06 — Permissões por papel

1. Entre como `auditor@alfa.demo`.
2. Abra o pedido e as fotos.
3. **Esperado:** consegue ler; **não** aparece botão de tirar/enviar foto.
4. Entre como `almox@alfa.demo` (fiscal).
5. Tente abrir o dossiê.
6. **Esperado:** a rota não é oferecida; se forçada pela URL, o servidor recusa.

### CT-07 — Isolamento entre construtoras

1. Como `outra@beta.demo`, tente abrir uma foto ou entrega da obra Alfa pela URL
   (use um id capturado no teste da Alfa).
2. **Esperado:** `não encontrado` (404). Não deve existir mensagem que confirme
   a existência do registro.

### CT-08 — Sessão e logout

1. Toque em sair.
2. Volte pelo histórico do navegador para uma tela protegida.
3. **Esperado:** o app volta ao login; nenhuma chamada autenticada retorna dados.

### CT-09 — Service worker e atualização

1. Com o app aberto, recarregue duas vezes.
2. **Esperado:** a versão nova do JS é servida sem ficar presa em cache antigo
   (o shell usa `stale-while-revalidate` e o cache é versionado).
3. Ative o modo avião e recarregue.
4. **Esperado:** o shell abre; qualquer ação que dependa do servidor mostra erro
   claro e não finge sucesso.

---

## 3. Evidências a anexar

- Capturas de tela de cada caso (mínimo: CT-01, CT-02, CT-03, CT-04, CT-05, CT-07).
- Modelo do aparelho, versão do sistema e do navegador.
- Hora de início e fim.
- Para CT-03/CT-05: captura do erro e do histórico depois do retry, mostrando
  que não há duplicata.
- Resultado do download da foto (abriu a imagem) e confirmação de que a rota
  pública do bucket não entrega o objeto.

## 4. Critério de aprovação

Todos os casos acima com evidência, **exceto** o que depende de iPhone/HTTPS.
Qualquer divergência deve ser registrada como bloqueio com o passo que a
reproduziu — não como "intermitente".

## 5. Limpeza

```powershell
# encerrar os servidores (Ctrl+C nas janelas)
adb reverse --remove-all
# reverter apiBaseUrl no pwa/index.html
```

O banco `stellspy_demo` pode ser recriado a qualquer momento pelo `seed_demo.py`;
não remova bancos de outros projetos nem o banco de testes `stellspy`.
