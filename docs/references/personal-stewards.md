# Três situações humanas executáveis

Estes exemplos ampliam as referências Release Steward e Evidence Analyst. Não são um produto financeiro, um resultado científico nem um organizador que faz reservas. São referências executáveis locais, com dados e pessoas inventados, para inspecionar continuidade, revisão de evidência e limites de ação.

## Começar em dois minutos

Python 3.11+, sem dependências de runtime adicionais:

```sh
PYTHONPATH=src python examples/references/personal_stewards.py \
  --domain finance --output /tmp/finance.json
PYTHONPATH=src python examples/references/personal_stewards.py \
  --domain research --output /tmp/research.json
PYTHONPATH=src python examples/references/personal_stewards.py \
  --domain gathering --output /tmp/gathering.json
```

Sem `--domain`, executa as sete trajetórias. `--artifact-root /tmp/new-unique-directory` conserva bancos SQLite e os arquivos locais para inspeção. Use uma pasta nova por execução: reutilizar um banco existente não cria uma nova experiência independente. A interrupção dentro de uma trajetória usa o comando `restart`, que restaura a mesma situação por replay.

```sh
PYTHONPATH=src python -m unittest discover -s tests \
  -p 'test_personal_stewards*.py' -v
```

O comando sem `--domain`, com `--output /tmp/personal-stewards-replay.json`, grava a execução completa, não um roteiro com eventos inventados. O PR contém somente fonte, testes e tutorial; logs e artefatos gerados não são publicados no repositório. `personal_stewards_domain.py` define fatos, regras específicas e comandos reproduzíveis; `personal_stewards.py` conecta isso ao SDK real. Os identificadores e timestamps de novas execuções variam; `replay_equal` compara a projeção persistida com uma reconstrução do mesmo log, não a igualdade byte a byte entre execuções diferentes.

## 1. Steward financeiro: preservar liquidez enquanto o cenário muda

Maya é uma pessoa fictícia. Valores inteiros em reais: salário mensal líquido de cenário R$14.500; despesas mensais R$9.200; caixa líquido R$42.000; vencimento futuro com R$18.000 de recebimento líquido hipotético; aluguel R$4.800; participação no empregador R$210.000, concentrada e ilíquida. Bônus R$0–24.000 é incerto. Nenhum desses dados descreve uma pessoa real.

1. O pedido estabelece uma revisão de liquidez, não um mandato para investir.
2. Sem nova mensagem humana, um timer aciona uma consulta de fixture de aluguéis e custo de mudança. A preparação local usa essa evidência.
3. Bônus é adiado; uma hipótese de custos familiares aumenta. O critério explícito de seis meses de despesas mais buffer passa de R$67.200 para R$73.200. Esse critério é uma preferência do cenário, não uma recomendação universal.
4. A nova lacuna de caixa é R$31.200. Só se o vencimento efetivamente receber os R$18.000 líquidos previstos, a lacuna cairia a R$13.200. Vencimento não é salário nem caixa atual. Bônus e ações ilíquidas não financiam a reserva disponível.
5. Dois relatos sintéticos discordam sobre inflação. A discordância permanece visível. Ela não impede a aritmética de caixa, mas não fundamenta retorno esperado nem seleção de instrumento. Mudança de expectativa de juros também não vira previsão.
6. Novo dado altera o wake, a recomendação fica versionada e a aprovação antiga perde validade. Após reinício real do runtime, uma decisão humana simulada aceita o documento atual. Readback e hash confirmam o artefato local antes de encerrar o compromisso de revisão.

A alternativa de aluguel calcula R$1.000/mês de economia potencial e seis meses para compensar R$6.000 de mudança. Não inclui impostos, alteração de trajetos, qualidade, custos ocultos ou disponibilidade real. As opções explicam essas limitações. Não há ferramenta de comprar, vender, transferir, abrir conta ou aceitar termos. O objetivo familiar e a situação financeira real não foram resolvidos pelo encerramento do documento.

## 2. Steward de pesquisa: colaboração sem transformar dúvida em achado

Lina e Omar têm um piloto fictício de 12 observações e um checkpoint na sexta. Uma consulta de fixture identifica três pares ausentes; uma reanálise independente discorda do sinal do efeito. A disponibilidade do colaborador muda para revisão assíncrona e antecipa a revisão.

A política escolhe preparar um relatório de lacunas. Replicação fica condicionada à disponibilidade e ao protocolo. A alternativa de afirmar um efeito positivo é inadmissível. A aprovação simulada do relatório não prova significância, replicação, submissão ou publicação. Isso exercita desacordo científico, dependência humana e redução do escopo de um prazo, em vez de maximizar uma pontuação financeira.

## 3. Steward de encontro: satisfação de restrições e espera útil

Oito adultos fictícios, sábado, R$600 e acessibilidade obrigatória. Um parque de R$120 depende do tempo; a sala inicialmente cotada a R$480 ainda não está disponível. Enquanto espera, uma consulta local confere a janela declarada dos convidados.

Chuva e informação de entrada apenas por escadas eliminam as primeiras opções. A resposta antecipa o wake. A alternativa de adiar continua disponível sem ultrapassar uma restrição. Depois, outra sala térrea de R$560 fica disponível no cenário e tem prazo próprio. O agente prepara um documento local para revisão; não reserva a sala nem envia convites. Na variante de mudança de horário depois da aprovação, a nova versão exige outra decisão, inclusive após reinício. A checagem original de convidados para 15h–18h não comprova disponibilidade no horário revisado de 17h–20h; a variante se abstém e exige evidência atual antes de nova preparação. O parque também exige acessibilidade explícita, orçamento suficiente e custo de R$15 por adulto.

## Por que não são três wrappers iguais

O ciclo de persistência, timer, autorização, preparação e verificação é compartilhado de propósito. As decisões não são:

- Finanças: aritmética dimensional de fluxo/estoque, liquidez, cenários condicionais e concentração.
- Pesquisa: evidência insuficiente/contraditória, disponibilidade de colaborador e escopo de um checkpoint.
- Encontro: conjunção de restrições duras e alternativas que se tornam inviáveis por chuva, acesso ou preço.

O objetivo pequeno e verificável compartilhado é um **documento local atual revisado**. As aplicações reais precisariam de compromissos adicionais para cada resultado externo; estas referências não fingem que gerar um JSON completa a vida da pessoa.

## Casos e critérios verificáveis

| Caso | Resultado esperado |
|---|---|
| P1 financeiro | Revisão local atual encerrada, conflito de inflação preservado |
| P2 pesquisa | Revisão local encerrada, estudo ainda inconclusivo |
| P3 encontro | Plano local encerrado, reserva/envio externos não realizados |
| P4 revogação | Zero preparação após revogação |
| P5 fonte expirada | Abstenção, nenhuma recomendação numérica com valores ausentes |
| P6 interrupção | Aprovação antiga inválida e nova janela sem confirmação; não prepara, continua aberto |
| P7 corrida de evidência | Intenção antiga abandonada, zero arquivo da versão stale |

As regressões de auditoria cobrem orçamento/acessibilidade do parque, arrays de aluguel inválidos, custo de mudança desconhecido, texto obrigatório nulo, evidência futura, relógio monotônico, aprovação expirada/revogada, corridas de preparo/readback e alteração do arquivo durante leitura. Os testes também cobrem fonte obrigatória conflitante, aprovação de versão errada, múltiplos wakes sem preparação duplicada, hash adulterado, ausência de vazamento de eventos futuros em cards, fórmulas financeiras e readback ligado à decisão humana. Esses testes sintéticos não medem utilidade no mundo, desempenho financeiro, eficácia da colaboração ou maturidade de produção.

## O que é nativo do SDK e o que pertence à aplicação

| Responsabilidade | Implementação demonstrada |
|---|---|
| Persistência e reconstrução | `NoemaKernel`, `SQLiteEventStore`, projeção de fatos e compromissos |
| Agente que acorda sem nova mensagem | `AsyncScheduler`, `AutonomousAgent`, `CognitiveController` |
| Decisão e rechecagem de autoridade | `RuleBasedReasoner`, `ActionIntent`, `PolicyEngine`; SDK pode abandonar intenção de versão anterior |
| Efeitos tipados e eventos de resultado | `CapabilityRegistry`, `CapabilitySpec`, `CapabilityResult` |
| O que é relevante e como comparar opções | Classes de domínio da aplicação, determinísticas |
| Atualidade e discordância de fontes | Esquema de claims e janela de validade da aplicação |
| Política financeira/científica/social | Aplicação; não conhecimento financeiro/científico embutido no Noema |
| Projeção humana e artefato local | Aplicação, com referências ao log nativo |
| Readback | Verificador local separado da escrita, integridade por hash e versão/evidência; não auditoria independente de aconselhamento |
| Integrações, custódia, mensagens, autorização real | Não implementadas; exigem adapters e autoridade específica |
| LLM, decision model, previsão causal | Não chamados nestes replays |

O timer nativo não é uma agenda distribuída durável. A aplicação persiste a intenção de wake como fato, cancela/substitui o handle e o reconstrói no reinício. No runner, minutos são sintéticos: `wake` entrega o timer por `AsyncScheduler.at` imediatamente, avançando o relógio lógico ao prazo. O handle de espera longa é apenas pacing de laboratório; o código não deve ser usado como scheduler de produção. Não há lease distribuído nem alegação de exclusão mútua entre processos. A aplicação coordena mutações com lock local e usa `NoemaKernel.emit_if_head` para compare-and-append no instante real de persistir o estado. O resultado da capability não devolve snapshots para escrita posterior pelo SDK. I/O ocorre fora do lock: nova evidência ou revogação invalida o resultado antigo. Evidência de preparação/readback é persistida antes da transição; falha de CAS deixa a situação aberta e pode deixar um arquivo candidato não atual. Isso não fornece uma transação distribuída entre filesystem e banco; adaptar para múltiplos executores exige leases/fencing e armazenamento de artefatos apropriado. Readback é prova pontual, não imutabilidade futura de um arquivo gravável.

## Onde cabe um provider opcional

A implementação atual escolhe operações exclusivamente por regras. O contrato separado `noema.decisions.DecisionProvider`, no PR paralelo de providers tipados, pode avaliar `DecisionRequest` tipado para uma pergunta delimitada (por exemplo, relevância de uma nova observação ou escolha entre alternativas já admissíveis). A ligação não está implementada neste runner; nenhuma probabilidade retornada por modelo aparece como sucesso real.

Integração futura deve registrar proveniência, rubric/version e origem `fixture`, `injected_transport` ou rede real; preservar recusas e validar opções; nunca promover julgamento a autorização nem substituir aritmética por um modelo. Um LLM pode propor perguntas/explicações; a aplicação deve validar fatos, unidades, versões, orçamento e efeito. Estes replays não dependem do módulo opcional e não exigem credenciais ou cobranças.

## Contrato do laboratório humano

Exportação v1: `{schema_version, scope, results}`. Cada resultado contém `scenario`, `domain`, `title`, `goal`, `stakes`, `status`, `cards`, `events`, `artifact`, `metrics` e `replay_equal`.

- `events` são `Event.to_dict()` do SDK, sem conversão para um log inventado.
- Um card é a payload persistida de `reference.card`, acrescida de `event_id` e `sequence` do mesmo evento. Mostrar o card somente quando esse evento estiver visível no cursor do replay.
- `known` e `uncertain`: arrays de strings; claims expiram e fontes contraditórias não são silenciosamente sobrescritas.
- `options`: objetos `{id, label, admissible, tradeoff?, reason?, ...campos específicos}`. `admissible` significa alternativa para considerar no documento, não autorização de execução.
- `next_wake`: `null` ou `{due_minute, clock: "synthetic-minutes"}`.
- `human_decision`: `pending` ou `simulated-acceptance-current-local-review`. É aceitação fictícia do documento, nunca autorização real.
- `evidence_ids` apontam a observações anteriores ao card. Não substituir por uma fonte futura mais recente.
- `artifact`: `null` ou `{path, sha256, content, event_id, readback_event_id}`. `content` são os bytes UTF-8 representados como string JSON; o hash é sobre esses bytes. `path` é um nome local relativo, não uma URL pública. Só habilitar download após `event_id` visível; só chamar de verificado depois de `readback_event_id` visível.
- `closure` limita explicitamente o resultado à revisão local. O card antigo não pode reaparecer como atual após uma revisão. O `artifact` de topo do resultado pode ser histórico; só o artefato no card atual é elegível para apresentar como documento atual.

A aprovação não é uma interação do replay estático: ele apenas mostra a decisão simulada já gravada. Uma ramificação interativa requer execução real de novo cenário; não alterar silenciosamente o histórico original.

## Limites descobertos na revisão adversarial

A primeira execução congelada passou os dez testes iniciais, mas a revisão independente encontrou orçamento do parque não aplicado, valores ausentes tratados como zero, campos nulos, relógio reversível e uma corrida de escrita de snapshot após I/O. Essa execução foi invalidada e preservada como diagnóstico fora da distribuição atual. A implementação corrigida testa esses caminhos explicitamente e substitui o snapshot tardio por compare-and-append nativo. Testes de sucesso não demonstram segurança fora do domínio; esse registro não deve ser removido para transformar um laboratório em alegação de maturidade.
