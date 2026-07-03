"""Textos fixos do roteiro conversacional — transcritos do documento de
negócio já aprovado (Script_Atendente_Virtual_DGS.docx). Estes textos NÃO
são gerados por LLM; são enviados literalmente (com os placeholders
preenchidos) via integrations/whatsapp_client.send_text ou send_template.

Qualquer alteração de copy deve ser feita primeiro no documento de negócio
e só depois refletida aqui.
"""

M1_ABERTURA = (
    "Olá, {nome}! Aqui é a Alana, analista comercial da DGS. Vi que você entrou em "
    "contato com a gente pela DB1 e quero entender melhor o seu contexto antes de te "
    "conectar com o especialista certo. Leva menos de 5 minutos — posso te fazer "
    "algumas perguntas rápidas?"
)

M2_DOR_PRINCIPAL = (
    'Vi que você mencionou "{trecho_desafios}". Pra eu te conectar com o especialista certo: '
    "esse problema está afetando a operação agora, ou é algo que você está planejando resolver "
    "nos próximos meses?"
)

M3_TIMELINE = (
    "Entendido. E qual é a urgência disso pra você: tem um prazo específico para resolver, "
    "ou está mais em fase de pesquisa ainda?"
)

M4_AUTORIDADE = (
    "Pra garantir que nosso especialista venha preparado: além de você, quem mais costuma "
    "participar dessa decisão?"
)

M5_FIT_BUDGET = (
    "Última pergunta: você está buscando um parceiro técnico para resolver o problema de "
    "ponta a ponta, ou tem um orçamento definido e está cotando preço entre fornecedores?"
)

M6_FECHAMENTO_HOT = (
    "{nome}, pelo que você me contou, faz muito sentido a gente conversar o quanto antes. "
    "Vou acionar nosso especialista agora. Ele vai entrar em contato em breve pelo WhatsApp. "
    "Enquanto isso, posso te mandar um material rápido sobre como a DB1 resolveu esse tipo de "
    "desafio em empresas do seu setor?"
)

M6_FECHAMENTO_HOT_DIRETO = (
    "Claro! Nosso especialista vai entrar em contato em breve. Pra ele vir preparado: "
    "qual é o melhor horário para você hoje ou amanhã?"
)

M6_FECHAMENTO_WARM = (
    "{nome}, obrigado pelas informações! Nosso especialista em {setor} vai entrar em contato "
    "em breve para entender melhor o contexto e mostrar como a DB1 tem resolvido esse tipo de "
    "desafio. Tem algum horário que funciona melhor pra você essa semana?"
)

CONFIRMACAO_AGENDAMENTO = "Perfeito! Vou te enviar o invite na sequência. Obrigada e ótimo dia!"

M6_FECHAMENTO_TEPID = (
    "{nome}, faz sentido! Vou pedir para nosso time te mandar alguns conteúdos sobre como "
    "empresas do setor de {setor} estão resolvendo esse desafio. Se fizer sentido pra você, "
    "é só responder e a gente avança. Combinado?"
)

M6_FECHAMENTO_COLD = (
    "{nome}, obrigado pelo contato! Por enquanto talvez não seja o momento certo. Vou pedir "
    "ao nosso time para te incluir em nossa newsletter com conteúdos sobre {tema}. Se em algum "
    "momento fizer mais sentido, é só responder aqui. Até mais!"
)

REENGAJAMENTO_24H = (
    "Oi, {nome}! Aqui é a Alana de novo, da DGS. Você passou pelo site da DB1 e queria "
    "entender melhor o que te trouxe até nós. Tem 2 minutos pra gente continuar aquela "
    "conversa rápida?"
)

DIVULGACAO_SE_PERGUNTADA = (
    "Sou uma assistente virtual da DGS, sim — trabalho com a equipe comercial pra já "
    "chegar organizando as informações certas antes de te conectar com um especialista "
    "humano. Isso muda alguma coisa pra você, ou posso seguir com as perguntas?"
)

PEDIDO_MAIS_INFO = (
    "Claro! Posso te mandar um overview rápido. Mas para mandar o material mais relevante pro "
    "seu contexto, me fala: você tem mais urgência em {opcao_1} ou em {opcao_2}?"
)

DETECCAO_D5_PRECO = (
    "Entendo! Nesse caso, a DB1 talvez não seja a melhor opção por enquanto, já que nosso foco "
    "é em projetos onde o parceiro técnico faz diferença no resultado. Se em algum momento isso "
    "mudar, a gente fica por aqui. Até mais, {nome}!"
)
