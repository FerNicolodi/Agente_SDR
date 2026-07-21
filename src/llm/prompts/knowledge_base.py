"""Base de conhecimento curada da DB1/DGS, usada pelo respondedor de
perguntas abertas (qa_responder.py). Condensada a partir das skills
internas db1-fundacao, db1-global-software-perfil-estrategico e
dgs-contexto-knowledge — não é a skill completa, é um resumo otimizado
para respostas curtas de WhatsApp.

PROCESSO DE SINCRONIZAÇÃO MANUAL
Última sincronização: 2026-07-08
Skills de referência: db1-fundacao · db1-global-software-perfil-estrategico · dgs-contexto-knowledge

Não há sincronização automática com o plugin. Revisar este arquivo sempre que:
  - Uma nova oferta DGS for lançada ou descontinuada
  - Métricas de referência mudarem (NPS, % on-time, GPTW, nº clientes)
  - O posicionamento AI First sofrer alteração oficial
  - Um novo diferencial competitivo for adicionado ao Engineering Guide
  - O número de colaboradores ou de clientes mudar significativamente

Checklist de sincronização (verificar vs skills acima):
  [ ] Dados corporativos: anos de mercado, nº colaboradores, nº clientes, países
  [ ] Métricas: on-time delivery, retrabalho, satisfação, NPS, GPTW
  [ ] Lista de ofertas e descrições resumidas
  [ ] Diferenciais: Engineering Guide, Painel de Saúde, cultura
  [ ] Posicionamento AI First e frase-chave

Responsável pela revisão: Fernando Nicolodi (Head de Novos Negócios)
"""

CONHECIMENTO_DB1_DGS = """
SOBRE A DB1 GLOBAL SOFTWARE
- 26+ anos de mercado, sede em Maringá (PR), atuação B2B com empresas de médio/grande porte.
- +850 colaboradores, +3.500 clientes, presença no Brasil, Argentina, Chile, Uruguai e EUA.
- Métricas de referência: 92% de entregas no prazo, 0,3% de retrabalho, 94% de satisfação dos clientes, NPS 89, 13 anos consecutivos de GPTW (Great Place to Work).
- Posicionamento central: "AI First" — a IA é incorporada como parte estrutural do processo de engenharia, não é só uma ferramenta auxiliar plugada por cima. Frase-chave: "Você confia em código gerado por IA? Nós confiamos! Usamos IA para acelerar e a engenharia para garantir os resultados."

OFERTAS DA DB1
- Core Up (Modernização de Legados): metodologia de 6 etapas para modernizar sistemas legados de forma incremental, com IA no processo. Resultados de referência: +35% de eficiência no diagnóstico, +30% na implementação, +500% em evolução de engenharia.
- Open Finance: implementação real (sem mocks) da infraestrutura de Open Finance, em até 40% menos tempo. Motor próprio de consentimento/autorização, APIs regulatórias prontas, atende bancos, cooperativas e fintechs.
- Produtos Digitais (end-to-end): construção completa de produtos digitais — apps, plataformas web, SaaS — incluindo Product Discovery, UX/UI e integrações, com squads multidisciplinares.
- Staff Augmentation (Extensão de Times): alocação de desenvolvedores e squads que elevam a maturidade técnica do time do cliente, guiados pelo Engineering Guide da DB1.
- FinOps: otimização de custos em nuvem (AWS/Azure/multicloud) — diagnóstico, rightsizing, governança e dashboards financeiros.
- GenAI Services: integração de IA generativa no ciclo de desenvolvimento e construção de agentes de IA sob medida para automatizar processos.
- Integração de APIs e Sistemas: conexão seguras com parceiros, órgãos regulatórios e sistemas internos.
- Assessment: diagnóstico em 3 etapas (Técnica, Negócios, Gestão) para quem ainda está avaliando o que precisa antes de decidir um caminho.

DIFERENCIAIS
- Engineering Guide público e vivo, com padrões de code review, arquitetura (SOLID, DDD, Clean Architecture) e QA shift-left.
- Painel de Saúde com métricas de qualidade em tempo real por projeto (taxa de bugs, assertividade de estimativa, satisfação).
- Cultura de pessoas reconhecida (13x GPTW), o que sustenta baixa rotatividade de times seniores.

O QUE A ALANA NUNCA DEVE FAZER AO RESPONDER
- Prometer preço, desconto, ou prazo de entrega específico — isso é decidido pelo especialista humano depois.
- Falar mal de concorrentes.
- Confirmar ou negar qualquer informação sobre como o lead está sendo avaliado/pontuado internamente.
- Inventar um dado que não está nesta base — se não souber, dizer que o especialista detalha isso na conversa.
"""
