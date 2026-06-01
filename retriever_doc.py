import re,os
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_core.stores import InMemoryStore
from langchain_chroma import Chroma
from langchain_classic.retrievers import ParentDocumentRetriever
from langchain_text_splitters import RecursiveCharacterTextSplitter, MarkdownHeaderTextSplitter
from dotenv import load_dotenv

load_dotenv()

with open("tello无人机操作SDK.txt","r", encoding="utf-8") as f:
    book = f.read()
book_mark = re.sub(r'【(.+?)】', r'# \1', book)

parent_splitter = MarkdownHeaderTextSplitter(
    headers_to_split_on=[("#", "操作类型")],
    strip_headers=False   #保留标题
)
parent_docs = parent_splitter.split_text(book_mark)

child_splitter = RecursiveCharacterTextSplitter(
    chunk_size=100,
    chunk_overlap=20,
    separators = ["\n"]
)

embeddings = DashScopeEmbeddings(
    model="text-embedding-v1",
    dashscope_api_key=os.getenv("DASHSCOPE_API_KEY"),
)

store = InMemoryStore()

vectorstore = Chroma(
    embedding_function = embeddings,
    collection_name = "tello_sdk",
    persist_directory= "./chroma_db"
)

retriever = ParentDocumentRetriever(
    vectorstore = vectorstore,
    docstore = store,
    child_splitter=child_splitter,
    search_kwargs={"k": 1}
)
if vectorstore._collection.count() == 0:
    retriever.add_documents(parent_docs)
