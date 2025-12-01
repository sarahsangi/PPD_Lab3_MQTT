import paho.mqtt.client as mqtt
import threading
import time
import json
import random
import hashlib
import sys

# --- CONFIGURAÇÕES GLOBAIS ---
BROKER = '127.0.0.1' 
PORT = 1883
QOS = 1 

# --- PARÂMETROS DO SISTEMA ---
N_PARTICIPANTES = 3 
CLIENT_ID = random.randint(1, 65535) 
VOTE_ID = random.randint(1, 65535) 

# --- GESTÃO DE ESTADOS ---
STATE_INIT = 0
STATE_ELECTION = 1
STATE_RUNNING = 2
CURRENT_STATE = STATE_INIT

# Filas MQTT
TOPIC_INIT = "sd/init"
TOPIC_ELECTION = "sd/election"
TOPIC_CHALLENGE = "sd/challenge"
TOPIC_SOLUTION = "sd/solution"
TOPIC_RESULT = "sd/result"

# --- ELEIÇÃO E PARTICIPANTES ---
RECEIVED_INIT_MSGS = set() 
VOTES = {} 
IS_LEADER = False
LEADER_ID = None

# --- MINERADOR/CONTROLADOR ---
TRANSACTIONS = {} 
TABLE_LOCK = threading.Lock() 

# Controle de Mineração
FOUND_SOLUTION = None
MINING_STOP_EVENT = threading.Event()
MINING_TX_ID = -1 

# --- FUNÇÕES AUXILIARES ---

def check_challenge(challenge_level, solution_string):
    if not solution_string: return False, ""
    hash_object = hashlib.sha1(solution_string.encode('utf-8'))
    hex_dig = hash_object.hexdigest()
    target_prefix = '0' * challenge_level
    return hex_dig.startswith(target_prefix), hex_dig

def generate_new_challenge(transaction_id):
    challenge_level = random.randint(1, 4) 
    with TABLE_LOCK:
        TRANSACTIONS[transaction_id] = {
            'challenge': challenge_level, 'solution': "", 'winner': -1, 'solved': False
        }
    print(f"[CONTROLADOR] Novo Desafio Gerado (ID: {transaction_id}, Nível: {challenge_level})")
    return challenge_level

# --- PUBLICAÇÃO COM REGISTRO IMEDIATO ---

def publish_init_message(client):
    """Publica ID e já conta a si mesmo."""
    message = {"ClientID": CLIENT_ID}
    
    # 1. Publica (Retained para os outros verem depois)
    client.publish(TOPIC_INIT, json.dumps(message), qos=QOS, retain=True)
    
    # 2. Registra a si mesmo IMEDIATAMENTE (Não espera o broker devolver)
    if CLIENT_ID not in RECEIVED_INIT_MSGS:
        RECEIVED_INIT_MSGS.add(CLIENT_ID)
        print(f"[INIT] Registrei meu próprio ID. Total: {len(RECEIVED_INIT_MSGS)}/{N_PARTICIPANTES}")
    
    check_init_transition(client)

def publish_election_message(client):
    """Publica Voto e já conta a si mesmo."""
    message = {"ClientID": CLIENT_ID, "VoteID": VOTE_ID}
    
    # 1. Publica
    client.publish(TOPIC_ELECTION, json.dumps(message), qos=QOS, retain=True)
    
    # 2. Registra voto IMEDIATAMENTE
    if CLIENT_ID not in VOTES:
        VOTES[CLIENT_ID] = VOTE_ID
        print(f"[ELECTION] Registrei meu próprio voto. Total: {len(VOTES)}/{N_PARTICIPANTES}")
    
    check_election_transition(client)

def publish_challenge_message(client, tx_id, challenge_level):
    message = {"TransactionID": tx_id, "Challenge": challenge_level}
    client.publish(TOPIC_CHALLENGE, json.dumps(message), qos=QOS, retain=False)
    print(f"[CONTROLADOR] Desafio {tx_id} ({challenge_level} zeros) publicado.")

def publish_result_message(client, tx_id, solution, recipient_id, result_code):
    message = {"ClientID": recipient_id, "TransactionID": tx_id, "Solution": solution, "Result": result_code}
    client.publish(TOPIC_RESULT, json.dumps(message), qos=QOS, retain=False)
    print(f"[CONTROLADOR] Resultado enviado para {recipient_id} (Code: {result_code}).")

def publish_solution_message(client, tx_id, solution):
    message = {"ClientID": CLIENT_ID, "TransactionID": tx_id, "Solution": solution}
    client.publish(TOPIC_SOLUTION, json.dumps(message), qos=QOS, retain=False)
    print(f"[MINERADOR] Solução submetida para TX ID {tx_id}.")

# --- LÓGICA DE MINERAÇÃO ---

def mine_challenge(challenge_level, thread_id):
    global FOUND_SOLUTION
    target_prefix = '0' * challenge_level
    counter = 0
    while not MINING_STOP_EVENT.is_set():
        input_string = f"{CLIENT_ID}-{thread_id}-{counter}-{time.time()}" 
        hash_object = hashlib.sha1(input_string.encode('utf-8'))
        hex_dig = hash_object.hexdigest()
        if hex_dig.startswith(target_prefix):
            FOUND_SOLUTION = input_string
            MINING_STOP_EVENT.set()
            print(f"\n[MINERADOR: Thread {thread_id}] SOLUÇÃO ENCONTRADA! Input: {input_string}")
            return
        counter += 1

def start_mining(client, tx_id, challenge_level):
    global FOUND_SOLUTION, MINING_TX_ID
    MINING_TX_ID = tx_id
    FOUND_SOLUTION = None
    MINING_STOP_EVENT.clear()
    
    print(f"[MINERADOR] Buscando solução para TX {tx_id} (Nível {challenge_level})...")
    threads = []
    for i in range(4):
        t = threading.Thread(target=mine_challenge, args=(challenge_level, i+1))
        threads.append(t)
        t.start()
        
    MINING_STOP_EVENT.wait(timeout=60)
    MINING_STOP_EVENT.set()
    for t in threads: t.join() 
        
    if FOUND_SOLUTION:
        publish_solution_message(client, tx_id, FOUND_SOLUTION)
    else:
        print("[MINERADOR] Tempo esgotado sem solução.")

# --- CHECAGEM DE TRANSIÇÃO (Isolada para ser chamada de vários lugares) ---

def check_init_transition(client):
    global CURRENT_STATE
    if CURRENT_STATE == STATE_INIT and len(RECEIVED_INIT_MSGS) >= N_PARTICIPANTES:
        print("\n--- TRANSIÇÃO: INIT -> ELECTION ---")
        CURRENT_STATE = STATE_ELECTION
        client.unsubscribe(TOPIC_INIT)
        publish_election_message(client)

def check_election_transition(client):
    global CURRENT_STATE, IS_LEADER, LEADER_ID
    if CURRENT_STATE == STATE_ELECTION and len(VOTES) >= N_PARTICIPANTES:
        leader_info = max(VOTES.items(), key=lambda item: (item[1], item[0]))
        LEADER_ID = leader_info[0]
        IS_LEADER = (LEADER_ID == CLIENT_ID)
        
        print(f"\n--- TRANSIÇÃO: ELECTION -> RUNNING (Líder {LEADER_ID}) ---")
        CURRENT_STATE = STATE_RUNNING
        client.unsubscribe(TOPIC_ELECTION)
        
        if IS_LEADER:
            client.subscribe(TOPIC_SOLUTION, qos=QOS)
            time.sleep(2) 
            tx_id = 0
            lvl = generate_new_challenge(tx_id)
            publish_challenge_message(client, tx_id, lvl)
        else:
            client.subscribe(TOPIC_CHALLENGE, qos=QOS)
            client.subscribe(TOPIC_RESULT, qos=QOS)

# --- HANDLERS ---

def handle_init_message(client, payload):
    sender_id = payload.get('ClientID')
    if CURRENT_STATE != STATE_INIT: return 

    if sender_id not in RECEIVED_INIT_MSGS:
        RECEIVED_INIT_MSGS.add(sender_id)
        print(f"[INIT] Vi o ID: {sender_id}. Total: {len(RECEIVED_INIT_MSGS)}/{N_PARTICIPANTES}")
    
    check_init_transition(client)

def handle_election_message(client, payload):
    sender_id = payload.get('ClientID')
    vote = payload.get('VoteID')
    if CURRENT_STATE != STATE_ELECTION: return

    if sender_id not in VOTES:
        VOTES[sender_id] = vote
        print(f"[ELECTION] Vi o voto de {sender_id} ({vote}). Total: {len(VOTES)}/{N_PARTICIPANTES}")

    check_election_transition(client)

def handle_challenge_message(client, payload):
    tx_id = payload.get('TransactionID')
    lvl = payload.get('Challenge')
    print(f"[MINERADOR] Recebido Desafio TX {tx_id} (Nível {lvl})")
    threading.Thread(target=start_mining, args=(client, tx_id, lvl)).start()

def handle_solution_message(client, payload):
    tx_id = payload.get('TransactionID')
    submitter = payload.get('ClientID')
    sol = payload.get('Solution')
    
    with TABLE_LOCK:
        if tx_id not in TRANSACTIONS: return 
        if TRANSACTIONS[tx_id]['solved']:
            publish_result_message(client, tx_id, sol, submitter, 2)
            return
        lvl = TRANSACTIONS[tx_id]['challenge']

    valid, final_hash = check_challenge(lvl, sol)
    if valid:
        with TABLE_LOCK:
            if TRANSACTIONS[tx_id]['solved']:
                publish_result_message(client, tx_id, sol, submitter, 2)
                return
            TRANSACTIONS[tx_id].update({'solution': final_hash, 'winner': submitter, 'solved': True})
            print(f"\n[CONTROLADOR] VENCEDOR DA RODADA: {submitter}")
        
        publish_result_message(client, tx_id, sol, submitter, 1)
        new_id = tx_id + 1
        new_lvl = generate_new_challenge(new_id)
        publish_challenge_message(client, new_id, new_lvl)
    else:
        print(f"[CONTROLADOR] Solução rejeitada de {submitter}")
        publish_result_message(client, tx_id, sol, submitter, 0)

def handle_result_message(client, payload):
    res = payload.get('Result')
    tx = payload.get('TransactionID')
    if payload.get('ClientID') == CLIENT_ID:
        if res == 1: print(f"\n[MINERADOR] 🏆 GANHEI A RODADA TX {tx}!")
        elif res == 2: print(f"[MINERADOR] ⚠️ Cheguei tarde na TX {tx}.")
        elif res == 0: print(f"[MINERADOR] ❌ Solução inválida na TX {tx}.")

# --- CONFIGURAÇÃO MQTT ---

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[MQTT] Conectado! (Aguardando início manual...)")
        client.subscribe(TOPIC_INIT, qos=QOS)
        client.subscribe(TOPIC_ELECTION, qos=QOS)
    else:
        print(f"Erro de conexão: {rc}")

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode('utf-8'))
        sender = payload.get('ClientID')
    except: return

    # Importante: Com o registro local imediato, podemos ignorar mensagens próprias vindas da rede
    # para evitar duplicidade de log, embora a lógica de set/dict já proteja contra isso.
    if sender == CLIENT_ID: return 

    topic = msg.topic
    if topic == TOPIC_INIT: handle_init_message(client, payload)
    elif topic == TOPIC_ELECTION: handle_election_message(client, payload)
    elif CURRENT_STATE == STATE_RUNNING:
        if topic == TOPIC_CHALLENGE: handle_challenge_message(client, payload)
        elif topic == TOPIC_SOLUTION and IS_LEADER: handle_solution_message(client, payload)
        elif topic == TOPIC_RESULT and not IS_LEADER: handle_result_message(client, payload)

# --- MAIN ---

def main():
    print(f"--- SISTEMA PPD (ID: {CLIENT_ID}) ---")
    print("LEMBRETE: Reinicie o Docker antes de testar para evitar 'Zombies'!")
    
    client = mqtt.Client(client_id=str(CLIENT_ID))
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        client.connect(BROKER, PORT, 60)
        client.loop_start()

        # TRAVA MANUAL
        input("\n>>> Abra os 3 terminais e PRESSIONE ENTER aqui para começar <<<")
        
        # Dispara o processo
        publish_init_message(client)

        while True: time.sleep(1)
            
    except KeyboardInterrupt:
        print("Desconectando...")
        client.disconnect()

if __name__ == '__main__':
    main()
