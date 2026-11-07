# Simple PDF RAG chatbot

Ask questions about the PDF documents in `papers/`. The app extracts text from
each PDF, splits it into chunks, indexes the chunks in an in-memory FAISS vector
store, retrieves relevant passages, and asks Gemini to answer with page citations.

## Setup

1. Use Python 3.10 or newer and install the dependencies:

	```sh
	pip install -r requirements.txt
	```

2. Copy `.env.example` to `.env` and set your Google AI Studio API key as
	`GOOGLE_API_KEY`.

3. Run the chatbot from any directory:

	```sh
	python chatbot.py
	```

The vector index is rebuilt each time the app starts. Add PDF files to `papers/`
and restart to include them. Type `quit` (or `q`) to exit.