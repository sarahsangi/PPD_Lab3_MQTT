# PPD - Laboratório III: Comunicação Indireta e Eleição Distribuída

Este projeto implementa um sistema distribuído baseado no modelo de **Comunicação Indireta (Publish/Subscribe)**. O objetivo foi desenvolver um protótipo de minerador de criptomoedas onde os nós participantes realizam uma **eleição distribuída** para decidir quem será o Controlador (Líder) e quem serão os Mineradores.

**Aluna:** Sarah Candido Sangi  
**Disciplina:** Programação Paralela e Distribuída (PPD)

---

## 1. Tecnologias Utilizadas

* **Linguagem:** Python 3.x
* **Comunicação:** MQTT via biblioteca **Paho MQTT**.
* **Infraestrutura:** Docker (Container **EMQX** como Broker de Mensagens).
* **Concorrência:** Biblioteca `threading` (para mineração paralela e controle de fluxo).

---

## 2. Instruções de Execução

### 2.1. Pré-requisitos

1.  Ter o **Python 3.x** instalado.
2.  Instalar a biblioteca Paho MQTT:
    ```bash
    pip install paho-mqtt
    ```
3.  Ter o **Docker** instalado e rodando.

### 2.2. Configuração do Broker (Docker)

Antes de iniciar os nós, é necessário subir o Broker MQTT localmente. Execute no terminal:

```bash
docker run -d --name emqx -p 1883:1883 -p 8083:8083 emqx/emqx:latest
```
  **Dica:** Para garantir um teste limpo (sem mensagens antigas retidas), recomenda-se reiniciar o container antes de cada nova execução: 
    ```bach
    docker restart emqx
    ```

### 2.3. Execução dos Nós
O sistema exige no mínimo 3 participantes. Abra **3 terminais** diferentes e siga os passos abaixo:

1. Execute o script em cada terminal:

```bach
python miner_node.py
```
2. O programa irá conectar ao Broker e aguardar uma confirmação manual.

---

3. Quando os 3 terminais estiverem prontos, pressione **ENTER** em cada um deles (rapidamente, um após o outro) para iniciar a sincronização e a eleição.

## 3. Relatório Técnico
### 3.1. Introdução e Objetivo
O trabalho consiste na implementação de um sistema distribuído autônomo utilizando o modelo Publish/Subscribe. O cenário simulado é uma rede de criptomoedas onde não há um servidor central fixo; em vez disso, os nós conectados devem se auto-organizar, eleger um líder (Controlador) e iniciar o ciclo de mineração (Prova de Trabalho).

### 3.2. Metodologia de Implementação
**Arquitetura e Comunicação**
A comunicação entre os processos ocorre de forma indireta através do Broker MQTT (EMQX rodando em Docker). Todas as mensagens (Init, Election, Challenge, Solution) utilizam o formato JSON para estruturação dos dados.

**Algoritmo de Eleição Distribuída**
Foi implementada uma máquina de estados (`Init` → `Election` → `Running`) para coordenar o comportamento dos nós:

* **Inicialização:** Os nós publicam seus identificadores na fila `sd/init` e aguardam o reconhecimento dos demais participantes.

* **Votação:** Após o reconhecimento, os nós trocam mensagens de voto (`VoteID` aleatório) na fila `sd/election`.

* **Decisão:** O nó com o maior `VoteID` (com critério de desempate pelo maior `ClientID`) é eleito Líder e assume o papel de **Controlador**. Os demais tornam-se **Mineradores**.

**Estratégias de Sincronização** 
Para mitigar problemas de latência e garantir a consistência do estado em um ambiente local simulado, foram utilizadas:

* **Mensagens Retidas (MQTT Retain):** As mensagens críticas de inicialização e eleição são enviadas com a flag `retain=True`. Isso garante que, mesmo que um nó entre na rede com milissegundos de atraso, ele receba imediatamente o estado atual dos votos, prevenindo deadlocks na eleição.

* **Trava de Início Manual:** Uma barreira de entrada foi implementada para garantir que todos os processos estejam conectados ao Broker antes do início da troca de mensagens.

**Prova de Trabalho (PoW)**
O ciclo de mineração utiliza multithreading. Enquanto o nó escuta mensagens MQTT (como o anúncio de um novo bloco), quatro threads paralelas buscam uma solução SHA-1 que atenda ao desafio proposto pelo Controlador.

### 3.3. Resultados e Testes
O sistema foi validado com 3 participantes simultâneos. Os testes demonstraram:

* **Convergência da Eleição:** Em todas as execuções, os nós transicionaram corretamente de estado e concordaram com um único Líder.

* **Ciclo Contínuo:** O Controlador gerou desafios sequenciais, variando a dificuldade conforme especificado.

* **Competitividade:** Os logs comprovaram a alternância de vencedores entre os mineradores, validando a justiça da competição.

* **Tratamento de Concorrência:** O sistema identificou e rejeitou corretamente soluções enviadas tardiamente (após outro minerador já ter vencido a rodada), mantendo a integridade da cadeia.

---

## 4. Vídeo de Demonstração
O vídeo abaixo demonstra a inicialização do Docker, a execução dos 3 nós, o processo de eleição automática e o ciclo de mineração contínua.

**Link para o vídeo:** [ADICIONAR LINK AQUI]
