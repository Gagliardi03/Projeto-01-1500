import streamlit as st
import psycopg2
import psycopg2.extras
from openai import OpenAI
from dotenv import load_dotenv
import os
import uuid

# Load environment variables
load_dotenv()

# OpenAI API Configuration
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Database connection function
def get_db():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

# Function to sanitize SQL queries
def limpar_consulta_sql(consulta):
    consulta = consulta.replace("```sql", "").replace("```", "").strip()
    palavras_chave_sql = ["SELECT", "INSERT", "UPDATE", "DELETE", "WITH"]  # Added WITH
    if not any(consulta.upper().startswith(palavra) for palavra in palavras_chave_sql):
        raise ValueError("A resposta do OpenAI não é uma consulta SQL válida.")
    return consulta

# Function to fetch data from the database based on prompt
def buscar_dados_para_prompt(prompt, chat_history):
    try:
        db = get_db()
        cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # Construct a precise and detailed system message for OpenAI
        messages = [
            {
                "role": "system",
                "content": f"""Você é um especialista em PostgreSQL e otimizador de consultas. Dada uma pergunta sobre dados de inseminação,
                você deve gerar uma consulta SQL *precisa* para a tabela 'inseminacoes'. A tabela 'inseminacoes' tem estas colunas:
                    fazenda, estado, municipio, numero_animal, lote, raça, categoria, ecc, ciclicidade, protocolo,
                    implante_p4, empresa, gnrh_na_ia, pgf_no_d0, dose_pgf_retirada, marca_pgf_retirada, dose_ce,
                    ecg, dose_ecg, touro, raça_touro, empresa_touro, inseminador, num_iatf, dg,
                    vazia_com_ou_sem_cl, perda.

                Sua prioridade é gerar uma consulta SQL *correta* que responda *completamente* à pergunta do usuário.
                Não faça suposições; se a pergunta for ambígua, tente usar o histórico da conversa para esclarecer.
                Se a pergunta for vaga ou não puder ser respondida diretamente com os dados disponíveis,
                responda com uma mensagem amigável explicando que você não pode responder à pergunta com os dados disponíveis.

                Se a pergunta envolver múltiplas condições ou relações complexas entre as colunas, use subconsultas ou CTEs (WITH clause) para organizar a lógica da consulta.

                **Instruções Essenciais:**

                1.  **Agregação:** Se a pergunta pedir "maior", "menor", "média", "total", ou "número de", você DEVE usar funções de agregação SQL como `AVG()`, `COUNT()`, `MAX()`, `MIN()`, e `SUM()`.  Use `GROUP BY` para agrupar os resultados pelas colunas relevantes (por exemplo, `GROUP BY fazenda`).

                2.  **Limitar Resultados:** Se a pergunta pedir um número específico de resultados (por exemplo, "3 fazendas"), use a cláusula `LIMIT` para restringir o número de linhas retornadas.

                3.  **Ordenação:** Se a pergunta envolver "maior", "menor", "melhor" ou similar, use a cláusula `ORDER BY` para ordenar os resultados.  Use `DESC` para ordem decrescente (maior primeiro) e `ASC` para ordem crescente (menor primeiro).

                4.  **Priorizar 'protocolo':** Se a pergunta for sobre "eficácia" e você não tiver dados diretos sobre isso, assuma que o "protocolo" mais comum é o mais amplamente utilizado e, portanto, pode ser considerado o "melhor avaliado". Use `COUNT(protocolo)` e `GROUP BY protocolo` para encontrar os protocolos mais frequentes.

                Atenha-se APENAS ao código SQL, sem comentários, explicações ou formatação.
                Se a pergunta for sobre 'quais fazendas temos', liste apenas os nomes das fazendas, SEM detalhes adicionais.
                **Mantenha a consulta SQL o mais breve e eficiente possível. Evite junções desnecessárias. Use LIMIT para evitar grandes resultados.**

                Se encontrar erros de sintaxe ou agregação, corrija-os na consulta SQL.

                **Exemplo 1: Forneça 3 fazendas que têm maior número de animais**

                ```sql
                SELECT fazenda, COUNT(numero_animal) AS total_animais
                FROM inseminacoes
                GROUP BY fazenda
                ORDER BY total_animais DESC
                LIMIT 3;
                ```

                **Exemplo 2: Qual é o protocolo de inseminação artificial com maior eficácia?**

                ```sql
                SELECT protocolo, COUNT(protocolo) AS protocolo_count
                FROM inseminacoes
                GROUP BY protocolo
                ORDER BY protocolo_count DESC
                LIMIT 1;
                ```
                """
            },
            *chat_history,
            {"role": "user", "content": prompt}
        ]

        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages,
                temperature=0.0,  # Even more deterministic
                max_tokens=500,  # Allow more tokens for complex queries
                top_p=0.9
            )

            consulta_sql = response.choices[0].message.content.strip()
            consulta_sql = limpar_consulta_sql(consulta_sql)
            st.write(f"Consulta SQL Gerada: {consulta_sql}")  # Print SQL For Debugging

        except Exception as e:
            print(f"Erro ao obter consulta SQL do OpenAI: {e}")
            return "Desculpe, estou tendo dificuldades para elaborar a consulta SQL. Por favor, tente reformular sua pergunta ou tente novamente mais tarde."

        # Execute the SQL query
        try:
            cursor.execute(consulta_sql)
            dados = cursor.fetchall()

            if dados:
                resultados_finais = []
                for row in dados:
                    linha = {coluna: row[coluna] if row[coluna] is not None else "N/A" for coluna in row.keys()}
                    resultados_finais.append(linha)
                return resultados_finais
            else:
                return "Não encontrei nenhum resultado correspondente no banco de dados."

        except Exception as e:
            print(f"Erro ao executar a consulta SQL: {e}")
            return f"Erro ao consultar o banco de dados. Detalhes: {e}"

    except ValueError as e:
        return f"Erro na consulta SQL: {e}"
    except psycopg2.OperationalError as e:
        return f"Erro ao buscar dados: {e}"
    except Exception as e:
        return f"Erro inesperado: {e}"

# Função para gerar uma resposta com base no prompt e histórico
def gerar_resposta(prompt, chat_history):
    # Check if the question is about extracting information from the database
    if any(palavra in prompt.lower() for palavra in ["fazenda", "estado", "municipio", "numero_animal", "lote", "raça",
            "categoria", "ecc", "ciclicidade", "protocolo", "implante_p4", "empresa", "gnrh_na_ia", "pgf_no_d0",
            "dose_pgf_retirada", "marca_pgf_retirada", "dose_ce", "ecg", "dose_ecg", "touro", "raça_touro",
            "empresa_touro", "inseminador", "num_iatf", "dg", "vazia_com_ou_sem_cl", "perda"]):

        dados_adicionais = buscar_dados_para_prompt(prompt, chat_history)

        if isinstance(dados_adicionais, str):
            return dados_adicionais  # Retorna a mensagem de erro do OpenAI

        if dados_adicionais:
            # Format the database response in a "futuristic" and readable way
            formatted_response = "<div style='font-family: sans-serif;'>"
            for item in dados_adicionais:
                if "fazenda" in item:
                    formatted_response += f"<p><span style='color:#64ffda;'>{item['fazenda']}</span></p>"
                else:  # All other values
                    for key, value in item.items():
                        formatted_response += f"<p><strong>{key}:</strong> <span style='color:#64ffda;'>{value}</span></p>"
                    formatted_response += "<hr style='border-top: 1px dashed #64ffda;'>"  # Dotted line separator
            formatted_response += "</div>"
            return formatted_response  # Retorna a resposta formatada
        else:  # Se o banco de dados retornar None ou uma string
            messages = []
            for turn in chat_history:
                messages.append({"role": turn["role"], "content": turn["content"]})

            # Get message content and prompt, save on chat history
            messages.append({"role": "user", "content": prompt})

            try:
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=messages,
                    temperature=0.2  # More deterministic, less "creative"
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                return f"Erro ao obter resposta do OpenAI: {e}"

    # Se não for uma pergunta sobre o banco de dados, use o OpenAI normalmente
    messages = []
    for turn in chat_history:
        messages.append({"role": turn["role"], "content": turn["content"]})

    messages.append({"role": "user", "content": prompt})

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Erro ao obter resposta do OpenAI: {e}"

# Streamlit App Starts Here
st.set_page_config(page_title="FarmAssist 🐄 Chat", page_icon="🐄")

# Custom CSS for a Futuristic Theme
st.markdown(
    """
    <style>
    .sidebar .sidebar-content {
        background-color: #1e293b; /* Dark background */
        color: #f0f0f0;
        padding-top: 1rem;
        display: flex; /* Use flexbox to position items */
        flex-direction: column; /* Stack items vertically */
    }
    .sidebar h2 {
        color: #94a3b8; /* Subdued header color */
        padding-left: 1rem;
        font-family: 'Arial Black', Gadget, sans-serif; /* Futuristic Font */
        margin-bottom: auto; /* Push the header to the top */
        font-size: 2em; /* Adjusted font size */
    }
    .sidebar .stButton>button {
        background-color: #334155; /* Button background */
        color: #f0f0f0;
        border: none;
        border-radius: 0.5rem;
        padding: 0.5rem 1rem;
        margin-bottom: 0.5rem;
        width: 100%;
        transition: background-color 0.2s ease;
    }
    .sidebar .stButton>button:hover {
        background-color: #475569; /* Hovered button background */
    }
    .sidebar .stTextInput>div>div>input {
        background-color: #273243; /* Input background */
        color: #f0f0f0;
        border: none;
        border-radius: 0.5rem;
        padding: 0.5rem;
    }
    .sidebar .avatar {
        margin-top: auto; /* Push the avatar to the bottom */
        margin-left: 1rem; /* Add some left margin */
        margin-bottom: 1rem; /* Add some bottom margin */
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Initialize conversations in session state
if 'conversations' not in st.session_state:
    st.session_state['conversations'] = {}
# You could make the default name here
DEFAULT_CONVO_NAME = "Conversa"

def get_new_conversation_name():
    num_default_conversations = sum(1 for convo_name in st.session_state['conversations'].keys() if convo_name.startswith(DEFAULT_CONVO_NAME))

    return f"{DEFAULT_CONVO_NAME} {num_default_conversations + 1}" # Conversa 1, Conversa 2 etc.

# Sidebar for Conversation Management
with st.sidebar:
    # Title With Custom Logo
    st.markdown("<h2 style='text-align: center;'>FarmAssist 🐄</h2>", unsafe_allow_html=True)  # Centered title with cow emoji

    def create_new_conversation():
        # Generate a unique ID for the new conversation
        new_convo_id = str(uuid.uuid4())  # Use UUID for unique keys
        # Use default name
        new_convo_name = get_new_conversation_name() # Generating the conversation name
        st.session_state['conversations'][new_convo_id] = {"name": new_convo_name, "history": []} # Name and empty chat history
        st.session_state['current_conversation'] = new_convo_id # Set it to the new conversation
        st.rerun()

    st.button(" ➕ New chat", on_click=create_new_conversation) # Sleek button

    def rename_conversation(convo_id, new_name): # Renaming conversation by params
        st.session_state['conversations'][convo_id]["name"] = new_name
        st.rerun()

    def delete_conversation(convo_id):
        del st.session_state['conversations'][convo_id]
        if 'current_conversation' in st.session_state and st.session_state['current_conversation'] == convo_id:
            del st.session_state['current_conversation']
        st.rerun()

    # Display existing conversations as buttons
    if 'conversations' in st.session_state:
        for convo_id, convo_data in st.session_state['conversations'].items(): # The key is the id
            convo_name = convo_data['name']
            col1, col2 = st.columns([0.8, 0.2])  # Adjust column widths as needed
            with col1:
                if st.button(f"{convo_name}", key=f"select_{convo_id}"):  # Showing the UUID
                    st.session_state['current_conversation'] = convo_id
                    st.rerun()  # Refresh to load the selected conversation

            with col2:
                # Replaced selectbox by buttons
                if st.button(f"⚙️", key=f"button_config{convo_id}"):
                    st.session_state[f'show_config_{convo_id}'] = not st.session_state.get(f'show_config_{convo_id}', False)

                if st.session_state.get(f'show_config_{convo_id}', False):
                    new_convo_name = st.text_input("New Name", value = convo_name, key=f"new_name_{convo_id}")
                    if st.button(" ✏️ ", key=f"rename{convo_id}") and new_convo_name:
                        rename_conversation(convo_id, new_convo_name)
                    if st.button(" 🗑️ ", key=f"delete{convo_id}"):
                        delete_conversation(convo_id)


# Main Chat Interface
st.title("FarmAssist 🐄 Chat")

if 'current_conversation' in st.session_state:
    conversation_id = st.session_state['current_conversation']
    convo_data = st.session_state['conversations'][conversation_id]
    st.subheader(f"Conversa: {convo_data['name']}")
    chat_history = convo_data['history']  # Gets history

    # Display Chat History
    for i, message in enumerate(chat_history):
        with st.chat_message(message['role']):
            st.markdown(message['content'], unsafe_allow_html=True)

    # User Input
    prompt = st.chat_input("Digite sua mensagem...", key=f"chat_input_{conversation_id}")  # Add the id chat, to separate
    if prompt:
        # Create the most recent message object
        user_message = {"role": "user", "content": prompt}

        # Check if prompt already in the last turn
        if chat_history and chat_history[-1]['role'] == 'user' and chat_history[-1]['content'] == prompt:
            st.warning("Duplicate message. Please try something else.")
        else:
            chat_history.append(user_message)
            with st.chat_message("user"):
                st.write(prompt)

            messages = []
            for turn in chat_history:
                messages.append({"role": turn["role"], "content": turn["content"]})

            resposta_assistente = gerar_resposta(prompt, messages)  # Get Response by OpenAI API
            assistant_message = {"role": "assistant", "content": resposta_assistente}  # Create Assistant message

            chat_history.append(assistant_message)  # Append Assistant

            with st.chat_message("assistant"):
                st.markdown(resposta_assistente, unsafe_allow_html=True)

            # Store conversation and prompt.
            st.session_state['conversations'][conversation_id]['history'] = chat_history  # Setting history
else:
    st.info("Selecione ou crie uma conversa na barra lateral para começar. 🐄")
