import reflex as rx
from reflex import Field
from sqlmodel import SQLModel, Field, Relationship, select
from sqlalchemy import PrimaryKeyConstraint
from typing import List, Optional
import time

class QA(rx.Base):
    """A question and answer pair."""

    question: str
    answer: str
    id: Optional[int] = -1
    created_at: float = Field(default_factory=lambda: time.time())

class DataPlot(rx.Base):
    """A plot data"""

    plot_name: str
    column: str
    xaxis: str
    color: str
    title: str
    nickname: str
    id: Optional[int] = -1
    created_at: float = Field(default_factory=lambda: time.time())

class DataTable(rx.Base):
    """A plot data"""
    table_name: str
    title: str
    nickname: str
    id: Optional[int] = -1
    created_at: float = Field(default_factory=lambda: time.time())

class Portfolio(rx.Base):
    """A portfolio"""
    portfolio_name: str
    nickname: str
    id: Optional[int] = -1
    created_at: float = Field(default_factory=lambda: time.time())

class QAs(rx.Model, table=True):
    id: int = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    chat_id: int = Field(foreign_key="chats.id")
    question: str
    answer: str
    created_at: float = Field(default_factory=lambda: time.time())
    chat: Optional["Chats"] = Relationship(back_populates="qas")
    user: Optional["User"] = Relationship(back_populates="qas")
    

class DataPlots(rx.Model, table=True):
    id: int = Field()
    user_id: int = Field(foreign_key="user.id")
    chat_id: int = Field(foreign_key="chats.id")
    plot_name: str
    column: str
    xaxis: str
    color: str
    title: str
    nickname: str
    created_at: float = Field(default_factory=lambda: time.time())
    chat: Optional["Chats"] = Relationship(back_populates="dataplots")
    user: Optional["User"] = Relationship(back_populates="dataplots")
    
    __table_args__ = (
        PrimaryKeyConstraint('id', 'user_id', 'chat_id'),
    )

class DataTables(rx.Model, table=True):
    id: int = Field()
    user_id: int = Field(foreign_key="user.id")
    chat_id: int = Field(foreign_key="chats.id")
    table_name: str
    title: str
    nickname: str
    created_at: float = Field(default_factory=lambda: time.time())
    chat: Optional["Chats"] = Relationship(back_populates="datatables")
    user: Optional["User"] = Relationship(back_populates="datatables")

    __table_args__ = (
        PrimaryKeyConstraint('id', 'user_id', 'chat_id'),
    )

class Portfolios(rx.Model, table=True):
    id: int = Field()
    user_id: int = Field(foreign_key="user.id")
    chat_id: int = Field(foreign_key="chats.id")
    portfolio_name: str
    nickname: str
    created_at: float = Field(default_factory=lambda: time.time())
    chat: Optional["Chats"] = Relationship(back_populates="portfolios")
    user: Optional["User"] = Relationship(back_populates="portfolios")
    __table_args__ = (
        PrimaryKeyConstraint('id', 'user_id', 'chat_id'),
    )

class AgentSessions(rx.Model, table=True):
    """Store session_id for agent-chat-user combinations"""
    id: int = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    chat_id: int = Field(foreign_key="chats.id")
    agent_name: str
    session_id: str
    created_at: float = Field(default_factory=lambda: time.time())
    updated_at: float = Field(default_factory=lambda: time.time())
    chat: Optional["Chats"] = Relationship(back_populates="agent_sessions")
    user: Optional["User"] = Relationship(back_populates="agent_sessions")

class ChatDirectory(rx.Model, table=True):
    """A directory to organize chats. Supports up to 2 levels (root dirs and subdirs)."""
    id: int = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    name: str
    parent_id: Optional[int] = Field(default=None, foreign_key="chatdirectory.id")
    order: int = Field(default=0)
    created_at: float = Field(default_factory=lambda: time.time())
    user: Optional["User"] = Relationship(back_populates="chat_directories")
    chats: List["Chats"] = Relationship(back_populates="directory")


class Chats(rx.Model, table=True):
    id: int = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    chat_title: str
    directory_id: Optional[int] = Field(default=None, foreign_key="chatdirectory.id")
    created_at: float = Field(default_factory=lambda: time.time())
    qas:  List["QAs"] = Relationship(back_populates="chat")
    dataplots: List["DataPlots"] = Relationship(back_populates="chat")
    datatables: List["DataTables"] = Relationship(back_populates="chat")
    portfolios: List["Portfolios"] = Relationship(back_populates="chat")
    agent_sessions: List["AgentSessions"] = Relationship(back_populates="chat")
    user: Optional["User"] = Relationship(back_populates="chats")
    directory: Optional["ChatDirectory"] = Relationship(back_populates="chats")
    

class User(rx.Model, table=True):
    id: int = Field(primary_key=True)
    username: str
    email: str = ""  # Email for verification (optional for backwards compatibility)
    password: str
    created_at: float = Field(default_factory=lambda: time.time())
    # Terms of Service acceptance tracking
    terms_accepted_at: Optional[float] = None  # Timestamp when terms were accepted
    terms_version: str = ""  # Version of terms accepted (e.g., "2025-01")
    chats: List["Chats"] = Relationship(back_populates="user")
    chat_directories: List["ChatDirectory"] = Relationship(back_populates="user")
    qas: List["QAs"] = Relationship(back_populates="user")
    dataplots: List["DataPlots"] = Relationship(back_populates="user")
    datatables: List["DataTables"] = Relationship(back_populates="user")
    portfolios: List["Portfolios"] = Relationship(back_populates="user")
    agent_sessions: List["AgentSessions"] = Relationship(back_populates="user")
    

    # def to_dict(self):
    #     return {
    #         "id": self.id,
    #         "username": self.username,
    #         "chats_ids": [chat.id for chat in self.chats],
    #     }