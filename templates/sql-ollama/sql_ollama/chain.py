from langchain.chat_models import ChatOllama
from langchain.prompts import ChatPromptTemplate
from langchain.schema.output_parser import StrOutputParser
from langchain.schema.runnable import RunnablePassthrough

# Add the LLM downloaded from Ollama
ollama_llm = "llama2:13b-chat"
llm = ChatOllama(model=ollama_llm)

from pathlib import Path
from langchain.utilities import SQLDatabase
db_path = Path(__file__).parent / "nba_roster.db"
rel = db_path.relative_to(Path.cwd())
db_string = f"sqlite:///{rel}"
db = SQLDatabase.from_uri(db_string, sample_rows_in_table_info=0)

def get_schema(_):
    return db.get_table_info()

def run_query(query):
    return db.run(query)

# Prompt
from langchain.memory import ConversationBufferMemory
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
template = """Based on the table schema below, write a SQL query that would answer the user's question:
{schema}

Question: {question}
SQL Query:"""
prompt = ChatPromptTemplate.from_messages([
    ("system", "Given an input question, convert it to a SQL query. No pre-amble."),
    MessagesPlaceholder(variable_name="history"),
    ("human", template)
])

memory = ConversationBufferMemory(return_messages=True)

# Chain to query with memory 
from langchain.schema.runnable import RunnableLambda

sql_chain = (
    RunnablePassthrough.assign(
       schema=get_schema,
       history=RunnableLambda(lambda x: memory.load_memory_variables(x)["history"])
    )| prompt
    | llm.bind(stop=["\nSQLResult:"])
    | StrOutputParser()
)

def save(input_output):
    output = {"output": input_output.pop("output")}
    memory.save_context(input_output, output)
    return output['output']
    
sql_response_memory = RunnablePassthrough.assign(output=sql_chain) | save

# Chain to answer
template = """Based on the table schema below, question, sql query, and sql response, write a natural language response:
{schema}

Question: {question}
SQL Query: {query}
SQL Response: {response}"""
prompt_response = ChatPromptTemplate.from_messages([
    ("system", "Given an input question and SQL response, convert it to a natural language answer. No pre-amble."),
    ("human", template)
])

chain = (
    RunnablePassthrough.assign(query=sql_response_memory) 
    | RunnablePassthrough.assign(
        schema=get_schema,
        response=lambda x: db.run(x["query"]),
    )
    | prompt_response 
    | llm
)
