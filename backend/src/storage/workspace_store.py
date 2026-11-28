from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from pymongo import ASCENDING, DESCENDING

from src.schemas.document import utc_now_iso
from src.schemas.workspace import (
    ConversationItem,
    ConversationMessage,
    ConversationSummary,
    NotebookItem,
    NoteItem,
    NoteType,
)


class WorkspaceStore(ABC):
    """Persistence contract for Notebooks, Conversations, and Saved Studio Notes."""

    @abstractmethod
    def ensure_indexes(self) -> None:
        raise NotImplementedError

    # --- Notebooks ---
    @abstractmethod
    def list_notebooks(self) -> list[NotebookItem]:
        raise NotImplementedError

    @abstractmethod
    def get_notebook(self, notebook_id: str) -> NotebookItem | None:
        raise NotImplementedError

    @abstractmethod
    def create_notebook(self, *, title: str, description: str = "", document_ids: list[str] | None = None) -> NotebookItem:
        raise NotImplementedError

    @abstractmethod
    def update_notebook(self, notebook_id: str, **updates) -> NotebookItem | None:
        raise NotImplementedError

    @abstractmethod
    def delete_notebook(self, notebook_id: str) -> bool:
        raise NotImplementedError

    # --- Conversations ---
    @abstractmethod
    def list_conversations(self, *, notebook_id: str | None = None, limit: int = 50) -> list[ConversationSummary]:
        raise NotImplementedError

    @abstractmethod
    def get_conversation(self, conversation_id: str) -> ConversationItem | None:
        raise NotImplementedError

    @abstractmethod
    def create_conversation(self, *, title: str = "Cuộc hội thoại mới", notebook_id: str | None = None) -> ConversationItem:
        raise NotImplementedError

    @abstractmethod
    def update_conversation_title(self, conversation_id: str, title: str) -> ConversationItem | None:
        raise NotImplementedError

    @abstractmethod
    def append_messages(
        self,
        conversation_id: str,
        new_messages: list[ConversationMessage],
        *,
        auto_title: str | None = None,
    ) -> ConversationItem | None:
        raise NotImplementedError

    @abstractmethod
    def delete_conversation(self, conversation_id: str) -> bool:
        raise NotImplementedError

    # --- Notes ---
    @abstractmethod
    def list_notes(self, *, notebook_id: str | None = None, limit: int = 100) -> list[NoteItem]:
        raise NotImplementedError

    @abstractmethod
    def create_note(
        self,
        *,
        title: str,
        content: str,
        note_type: NoteType = "pinned",
        notebook_id: str | None = None,
        source_document_ids: list[str] | None = None,
    ) -> NoteItem:
        raise NotImplementedError

    @abstractmethod
    def delete_note(self, note_id: str) -> bool:
        raise NotImplementedError


def _to_summary(conv: ConversationItem) -> ConversationSummary:
    return ConversationSummary(
        id=conv.id,
        title=conv.title,
        notebook_id=conv.notebook_id,
        message_count=len(conv.messages),
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


class InMemoryWorkspaceStore(WorkspaceStore):
    """In-memory workspace store for unit tests and `--memory` runs."""

    def __init__(self) -> None:
        self.notebooks: dict[str, NotebookItem] = {}
        self.conversations: dict[str, ConversationItem] = {}
        self.notes: dict[str, NoteItem] = {}

    def ensure_indexes(self) -> None:
        return None

    def list_notebooks(self) -> list[NotebookItem]:
        items = list(self.notebooks.values())
        items.sort(key=lambda n: n.updated_at, reverse=True)
        return items

    def get_notebook(self, notebook_id: str) -> NotebookItem | None:
        return self.notebooks.get(notebook_id)

    def create_notebook(self, *, title: str, description: str = "", document_ids: list[str] | None = None) -> NotebookItem:
        now = utc_now_iso()
        nb = NotebookItem(
            id=f"nb-{uuid.uuid4().hex[:10]}",
            title=title.strip(),
            description=description.strip(),
            document_ids=list(document_ids or []),
            created_at=now,
            updated_at=now,
        )
        self.notebooks[nb.id] = nb
        return nb

    def update_notebook(self, notebook_id: str, **updates) -> NotebookItem | None:
        nb = self.notebooks.get(notebook_id)
        if nb is None:
            return None
        clean = {k: v for k, v in updates.items() if v is not None}
        clean["updated_at"] = utc_now_iso()
        updated = nb.model_copy(update=clean)
        self.notebooks[notebook_id] = updated
        return updated

    def delete_notebook(self, notebook_id: str) -> bool:
        return self.notebooks.pop(notebook_id, None) is not None

    def list_conversations(self, *, notebook_id: str | None = None, limit: int = 50) -> list[ConversationSummary]:
        items = list(self.conversations.values())
        if notebook_id is not None:
            items = [c for c in items if c.notebook_id == notebook_id]
        items.sort(key=lambda c: c.updated_at, reverse=True)
        return [_to_summary(c) for c in items[:limit]]

    def get_conversation(self, conversation_id: str) -> ConversationItem | None:
        return self.conversations.get(conversation_id)

    def create_conversation(self, *, title: str = "Cuộc hội thoại mới", notebook_id: str | None = None) -> ConversationItem:
        now = utc_now_iso()
        conv = ConversationItem(
            id=f"conv-{uuid.uuid4().hex[:10]}",
            title=title.strip() or "Cuộc hội thoại mới",
            notebook_id=notebook_id,
            messages=[],
            created_at=now,
            updated_at=now,
        )
        self.conversations[conv.id] = conv
        return conv

    def update_conversation_title(self, conversation_id: str, title: str) -> ConversationItem | None:
        conv = self.conversations.get(conversation_id)
        if conv is None:
            return None
        updated = conv.model_copy(update={"title": title.strip(), "updated_at": utc_now_iso()})
        self.conversations[conversation_id] = updated
        return updated

    def append_messages(
        self,
        conversation_id: str,
        new_messages: list[ConversationMessage],
        *,
        auto_title: str | None = None,
    ) -> ConversationItem | None:
        conv = self.conversations.get(conversation_id)
        if conv is None:
            return None
        title = conv.title
        if auto_title and not conv.messages and conv.title in {"Cuộc hội thoại mới", "Cuộc hỏi mới"}:
            title = auto_title.strip()[:80]
        updated = conv.model_copy(
            update={
                "title": title,
                "messages": [*conv.messages, *new_messages],
                "updated_at": utc_now_iso(),
            }
        )
        self.conversations[conversation_id] = updated
        return updated

    def delete_conversation(self, conversation_id: str) -> bool:
        return self.conversations.pop(conversation_id, None) is not None

    def list_notes(self, *, notebook_id: str | None = None, limit: int = 100) -> list[NoteItem]:
        items = list(self.notes.values())
        if notebook_id is not None:
            items = [n for n in items if n.notebook_id == notebook_id]
        items.sort(key=lambda n: n.updated_at, reverse=True)
        return items[:limit]

    def create_note(
        self,
        *,
        title: str,
        content: str,
        note_type: NoteType = "pinned",
        notebook_id: str | None = None,
        source_document_ids: list[str] | None = None,
    ) -> NoteItem:
        now = utc_now_iso()
        note = NoteItem(
            id=f"note-{uuid.uuid4().hex[:10]}",
            notebook_id=notebook_id,
            title=title.strip(),
            content=content,
            note_type=note_type,
            source_document_ids=list(source_document_ids or []),
            created_at=now,
            updated_at=now,
        )
        self.notes[note.id] = note
        return note

    def delete_note(self, note_id: str) -> bool:
        return self.notes.pop(note_id, None) is not None


class MongoWorkspaceStore(WorkspaceStore):
    """MongoDB persistence for Notebooks, Conversations, and Saved Notes."""

    def __init__(self, db) -> None:
        self.db = db
        self.notebooks_col = db["notebooks"]
        self.conversations_col = db["conversations"]
        self.notes_col = db["notes"]

    def ensure_indexes(self) -> None:
        self.notebooks_col.create_index([("id", ASCENDING)], unique=True)
        self.notebooks_col.create_index([("updated_at", DESCENDING)])

        self.conversations_col.create_index([("id", ASCENDING)], unique=True)
        self.conversations_col.create_index([("notebook_id", ASCENDING), ("updated_at", DESCENDING)])

        self.notes_col.create_index([("id", ASCENDING)], unique=True)
        self.notes_col.create_index([("notebook_id", ASCENDING), ("updated_at", DESCENDING)])

    def list_notebooks(self) -> list[NotebookItem]:
        cursor = self.notebooks_col.find({}, {"_id": 0}).sort("updated_at", DESCENDING)
        return [NotebookItem.model_validate(row) for row in cursor]

    def get_notebook(self, notebook_id: str) -> NotebookItem | None:
        raw = self.notebooks_col.find_one({"id": notebook_id}, {"_id": 0})
        return NotebookItem.model_validate(raw) if raw else None

    def create_notebook(self, *, title: str, description: str = "", document_ids: list[str] | None = None) -> NotebookItem:
        now = utc_now_iso()
        nb = NotebookItem(
            id=f"nb-{uuid.uuid4().hex[:10]}",
            title=title.strip(),
            description=description.strip(),
            document_ids=list(document_ids or []),
            created_at=now,
            updated_at=now,
        )
        self.notebooks_col.replace_one({"id": nb.id}, nb.model_dump(mode="json", by_alias=False), upsert=True)
        return nb

    def update_notebook(self, notebook_id: str, **updates) -> NotebookItem | None:
        nb = self.get_notebook(notebook_id)
        if nb is None:
            return None
        clean = {k: v for k, v in updates.items() if v is not None}
        clean["updated_at"] = utc_now_iso()
        updated = nb.model_copy(update=clean)
        self.notebooks_col.replace_one(
            {"id": notebook_id},
            updated.model_dump(mode="json", by_alias=False),
            upsert=True,
        )
        return updated

    def delete_notebook(self, notebook_id: str) -> bool:
        res = self.notebooks_col.delete_one({"id": notebook_id})
        return res.deleted_count > 0

    def list_conversations(self, *, notebook_id: str | None = None, limit: int = 50) -> list[ConversationSummary]:
        flt = {"notebook_id": notebook_id} if notebook_id is not None else {}
        cursor = self.conversations_col.find(flt, {"_id": 0}).sort("updated_at", DESCENDING).limit(limit)
        return [_to_summary(ConversationItem.model_validate(row)) for row in cursor]

    def get_conversation(self, conversation_id: str) -> ConversationItem | None:
        raw = self.conversations_col.find_one({"id": conversation_id}, {"_id": 0})
        return ConversationItem.model_validate(raw) if raw else None

    def create_conversation(self, *, title: str = "Cuộc hội thoại mới", notebook_id: str | None = None) -> ConversationItem:
        now = utc_now_iso()
        conv = ConversationItem(
            id=f"conv-{uuid.uuid4().hex[:10]}",
            title=title.strip() or "Cuộc hội thoại mới",
            notebook_id=notebook_id,
            messages=[],
            created_at=now,
            updated_at=now,
        )
        self.conversations_col.replace_one({"id": conv.id}, conv.model_dump(mode="json", by_alias=False), upsert=True)
        return conv

    def update_conversation_title(self, conversation_id: str, title: str) -> ConversationItem | None:
        conv = self.get_conversation(conversation_id)
        if conv is None:
            return None
        updated = conv.model_copy(update={"title": title.strip(), "updated_at": utc_now_iso()})
        self.conversations_col.replace_one(
            {"id": conversation_id},
            updated.model_dump(mode="json", by_alias=False),
            upsert=True,
        )
        return updated

    def append_messages(
        self,
        conversation_id: str,
        new_messages: list[ConversationMessage],
        *,
        auto_title: str | None = None,
    ) -> ConversationItem | None:
        conv = self.get_conversation(conversation_id)
        if conv is None:
            return None
        title = conv.title
        if auto_title and not conv.messages and conv.title in {"Cuộc hội thoại mới", "Cuộc hỏi mới"}:
            title = auto_title.strip()[:80]
        updated = conv.model_copy(
            update={
                "title": title,
                "messages": [*conv.messages, *new_messages],
                "updated_at": utc_now_iso(),
            }
        )
        self.conversations_col.replace_one(
            {"id": conversation_id},
            updated.model_dump(mode="json", by_alias=False),
            upsert=True,
        )
        return updated

    def delete_conversation(self, conversation_id: str) -> bool:
        res = self.conversations_col.delete_one({"id": conversation_id})
        return res.deleted_count > 0

    def list_notes(self, *, notebook_id: str | None = None, limit: int = 100) -> list[NoteItem]:
        flt = {"notebook_id": notebook_id} if notebook_id is not None else {}
        cursor = self.notes_col.find(flt, {"_id": 0}).sort("updated_at", DESCENDING).limit(limit)
        return [NoteItem.model_validate(row) for row in cursor]

    def create_note(
        self,
        *,
        title: str,
        content: str,
        note_type: NoteType = "pinned",
        notebook_id: str | None = None,
        source_document_ids: list[str] | None = None,
    ) -> NoteItem:
        now = utc_now_iso()
        note = NoteItem(
            id=f"note-{uuid.uuid4().hex[:10]}",
            notebook_id=notebook_id,
            title=title.strip(),
            content=content,
            note_type=note_type,
            source_document_ids=list(source_document_ids or []),
            created_at=now,
            updated_at=now,
        )
        self.notes_col.replace_one({"id": note.id}, note.model_dump(mode="json", by_alias=False), upsert=True)
        return note

    def delete_note(self, note_id: str) -> bool:
        res = self.notes_col.delete_one({"id": note_id})
        return res.deleted_count > 0
