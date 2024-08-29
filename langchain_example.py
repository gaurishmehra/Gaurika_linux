from langchain import LLMChain, PromptTemplate
from langchain.chat_models import ChatOpenAI

template = PromptTemplate(input_variables=["name"], template="Hello, my name is {name}.")
llm_chain = LLMChain(llm=ChatOpenAI(), prompt=template,)
output = llm_chain({"name": "John"})
print(output)
