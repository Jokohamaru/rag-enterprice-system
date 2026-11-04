from langchain_community.document_loaders import DirectoryLoader, UnstructuredFileLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from dotenv import load_dotenv

load_dotenv()

from pprint import pprint

MARKDOWN_SEPARATOR = [
    "\n#{1,6} ",
    "```\n",
    "\n\\*\\*\\*+\n",
    "\n---+\n",
    "\n___+\n",
    "\n\n",
    "\n",
    " ",
    "",
]

loader = DirectoryLoader(
    path='./papers',
    glob="**/*.pdf",
    loader_cls=UnstructuredFileLoader,
    show_progress=True,
    use_multithreading=True
)

docs = loader.load()

text_spliter = RecursiveCharacterTextSplitter(
    chunk_size=1200,
    chunk_overlap=200,
    add_start_index=True,
    strip_whitespace=True,
    separators=MARKDOWN_SEPARATOR,
)

splits = text_spliter.split_documents(docs)

pprint(splits)