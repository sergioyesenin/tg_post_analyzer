import os

os.environ["LITELLM_LOG"] = "ERROR"   # либо "WARNING"
os.environ["LITELLM_VERBOSE"] = "false"


from crewai import LLM

llm = LLM(
    model="ollama/llama3:8b-instruct-q4_K_M",
    base_url="http://localhost:11434",
    temperature=0.2,
)

response = llm.call("Напиши короткий тестовый ответ.")
print(response)
