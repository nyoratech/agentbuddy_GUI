import os
# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv('/home/riccardo247/YourIndexingAI/finbuddy/.env')

import reflex as rx
from sqlmodel import select, SQLModel, Field, Relationship
from openai import OpenAI
from YourIndexingAI.rx_interface import (init_bot, list_saved_portfolios, list_all_portfolios, list_saved_plots,
                                         load_files_from_directory, read_live_portfolio,
                                         read_portfolio,
                                         load_datas_from_directory,
                                         pool_jobids)
from finbuddy.data_models.db_users import QA, QAs, Chats, User, DataPlot, DataPlots, DataTable, DataTables, Portfolio, Portfolios, AgentSessions, ChatDirectory
from finbuddy.data_models.portfolios import liveinstruments
from YourIndexingAI.modules.modules_utils import process_table, replace_expection, extract_tag_content
import re

from PIL import Image
import sqlalchemy
import pandas as pd
from plotly import express as px
from plotly.graph_objects import Figure as Figure_plotly
from typing import TypedDict, Optional, List, Dict, Tuple, Any, Union
import time
import json
import sys
from io import StringIO
from pathlib import Path
import asyncio
import aio_pika
import json

# PostgreSQL permission checking for shared chats
from permission_db.postgres.connection import get_connection, check_permission, init_pool

# Initialize PostgreSQL connection pool for RBAC
try:
    init_pool()
    print("[INFO] PostgreSQL connection pool initialized for RBAC")
except Exception as e:
    print(f"[WARNING] Failed to initialize PostgreSQL pool: {e}")

# FastStream imports for CloudAMQP support
try:
    from faststream.rabbit import RabbitBroker, RabbitExchange, RabbitQueue, ExchangeType
    FASTSTREAM_AVAILABLE = True
except ImportError:
    FASTSTREAM_AVAILABLE = False
    print("[WARNING] FastStream not available - CloudAMQP consumer disabled")

# Flag to use CloudAMQP instead of local RabbitMQ
# Set via environment variable or defaults to False (use local)
USE_CLOUDAMQP = os.getenv("USE_CLOUDAMQP", "false").lower() == "true"
CLOUDAMQP_URL = os.getenv("CLOUDAMQP_URL", "")

# In this minimal/mock build the agent is mocked, so an OpenAI key is optional.
if not os.getenv("OPENAI_API_KEY"):
    print("[WARNING] OPENAI_API_KEY not set - OK for the minimal/mock build.")




DEFAULT_CHATS = {
    "Buddy": [],
}





bot = init_bot()
from finbuddy.data_models.db_users import DataTable, DataPlot

# Global store for running background tasks, to avoid storing them in the picklable state.
# We'll key this by user ID to manage per-user tasks.
_background_tasks = {}

from datetime import datetime, timedelta

import numpy as np
# Generate 50 months of portfolio data, ending at June 2025
portfolio_data = []
base_value = 100000
current_date = datetime(2025, 6, 25)
for i in range(50):
    date_str = current_date.strftime("%d/%m")
    # Add random variation: std normal noise with 10% stddev
    noise = np.random.normal(0, 0.10)
    value = (base_value + i * 500) * (1 + noise)
    portfolio_data.append({"date": date_str, "value": round(value, 2)})
    # Move back 1 month
    if current_date.month == 1:
        current_date = current_date.replace(year=current_date.year - 1, month=12)
    else:
        current_date = current_date.replace(month=current_date.month - 1)
# Reverse to chronological order
portfolio_data = list(reversed(portfolio_data))


class DirectoryInfo(TypedDict):
    """Typed dict for directory information in foreach."""
    id: int
    name: str
    parent_id: Optional[int]
    chat_titles: List[str]


class SharedChatInfo(TypedDict):
    """Typed dict for shared chat information."""
    chat_id: int
    title: str
    owner: str
    permission: str  # 'read', 'write', or 'admin'


class InstrumentMerged(TypedDict):
    file: str
    name: str
    price: str
    day: str
    month: str
    six_months: str
    prompt: str
    returns: List[Dict]  # or Dict[str, Any] if you have mixed types
    chart_y_max: float
    chart_y_min: float
    day_is_negative: bool
    month_is_negative: bool
    six_months_is_negative: bool

class InstrumentSection(TypedDict):
    section: str
    merged_date: List[InstrumentMerged]


class State(rx.State):
    """The app state."""

    # JWT token for API authentication (stored in browser localStorage)
    jwt_token: str = rx.LocalStorage(name="jwt_token")

    # A dict from the chat name to the list of questions and answers.
    chats_list: dict[str, list[QA]] = DEFAULT_CHATS

    #this is the new structure for plots. even old plots should migrate to this one
    chats_name_plots: dict[str, list[DataPlot]] = DEFAULT_CHATS
    chats_name_tables: dict[str, list[DataTable]] = DEFAULT_CHATS
    chats_data_plots: dict[str, List[Tuple[Figure_plotly, Dict[str, str]]]] = DEFAULT_CHATS
    chats_data_lightweight: dict[str, List[Tuple[str, Dict[str, str]]]] = DEFAULT_CHATS
    chats_data_tables: dict[str, List[Tuple[pd.DataFrame, Dict[str, str]]]] = DEFAULT_CHATS
    chats_name_portfolios: dict[str, list[Portfolio]] = DEFAULT_CHATS
    
    # New state variable for combined content in chronological order
    # Each item is a tuple: (content_type, content, timestamp)
    # where content_type is "message", "table", or "plot"
    combined_name: dict[str, list[Tuple[str,Union[QA, DataPlot, DataTable], float]]] = DEFAULT_CHATS
    combined_content: dict[str, List[Tuple[str, Union[QA,Tuple[Figure_plotly, Dict[str, str]],Tuple[pd.DataFrame, Dict[str, str]]], float]]] = DEFAULT_CHATS

    # The current chat name.
    current_chat = "Buddy"
    # The current chat ID (used for shared chats where user doesn't own the chat)
    current_chat_id: Optional[int] = None
    # Whether current chat is a shared chat (not owned by current user)
    is_current_chat_shared: bool = False
    # Username of the owner of the current shared chat (for loading files from their directory)
    shared_chat_owner: str = ""

    # Sharing UI state
    share_chat_name: str = ""  # Chat name being shared (for context menu)
    share_username_input: str = ""  # Username input for sharing
    share_permission: str = "read"  # Permission level: read, write, admin
    user_groups: List[Dict[str, str]] = []  # User's groups: [{"group_id": str, "group_name": str}]

    # Container share dialog state
    share_container_dialog_open: bool = False
    share_dialog_container_id: str = ""
    share_dialog_container_name: str = ""

    # The current question.
    question: str

    def set_question(self, question: str):
        """Set the question in the state."""
        self.question = question

    # Whether we are processing the question.
    processing: bool = False

    # The name of the new chat.
    new_chat_name: str = ""

    # Chat directory management
    # Structure: {dir_id: {"name": str, "parent_id": int|None, "expanded": bool}}
    chat_directories: Dict[int, Dict[str, Any]] = {}
    # Set of expanded directory IDs
    expanded_dirs: List[int] = []
    # Name for creating new directory
    new_dir_name: str = ""
    # Directory being renamed (id or None)
    renaming_dir_id: Optional[int] = None
    # New name during rename
    rename_dir_value: str = ""
    # Drag-and-drop state
    dragging_chat: str = ""  # Chat title being dragged
    drag_over_dir_id: Optional[int] = None  # Directory being hovered over

    # Shared chats (from PostgreSQL RBAC) - chats shared with this user by others
    shared_chats: List[Dict[str, Any]] = []
    # ID of the "Shared with you" directory (set during load_directories_from_db)
    shared_with_you_dir_id: Optional[int] = None

    # Audio playback state
    is_audio_playing: bool = False
    audio_interaction_occurred: bool = False  # True after first user interaction to enable audio
    audio_play_enabled: bool = False  # User preference to play audio, controlled by toggle

    #live portfolio to analise they are json strings
    live_portfolio: str = ""
    live_code: str = ""
    live_return: str = ""
    live_plot: List[Tuple[Figure_plotly, Dict[str, str]]] = []
    #
    #stats dashboard portfolio to analise they are json strings
    stats_portfolio: str = ""
    stats_code: str = ""
    stats_return: str = ""
    stats_stats: str = ""
    stats_plot: List[Tuple[Figure_plotly, Dict[str, str]]] = []
    stats_risk: str = "Medium"
    stats_risk_level: int = 50
    #stats_dash_value: int = 50
    #stats_dash_arrow: int = 50
    #risk_level: int = 50
    #dash_value: int = 50
    stats_std_annual: float = 0.15  
    class EqPerformance(TypedDict):
        month: str
        value: int

    class EqPerformanceLightweight(TypedDict):
        plot_name: str
        title: str
        xaxis: str
        yaxis: str
        series_name: str
        series_data: List[Dict[str, Any]]

    class EqSector(TypedDict):
        name: str
        value: int
        value_str: str
        fill: str

    class EqStat(TypedDict):
        metric_name: str
        metric_value: str

    class EqHoldings(TypedDict):
        ticker: str
        weight: float

    eq_performance: List[EqPerformance] = [
        {"month": "Jan", "value": 100000},
        {"month": "Feb", "value": 102500},
    ]
    eq_performance_lightweight: EqPerformanceLightweight= {"plot_name": "eq_performance", 
    "title": "Portfolio Historical Performance", 
    "xaxis": "Month", "yaxis": "Value", 
    "series_name": "Portfolio", 
    "series_data": eq_performance}
    eq_performance_lightweight_json: str = ""

    fi_performance: List[EqPerformance] = [
        {"month": "Jan", "value": 100000},
        {"month": "Feb", "value": 102500},
    ]
    fi_performance_lightweight: EqPerformanceLightweight= {"plot_name": "fi_performance", 
    "title": "Portfolio Historical Performance", 
    "xaxis": "Month", "yaxis": "Value", 
    "series_name": "Portfolio", 
    "series_data": fi_performance}
    fi_performance_lightweight_json: str = ""

    eq_stats: List[EqStat] = [
        {"metric_name": "Portfolio Value", "metric_value": "$120,540"},
        {"metric_name": "Net Return", "metric_value": "25.3%"},
        {"metric_name": "Volatility", "metric_value": "18.5%"},
        {"metric_name": "Sharpe Ratio", "metric_value": "1.22"},
    ]
    FI_stats: List[EqStat] = [
        {"metric_name": "Portfolio Value", "metric_value": "$120,540"},
        {"metric_name": "Net Return", "metric_value": "25.3%"},
        {"metric_name": "Volatility", "metric_value": "18.5%"},
        {"metric_name": "Sharpe Ratio", "metric_value": "1.22"},
    ]
    fi_returns: List[EqStat] = [
        {"metric_name": "Portfolio Value", "metric_value": "$120,540"},
        {"metric_name": "Net Return", "metric_value": "25.3%"},
        {"metric_name": "Volatility", "metric_value": "18.5%"},
        {"metric_name": "Sharpe Ratio", "metric_value": "1.22"},
    ]

    # Agent builder shelf mode: when True, shelf shows chat instead of tools
    agent_shelf_chat_mode: bool = False
    # Sidebar visibility for agent builder
    agent_sidebar_visible: bool = True
    # Test Run section expanded/collapsed
    test_run_expanded: bool = False

    def toggle_test_run(self):
        """Toggle the Test Run section expanded/collapsed."""
        self.test_run_expanded = not self.test_run_expanded

    def toggle_agent_sidebar(self):
        """Toggle the agent sidebar visibility."""
        self.agent_sidebar_visible = not self.agent_sidebar_visible

    def go_to_chat_with_prompt(self, prompt: str):
        """Redirect to the main chat page and set the question in the text area."""
        self.question = prompt
        return rx.redirect("/")

    def toggle_agent_shelf_chat_mode(self, value: bool):
        """Toggle the agent builder shelf between tools view and chat view."""
        self.agent_shelf_chat_mode = value

    eq_sectors: List[EqSector] = [
        {"name": "Technology", "value": 400, "fill": "#8884d8"},
        {"name": "Financials", "value": 300, "fill": "#AC0E08"},
    ]
    eq_holdings: List[EqHoldings] = []
    FI_holdings: List[EqHoldings] = []
    current_portfolio_holdings: List[EqHoldings] = []
    eq_stats: List[EqStat] = [
        {"metric_name": "Portfolio Value", "metric_value": "$120,540"},
        {"metric_name": "Net Return", "metric_value": "25.3%"},
        {"metric_name": "Volatility", "metric_value": "18.5%"},
        {"metric_name": "Sharpe Ratio", "metric_value": "1.22"},
    ]
    eq_returns: List[EqStat] = [
        {"metric_name": "Portfolio Value", "metric_value": "$120,540"},
        {"metric_name": "Net Return", "metric_value": "25.3%"},
        {"metric_name": "Volatility", "metric_value": "18.5%"},
        {"metric_name": "Sharpe Ratio", "metric_value": "1.22"},
    ]
    #variable s for markets dashboard
    instrument_sections: List[str] = ["USA", "USA Factors", "WORLD", "FOREX"]

    instrument_data: List[List[Dict[str, str]]] = [
        [  # USA
            {"file":"portfolio_factors_1","name": "S&P 500", "price": "4,207.45", "day": "+1.2%", "month": "4.1%", "six_months": "1.3%", "prompt": "create custom portfolio"},
            {"file":"","name": "FB - S&P 500 ESG", "price": "4,207.45", "day": "+1.2%", "month": "4.1%", "six_months": "1.3%", "prompt": "create custom portfolio"},
            {"file":"","name": "FB - S&P 500 Green", "price": "4,207.45", "day": "+1.2%", "month": "4.1%", "six_months": "1.3%", "prompt": "create custom portfolio"},
            {"file":"","name": "FB - S&P 500 Defensive", "price": "4,207.45", "day": "+1.2%", "month": "4.1%", "six_months": "1.3%", "prompt": "create custom portfolio"},
            {"file":"","name": "NASDAQ", "price": "12,578.99", "day": "+1.91%", "month": "1.7%", "six_months": "4.6%", "prompt": "create custom portfolio"},
        ],
        [  # USA Factors
            {"file":"","name": "FB - S&P 500 Quality", "price": "4,207.45", "day": "+1.2%", "month": "4.1%", "six_months": "1.3%", "prompt": "create custom portfolio"},
            {"file":"","name": "FB - S&P 500 Value", "price": "4,207.45", "day": "+1.2%", "month": "4.1%", "six_months": "1.3%", "prompt": "create custom portfolio"},
            {"file":"","name": "FB - S&P 500 Growth", "price": "4,207.45", "day": "+1.2%", "month": "4.1%", "six_months": "1.3%", "prompt": "create custom portfolio"},
            {"file":"","name": "FB - S&P 500 Momentum", "price": "4,207.45", "day": "+1.2%", "month": "4.1%", "six_months": "1.3%", "prompt": "create custom portfolio"},
        ],
        [  # WORLD
            {"file":"","name": "FTSE 100", "price": "7,852.64", "day": "+0.6%", "month": "6.0%", "six_months": "2.3%", "prompt": "create custom portfolio"},
            {"file":"","name": "DAX", "price": "15,798.42", "day": "+0.8%", "month": "0.7%", "six_months": "2.3%", "prompt": "create custom portfolio"},
        ],
        [  # FOREX
            {"file":"","name": "EUR/USD", "price": "1.0963", "day": "-0.02%", "month": "0.19%", "six_months": "3.8%", "prompt": "create custom portfolio"},
        ]
    ]
    instrument_return: List[List[Dict[str, str]]] = [
        [  # USA
            portfolio_data,
            portfolio_data,
            portfolio_data,
            portfolio_data,
            portfolio_data,
        ],
        [  # USA Factors
            portfolio_data,
            portfolio_data,
            portfolio_data,
            portfolio_data,
        ],  # USA Factors
        [  # WORLD
            portfolio_data,
            portfolio_data,
        ],
        [  # FOREX
            portfolio_data,
        ]
    ]


    instrument_merged: List[List[InstrumentMerged]] = [
        [
            {**item, "returns": returns,
                "day_is_negative": item["day"].startswith("-"),
                "month_is_negative": item["month"].startswith("-"),
            "six_months_is_negative": item["six_months"].startswith("-")}
            for item, returns in zip(section_items, section_returns)
        ]
        for section_items, section_returns in zip(instrument_data, instrument_return)
    ]

    instrument_data_all: List[InstrumentSection] = [
        {"section": section, "merged_date": merged_date}
        for section, merged_date in zip(instrument_sections, instrument_merged)
    ]

    #variables for markets strip top
    market_strip: List[Dict[str, str]] = [
            {"ticker": "XRP",  "perc_move": "4.44", "up_down": True},
            {"ticker": "AMGO", "perc_move": "0.00", "up_down": True},
            {"ticker": "AVCT", "perc_move": "-5.11", "up_down": False},
            {"ticker": "ITV",  "perc_move": "-1.24", "up_down": False},
            {"ticker": "BT.A", "perc_move": "-0.73", "up_down": False},
            {"ticker": "AAPL", "perc_move": "1.64",  "up_down": True},
            {"ticker": "TSLA", "perc_move": "3.67",  "up_down": True},
            {"ticker": "GOOG", "perc_move": "2.15",  "up_down": True},
            {"ticker": "MSFT", "perc_move": "-0.88", "up_down": False},
            {"ticker": "NFLX", "perc_move": "5.23",  "up_down": True},
            {"ticker": "NVDA", "perc_move": "-2.34", "up_down": False},
            {"ticker": "META", "perc_move": "0.75",  "up_down": True},
            {"ticker": "BABA", "perc_move": "-1.12", "up_down": False},
            {"ticker": "ORCL", "perc_move": "0.89",  "up_down": True},
            {"ticker": "AMD",  "perc_move": "3.10",  "up_down": True},
            {"ticker": "IBM",  "perc_move": "-0.45", "up_down": False},
            {"ticker": "SAP",  "perc_move": "1.22",  "up_down": True},
            {"ticker": "SONY", "perc_move": "-2.00", "up_down": False},
            {"ticker": "UBER", "perc_move": "4.01",  "up_down": True},
            {"ticker": "SHOP", "perc_move": "2.74",  "up_down": True},
            {"ticker": "PYPL", "perc_move": "-3.21", "up_down": False},
            {"ticker": "ADBE", "perc_move": "0.58",  "up_down": True},
        ]

    # how many tiles you want to show at once
    market_window_size: int = 15
    # index of the first element currently visible               (⬅ updated by the buttons)
    market_window_start: int = 5


    #portfolio dashboard factor exposures
    eq_factor_scores: List[Dict[str, Union[str, float]]] = [
        {"factor": "Value", "score": 3.0},
        {"factor": "Quality", "score": 4.0},
        {"factor": "Size", "score": 3.0},
        {"factor": "Momentum", "score": 2.0},
        {"factor": "Volatility", "score": 2.5},
    ]
    for item in eq_factor_scores:
        item["dash"] = ((item["score"]+3) / 6.5) * 282.74
        item["arrow_angle"] = -90 + ((item["score"]+3)/6.5) * 180
        item["score_norm"] = round((item["score"]+3) / 6.5, 2)

    # ==================== Fixed Income Fake Data ====================

    # Fake data for Fixed Income charts
    FI_stats_duration_buckets: List[Dict[str, Union[str, float]]] = [
        {"bucket": "0–3y", "weight": 15},
        {"bucket": "3–6y", "weight": 25},
        {"bucket": "6–10y", "weight": 30},
        {"bucket": "10–20y", "weight": 20},
        {"bucket": "20y+", "weight": 10},
    ]

    FI_stats_yield_buckets: List[Dict[str, Union[str, float]]] = [
        {"bucket": "0–1%", "weight": 5},
        {"bucket": "1–2%", "weight": 15},
        {"bucket": "2–3%", "weight": 30},
        {"bucket": "3–4%", "weight": 25},
        {"bucket": "4%+", "weight": 25},
    ]

    # Coupon-rate buckets (notional distribution)
    FI_stats_coupon_buckets: List[Dict[str, Union[str, float]]] = [
        {"bucket": "<2%", "notional": 20},
        {"bucket": "2–4%", "notional": 50},
        {"bucket": ">4%", "notional": 30},
    ]

    # Average coupon by duration bucket
    FI_stats_duration_avg_coupon: List[Dict[str, Union[str, float]]] = [
        {"bucket": "0–3y", "avg_coupon": 2.5},
        {"bucket": "3–6y", "avg_coupon": 3.1},
        {"bucket": "6–10y", "avg_coupon": 4.0},
        {"bucket": "10–20y", "avg_coupon": 4.4},
        {"bucket": "20y+", "avg_coupon": 4.8},
    ]

    # Average yield by duration bucket
    FI_stats_duration_avg_yield: List[Dict[str, Union[str, float]]] = [
        {"bucket": "0–3y", "avg_yield": 1.8},
        {"bucket": "3–6y", "avg_yield": 2.4},
        {"bucket": "6–10y", "avg_yield": 3.2},
        {"bucket": "10–20y", "avg_yield": 3.6},
        {"bucket": "20y+", "avg_yield": 4.1},
    ]

    # Fake summary metrics for Fixed Income portfolio
    FI_stats_notional: str = "10Mln"
    FI_stats_yield: str = "3.2%"
    FI_stats_coupon: str = "4.5%"
    FI_stats_duration: str = "6.5y"
    FI_stats_mod_duration: str = "5.8y"
    FI_stats_convexity: str = "120.4"
    FI_stats_dv01: str = "0.07"

    # Fake key rate sensitivity data (bps change per maturity)
    FI_stats_keyrate_sensitivity: List[Dict[str, Union[int, float]]] = [
        {"maturity": "1y", "bps": 5},
        {"maturity": "2y", "bps": -3},
        {"maturity": "5y", "bps": 10},
        {"maturity": "10y", "bps": -8},
        {"maturity": "15y", "bps": 4},
        {"maturity": "20y", "bps": -6},
        {"maturity": "30y", "bps": 2},
    ]

    # portfolios created
    #this is to test background task
    _n_tasks: int = 0
    counter: int = 0
    max_counter: int = 60
    running: bool = False
    # Audio playback state
    current_audio_b64_src: str = "" # This is not actively used now but kept for potential future use
    is_audio_playing: bool = False
    audio_interaction_occurred: bool = False  # Tracks if user has interacted to allow audio
    _rabbitmq_consumer_started: bool = False
    need_plot_refresh: bool = False
    job_ready_chats: list[str] = []
    _chat_refresh_counter: int = 0  # Increment this to force UI refresh of chat content
    #this s not needed
    question: str = ""
    #endpoint as @finbuddy.ETF
    endpoint: str = ""
    #this are ids of jobs open
    job_ids = []
    job_ids_chats = []
    # Current chart session ID - set when a chart agent job starts
    # The chart component connects to relay using this ID
    chart_session_id: str = ""
    #this is for blink of chat notification
    chat_color = 6
    color_badge = "indigo"

    value: int = 0
    job_update_progress: int = 0
    #active tab
    active_tab="Buddy"
    tabs_list: list[str] = []
    # live portfolios
    instruments: list[liveinstruments] = []
    portfolios: list[str] = []
    all_portfolios: list[str] = []
    groupby_sector: list[dict] = []
    live_sort_value = ""
    live_search_value = ""
    #current user
    user: Optional[User] = None

    portfolios = list_saved_portfolios(user.username if user is not None else "")
    all_portfolios = list_all_portfolios(user.username if user is not None else "")

    plots : list[pd.DataFrame] = [] #load_files_from_directory(user.username if user is not None else "")
    plots_names: list[str] = []
    plots_fig: List[Tuple[Figure_plotly, Dict[str, str]]] = []
    plot1: Figure_plotly = px.data.gapminder().query("country=='Canada'")

    def logout(self):
        """Log out a user."""
        self.reset()
        return rx.redirect("/")

    def check_login(self):
        """Check if a user is logged in."""
        if not self.logged_in:
            return rx.redirect("/login")
        else:
            # Only run the RabbitMQ notification consumer in async mode; the
            # default sync mode needs no broker.
            if os.getenv("USE_ASYNC_JOBS", "false").lower() == "true":
                asyncio.create_task(self.ensure_rabbitmq_consumer())
            # Load running containers on page load
            self.load_running_containers()

    @rx.var
    def logged_in(self)-> bool:
        """Check if a user is logged in."""
        return self.user is not None

    @rx.var
    def is_chat_page(self) -> bool:
        """Check if we're on the main chat page (index).

        Returns True only for the index page where chat controls should be shown.
        Returns False for agent builder, data onboarding, page builder, etc.
        """
        return self.router.page.path == "/"
    #current_item: liveinstruments = liveinstruments()

    async def create_chat(self):
        """Create a new chat."""
        # Add the new chat to the list of chats.
        self.current_chat = self.new_chat_name
        self.chats_list[self.new_chat_name] = []
        self.chats_data_plots[self.new_chat_name] = []
        self.chats_name_plots[self.new_chat_name] = []
        self.chats_name_tables[self.new_chat_name] = []
        self.chats_name_portfolios[self.new_chat_name] = []
        self.chats_data_tables[self.new_chat_name] = []
        self.combined_content[self.new_chat_name] = []
        self.combined_name[self.new_chat_name] = []
        #add to tabs list
        self.tabs_list.append(self.new_chat_name)
        self.active_tab=self.new_chat_name
        with rx.session() as session:
            session.add(Chats(chat_title=self.new_chat_name, user_id=self.user.id)
            )
            session.commit()

    def delete_chat(self):
        """Delete the current chat."""
        del self.chats_list[self.current_chat]
        if len(self.chats_list) == 0:
            self.chats_list = DEFAULT_CHATS
        self.current_chat = list(self.chats_list.keys())[0]

    async def close_tab(self, chat_name: str):
        """Close the current chat.

        Args:
            chat_name: The name of the chat.
        """
        if chat_name in self.tabs_list and len(self.tabs_list) > 1:
            self.tabs_list.remove(chat_name)

            # Clear chat settings when closing tab
            if chat_name in self.chat_settings:
                del self.chat_settings[chat_name]
                print(f"[CHAT-SETTINGS] Cleared settings for closed chat: {chat_name}")

            if chat_name == self.active_tab:
                if len(self.tabs_list) > 0:
                    self.active_tab = self.tabs_list[0]
                    await self.set_chat_and_refresh(self.active_tab)

    async def set_chat(self, chat_name: str):
        """Set the name of the current chat.

        Args:
            chat_name: The name of the chat.
        """
        if chat_name not in self.tabs_list:
            self.tabs_list.append(chat_name)
        self.active_tab=chat_name

        self.current_chat = chat_name
        # Reset shared chat tracking - will be set by set_shared_chat for shared chats
        self.current_chat_id = None
        self.is_current_chat_shared = False

    def set_shared_chat(self, chat_name: str, chat_id: int, owner_username: str):
        """Set the current chat to a shared chat (not owned by current user).

        Args:
            chat_name: The name/title of the shared chat
            chat_id: The database ID of the chat
            owner_username: Username of the chat owner
        """
        if chat_name not in self.tabs_list:
            self.tabs_list.append(chat_name)
        self.active_tab = chat_name
        self.current_chat = chat_name
        self.current_chat_id = chat_id
        self.is_current_chat_shared = True
        self.shared_chat_owner = owner_username  # Store owner for loading files from their directory
        print(f"[SHARED CHAT] Set shared chat: {chat_name} (id={chat_id}, owner={owner_username})")

    @rx.event
    async def set_chat_and_refresh(self, chat_name: str):
        # SAVE current chat settings before switching
        if self.current_chat and self.current_chat != chat_name:
            self.chat_settings[self.current_chat] = {
                'selected_container_id': self.selected_container_id,
                'selected_container_name': self.selected_container_name,
                'current_session_id': self.current_session_id,
                'show_page_view': self.show_page_view,
                'message_routing': self.message_routing,
                'active_page_json': self.active_page_json,  # Save GUI layout
            }
            print(f"[CHAT-SETTINGS] Saved settings for chat: {self.current_chat}")

        # Switch to new chat
        await self.set_chat(chat_name)
        await self.set_plots_frontend(chat_name)

        # RESTORE settings for new chat
        if chat_name in self.chat_settings:
            settings = self.chat_settings[chat_name]
            self.selected_container_id = settings['selected_container_id']
            self.selected_container_name = settings['selected_container_name']
            self.current_session_id = settings['current_session_id']
            self.show_page_view = settings['show_page_view']
            self.message_routing = settings['message_routing']
            self.active_page_json = settings.get('active_page_json', '{"modules": []}')  # Restore GUI layout
            print(f"[CHAT-SETTINGS] Restored settings for chat: {chat_name}")
        else:
            # New chat - set defaults
            self.selected_container_id = ""
            self.selected_container_name = ""
            self.current_session_id = ""
            self.show_page_view = False
            self.message_routing = "finbuddy"
            self.active_page_json = '{"modules": []}'  # Clear GUI layout
            print(f"[CHAT-SETTINGS] Initialized default settings for chat: {chat_name}")

        # Remove from job_ready_chats if present
        if chat_name in self.job_ready_chats:
            self.job_ready_chats.remove(chat_name)

        return rx.redirect("/")

    @rx.event
    async def select_shared_chat(self, shared_chat: Dict[str, Any]):
        """Select a shared chat from the 'Shared with you' directory.

        Args:
            shared_chat: Dict with chat_id, title, owner, permission
        """
        chat_id = shared_chat.get("chat_id")
        chat_title = shared_chat.get("title", "Shared Chat")
        owner = shared_chat.get("owner", "unknown")

        # Load the shared chat's messages into chats_list if not already loaded
        if chat_title not in self.chats_list:
            # Load QAs from the shared chat
            with rx.session() as session:
                chat = session.exec(
                    select(Chats).where(Chats.id == chat_id)
                ).first()
                if chat:
                    qa_list = []
                    for qa in chat.qas:
                        qa_list.append(QA(question=qa.question, answer=qa.answer, created_at=qa.created_at))
                    self.chats_list[chat_title] = qa_list
                    self.chats_name_plots[chat_title] = []
                    self.chats_name_tables[chat_title] = []
                    self.chats_name_portfolios[chat_title] = []
                    self.chats_data_plots[chat_title] = []
                    self.chats_data_tables[chat_title] = []
                    self.combined_name[chat_title] = [("message", q, q.created_at) for q in qa_list]
                    self.combined_content[chat_title] = [("message", q, q.created_at) for q in qa_list]

        # Set as current shared chat
        self.set_shared_chat(chat_title, chat_id, owner)
        await self.set_plots_frontend(chat_title)
        return rx.redirect("/")

    def share_chat(self, chat_id: int, target_user_id: str, permission_level: str = 'read'):
        """Share a chat with another user by creating resource and permission in PostgreSQL.

        Args:
            chat_id: The ID of the chat to share
            target_user_id: Username of the user to share with
            permission_level: 'read', 'write', or 'admin'

        Returns:
            bool: True if sharing succeeded, False otherwise
        """
        import uuid
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    resource_id = f"chat_{chat_id}"

                    # First, ensure the resource exists in the resources table
                    cur.execute("""
                        INSERT INTO resources (resource_id, resource_type, owner_id, visibility)
                        VALUES (%s, 'chat', %s, 'private')
                        ON CONFLICT (resource_id) DO NOTHING
                    """, [resource_id, self.user.username])

                    # Grant permission to target user
                    permission_id = str(uuid.uuid4())
                    cur.execute("""
                        INSERT INTO resource_permissions
                            (permission_id, resource_id, entity_type, entity_id, permission_level, granted_by)
                        VALUES (%s, %s, 'user', %s, %s, %s)
                        ON CONFLICT (resource_id, entity_type, entity_id)
                        DO UPDATE SET permission_level = EXCLUDED.permission_level,
                                      granted_by = EXCLUDED.granted_by,
                                      granted_at = CURRENT_TIMESTAMP
                    """, [permission_id, resource_id, target_user_id, permission_level, self.user.username])

                    print(f"[SHARE CHAT] Shared chat {chat_id} with {target_user_id} ({permission_level})")
                    return True
        except Exception as e:
            print(f"[SHARE CHAT] Failed to share chat {chat_id}: {e}")
            return False

    def unshare_chat(self, chat_id: int, target_user_id: str):
        """Remove sharing permission for a chat.

        Args:
            chat_id: The ID of the chat
            target_user_id: Username of the user to remove access from

        Returns:
            bool: True if unsharing succeeded, False otherwise
        """
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    resource_id = f"chat_{chat_id}"
                    cur.execute("""
                        DELETE FROM resource_permissions
                        WHERE resource_id = %s
                          AND entity_type = 'user'
                          AND entity_id = %s
                    """, [resource_id, target_user_id])
                    print(f"[UNSHARE CHAT] Removed {target_user_id}'s access to chat {chat_id}")
                    return True
        except Exception as e:
            print(f"[UNSHARE CHAT] Failed to unshare chat {chat_id}: {e}")
            return False

    def set_share_chat_name(self, chat_name: str):
        """Set the chat name that is being shared (for context menu)."""
        self.share_chat_name = chat_name
        self.share_username_input = ""
        self.share_permission = "read"

    def set_share_username_input(self, username: str):
        """Set the username input for sharing."""
        self.share_username_input = username

    def set_share_permission(self, permission: str):
        """Set the permission level for sharing."""
        if permission in ["read", "write", "admin"]:
            self.share_permission = permission

    def check_user_exists(self, username: str) -> bool:
        """Check if a username exists in the PostgreSQL RBAC database.

        Args:
            username: The username to check

        Returns:
            bool: True if user exists, False otherwise
        """
        try:
            with get_connection(read_only=True) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM users WHERE user_id = %s", [username])
                    return cur.fetchone() is not None
        except Exception as e:
            print(f"[CHECK USER EXISTS] Error: {e}")
            return False

    def get_user_groups_list(self):
        """Load the groups that the current user belongs to."""
        if not self.user:
            self.user_groups = []
            return

        try:
            with get_connection(read_only=True) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT g.group_id, g.group_name
                        FROM groups g
                        JOIN user_groups ug ON g.group_id = ug.group_id
                        WHERE ug.user_id = %s
                    """, [self.user.username])
                    rows = cur.fetchall()
                    self.user_groups = [
                        {"group_id": row[0], "group_name": row[1]}
                        for row in rows
                    ]
                    print(f"[GET USER GROUPS] Found {len(self.user_groups)} groups for {self.user.username}")
        except Exception as e:
            print(f"[GET USER GROUPS] Error: {e}")
            self.user_groups = []

    @rx.event
    def share_chat_with_username(self):
        """Share the current chat with the username in share_username_input."""
        if not self.share_username_input:
            return rx.window_alert("Please enter a username")

        if not self.share_chat_name:
            return rx.window_alert("No chat selected for sharing")

        # Check if user exists
        if not self.check_user_exists(self.share_username_input):
            return rx.window_alert(f"User '{self.share_username_input}' does not exist")

        # Get chat_id from chat name
        with rx.session() as session:
            chat = session.exec(
                select(Chats).where(
                    Chats.chat_title == self.share_chat_name,
                    Chats.user_id == self.user.id
                )
            ).first()
            if not chat:
                return rx.window_alert("Chat not found")

            chat_id = chat.id

        # Share the chat
        if self.share_chat(chat_id, self.share_username_input, self.share_permission):
            username_shared = self.share_username_input
            self.share_username_input = ""
            return rx.window_alert(f"Shared '{self.share_chat_name}' with {username_shared} ({self.share_permission})")
        else:
            return rx.window_alert("Failed to share chat")

    @rx.event
    def share_chat_with_username_direct(self, chat_name: str):
        """Share a chat with the username in share_username_input (direct method with chat name).

        Args:
            chat_name: The name of the chat to share
        """
        if not self.share_username_input:
            return rx.window_alert("Please enter a username")

        # Check if user exists
        if not self.check_user_exists(self.share_username_input):
            return rx.window_alert(f"User '{self.share_username_input}' does not exist")

        # Get chat_id from chat name
        with rx.session() as session:
            chat = session.exec(
                select(Chats).where(
                    Chats.chat_title == chat_name,
                    Chats.user_id == self.user.id
                )
            ).first()
            if not chat:
                return rx.window_alert("Chat not found")

            chat_id = chat.id

        # Share the chat
        username_shared = self.share_username_input
        if self.share_chat(chat_id, username_shared, self.share_permission):
            self.share_username_input = ""
            return rx.window_alert(f"Shared '{chat_name}' with {username_shared} ({self.share_permission})")
        else:
            return rx.window_alert("Failed to share chat")

    def share_chat_with_group(self, group_id: str, group_name: str):
        """Share the current chat with a group.

        Args:
            group_id: The group ID to share with
            group_name: The group name (for display)
        """
        if not self.share_chat_name:
            return rx.window_alert("No chat selected for sharing")

        # Get chat_id from chat name
        with rx.session() as session:
            chat = session.exec(
                select(Chats).where(
                    Chats.chat_title == self.share_chat_name,
                    Chats.user_id == self.user.id
                )
            ).first()
            if not chat:
                return rx.window_alert("Chat not found")

            chat_id = chat.id

        # Share with group using entity_type='group'
        import uuid
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    resource_id = f"chat_{chat_id}"

                    # Ensure resource exists
                    cur.execute("""
                        INSERT INTO resources (resource_id, resource_type, owner_id, visibility)
                        VALUES (%s, 'chat', %s, 'private')
                        ON CONFLICT (resource_id) DO NOTHING
                    """, [resource_id, self.user.username])

                    # Grant permission to group
                    permission_id = str(uuid.uuid4())
                    cur.execute("""
                        INSERT INTO resource_permissions
                            (permission_id, resource_id, entity_type, entity_id, permission_level, granted_by)
                        VALUES (%s, %s, 'group', %s, %s, %s)
                        ON CONFLICT (resource_id, entity_type, entity_id)
                        DO UPDATE SET permission_level = EXCLUDED.permission_level,
                                      granted_by = EXCLUDED.granted_by,
                                      granted_at = CURRENT_TIMESTAMP
                    """, [permission_id, resource_id, group_id, self.share_permission, self.user.username])

                    print(f"[SHARE CHAT WITH GROUP] Shared chat {chat_id} with group {group_name} ({self.share_permission})")
                    return rx.window_alert(f"Shared '{self.share_chat_name}' with group '{group_name}'")
        except Exception as e:
            print(f"[SHARE CHAT WITH GROUP] Error: {e}")
            return rx.window_alert("Failed to share chat with group")

    def share_chat_with_group_direct(self, chat_name: str, group_id: str, group_name: str):
        """Share a chat with a group (direct method with chat name).

        Args:
            chat_name: The name of the chat to share
            group_id: The group ID to share with
            group_name: The group name (for display)
        """
        # Get chat_id from chat name
        with rx.session() as session:
            chat = session.exec(
                select(Chats).where(
                    Chats.chat_title == chat_name,
                    Chats.user_id == self.user.id
                )
            ).first()
            if not chat:
                return rx.window_alert("Chat not found")

            chat_id = chat.id

        # Share with group using entity_type='group'
        import uuid
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    resource_id = f"chat_{chat_id}"

                    # Ensure resource exists
                    cur.execute("""
                        INSERT INTO resources (resource_id, resource_type, owner_id, visibility)
                        VALUES (%s, 'chat', %s, 'private')
                        ON CONFLICT (resource_id) DO NOTHING
                    """, [resource_id, self.user.username])

                    # Grant permission to group
                    permission_id = str(uuid.uuid4())
                    cur.execute("""
                        INSERT INTO resource_permissions
                            (permission_id, resource_id, entity_type, entity_id, permission_level, granted_by)
                        VALUES (%s, %s, 'group', %s, %s, %s)
                        ON CONFLICT (resource_id, entity_type, entity_id)
                        DO UPDATE SET permission_level = EXCLUDED.permission_level,
                                      granted_by = EXCLUDED.granted_by,
                                      granted_at = CURRENT_TIMESTAMP
                    """, [permission_id, resource_id, group_id, self.share_permission, self.user.username])

                    print(f"[SHARE CHAT WITH GROUP] Shared chat {chat_id} with group {group_name} ({self.share_permission})")
                    return rx.window_alert(f"Shared '{chat_name}' with group '{group_name}'")
        except Exception as e:
            print(f"[SHARE CHAT WITH GROUP] Error: {e}")
            return rx.window_alert("Failed to share chat with group")

    def share_chat_public(self):
        """Make the current chat public (visible to all users)."""
        if not self.share_chat_name:
            return rx.window_alert("No chat selected for sharing")

        # Get chat_id from chat name
        with rx.session() as session:
            chat = session.exec(
                select(Chats).where(
                    Chats.chat_title == self.share_chat_name,
                    Chats.user_id == self.user.id
                )
            ).first()
            if not chat:
                return rx.window_alert("Chat not found")

            chat_id = chat.id

        # Set visibility to public
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    resource_id = f"chat_{chat_id}"

                    # Insert or update resource with public visibility
                    cur.execute("""
                        INSERT INTO resources (resource_id, resource_type, owner_id, visibility)
                        VALUES (%s, 'chat', %s, 'public')
                        ON CONFLICT (resource_id)
                        DO UPDATE SET visibility = 'public', updated_at = CURRENT_TIMESTAMP
                    """, [resource_id, self.user.username])

                    print(f"[SHARE CHAT PUBLIC] Made chat {chat_id} public")
                    return rx.window_alert(f"'{self.share_chat_name}' is now public")
        except Exception as e:
            print(f"[SHARE CHAT PUBLIC] Error: {e}")
            return rx.window_alert("Failed to make chat public")

    def share_chat_public_direct(self, chat_name: str):
        """Make a chat public (direct method with chat name).

        Args:
            chat_name: The name of the chat to make public
        """
        # Get chat_id from chat name
        with rx.session() as session:
            chat = session.exec(
                select(Chats).where(
                    Chats.chat_title == chat_name,
                    Chats.user_id == self.user.id
                )
            ).first()
            if not chat:
                return rx.window_alert("Chat not found")

            chat_id = chat.id

        # Set visibility to public
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    resource_id = f"chat_{chat_id}"

                    # Insert or update resource with public visibility
                    cur.execute("""
                        INSERT INTO resources (resource_id, resource_type, owner_id, visibility)
                        VALUES (%s, 'chat', %s, 'public')
                        ON CONFLICT (resource_id)
                        DO UPDATE SET visibility = 'public', updated_at = CURRENT_TIMESTAMP
                    """, [resource_id, self.user.username])

                    print(f"[SHARE CHAT PUBLIC] Made chat {chat_id} public")
                    return rx.window_alert(f"'{chat_name}' is now public")
        except Exception as e:
            print(f"[SHARE CHAT PUBLIC] Error: {e}")
            return rx.window_alert("Failed to make chat public")

    # ==================== CONTAINER SHARING ====================

    @rx.event
    def open_share_container_dialog(self, container_id: str, container_name: str):
        """Open the share container dialog.

        Args:
            container_id: The container/agent instance ID
            container_name: The container name for display
        """
        self.share_dialog_container_id = container_id
        self.share_dialog_container_name = container_name
        self.share_username_input = ""
        self.share_permission = "read"
        self.share_container_dialog_open = True

    @rx.event
    def share_container_from_dialog(self):
        """Share the container from the dialog using share_dialog_container_id."""
        if not self.share_dialog_container_id:
            return rx.window_alert("No container selected")

        if not self.share_username_input:
            return rx.window_alert("Please enter a username")

        # Check if user exists
        if not self.check_user_exists(self.share_username_input):
            return rx.window_alert(f"User '{self.share_username_input}' does not exist")

        username_to_share = self.share_username_input
        container_id = self.share_dialog_container_id

        try:
            import uuid as uuid_module
            with get_connection() as conn:
                with conn.cursor() as cur:
                    resource_id = container_id

                    # First ensure the resource exists in resources table
                    cur.execute("""
                        INSERT INTO resources (resource_id, resource_type, owner_id, visibility)
                        VALUES (%s, 'agent_instance', %s, 'private')
                        ON CONFLICT (resource_id) DO NOTHING
                    """, [resource_id, self.user.username])

                    # Grant permission to target user
                    permission_id = str(uuid_module.uuid4())
                    cur.execute("""
                        INSERT INTO resource_permissions (permission_id, resource_id, entity_type, entity_id, permission_level, granted_by)
                        VALUES (%s, %s, 'user', %s, %s, %s)
                        ON CONFLICT (resource_id, entity_type, entity_id)
                        DO UPDATE SET permission_level = EXCLUDED.permission_level, granted_at = CURRENT_TIMESTAMP
                    """, [permission_id, resource_id, username_to_share, self.share_permission, self.user.username])

                    print(f"[SHARE CONTAINER] Shared container {container_id} with {username_to_share} ({self.share_permission})")
                    self.share_username_input = ""
                    self.share_container_dialog_open = False
                    return rx.window_alert(f"Shared container with {username_to_share} ({self.share_permission})")
        except Exception as e:
            print(f"[SHARE CONTAINER] Error: {e}")
            return rx.window_alert("Failed to share container")

    @rx.event
    def share_container_public_from_dialog(self):
        """Make the container public from the dialog."""
        if not self.share_dialog_container_id:
            return rx.window_alert("No container selected")

        container_id = self.share_dialog_container_id

        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    resource_id = container_id

                    # Insert or update resource with public visibility
                    cur.execute("""
                        INSERT INTO resources (resource_id, resource_type, owner_id, visibility)
                        VALUES (%s, 'agent_instance', %s, 'public')
                        ON CONFLICT (resource_id)
                        DO UPDATE SET visibility = 'public', updated_at = CURRENT_TIMESTAMP
                    """, [resource_id, self.user.username])

                    print(f"[SHARE CONTAINER] Made container {container_id} public")
                    self.share_container_dialog_open = False
                    return rx.window_alert("Container is now public")
        except Exception as e:
            print(f"[SHARE CONTAINER] Error: {e}")
            return rx.window_alert("Failed to make container public")

    @rx.event
    def share_container_with_username_direct(self, container_id: str):
        """Share a container with the username in share_username_input.

        Args:
            container_id: The container/agent instance ID to share
        """
        if not self.share_username_input:
            return rx.window_alert("Please enter a username")

        # Check if user exists
        if not self.check_user_exists(self.share_username_input):
            return rx.window_alert(f"User '{self.share_username_input}' does not exist")

        username_to_share = self.share_username_input

        try:
            import uuid as uuid_module
            with get_connection() as conn:
                with conn.cursor() as cur:
                    # The container_id is the instance_id which is the resource_id
                    resource_id = container_id

                    # First ensure the resource exists in resources table
                    cur.execute("""
                        INSERT INTO resources (resource_id, resource_type, owner_id, visibility)
                        VALUES (%s, 'agent_instance', %s, 'private')
                        ON CONFLICT (resource_id) DO NOTHING
                    """, [resource_id, self.user.username])

                    # Grant permission to target user
                    permission_id = str(uuid_module.uuid4())
                    cur.execute("""
                        INSERT INTO resource_permissions (permission_id, resource_id, entity_type, entity_id, permission_level, granted_by)
                        VALUES (%s, %s, 'user', %s, %s, %s)
                        ON CONFLICT (resource_id, entity_type, entity_id)
                        DO UPDATE SET permission_level = EXCLUDED.permission_level, granted_at = CURRENT_TIMESTAMP
                    """, [permission_id, resource_id, username_to_share, self.share_permission, self.user.username])

                    print(f"[SHARE CONTAINER] Shared container {container_id} with {username_to_share} ({self.share_permission})")
                    self.share_username_input = ""
                    return rx.window_alert(f"Shared container with {username_to_share} ({self.share_permission})")
        except Exception as e:
            print(f"[SHARE CONTAINER] Error: {e}")
            return rx.window_alert("Failed to share container")

    @rx.event
    def share_container_with_group_direct(self, container_id: str, group_id: str, group_name: str):
        """Share a container with a group.

        Args:
            container_id: The container/agent instance ID to share
            group_id: The group ID to share with
            group_name: The group name (for display)
        """
        try:
            import uuid as uuid_module
            with get_connection() as conn:
                with conn.cursor() as cur:
                    resource_id = container_id

                    # First ensure the resource exists
                    cur.execute("""
                        INSERT INTO resources (resource_id, resource_type, owner_id, visibility)
                        VALUES (%s, 'agent_instance', %s, 'private')
                        ON CONFLICT (resource_id) DO NOTHING
                    """, [resource_id, self.user.username])

                    # Grant permission to group
                    permission_id = str(uuid_module.uuid4())
                    cur.execute("""
                        INSERT INTO resource_permissions (permission_id, resource_id, entity_type, entity_id, permission_level, granted_by)
                        VALUES (%s, %s, 'group', %s, %s, %s)
                        ON CONFLICT (resource_id, entity_type, entity_id)
                        DO UPDATE SET permission_level = EXCLUDED.permission_level, granted_at = CURRENT_TIMESTAMP
                    """, [permission_id, resource_id, group_id, self.share_permission, self.user.username])

                    print(f"[SHARE CONTAINER] Shared container {container_id} with group {group_name} ({self.share_permission})")
                    return rx.window_alert(f"Shared container with group '{group_name}' ({self.share_permission})")
        except Exception as e:
            print(f"[SHARE CONTAINER] Error: {e}")
            return rx.window_alert("Failed to share container with group")

    @rx.event
    def share_container_public_direct(self, container_id: str):
        """Make a container public.

        Args:
            container_id: The container/agent instance ID to make public
        """
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    resource_id = container_id

                    # Insert or update resource with public visibility
                    cur.execute("""
                        INSERT INTO resources (resource_id, resource_type, owner_id, visibility)
                        VALUES (%s, 'agent_instance', %s, 'public')
                        ON CONFLICT (resource_id)
                        DO UPDATE SET visibility = 'public', updated_at = CURRENT_TIMESTAMP
                    """, [resource_id, self.user.username])

                    print(f"[SHARE CONTAINER] Made container {container_id} public")
                    return rx.window_alert("Container is now public")
        except Exception as e:
            print(f"[SHARE CONTAINER] Error: {e}")
            return rx.window_alert("Failed to make container public")

    def get_shared_chats(self) -> list:
        """Get list of chats shared with the current user.

        Returns:
            List of dicts with chat info: [{"chat_id": int, "title": str, "owner": str, "permission": str}]
        """
        shared_chats = []
        if not self.user:
            print("[GET SHARED CHATS] No user logged in")
            return shared_chats

        print(f"[GET SHARED CHATS] Fetching shared chats for user: {self.user.username}")
        try:
            with get_connection(read_only=True) as conn:
                with conn.cursor() as cur:
                    # Find all chat resources where current user has permission but is not owner
                    cur.execute("""
                        SELECT r.resource_id, rp.permission_level, r.owner_id
                        FROM resources r
                        JOIN resource_permissions rp ON r.resource_id = rp.resource_id
                        WHERE r.resource_type = 'chat'
                          AND rp.entity_type = 'user'
                          AND rp.entity_id = %s
                          AND r.owner_id != %s
                          AND (rp.expires_at IS NULL OR rp.expires_at > NOW())
                    """, [self.user.username, self.user.username])

                    rows = cur.fetchall()
                    print(f"[GET SHARED CHATS] Found {len(rows)} shared chat permissions")

                    for row in rows:
                        resource_id = row[0]  # format: "chat_123"
                        permission = row[1]
                        owner = row[2]
                        chat_id = int(resource_id.replace("chat_", ""))
                        print(f"[GET SHARED CHATS] Processing chat_id={chat_id}, owner={owner}, permission={permission}")

                        # Get chat title from Reflex DB
                        with rx.session() as session:
                            chat = session.exec(
                                select(Chats).where(Chats.id == chat_id)
                            ).first()
                            if chat:
                                shared_chats.append({
                                    "chat_id": chat_id,
                                    "title": chat.chat_title,
                                    "owner": owner,
                                    "permission": permission
                                })
                                print(f"[GET SHARED CHATS] Added shared chat: {chat.chat_title}")
                            else:
                                print(f"[GET SHARED CHATS] Chat {chat_id} not found in Reflex DB")
        except Exception as e:
            print(f"[GET SHARED CHATS] Error: {e}")
            import traceback
            traceback.print_exc()

        return shared_chats

    async def set_portfolios(self):
        """Set the name of the current chat.

        Args:
            chat_name: The name of the chat.
        """
        self.portfolios = list_saved_portfolios(self.user.username if self.user is not None else "")

    @rx.event
    async def handle_redirect_markets(self):
        # Your logic here
        await self.set_all_marketsportfolio()
        return rx.redirect("/markets")

    async def set_allportfolios(self):
        """Set the name of the current chat.

        Args:
            chat_name: The name of the chat.
        """
        self.all_portfolios = list_all_portfolios(self.user.username if self.user is not None else "")

    async def set_plot(self):
        """Set the name of the current chat.

        Args:
            chat_name: The name of the chat.
        """
        self.plots, self.plots_names = load_files_from_directory(self.user.username)
        self.plots_fig = []
        for df, plt_name in zip(self.plots, self.plots_names):
            fig =  px.line(
                df,
                x="Date",
                y="Cumulative Performance (%)",
                title="Portfolio returns"
            )
            fig.update_layout(
                title={
                    'text': f"Portfolio returns: {plt_name}",
                    'font': {
                        'color': 'blue'
                    }
                },
                paper_bgcolor = 'white',  # Set the background color of the paper (outside the plot area)
                plot_bgcolor = 'white'  # Set the background color of the plot area
            )
            layout_dict = fig.to_plotly_json()['layout']
            self.plots_fig.append((fig, layout_dict))
        #load tables


    async def set_plots_frontend(self, current_chat=None):
        """This is main function to load plots from the directory and set them in the frontend."""
        if not current_chat:
            current_chat = self.current_chat
        if self.chats_name_plots[current_chat]:
            plots_names = []
            columns = []
            xaxises = []
            colors = []
            titles = []
            nicknames = []
            for data_plot in self.chats_name_plots[current_chat]:
                plots_names.append(Path(data_plot.plot_name).name)
                columns.append(data_plot.column)
                xaxises.append(data_plot.xaxis)
                colors.append(data_plot.color)
                titles.append(data_plot.title)
                nicknames.append(data_plot.nickname)
            data_plots = load_datas_from_directory(user_dir=self.user.username, file_names=plots_names)
            print("loaded data_lots from file n.:   ", len(data_plots))
        else:
            plots_names, columns, xaxises, colors, titles, nicknames = [], [], [], [], [], []
            data_plots = []
        plots_fig = []
        js_plots_data = []
        print("len of data_plots:", len(data_plots))
        print("len of plots_names:", len(plots_names))
        print("len of columns:", len(columns))
        print("len of colors:", len(colors))
        print("len of xaxises:", len(xaxises))
        print("len of titles:", len(titles))
        print("len of nicknames:", len(nicknames))
        for idx, (plt_name, col, color, xaxis, title, nickname) in enumerate(zip(
                                                             plots_names,
                                                             columns,
                                                             colors,
                                                             xaxises,
                                                             titles,
                                                             nicknames
                                                             )):
            #do some checking to make sure you can plot it or will ruin all the the list
            df = data_plots.get(plt_name)
            
            if df is None:
                print("df is None")
                continue
            if not isinstance(df, pd.DataFrame):
                print("df is not a DataFrame")
                continue
            col_dict = {"cum_return":"Cumulative Performance (%)", "cum_pct_day_NAV":"NAV Cumulative Performance (%)"}
            if any(val not in df for val in [col, xaxis]):#color can be null for plots out of analysis
                print("df has not right columns ", df.columns)
                print("columns needed:", [col, xaxis])
                continue
            display_col = col_dict.get(col, col)
            print("plot_name:",plt_name)
            # Remove '.csv' from plt_name if present
            if isinstance(plt_name, str) and plt_name.endswith('.csv'):
                plt_name = plt_name[:-4]
            # Transform nickname if it starts with 'returns_'
            if isinstance(plt_name, str) and plt_name.startswith('returns_'):
                plt_name = 'portfolio_' + plt_name[len('returns_'):]
                # --- Prepare data for Lightweight Charts JS ---
                # This block converts the dataframe into a JSON-friendly structure that
                # a Lightweight-Charts front-end can consume.  We keep it lightweight by
                # only extracting the required x/y columns (plus an optional colour/group
                # column) and converting dates to ISO-YYYY-MM-DD strings.
                # if not hasattr(self, 'chats_data_lightweight'):
                #     # Mirror the structure used for other chat-scoped data containers.
                #     self.chats_data_lightweight = DEFAULT_CHATS
                # plot_js_data = self.chats_data_lightweight.get(current_chat, [])

            try:
                base_cols = [xaxis, col]
                if color:
                    base_cols.append(color)
                df_js = df[base_cols].copy()
                # Ensure the x-axis is datetime so we can serialize properly.
                df_js[xaxis] = pd.to_datetime(df_js[xaxis], errors='coerce')
                df_js = df_js.dropna(subset=[xaxis, col])

                if color:
                    # Multiple line series, one per group in the colour column.
                    for grp_name, grp_df in df_js.groupby(color):
                        series_data = [
                            {"time": ts.strftime('%Y-%m-%d'), "value": float(val)}
                            for ts, val in zip(grp_df[xaxis], grp_df[col])
                        ]
            #             plot_js_data.append({
            #                 "plot_name": plt_name,
            #                 "title": title,
            #                 "xaxis": xaxis,
            #                 "yaxis": col,
            #                 "series_name": str(grp_name),
            #                 "series_data": series_data,
            #             })
                else:
                    # Single series chart.
                    series_data = [
                        {"time": ts.strftime('%Y-%m-%d'), "value": float(val)}
                        for ts, val in zip(df_js[xaxis], df_js[col])
                    ]
            #         plot_js_data.append({
            #             "plot_name": plt_name,
            #             "title": title,
            #             "xaxis": xaxis,
            #             "yaxis": col,
            #             "series_name": col,
            #             "series_data": series_data,
            #         })
            except Exception as e:
                # Non-fatal; continue generating Plotly figure.
                print("Error preparing lightweight chart data:", e)

            # Persist the prepared data for the current chat so the frontend can
            # fetch it (e.g. via an endpoint or state variable) and render the
            # Lightweight-Charts instance.
            #by now try onlt with data then we can add title and labels
            config = {
                "title": title,
                "xaxis": xaxis,
                "yaxis": display_col,
                "plot_name": plt_name,
            }
            js_plots_data.append((json.dumps(series_data), config))

            fig = px.line(
                df,
                x=xaxis,
                y=col,
                title=title,
                **({"color": color} if color else {})  # Include 'color' only if it's not empty
            )

            fig.update_layout(
                yaxis_title=display_col,
                legend_title_text='', #remove col name of color column, show only group names
                title={
                    'text': f"{plt_name}",#f"{title}: {nickname}",
                    'font': {
                        'color': 'blue'
                    }
                },
                paper_bgcolor='white',  # Set the background color of the paper (outside the plot area)
                plot_bgcolor='white',  # Set the background color of the plot area
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="center",
                    x=0.5
                )
            )
            layout_dict = fig.to_plotly_json()['layout']
            plots_fig.append((fig, layout_dict))
        print("final len of plots_fig:", len(plots_fig))
        print("final len of js_plots_data:", len(js_plots_data))
        self.chats_data_plots[current_chat] = plots_fig
        self.chats_data_lightweight[current_chat] = js_plots_data
        tables_data = []
        if self.chats_name_tables[current_chat]:
            tables_names = []
            for table in self.chats_name_tables[current_chat]:
                tables_names.append(table.table_name)
            data_tables = load_datas_from_directory(user_dir=self.user.username, file_names=tables_names)

            for table_name in tables_names:
                table = data_tables.get(table_name)
                if table is None:
                    continue
                if not isinstance(table, pd.DataFrame):
                    continue
                if "info" in table.columns:
                    table = table.drop(columns=["info"])
                tables_data.append((table,{}))
        self.chats_data_tables[current_chat] = tables_data

        #now all the tables and plots are update in ther list. now i need to populate the combined_content from the names in combined_name
        #for each entry in combined_name:
        #  if it is a message append same qa into combined_contect
        #  if it is a table search for table in chats_name_tables and append the corresponding table at same index in chats_data_tables
        #  if it is a plot search for plot in chats_name_plots and append the corresponding plot at same index in chats_data_plots
        # since they are in order keep an increasing index into  chats_name_tables and chats_name_plots to do the search
        # remmeber combined_content is a list of tuples (content_type, content, timestamp)

        plots = [("plot", plot, plot.created_at) for plot in self.chats_name_plots[current_chat]]
        tables = [("table", table, table.created_at) for table in self.chats_name_tables[current_chat]]
        messages = [("message", message, message.created_at) for message in self.chats_list[current_chat]]

        # Combine and sort by the third element of each tuple (created_at)
        self.combined_name[current_chat] = sorted(plots + tables + messages, key=lambda x: x[2])

        index_tables = 0
        index_plots = 0
        
        # Retrieve the lists for the current chat once at the start
        current_chats_name_tables = self.chats_name_tables.get(current_chat, [])
        current_chats_name_plots = self.chats_name_plots.get(current_chat, [])
        current_chats_data_tables = self.chats_data_tables.get(current_chat, [])
        #current_chats_data_plots = self.chats_data_plots.get(current_chat, [])
        current_chats_data_plots = self.chats_data_lightweight.get(current_chat, [])
        current_combined_content = []
        
        for content_type, content, timestamp in self.combined_name[current_chat]:
            content_to_add = None
            if content_type == "message":
                print("message....")
                content_to_add = content
            elif content_type == "table":
                print("table....")
                content_to_add, index_tables = self._find_and_update_content(
                    current_chats_name_tables, current_chats_data_tables, content, index_tables
                )
            elif content_type == "plot":
                print("plot....", str(timestamp))
                content_to_add, index_plots = self._find_and_update_content(
                    current_chats_name_plots, current_chats_data_plots, content, index_plots
                )
            if content_to_add is not None:
                current_combined_content.append((content_type, content_to_add, timestamp))
            else:
                print("content_to_add is None")
        self.combined_content[current_chat] = current_combined_content
        rx.set_value("question", "")
        print("set_plots_frontend done. for chat ", current_chat)

    def audio_playback_finished(self):
        """Called by JavaScript when audio playback has finished."""
        self.is_audio_playing = False
        print(f"State: audio_playback_finished called, is_audio_playing: {{self.is_audio_playing}}")

    def user_interacted_for_audio(self):
        """Called when the user clicks a button to enable audio playback."""
        self.audio_interaction_occurred = True
        print("State: User interaction for audio has occurred. Audio playback should now be allowed.")

    def handle_audio_toggle_click(self):
        """Handles the audio toggle button click. Sets interaction flag and toggles play enabled state."""
        if not self.audio_interaction_occurred:
            self.audio_interaction_occurred = True
            print("State: First user interaction for audio via toggle. Audio playback should now be allowed.")
            # On first interaction, also enable audio playback by default
            self.audio_play_enabled = True
        else:
            self.audio_play_enabled = not self.audio_play_enabled
            print(f"State: Audio play enabled toggled to: {self.audio_play_enabled}")

    autopilot_enabled: bool = False

    def handle_autopilot_toggle_click(self):
        """Handles the autopilot toggle button click."""
        self.autopilot_enabled = not self.autopilot_enabled
        print(f"Autopilot enabled toggled to: {self.autopilot_enabled}")

    @rx.event
    def set_autopilot(self, enabled: bool):
        """Sets the autopilot state."""
        self.autopilot_enabled = enabled
        print(f"Autopilot enabled set to: {self.autopilot_enabled}")

    def _find_and_update_content(self, names_list, data_list, content, index):
        """Helper function to find content and update index."""
        # Check if index is within bounds
        #min is to avoid errors indexing out of range
        if index >= min(len(names_list), len(data_list)):
            print("out of range, len names_list:", len(names_list), "len data_list:", len(data_list))
            print("index:", index)
            return None, index
        
        for i, name in enumerate(names_list[index:], start=index):
            print("eacrhing for content ", content, ", current name:", name)
            if name == content:
                return data_list[i], i + 1
        return None, index

    async def set_liveportfolio(self, portfolio_name: str):
        """set live portfolio to analise in page live trading"""
        self.live_portfolio, self.live_return = read_live_portfolio(portfolio_name, self.user.username if self.user is not None else "")
        self.live_code = portfolio_name#"_".join(portfolio_name.split("_")[:2])
        self.live_plot = []
        if self.live_return is None:
            return
        if len(self.live_return) > 0:
            data_plot = pd.read_json(StringIO(self.live_return))
            data_plot.columns = [c.lower() for c in data_plot.columns]
        #mow set performance plot
        if data_plot is None:
            return
        if not isinstance(data_plot, pd.DataFrame):
            return
        if any(val not in data_plot.columns for val in ["date", "cum_return"]):
            return
        fig = px.line(
            data_plot,
            x="date",
            y="cum_return",
            #color=color,
            title="portfolio return"
        )
        fig.update_layout(
            title={
                'text': f"portfolio: {self.live_code}",
                'font': {
                    'color': 'blue'
                }
            },
            paper_bgcolor='white',  # Set the background color of the paper (outside the plot area)
            plot_bgcolor='white'  # Set the background color of the plot area
        )
        layout_dict = fig.to_plotly_json()['layout']
        self.live_plot.append((fig, layout_dict))

    
    async def set_all_marketsportfolio(self):
        for i, section in enumerate(self.instrument_data):
            for j, portfolio_info in enumerate(section):
                if portfolio_info["file"]:
                    print("setting portfolio:", portfolio_info["file"])
                    portfolio_returns, max_y_chart, min_y_chart = await self.set_marketsportfolio(portfolio_info["file"])
                    self.instrument_return[i][j] = portfolio_returns
                    self.instrument_data[i][j]["chart_y_max"] = max_y_chart
                    self.instrument_data[i][j]["chart_y_min"] = min_y_chart
        
        self.instrument_merged: List[List[InstrumentMerged]] = [
        [
            {
                **item,
                "returns": returns,
                "day_is_negative": item["day"].startswith("-"),
                "month_is_negative": item["month"].startswith("-"),
            "six_months_is_negative": item["six_months"].startswith("-")
            }
            for item, returns in zip(section_items, section_returns)
        ]
        for section_items, section_returns in zip(self.instrument_data, self.instrument_return)
        ]
        self.instrument_data_all: List[InstrumentSection] = [
        {"section": section, "merged_date": merged_date}
        for section, merged_date in zip(self.instrument_sections, self.instrument_merged)
        ]
        print("setting portfolio done")
        return

            

    
    async def set_marketsportfolio(self, portfolio_name: str):
        """set live portfolio to analise in page live trading"""
        _, stats_return, stats_stats = read_portfolio(portfolio_name, self.user.username if self.user is not None else "")
        stats_code = portfolio_name#"_".join(portfolio_name.split("_")[:2])
        stats_plot = []
        if stats_return is None:
            return
        data_plot = None
        if len(stats_return) > 0:
            try:
                data_plot = pd.read_json(StringIO(stats_return))
                data_plot.columns = [c.lower() for c in data_plot.columns]
            except Exception as e:
                print("Error reading stats_return:", e)
            
        #mow set performance plot
        if data_plot is None:
            return
        if not isinstance(data_plot, pd.DataFrame):
            return
        if any(val not in data_plot.columns for val in ["date", "cum_return"]):
            return
        portfolio_performance = []
        # Sort by date, then format and take last 30
        data_plot["date_dt"] = pd.to_datetime(data_plot["date"])
        data_plot = data_plot.sort_values("date_dt")
        data_plot["date"] = data_plot["date_dt"].dt.strftime("%y/%m")
        last_n = data_plot.tail(90)
        for i in range(len(last_n)):
            portfolio_performance.append({"date": last_n.iloc[i]["date"], "value": last_n.iloc[i]["cum_return"]})
        
        max_y_chart = last_n["cum_return"].max()
        min_y_chart = last_n["cum_return"].min()
        return portfolio_performance, max_y_chart, min_y_chart

    async def set_holdings(self):
        if not self.is_hydrated:
            return

        if not self.current_portfolio_name:
            # If no portfolio is selected, try to load the default one.
            await self.load_default_stats_data()

        if self.current_portfolio_name:
            # In a real app, you'd fetch holdings from a DB based on portfolio name
            # For now, using dummy data.
            if self.current_portfolio_name == "My First Portfolio":
                self.current_portfolio_holdings = [
                    self.EqHoldings(ticker="AAPL", weight=0.3),
                    self.EqHoldings(ticker="GOOG", weight=0.2),
                    self.EqHoldings(ticker="MSFT", weight=0.5),
                ]
            else: # Dummy data for other portfolios
                self.current_portfolio_holdings = [
                    self.EqHoldings(ticker="TSLA", weight=0.4),
                    self.EqHoldings(ticker="AMZN", weight=0.6),
                ]
        else:
            # Fallback if no portfolio could be loaded
            self.current_portfolio_holdings = []

    @rx.event
    async def set_statsportfolio_FI(self, portfolio_name: str):
        """set live FI portfolio to analise in page live trading"""
        _, stats_return, stats_stats = read_portfolio(portfolio_name, self.user.username if self.user is not None else "", portfolio_type="fi")
        self.stats_code = portfolio_name
        self.stats_plot = []
        if stats_return is None:
            return

        data_plot = None
        if len(stats_return) > 0:
            try:
                data_plot = pd.read_json(StringIO(stats_return))
                data_plot.columns = [c.lower() for c in data_plot.columns]
            except Exception as e:
                print("Error reading stats_return:", e)
            
        #mow set performance plot
        if data_plot is None:
            return
        if not isinstance(data_plot, pd.DataFrame):
            return
        if any(val not in data_plot.columns for val in ["date", "cum_return"]):
            return
        #self.eq_performance = []
        #need to format into a list of date into YY/MM and value
        #need to parse date 2025-04-24 into dtae and then format into YY/MM
        data_plot["date"] = pd.to_datetime(data_plot["date"]).dt.strftime("%Y-%m-%d")
        #for i in range(len(data_plot)):
        #    self.eq_performance.append({"date": data_plot.iloc[i]["date"], "value": data_plot.iloc[i]["cum_return"]})


        # --- Prepare lightweight-chart data for the fi stats plot ---
        series_data_fi = []
        for d_str, val in zip(data_plot["date"], data_plot["cum_return"]):
            if pd.isna(val):
                continue
            # Convert date string to a datetime object and then format it to YYYY-MM-DD.
            try:
                ts_obj = pd.to_datetime(d_str, errors='coerce')
                if pd.isna(ts_obj):
                    continue
                ts = ts_obj.strftime('%Y-%m-%d')
            except Exception:
                continue  # Skip if date format is invalid

            series_data_fi.append({
                "time": ts,
                "value": float(val),
            })
        self.fi_performance_lightweight = {
            "plot_name": self.stats_code,
            "title": "Portfolio Performance",
            "xaxis": "date",
            "yaxis": "cum_return",
            "series_name": "cum_return",
            "series_data": series_data_fi,
        }
        # store pre-serialized json string for frontend
        # Hardcoded data for testing the lightweight chart

        #self.eq_performance_lightweight_json = json.dumps(sample_chart_data)
        # Original line, commented out for testing:
        
        self.fi_performance_lightweight_json = json.dumps(series_data_fi)
        print("-----------------------------series_data_fi:")
        for s in series_data_fi:
            print(s["time"], s["value"])
        # Transform stats_stats JSON into State variables for Fixed Income dashboard
        stats = {}
        if stats_stats:
            try:
                stats = json.loads(stats_stats)
                #now fi_returns
                fi_returns = stats["returns"]
                self.fi_returns = []
                fi_stats = stats["statistics"]
                self.FI_stats = []
                for k,v in fi_stats.items():
                    self.FI_stats.append({"metric_name": k, "metric_value": v}) 
                for k,v in fi_returns.items():
                    self.fi_returns.append({"metric_name": k, "metric_value": v})  
            except Exception as e:
                print("Error reading stats_stats:", e)
                stats = {}
        else:
            print("stats_stats is None or empty")

        # ---------------- Map summary metrics ---------------- #
        self.FI_stats_notional = f"{round(stats.get('notional', 0)/1_000_000,2)}M" if 'notional' in stats else "N/A"

        duration_value = stats.get('duration')
        self.FI_stats_duration = f"{duration_value:.2f}y" if duration_value is not None else "N/A"

        self.FI_stats_yield = f"{stats.get('yield')*100:.2f}%" if stats.get('yield') is not None else "N/A"

        #holdings
        FI_holdings = stats["holdings"]
        self.FI_holdings = []
        for k,v in FI_holdings.items():
            self.FI_holdings.append({"ticker": k, "weight": v})
        print("FI_holdings:", str(self.FI_holdings))
        # Average coupon across portfolio (if provided)
        self.FI_stats_coupon = f"{stats.get('avg_coupon', 0):.2f}%" if stats.get('avg_coupon') is not None else "N/A"

        # Risk metrics
        self.FI_stats_mod_duration = (
            f"{stats.get('portfolio_mod_duration', 0):.2f}y" if stats.get('portfolio_mod_duration') is not None else "N/A"
        )
        self.FI_stats_convexity = (
            f"{stats.get('portfolio_convexity', 0):.2f}" if stats.get('portfolio_convexity') is not None else "N/A"
        )
        self.FI_stats_dv01 = (
            f"{stats.get('portfolio_dv01', 0):.4f}" if stats.get('portfolio_dv01') is not None else "N/A"
        )

        # ---------------- Map tables for charts ---------------- #
        def _series_to_list(obj, key_label, value_label):
            """Convert various container types to list[dict] expected by charts."""
            if obj is None:
                return []
            # Already in correct format
            if isinstance(obj, list):
                return obj
            # pandas Series or dict-like
            if hasattr(obj, 'items'):
                iterator = obj.items()
            elif isinstance(obj, dict):
                iterator = obj.items()
            else:
                # Fallback: try iterable of tuples
                iterator = obj
            out = []
            for item in iterator:
                try:
                    k, v = item
                except (ValueError, TypeError):
                    # Skip malformed items
                    continue
                out.append({
                    key_label: str(k),
                    value_label: (round(float(v)*100,2) if isinstance(v, (int,float)) and value_label=='weight' else (round(float(v),2) if isinstance(v,(int,float)) else v))
                })
            return out

        # Duration & Yield buckets (weights in %)
        self.FI_stats_duration_buckets = _series_to_list(stats.get('duration_table'), 'bucket', 'weight')
        print("duration buckets", self.FI_stats_duration_buckets, "and it was in dict ", stats.get('duration_table'))
        self.FI_stats_yield_buckets    = _series_to_list(stats.get('yield_table'),    'bucket', 'weight')

        # Coupon buckets (notional) if available
        self.FI_stats_coupon_buckets = _series_to_list(stats.get('coupon_buckets'), 'bucket', 'notional')

        # Duration bucket average coupon/yield lists if provided in stats
        self.FI_stats_duration_avg_coupon = _series_to_list(stats.get('duration_avg_coupon'), 'bucket', 'avg_coupon')
        self.FI_stats_duration_avg_yield  = _series_to_list(stats.get('duration_avg_yield'),  'bucket', 'avg_yield')

        # Key rate DV01s mapping
        kr_dv01s = stats.get('portfolio_kr_dv01s', {})
        if hasattr(kr_dv01s, 'items'):
            self.FI_stats_keyrate_sensitivity = [
                {'maturity': str(k)+'y', 'bps': round(v,4)} for k, v in kr_dv01s.items()
            ]
        else:
            self.FI_stats_keyrate_sensitivity = []

        

    @rx.event
    async def set_statsportfolio(self, portfolio_name: str):
        """set live portfolio to analise in page live trading"""
        _, stats_return, stats_stats = read_portfolio(portfolio_name, self.user.username if self.user is not None else "")
        self.stats_code = portfolio_name
        self.stats_plot = []
        if stats_return is None:
            return

        data_plot = None
        if len(stats_return) > 0:
            try:
                data_plot = pd.read_json(StringIO(stats_return))
                data_plot.columns = [c.lower() for c in data_plot.columns]
            except Exception as e:
                print("Error reading stats_return:", e)
            
        #mow set performance plot
        if data_plot is None:
            return
        if not isinstance(data_plot, pd.DataFrame):
            return
        if any(val not in data_plot.columns for val in ["date", "cum_return"]):
            return
        self.eq_performance = []
        #need to format into a list of date into YY/MM and value
        #need to parse date 2025-04-24 into dtae and then format into YY/MM
        data_plot["date"] = pd.to_datetime(data_plot["date"]).dt.strftime("%Y-%m-%d")
        for i in range(len(data_plot)):
            self.eq_performance.append({"date": data_plot.iloc[i]["date"], "value": data_plot.iloc[i]["cum_return"]})


        # --- Prepare lightweight-chart data for the equity stats plot ---
        series_data_eq = []
        for d_str, val in zip(data_plot["date"], data_plot["cum_return"]):
            if pd.isna(val):
                continue
            # 'date' is in YY/MM format – convert back to datetime safely.
            ts = d_str#pd.to_datetime(d_str, format='%Y-%m-%d', errors='coerce')
            if pd.isna(ts):
                continue
            series_data_eq.append({
                "time": ts,  # use 1st day of month
                "value": float(val),
            })
        self.eq_performance_lightweight = {
            "plot_name": self.stats_code,
            "title": "Portfolio Performance",
            "xaxis": "date",
            "yaxis": "cum_return",
            "series_name": "cum_return",
            "series_data": series_data_eq,
        }
        # store pre-serialized json string for frontend
        # Hardcoded data for testing the lightweight chart
        # sample_chart_data = [
        #     {"time": "2023-01-01", "value": 100},
        #     {"time": "2023-01-02", "value": 105},
        #     {"time": "2023-01-03", "value": 98},
        #     {"time": "2023-01-04", "value": 110},
        #     {"time": "2023-01-05", "value": 115},
        #     {"time": "2023-01-06", "value": 112},
        #     {"time": "2023-01-07", "value": 120},
        #     {"time": "2023-01-08", "value": 125},
        #     {"time": "2023-01-09", "value": 122},
        #     {"time": "2023-01-10", "value": 130},
        # ]
        # self.eq_performance_lightweight_json = json.dumps(sample_chart_data)
        # Original line, commented out for testing:
        
        self.eq_performance_lightweight_json = json.dumps(series_data_eq)
        print("-----------------------------series_data_eq:")
        for s in series_data_eq:
            print(s["time"], s["value"])
        #need to transform stats_stats into eq_stats
        try:
            stats = json.loads( stats_stats)
            eq_stats = stats["statistics"]
            self.eq_stats = []
            for k,v in eq_stats.items():
                self.eq_stats.append({"metric_name": k, "metric_value": v})    
            #now eq_returns
            eq_returns = stats["returns"]
            self.eq_returns = []
            for k,v in eq_returns.items():
                self.eq_returns.append({"metric_name": k, "metric_value": v})    
            fill_colors = [  
            "#82ca9d",  # green mint
            "#ffc658",  # golden yellow
            "#ff8042",  # orange
            "#8dd1e1",  # sky blue
            "#d0ed57",  # pastel yellow-green
            "#d885a3",  # soft pink
            "#8884d8",  # soft violet
            "#a4de6c",  # lime green
            "#83a6ed",  # cornflower blue
            "#b3b3cc",  # lavender gray
            ]
            #add fill colors to sector_weights
            eq_sectors = stats["sectors"]
            self.eq_sectors = []
            for n,(k,v) in enumerate(eq_sectors.items()):
                self.eq_sectors.append({
                    "name": k, 
                    "value": v,
                    "value_str": f"{round(v, 2)}%", 
                    "label": k,
                    "fill":fill_colors[n%len(fill_colors)]
                    })
            print("eq_sectors:", str(self.eq_sectors))

            #holdings
            eq_holdings = stats["holdings"]
            self.eq_holdings = []
            for k,v in eq_holdings.items():
                self.eq_holdings.append({"ticker": k, "weight": v})
            print("eq_holdings:", str(self.eq_holdings))


            self.stats_std_annual = float(stats["statistics"]["standard_deviation"])
            self.stats_risk_level = min(int(100*100*self.stats_std_annual/30),100)
            #self.stats_dash_value = int(282.74 * self.stats_risk_level / 100)  # max 180 degrees
            print("stats_risk_level:", self.stats_risk_level)
            print("risk_level:", self.stats_risk_level)
            if self.stats_std_annual<0.08:
                self.stats_risk = "Low"
            elif self.stats_std_annual<0.25:
                self.stats_risk = "Medium"
            else:
                self.stats_risk = "High"


            #factors exposures
            factor_exposures = stats["factor_exposures"]
            
            for item in self.eq_factor_scores:
                print("factor:", item["factor"], "score:", factor_exposures.get(item["factor"]))
                if item["factor"] in factor_exposures:
                    print("setting score:", factor_exposures[item["factor"]])
                    item["score"] = factor_exposures[item["factor"]]
                else:
                    item["score"] = 2.37
            #update values for the gauge
            for item in self.eq_factor_scores:
                item["dash"] = ((item["score"]+3) / 6.5) * 282.74
                item["arrow_angle"] = -90 + ((item["score"]+3)/6.5) * 180
                item["score_norm"] = round(((item["score"]+3) ), 2)


            return rx.redirect("/stats")
        except Exception as e:
            print("Error in reading json stats file", str(e))

        
        # fig = px.line(
        #     data_plot,
        #     x="date",
        #     y="cum_return",
        #     #color=color,
        #     title="portfolio return"
        # )
        # fig.update_layout(
        #     title={
        #         'text': f"portfolio: {self.stats_code}",
        #         'font': {
        #             'color': 'blue'
        #         }
        #     },
        #     paper_bgcolor='white',  # Set the background color of the paper (outside the plot area)
        #     plot_bgcolor='white'  # Set the background color of the plot area
        # )
        # layout_dict = fig.to_plotly_json()['layout']
        # self.stats_plot.append((fig, layout_dict))
        
    async def ensure_rabbitmq_consumer(self):
        import sys
        if self.user is None:
            print(f"[ensure_rabbitmq_consumer] No user logged in, skipping", flush=True)
            return

        user_id = self.user.username
        # Check if a task is already running for this user and is not done.
        if user_id in _background_tasks and not _background_tasks[user_id].done():
            print(f"[ensure_rabbitmq_consumer] Consumer already running for user {user_id}", flush=True)
            return

        print(f"[ensure_rabbitmq_consumer] Starting new consumer for user {user_id}", flush=True)
        print(f"[ensure_rabbitmq_consumer] USE_CLOUDAMQP={USE_CLOUDAMQP}, FASTSTREAM_AVAILABLE={FASTSTREAM_AVAILABLE}, CLOUDAMQP_URL={'set' if CLOUDAMQP_URL else 'not set'}", flush=True)

        # Choose consumer based on USE_CLOUDAMQP flag
        if USE_CLOUDAMQP and FASTSTREAM_AVAILABLE and CLOUDAMQP_URL:
            print(f"[ensure_rabbitmq_consumer] Using CloudAMQP for user {user_id}", flush=True)
            task = asyncio.create_task(self.start_cloudamqp_consumer(user_id))
        else:
            print(f"[ensure_rabbitmq_consumer] Using local RabbitMQ for user {user_id}", flush=True)
            task = asyncio.create_task(self.start_rabbitmq_consumer(user_id))

        _background_tasks[user_id] = task

        # Add a callback to remove the task from the store when it's finished.
        task.add_done_callback(lambda t: _background_tasks.pop(user_id, None))

    async def start_rabbitmq_consumer(self, user_id: str):
        import sys
        queue_name = f"user_{user_id}_queue"
        routing_key = f"user.{user_id}.job.*"
        print(f"[start_rabbitmq_consumer] Starting consumer for user={user_id}, queue={queue_name}, routing_key={routing_key}", file=sys.stderr, flush=True)

        async def on_message(message: aio_pika.IncomingMessage):
            async with message.process():
                try:
                    print(f"[RabbitMQ] ✅ Received message for user {user_id}: {message.body.decode()[:200]}...", file=sys.stderr, flush=True)
                    message_data = json.loads(message.body.decode())
                    job_id = message_data.get('job_id')
                    res=message_data.get('result')
                    chat = message_data.get('chat_id')
                    message_type = message_data.get('message_type')
                    status = message_data.get('status')
                    print(f"[RabbitMQ] DEBUG: job_id={job_id}, chat_id='{chat}', message_type={message_type}, status={status}", file=sys.stderr, flush=True)
                    if not chat:
                        print(f"[RabbitMQ] ⚠️ WARNING: chat_id is empty! Message will be dropped. Full message: {message_data}", file=sys.stderr, flush=True)
                        return
                    #zipped_lists = list(zip(self.job_ids, self.job_ids_chats))
                    #for uuuid, chat in list(reversed(zipped_lists)):
                    print("job_id:", job_id, "chat:", chat, ",job_id:", job_id, ",res:", res)
                    answer = ""
                    if message_type=="job_update" and status=="in_progress":
                        answer +=f"""<br>{res} """

                    #if uuuid==job_id:
                    print("matched received id with job in list")
                    if message_type=="job_update" and status=="completed":
                        #answer +=f"""<br> QUEUE: {uuuid} job done. <br> """
                        #answer +=f"""<br>job done. <br> """
                        #from ETFs
                        added=False
                        if "DATATABLE" in res:
                            data_table, name = self.get_params(res, 'DATATABLE' ,'NAME')
                            nickname = self.current_chat+"_"+"table"
                            title=name

                            datatable_obj = DataTable(
                                id=self.new_datatables_id(),
                                table_name=data_table,
                                title=title,
                                nickname=nickname
                            )
                            nickname = self.add_table_to_list(datatable_obj)
                            self.add_to_combined_content("table", datatable_obj, self.current_chat)
                            added=True
                            answer = self.get_text_after_keyword_from_str(res, "DATATOPLOT")
                        if "DATATOPLOT" in res:
                            data_toplot, column = self.get_params(res, 'DATATOPLOT')
                            xaxis = 'date'
                            color = 'etf'
                            nickname = self.current_chat + "_" + "plot"
                            title = 'ETF Cumulative Performance (%)'
                            print("added data plot with params: plotname", data_toplot, ",xaxis:", xaxis, ",column:", column, ",color:", color, ",title:", title)

                            dataplot_obj = DataPlot(
                                id=self.new_dataplots_id(),
                                plot_name=data_toplot,
                                column=column,
                                xaxis=xaxis,
                                color=color,
                                title=title,
                                nickname=nickname
                            )
                            nickname = self.add_plot_to_list(dataplot_obj)
                            self.add_to_combined_content("plot", dataplot_obj, self.current_chat)
                            added=True
                            #get the text after line contaning "DATATOPLOT"

                            answer = self.get_text_after_keyword_from_str(res, "DATATOPLOT")
                        if "PAPER_COMPLETED" in res:
                            # Handle paper generation completion - just extract final_answer
                            answer = extract_tag_content(res, "final_answer")
                            added=True
                            print(f"[PAPER_COMPLETED] Extracted final answer: {answer[:200]}...")
                        if "DATA_ANALYSIS_TO_PLOT" in res:
                            params = ["data_path", "title", "x_axis_column", "y_axis_column", "color_column"]
                            params_dict = self.get_params2(res, params=params)
                            xaxis = params_dict["x_axis_column"]
                            column = params_dict["y_axis_column"]
                            color = params_dict.get("color_column","")
                            plot_name = Path(params_dict["data_path"]).name
                            title = params_dict["title"]
                            nickname = chat + "_" + "plot"
                            print("added data plot with params: plotname", plot_name, "xaxis:", xaxis, "column:", column, "color:", color, "title:", title)
                            dataplot_obj = DataPlot(
                                id=self.new_dataplots_id(chat),
                                plot_name=plot_name,
                                column=column,
                                xaxis=xaxis,
                                color=color,
                                title=title,
                                nickname=nickname
                            )
                            answer = extract_tag_content(res, "final_answer")
                            nickname = self.add_plot_to_list(dataplot_obj, chat)
                            print("-----------ADDED TO LIST PLOT -----------")
                            self.add_to_combined_content("plot", dataplot_obj,chat)
                            print("-----------LIST COMBINED: -----------")
                            added=True
                        if "DATA_ANALYSIS_TO_TABLE" in res:
                            params=["data_path", "title","columns_list"]
                            params_dict = self.get_params2(res, params=params)
                            nickname = self.current_chat+"_"+"table"
                            title = params_dict["title"]
                            data_table = Path(params_dict["data_path"]).name

                            datatable_obj = DataTable(
                                id=self.new_datatables_id(),
                                table_name=data_table,
                                title=title,
                                nickname=nickname
                            )
                            answer = extract_tag_content(res, "final_answer")
                            nickname = self.add_table_to_list(datatable_obj)  
                            self.add_to_combined_content("table", datatable_obj,chat)  
                            added=True
                        if not added:
                            if "csv" in res:
                                portfolio_name = res.split(":")[1]
                                #if it is equity you need to do stil generate performance still
                                if "TYPE:FI" not in res:
                                    #answer += f"<br> you can generate plots with: <br> @finbuddy.equity_longshort generate performance for portfolio {portfolio_name} marketcap_weight 130/30"
                                    answer = "generated portfolio:"
                                    answer_plot, _ = self.add_portfolio_plot(res, chat)
                                    answer+=answer_plot
                                    print("added all plots for not FI from rabbit")
                                    #rx.set_value("question", f"@finbuddy.equity_longshort generate performance for portfolio {portfolio_name} marketcap_weight 130/30")
                                #if it is FI generates portfolio and performance together
                                if "TYPE:FI" in res:
                                    print("received answer:", answer)
                                    answer_plot, _ = self.add_portfolio_plot(res, chat)
                                    answer+=answer_plot
                                    print("added all plots for FI from rabbit")
                                    #yield State.set_plots_frontend()
                                    answer = replace_expection(answer)
                            else:
                                # Plain text result (no special keywords) - use res directly
                                answer = res
                    print("list of chats:")
                    for k,v in self.chats_list.items():
                                print("...+++====,",k)
                    if message_type=="job_update":
                        if status=="completed":
                            self.chats_list[chat][-1].answer = answer
                        else:
                            br_count = self.chats_list[chat][-1].answer.count("<br>")
                            update_cnt = self.job_update_progress
                            update_cnt+=10
                            self.job_update_progress = update_cnt if update_cnt<100 else 0
                            if br_count>=6:
                                self.chats_list[chat][-1].answer = "Generating: " + answer
                            else:
                                if "Generating: " not in answer:
                                    self.chats_list[chat][-1].answer = "Generating: "+answer
                                else:
                                    self.chats_list[chat][-1].answer += answer
                    with rx.session() as session:
                        id = self.chats_list[chat][-1].id
                        if id > 0:
                            # update answer
                            this_qa = session.query(QAs).filter(QAs.id == id).first()
                            this_qa.answer = self.chats_list[chat][-1].answer
                            # update plot if any

                            session.commit()
                    if message_type=="job_update" and status=="completed":
                        pass #TODO keep a list of jobs open front end side?
                        # idx = self.job_ids.index(uuuid)
                        # del self.job_ids[idx]
                        # del self.job_ids_chats[idx]
                        if chat not in self.job_ready_chats:
                            self.job_ready_chats.append(chat)
                    self.need_plot_refresh = True
                except Exception as e:
                    print(f"Error processing message: {e}")

        while True:
            try:
                print(f"[start_rabbitmq_consumer] Connecting to amqp://guest:guest@localhost/...", file=sys.stderr, flush=True)
                connection = await aio_pika.connect_robust("amqp://guest:guest@localhost/")
                async with connection:
                    print(f"[start_rabbitmq_consumer] ✅ Connected! Setting up channel...", file=sys.stderr, flush=True)
                    channel = await connection.channel()
                    await channel.set_qos(prefetch_count=1)
                    exchange = await channel.declare_exchange(
                        "jobs_exchange", aio_pika.ExchangeType.TOPIC, durable=True
                    )
                    print(f"[start_rabbitmq_consumer] ✅ Exchange 'jobs_exchange' declared", file=sys.stderr, flush=True)
                    queue = await channel.declare_queue(queue_name, durable=True)
                    print(f"[start_rabbitmq_consumer] ✅ Queue '{queue_name}' declared", file=sys.stderr, flush=True)
                    await queue.bind(exchange, routing_key)
                    print(f"[start_rabbitmq_consumer] ✅ Queue bound to exchange with routing_key='{routing_key}'", file=sys.stderr, flush=True)
                    print(f"[start_rabbitmq_consumer] 🎧 RabbitMQ consumer started for user {user_id}. Waiting for messages...", file=sys.stderr, flush=True)
                    await queue.consume(on_message)
                    await asyncio.Future()  # Wait indefinitely.
            except (aio_pika.exceptions.AMQPConnectionError, ConnectionError) as e:
                print(f"[start_rabbitmq_consumer] ❌ RabbitMQ connection failed: {e}. Retrying in 5 seconds...", file=sys.stderr, flush=True)
                await asyncio.sleep(5)
            except Exception as e:
                print(f"[start_rabbitmq_consumer] ❌ Unexpected error: {e}", file=sys.stderr, flush=True)
                import traceback
                traceback.print_exc()
                await asyncio.sleep(5)

    async def start_cloudamqp_consumer(self, user_id: str):
        """
        FastStream-based consumer for CloudAMQP.
        Uses the same message handling logic as start_rabbitmq_consumer but with FastStream.
        Includes automatic reconnection on connection failures.
        """
        print(f"[CloudAMQP Consumer] ====== STARTING for user {user_id} ======", flush=True)

        if not FASTSTREAM_AVAILABLE:
            print(f"[CloudAMQP Consumer] ERROR: FastStream not available!", flush=True)
            return

        if not CLOUDAMQP_URL:
            print(f"[CloudAMQP Consumer] ERROR: CLOUDAMQP_URL not set!", flush=True)
            return

        print(f"[CloudAMQP Consumer] CLOUDAMQP_URL is set, FASTSTREAM_AVAILABLE={FASTSTREAM_AVAILABLE}", flush=True)

        queue_name = f"user_{user_id}_queue"
        routing_key = f"user.{user_id}.job.*"
        print(f"[CloudAMQP Consumer] Queue: {queue_name}, Routing key: {routing_key}", flush=True)

        # Define exchange and queue for FastStream
        jobs_exchange = RabbitExchange(
            name="jobs_exchange",
            type=ExchangeType.TOPIC,
            durable=True
        )

        user_queue = RabbitQueue(
            name=queue_name,
            durable=True,
            routing_key=routing_key
        )

        async def process_message(message_body: dict):
            """Process incoming message - same logic as on_message in aio_pika version."""
            import sys
            try:
                print(f"[CloudAMQP] ===== RECEIVED MESSAGE for user {user_id} =====", flush=True)
                print(f"[CloudAMQP] Message body: {message_body}", flush=True)

                job_id = message_body.get('job_id')
                res = message_body.get('result')
                chat = message_body.get('chat_id')
                message_type = message_body.get('message_type')
                status = message_body.get('status')

                print(f"[CloudAMQP] DEBUG: job_id={job_id}, chat_id='{chat}', message_type={message_type}, status={status}", file=sys.stderr, flush=True)

                if not chat:
                    print(f"[CloudAMQP] ⚠️ WARNING: chat_id is empty! Message will be dropped. Full message: {message_body}", file=sys.stderr, flush=True)
                    return

                print(f"[CloudAMQP] job_id: {job_id}, chat: {chat}, res: {res[:100] if res else 'None'}...")

                answer = ""
                # Handle progress updates (unified format: job_update + in_progress)
                if message_type == "job_update" and status == "in_progress":
                    answer += f"""<br>{res} """

                print("matched received id with job in list")
                # Handle completion (unified format: job_complete OR job_update with completed status)
                if (message_type == "job_complete" and status == "completed") or (message_type == "job_update" and status == "completed"):
                    # Use unified process_agent_result method (supports both JSON and legacy formats)
                    answer, added = self.process_agent_result(res, chat)

                print("list of chats:")
                for k, v in self.chats_list.items():
                    print("...+++====,", k)

                # SPECIAL HANDLING: Agent Builder uses a different response field
                if chat == "agent_builder":
                    print(f"[CloudAMQP] Agent Builder message - type={message_type}, status={status}")

                    # Handle all message types for Agent Builder
                    # NOTE: We set _pending_agent_result which gets applied by check_pending_agent_result event
                    # This is required because Reflex state changes in background tasks don't trigger UI updates
                    if status == "completed":
                        # Completed - show success with result
                        display_text = res if res else answer
                        if len(display_text) > 2000:
                            display_text = display_text[:2000] + "..."
                        self._pending_agent_result = f"✅ Agent Response:\n\n{display_text}"
                    elif status == "error":
                        # Error - show error message
                        error_text = res if res else "Unknown error"
                        self._pending_agent_result = f"❌ Error:\n\n{error_text[:500]}"
                    elif status == "in_progress":
                        # In-progress - show progress update
                        progress_text = res[:300] if res else "Working..."
                        self._pending_agent_result = f"🔄 {progress_text}"
                    else:
                        # Any other status - just show the result
                        display_text = res if res else f"Status: {status}"
                        if len(display_text) > 1000:
                            display_text = display_text[:1000] + "..."
                        self._pending_agent_result = f"📨 {message_type or 'Update'}:\n\n{display_text}"

                    print(f"[CloudAMQP] Set _pending_agent_result: {self._pending_agent_result[:100]}...")
                    self.need_plot_refresh = True
                    return  # Skip chat_list handling for agent_builder

                # Handle "job_update", "job_complete", and "job_error" message types (unified format)
                if message_type in ("job_update", "job_complete", "job_error"):
                    # Instead of modifying chats_list directly (which doesn't trigger UI updates),
                    # queue the update for processing by the Reflex event system
                    # Extract <final_answer> from res if answer is empty (agent didn't parse it)
                    final_answer = answer if answer else extract_tag_content(res, "final_answer") or "job completed"
                    update = {
                        "chat": chat,
                        "status": status,
                        "answer": final_answer,
                        "message_type": message_type
                    }
                    self._pending_chat_updates.append(update)
                    print(f"[CloudAMQP] 📝 Queued chat update for '{chat}': status={status}, answer={final_answer[:50] if final_answer else 'None'}...", file=sys.stderr, flush=True)

                    # Save to database only on completion (same as aio_pika path at line 2343-2351)
                    # Skip in_progress messages - only save final answer
                    if status == "completed" and chat in self.chats_list and self.chats_list[chat]:
                        qa_id = self.chats_list[chat][-1].id
                        if qa_id and qa_id > 0:
                            with rx.session() as session:
                                this_qa = session.query(QAs).filter(QAs.id == qa_id).first()
                                if this_qa:
                                    this_qa.answer = final_answer
                                    session.commit()
                                    print(f"[CloudAMQP] 💾 Saved answer to DB for QA id={qa_id}", file=sys.stderr, flush=True)

                # The update will be applied by apply_pending_chat_updates() called from start_progress2
                self.need_plot_refresh = True

            except Exception as e:
                print(f"[CloudAMQP] Error processing message: {e}", file=sys.stderr, flush=True)
                import traceback
                traceback.print_exc()

        # Reconnection loop - similar to aio_pika version
        while True:
            broker = None
            try:
                print(f"[CloudAMQP] Connecting to CloudAMQP for user {user_id}...")
                broker = RabbitBroker(CLOUDAMQP_URL)
                await broker.connect()

                # Declare exchange - returns the actual aio_pika exchange object
                declared_exchange = await broker.declare_exchange(jobs_exchange)

                # Declare queue and explicitly bind to exchange with routing key
                declared_queue = await broker.declare_queue(user_queue)
                # Use exchange name string for binding
                await declared_queue.bind("jobs_exchange", routing_key)

                print(f"[CloudAMQP] Consumer started for user {user_id}. Queue: {queue_name}, Routing: {routing_key}")

                # Subscribe to the queue
                @broker.subscriber(user_queue, exchange=jobs_exchange)
                async def handle_message(message: dict):
                    await process_message(message)

                # Start consuming - this will run until connection fails
                await broker.start()

                # Keep running until error
                await asyncio.Future()

            except Exception as e:
                print(f"[CloudAMQP] Connection failed for user {user_id}: {e}. Retrying in 5 seconds...")
                if broker:
                    try:
                        await broker.close()
                    except:
                        pass
                await asyncio.sleep(5)

    @rx.event
    async def maybe_refresh_plots(self):
        if self.need_plot_refresh:
            await self.set_plots_frontend()
            self.need_plot_refresh = False

    @rx.event
    async def check_pending_agent_result(self):
        """Check for pending agent results from RabbitMQ consumer and apply them."""
        if self._pending_agent_result:
            print(f"[check_pending_agent_result] Applying pending result: {self._pending_agent_result[:80]}...")
            self.agent_call_result = self._pending_agent_result
            self._pending_agent_result = ""  # Clear the pending result

    @rx.event
    async def apply_pending_chat_updates(self):
        """Apply pending chat updates from RabbitMQ consumer to the state.

        This must be called from within a Reflex event context to properly trigger UI updates.
        """
        import sys
        if not self._pending_chat_updates:
            return

        print(f"[apply_pending_chat_updates] Processing {len(self._pending_chat_updates)} pending updates", file=sys.stderr, flush=True)

        for update in self._pending_chat_updates[:]:  # Copy list to avoid modification during iteration
            chat = update["chat"]
            status = update["status"]
            answer = update["answer"]

            print(f"[apply_pending_chat_updates] Applying update to chat '{chat}': status={status}", file=sys.stderr, flush=True)

            # Find the QA in combined_content (the source of truth for UI)
            if chat in self.combined_content and self.combined_content[chat]:
                # Find the last message entry in combined_content
                for i in range(len(self.combined_content[chat]) - 1, -1, -1):
                    content_type, content_obj, timestamp = self.combined_content[chat][i]
                    if content_type == "message" and hasattr(content_obj, 'answer'):
                        # Update the answer based on status
                        if status == "completed":
                            content_obj.answer = answer
                            print(f"[apply_pending_chat_updates] ✅ Updated combined_content QA answer: {answer[:100] if answer else 'None'}...", file=sys.stderr, flush=True)
                        elif status == "error":
                            # Handle error status (unified format: job_error)
                            content_obj.answer = f"❌ Error: {answer}" if answer else "❌ An error occurred"
                            print(f"[apply_pending_chat_updates] ❌ Updated with error: {content_obj.answer[:100]}...", file=sys.stderr, flush=True)
                        else:
                            # For in-progress, append/update progress
                            br_count = content_obj.answer.count("<br>") if content_obj.answer else 0
                            if br_count >= 6:
                                content_obj.answer = "Generating: " + str(answer)
                            else:
                                if "Generating: " not in str(content_obj.answer):
                                    content_obj.answer = "Generating: " + str(answer)
                                else:
                                    content_obj.answer += str(answer)
                            print(f"[apply_pending_chat_updates] 🔄 Updated progress: {content_obj.answer[:100]}...", file=sys.stderr, flush=True)
                        break
                else:
                    print(f"[apply_pending_chat_updates] ⚠️ No message QA found in combined_content[{chat}]", file=sys.stderr, flush=True)
            else:
                print(f"[apply_pending_chat_updates] ⚠️ Chat '{chat}' not found in combined_content", file=sys.stderr, flush=True)

            # Also update chats_list for compatibility
            if chat in self.chats_list and self.chats_list[chat]:
                if status == "completed":
                    self.chats_list[chat][-1].answer = answer
                    if chat not in self.job_ready_chats:
                        self.job_ready_chats.append(chat)
                elif status == "error":
                    # Handle error status (unified format: job_error)
                    self.chats_list[chat][-1].answer = f"❌ Error: {answer}" if answer else "❌ An error occurred"

            self._pending_chat_updates.remove(update)

        # Force Reflex to detect state change - this is the key!
        # Re-assign combined_content to itself to trigger reactivity (same pattern as line 2574)
        self.combined_content = self.combined_content
        self._chat_refresh_counter += 1
        self.need_plot_refresh = True
        print(f"[apply_pending_chat_updates] ✅ State updated, counter={self._chat_refresh_counter}, UI should refresh", file=sys.stderr, flush=True)

    @rx.event(background=True)
    async def start_progress2(self):
        async with self:
            if self._n_tasks > 0:
                return
            self._n_tasks += 1
            self.value = 0
            max_time = 2000

        while self.value < max_time:
            await asyncio.sleep(3)
            async with self:
                if self.logged_in:
                    asyncio.create_task(self.ensure_rabbitmq_consumer())
                # Check for pending agent results from RabbitMQ
                if self._pending_agent_result:
                    await self.check_pending_agent_result()
                # Check for pending chat updates from RabbitMQ
                if self._pending_chat_updates:
                    await self.apply_pending_chat_updates()
                # Periodically refresh running containers list (every ~15 seconds)
                if self.value > 0 and self.value % 5 == 0:
                    self.load_running_containers()
                # Check and refresh plots if needed
                if self.value > 5 and self.value % 10 == 0 and self.need_plot_refresh:
                    await self.maybe_refresh_plots()
                # Progress logic
                if len(self.job_ids) > 0:
                    self.value += 10
                    #n=TODO check if better to stop or always run this to update UI
                if len(self.job_ids) == 0 or self.value>1850:
                    self.value = 0

        async with self:
            self._n_tasks = 0   

    @rx.event(background=True)
    async def start_progress(self):
        async with self:
            self.value = 0
            # The latest state values are always available inside the context
            if self._n_tasks > 0:
                # only allow 1 concurrent task
                return
            # State mutation is only allowed inside context block
            self._n_tasks += 1
            max_time = 2000
        while self.value < max_time:
            await asyncio.sleep(10)
            async with self:
                if  self.value>5 and self.value%10==0:
                    print("timer loop")
                    results = pool_jobids(list(self.job_ids), self.user.username)
                    results = results['uuid_results']
                    done_cnt=0
                    zipped_lists = list(zip(results, self.job_ids, self.job_ids_chats))
                    for res, uuuid, chat in list(reversed(zipped_lists)):
                        answer = ""
                        if res!='.':
                            answer +=f"""<br> QUEUE: {uuuid} job done. <br> {res}"""
                            if "csv" in res:
                                portfolio_name = res.split(":")[1]
                                #if it is equity you need to do stil generate performance still
                                if "FI" not in res:
                                    answer += f"<br> you can generate plots with: <br> @finbuddy.equity_longshort generate performance for portfolio {portfolio_name} marketcap_weight 130/30"
                                    rx.set_value("question", f"@finbuddy.equity_longshort generate performance for portfolio {portfolio_name} marketcap_weight 130/30")
                                #if it is FI generates portfolio and performance together
                                else:
                                    print("received answer:", answer)
                                    #answer, _ = self.add_portfolio_plot(answer)
                                    print("added all plots for FI from timer")
                                    #yield State.set_plots_frontend()
                                    answer = replace_expection(answer)
                            self.chats_list[chat][-1].answer += answer
                            with rx.session() as session:
                                id = self.chats_list[chat][-1].id
                                if id > 0:
                                    # update answer
                                    this_qa = session.query(QAs).filter(QAs.id == id).first()
                                    this_qa.answer += answer
                                    # update plot if any

                                    session.commit()
                            done_cnt +=1
                            idx = self.job_ids.index(uuuid)
                            del self.job_ids[idx]
                            del self.job_ids_chats[idx]

                if len(self.job_ids)>0:
                    self.value += 10
                if len(self.job_ids)==0:
                    self.value = max_time
        async with self:
            self._n_tasks = 0
            # if len(self.job_ids)>0:
            #     zipped_lists = list(zip(self.job_ids, self.job_ids_chats))
            #     for uuuid, chat in list(reversed(zipped_lists)):
            #         self.chats_list[chat][-1].answer += f"<br>-->{uuuid} timed out. <br> sorry for the inconvenience, try to type again..."
            #     self.job_ids_chats = []
            #     self.job_ids = []

    def load_table(self) -> list[liveinstruments]:
        with rx.session() as session:
            self.instruments = session.exec(
               select(liveinstruments)
            ).all()
            sectors_gby = session.exec(
                sqlalchemy.text("""
                                SELECT sector,
                                       SUM(weight) AS weight,
                                       SUM(notional) AS notional
                                FROM LiveInstruments
                                GROUP BY sector
                                """,
                )

            ).fetchall()
            self.groupby_sector = [tuple(row) for row in sectors_gby]

    def load_entries(self):
        """Get all instruments from the database.
        REMEMBER TO INIT the db with REFLEX DB INIT"""
        with rx.session() as session:
            if len(self.live_portfolio)>0:
                data = pd.read_json(StringIO(self.live_portfolio))
                data = data[["ticker", "weight", "notional", "close", "sector", "industry", "description","side_long", "side_short"]]
                session.exec(select(liveinstruments)).delete()
                for index, row in data.iterrows():
                    data_tuple = row.to_dict()
                    # Create an instance of Model using dictionary unpacking
                    item = liveinstruments(**data_tuple)
                    session.add(item)
            #
            session.commit()
            self.load_table()
        # return self.instruments

    @rx.var(cache=True)
    def current_instruments(self) -> list[liveinstruments]:
        instruments = self.instruments

        if self.live_sort_value != "":
            instruments = sorted(
                instruments,
                key=lambda inst: getattr(
                    inst, self.live_sort_value
                ).lower(),
            )

        if self.live_search_value != "":
            instruments = [
                instrument
                for instrument in instruments
                if any(
                    self.live_search_value
                    in getattr(instrument, attr).lower()
                    for attr in ["ticker",
                                 "sector"
                                 ]
                )
            ]
        return instruments

    @rx.var
    def chat_titles(self) -> list[str]:
        """Get the list of chat titles.

        Returns:
            The list of chat names.
        """
        return list(self.chats_list.keys())

    # ========== Chat Directory Methods ==========

    @rx.var
    def root_directories(self) -> List[DirectoryInfo]:
        """Get root-level directories (parent_id is None)."""
        return [
            DirectoryInfo(
                id=dir_id,
                name=dir_data.get("name", ""),
                parent_id=dir_data.get("parent_id"),
                chat_titles=dir_data.get("chat_titles", [])
            )
            for dir_id, dir_data in self.chat_directories.items()
            if dir_data.get("parent_id") is None
        ]

    @rx.var
    def root_chats(self) -> List[str]:
        """Get chats that are not in any directory."""
        # Chats with no directory_id (at root level)
        chats_with_dirs = set()
        for dir_data in self.chat_directories.values():
            chats_with_dirs.update(dir_data.get("chat_titles", []))
        return [chat for chat in self.chats_list.keys() if chat not in chats_with_dirs]

    @rx.var
    def shared_chats_list(self) -> List[Dict[str, Any]]:
        """Get list of shared chats for display in 'Shared with you' directory."""
        return self.shared_chats

    @rx.var
    def user_groups_list(self) -> List[Dict[str, str]]:
        """Get list of user's groups for display in share menu."""
        return self.user_groups

    # JSON vars for JavaScript tree component
    @rx.var
    def directories_json(self) -> str:
        """Get directories as JSON for JS component."""
        dirs = [
            {
                "id": dir_id,
                "name": dir_data.get("name", ""),
                "parent_id": dir_data.get("parent_id"),
                "chat_titles": dir_data.get("chat_titles", [])
            }
            for dir_id, dir_data in self.chat_directories.items()
            if dir_data.get("parent_id") is None
        ]
        return json.dumps(dirs)

    @rx.var
    def root_chats_json(self) -> str:
        """Get root chats as JSON for JS component."""
        chats_with_dirs = set()
        for dir_data in self.chat_directories.values():
            chats_with_dirs.update(dir_data.get("chat_titles", []))
        root = [chat for chat in self.chats_list.keys() if chat not in chats_with_dirs]
        return json.dumps(root)

    @rx.var
    def expanded_dirs_json(self) -> str:
        """Get expanded dirs as JSON for JS component."""
        return json.dumps(self.expanded_dirs)

    def rename_directory_js(self, dir_id: int, new_name: str):
        """Rename a directory from JS component."""
        if not self.user or not new_name.strip():
            return

        with rx.session() as session:
            directory = session.get(ChatDirectory, dir_id)
            if directory and directory.user_id == self.user.id:
                directory.name = new_name.strip()
                session.commit()

                # Update local state
                if dir_id in self.chat_directories:
                    self.chat_directories[dir_id]["name"] = new_name.strip()

    def handle_drag_drop_action(self, value: str):
        """Handle drag-drop action from JavaScript.

        Args:
            value: JSON string with {chat: str, dir_id: int|null}
        """
        print(f"[DRAG-DROP] handle_drag_drop_action called with value: {value}")

        if not value or not self.user:
            print(f"[DRAG-DROP] Early return: value={bool(value)}, user={bool(self.user)}")
            return

        try:
            data = json.loads(value)
            chat_name = data.get("chat")
            dir_id = data.get("dir_id")
            print(f"[DRAG-DROP] Parsed data: chat={chat_name}, dir_id={dir_id}")

            if chat_name:
                # Convert dir_id to int if it's a string, or None
                if dir_id is not None:
                    dir_id = int(dir_id)

                print(f"[DRAG-DROP] Calling move_chat_to_directory({chat_name}, {dir_id})")
                self.move_chat_to_directory(chat_name, dir_id)
                print(f"[DRAG-DROP] Move completed successfully")
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[DRAG-DROP] Error: {e}")

    def handle_drag_drop_click(self):
        """Handle click from hidden drag-drop trigger button.

        Uses rx.call_script to retrieve drag-drop data from window.__dragDropData.
        """
        print("[DRAG-DROP] handle_drag_drop_click called - fetching data from JS")
        return rx.call_script(
            "JSON.stringify(window.__dragDropData || {})",
            callback=State.process_drag_drop_data,
        )

    def process_drag_drop_data(self, data: str):
        """Process the drag-drop data retrieved from JavaScript.

        Args:
            data: JSON string with {chat: str, dir_id: int|null}
        """
        print(f"[DRAG-DROP] process_drag_drop_data called with: {data}")

        if not data or data == "{}" or not self.user:
            print(f"[DRAG-DROP] Early return: data={data}, user={bool(self.user)}")
            return

        try:
            parsed = json.loads(data)
            chat_name = parsed.get("chat")
            dir_id = parsed.get("dir_id")
            print(f"[DRAG-DROP] Parsed: chat={chat_name}, dir_id={dir_id}")

            if chat_name:
                # Convert dir_id to int if it's a string, or None
                if dir_id is not None:
                    dir_id = int(dir_id)

                print(f"[DRAG-DROP] Calling move_chat_to_directory({chat_name}, {dir_id})")
                self.move_chat_to_directory(chat_name, dir_id)
                print(f"[DRAG-DROP] Move completed successfully")
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[DRAG-DROP] Error parsing data: {e}")

    def get_subdirectories(self, parent_id: int) -> List[Dict[str, Any]]:
        """Get subdirectories for a given parent directory."""
        return [
            {"id": dir_id, **dir_data}
            for dir_id, dir_data in self.chat_directories.items()
            if dir_data.get("parent_id") == parent_id
        ]

    def get_chats_in_directory(self, dir_id: int) -> List[str]:
        """Get chat titles that belong to a specific directory."""
        dir_data = self.chat_directories.get(dir_id, {})
        return dir_data.get("chat_titles", [])

    def toggle_directory(self, dir_id: int):
        """Toggle expand/collapse state of a directory."""
        if dir_id in self.expanded_dirs:
            self.expanded_dirs = [d for d in self.expanded_dirs if d != dir_id]
        else:
            self.expanded_dirs = self.expanded_dirs + [dir_id]

    def is_directory_expanded(self, dir_id: int) -> bool:
        """Check if a directory is expanded."""
        return dir_id in self.expanded_dirs

    def load_directories_from_db(self):
        """Load chat directories from database and populate state."""
        if not self.user:
            return

        with rx.session() as session:
            # Load all directories for this user
            dirs = session.exec(
                select(ChatDirectory).where(ChatDirectory.user_id == self.user.id)
            ).all()

            # Load all chats with their directory assignments
            chats = session.exec(
                select(Chats).where(Chats.user_id == self.user.id)
            ).all()

            # Build directory structure
            new_directories = {}
            shared_dir_id = None
            for d in dirs:
                new_directories[d.id] = {
                    "name": d.name,
                    "parent_id": d.parent_id,
                    "order": d.order,
                    "chat_titles": [],
                    "is_shared_dir": d.name == "Shared with you"  # Mark the shared directory
                }
                # Track the "Shared with you" directory ID
                if d.name == "Shared with you":
                    shared_dir_id = d.id

            # Assign chats to directories
            for chat in chats:
                if chat.directory_id and chat.directory_id in new_directories:
                    new_directories[chat.directory_id]["chat_titles"].append(chat.chat_title)

            self.chat_directories = new_directories
            self.shared_with_you_dir_id = shared_dir_id

            # Load shared chats from PostgreSQL RBAC
            self.shared_chats = self.get_shared_chats()

    def create_directory(self, name: str, parent_id: Optional[int] = None):
        """Create a new chat directory."""
        if not self.user or not name.strip():
            return

        # Enforce 2-level limit: if parent has a parent, don't allow
        if parent_id is not None:
            parent_data = self.chat_directories.get(parent_id, {})
            if parent_data.get("parent_id") is not None:
                # Parent is already a subdirectory, can't go deeper
                return

        with rx.session() as session:
            new_dir = ChatDirectory(
                user_id=self.user.id,
                name=name.strip(),
                parent_id=parent_id,
                order=len(self.chat_directories)
            )
            session.add(new_dir)
            session.commit()
            session.refresh(new_dir)

            # Update local state
            self.chat_directories[new_dir.id] = {
                "name": new_dir.name,
                "parent_id": new_dir.parent_id,
                "order": new_dir.order,
                "chat_titles": []
            }

        self.new_dir_name = ""

    def delete_directory(self, dir_id: int):
        """Delete a directory and all chats inside it."""
        if not self.user or dir_id not in self.chat_directories:
            return

        with rx.session() as session:
            # Delete all chats in this directory
            chats_to_delete = session.exec(
                select(Chats).where(
                    Chats.user_id == self.user.id,
                    Chats.directory_id == dir_id
                )
            ).all()

            for chat in chats_to_delete:
                # Remove from local state
                if chat.chat_title in self.chats_list:
                    del self.chats_list[chat.chat_title]
                session.delete(chat)

            # Delete subdirectories first
            subdirs = session.exec(
                select(ChatDirectory).where(
                    ChatDirectory.user_id == self.user.id,
                    ChatDirectory.parent_id == dir_id
                )
            ).all()

            for subdir in subdirs:
                # Recursively delete subdirectory chats
                sub_chats = session.exec(
                    select(Chats).where(
                        Chats.user_id == self.user.id,
                        Chats.directory_id == subdir.id
                    )
                ).all()
                for chat in sub_chats:
                    if chat.chat_title in self.chats_list:
                        del self.chats_list[chat.chat_title]
                    session.delete(chat)
                session.delete(subdir)
                if subdir.id in self.chat_directories:
                    del self.chat_directories[subdir.id]

            # Delete the directory itself
            directory = session.get(ChatDirectory, dir_id)
            if directory:
                session.delete(directory)

            session.commit()

        # Remove from local state
        if dir_id in self.chat_directories:
            del self.chat_directories[dir_id]
        if dir_id in self.expanded_dirs:
            self.expanded_dirs = [d for d in self.expanded_dirs if d != dir_id]

    def move_chat_to_directory(self, chat_title: str, dir_id: Optional[int]):
        """Move a chat to a directory (or to root if dir_id is None)."""
        if not self.user:
            return

        with rx.session() as session:
            chat = session.exec(
                select(Chats).where(
                    Chats.user_id == self.user.id,
                    Chats.chat_title == chat_title
                )
            ).first()

            if chat:
                old_dir_id = chat.directory_id
                chat.directory_id = dir_id
                session.commit()

                # Update local state
                if old_dir_id and old_dir_id in self.chat_directories:
                    old_titles = self.chat_directories[old_dir_id].get("chat_titles", [])
                    self.chat_directories[old_dir_id]["chat_titles"] = [
                        t for t in old_titles if t != chat_title
                    ]

                if dir_id and dir_id in self.chat_directories:
                    self.chat_directories[dir_id]["chat_titles"].append(chat_title)

    def set_new_dir_name(self, name: str):
        """Set the name for a new directory."""
        self.new_dir_name = name

    # ========== Directory Rename Methods ==========

    def start_rename_directory(self, dir_id: int):
        """Start renaming a directory (triggered by double-click)."""
        if dir_id in self.chat_directories:
            self.renaming_dir_id = dir_id
            self.rename_dir_value = self.chat_directories[dir_id]["name"]

    def set_rename_dir_value(self, value: str):
        """Update the rename input value."""
        self.rename_dir_value = value

    def cancel_rename_directory(self):
        """Cancel directory rename."""
        self.renaming_dir_id = None
        self.rename_dir_value = ""

    def confirm_rename_directory(self):
        """Confirm and save the directory rename."""
        if not self.user or not self.renaming_dir_id or not self.rename_dir_value.strip():
            self.cancel_rename_directory()
            return

        with rx.session() as session:
            directory = session.get(ChatDirectory, self.renaming_dir_id)
            if directory and directory.user_id == self.user.id:
                directory.name = self.rename_dir_value.strip()
                session.commit()

                # Update local state
                if self.renaming_dir_id in self.chat_directories:
                    self.chat_directories[self.renaming_dir_id]["name"] = self.rename_dir_value.strip()

        self.renaming_dir_id = None
        self.rename_dir_value = ""

    def rename_directory_on_blur(self):
        """Handle blur event - confirm rename."""
        self.confirm_rename_directory()

    def rename_directory_on_key(self, key: str):
        """Handle key press during rename."""
        if key == "Enter":
            self.confirm_rename_directory()
        elif key == "Escape":
            self.cancel_rename_directory()

    # ========== Menu-based Move Methods ==========

    # Chat being moved via context menu
    moving_chat: str = ""

    @rx.var
    def has_directories(self) -> bool:
        """Check if there are any directories."""
        return len(self.chat_directories) > 0

    @rx.var
    def directory_menu_items(self) -> List[Dict[str, Any]]:
        """Get list of directories for the move menu."""
        return [
            {"id": dir_id, "name": dir_data["name"]}
            for dir_id, dir_data in self.chat_directories.items()
        ]

    def set_moving_chat(self, chat_title: str):
        """Set the chat that is being moved via menu."""
        self.moving_chat = chat_title

    def move_current_chat_to_directory(self, dir_id: int):
        """Move the currently selected chat (from menu) to a directory."""
        if self.moving_chat:
            self.move_chat_to_directory(self.moving_chat, dir_id)
            self.moving_chat = ""

    def delete_chat_by_name(self, chat_title: str):
        """Delete a chat by its title."""
        if not self.user:
            return

        with rx.session() as session:
            chat = session.exec(
                select(Chats).where(
                    Chats.user_id == self.user.id,
                    Chats.chat_title == chat_title
                )
            ).first()

            if chat:
                # Remove from directory if in one
                if chat.directory_id and chat.directory_id in self.chat_directories:
                    old_titles = self.chat_directories[chat.directory_id].get("chat_titles", [])
                    self.chat_directories[chat.directory_id]["chat_titles"] = [
                        t for t in old_titles if t != chat_title
                    ]

                # Delete the chat
                session.delete(chat)
                session.commit()

                # Remove from local state
                if chat_title in self.chats_list:
                    del self.chats_list[chat_title]
                if chat_title in self.chats_name_plots:
                    del self.chats_name_plots[chat_title]
                if chat_title in self.chats_name_tables:
                    del self.chats_name_tables[chat_title]
                if chat_title in self.chats_name_portfolios:
                    del self.chats_name_portfolios[chat_title]
                if chat_title in self.chats_data_plots:
                    del self.chats_data_plots[chat_title]
                if chat_title in self.chats_data_tables:
                    del self.chats_data_tables[chat_title]

                # Switch to another chat if this was the current one
                if self.current_chat == chat_title:
                    remaining = list(self.chats_list.keys())
                    self.current_chat = remaining[0] if remaining else "Buddy"

    # ========== End Chat Directory Methods ==========

    @rx.var
    def saved_portfolios(self) -> list[str]:
        """Get the list of chat titles.

        Returns:
            The list of chat names.
        """
        return self.portfolios

    @rx.var
    def all_saved_portfolios(self) -> list[str]:
        """Get the list of chat titles.

        Returns:
            The list of chat names.
        """
        return self.all_portfolios

    @rx.var
    def saved_plots(self) -> List[Tuple[Figure_plotly, Dict[str, str]]]:
        """Get the list of chat titles.

        Returns:
            The list of chat names.
        """
        return self.plots_fig

    @rx.var
    def dash_value_rx(self) -> float:
        radius = 90  # Must match SVG's radius (A90,90)
        circumference = 3.1416 * radius  # ≈282.74
        return (self.stats_risk_level / 100) * circumference  # Auto-updates when risk_level changes
    
    @rx.var
    def dash_arrow_rx(self) -> float:
        radius = 90  # Must match SVG's radius (A90,90)
        circumference = 180  # ≈282.74
        return (self.stats_risk_level / 100) * circumference  # Auto-updates when risk_level changes
    

    @rx.var
    def risk_level_rx(self) -> float:
        return self.stats_risk_level

    @rx.var
    def risk_level_txt_rx(self) -> str:
        return self.stats_risk

    @rx.var
    def std_annual_rx(self) -> int:
        return int(self.stats_std_annual*100)

    @rx.var
    def chat_plots(self) -> List[Tuple[Figure_plotly, Dict[str, str]]]:
        """Get the list of data for plots for currecnt chat.

        Returns:
            The list of chat names.
        """
        if self.current_chat in self.chats_data_plots:
            return self.chats_data_plots[self.current_chat]
        else:
            return []

    @rx.var
    def current_chat_content(self) -> rx.Var[List[Tuple[str, Union[QA,Tuple[Figure_plotly, Dict[str, str]],Tuple[pd.DataFrame, Dict[str, str]]], float]]]:
        # Access _chat_refresh_counter to create dependency - when it changes, this var re-computes
        _ = self._chat_refresh_counter
        return self.combined_content[self.current_chat]


    async def process_question(self, form_data: dict[str, str]):
        # Get the question from the form
        question = form_data["question"]
        self.question=""
        # Check if the question is empty
        if question is None or question == "":
            return
        if self.user is None:
            return
        self.question=question
        model = State.lc_bot_process_question


        yield model
        #async for value in model(question):
        #    yield value

        #functions and properties for markets strip
    @rx.var
    def market_max_start(self) -> int:
        """Largest valid window_start (len−window_size, never <0)."""
        return max(len(self.market_strip) - self.market_window_size, 0)

    @rx.var
    def market_strip_window(self) -> List[Dict]:
        """Slice that is actually rendered."""
        end = self.market_window_start + self.market_window_size
        return self.market_strip[self.market_window_start:end]

    @rx.var
    def market_can_scroll_left(self) -> bool:
        return self.market_window_start > 0

    @rx.var
    def market_can_scroll_right(self) -> bool:
        return self.market_window_start < self.market_max_start

    # ── event handlers ───────────────────────────────────────────
    def market_scroll_left(self):
        # shift one window left & clamp at 0
        self.market_window_start = max(self.market_window_start - int(self.market_window_size/4), 0)

    def market_scroll_right(self):
        # shift one window right & clamp at max_start
        self.market_window_start = min(self.market_window_start + int(self.market_window_size/4), self.market_max_start)


    async def process_question_event(self, form_data: dict[str, Any]):
        #yield State.reply_tag(form_data) #doe not work
        yield State.process_question(form_data)

    def get_params(self, answer_text, first_param='DATATOPLOT', second_param='COLUMN'):
        datatoplot_pattern = re.compile(rf'{first_param}:\s*([A-Za-z0-9_\.]+)')
        column_pattern = re.compile(rf'{second_param}:\s*([A-Za-z0-9_]+)')
        # # Find the first match
        # # get column name
        # column_match = column_pattern.search(answer_text)
        # column = column_match.group(1)
        # # get plot_name
        # data_match = datatoplot_pattern.search(answer_text)
        # data_toplot = data_match.group(1)
        # #normalise name this is return df
        # #data_toplot = "_".join(data_toplot.split("_")[:2])+"_return.csv"

        # Find all matches for the patterns
        column_matches = column_pattern.findall(answer_text)
        data_matches = datatoplot_pattern.findall(answer_text)

        # Get the last match if it exists, otherwise None
        column = column_matches[-1] if column_matches else None
        data_toplot = data_matches[-1] if data_matches else None

        return data_toplot, column
    
    def get_params2(self, answer_text="", params=["DATA_PATH", "TITLE", "X_AXIS_COLUMN", "Y_AXIS_COLUMN", "COLOR_COLUMN"]):
        params_dict = {}
        for param in params:
            pattern = re.compile(rf'"{param}"\s*:\s*"([^"]*)"')
            match = pattern.search(answer_text)
            if match:
                params_dict[param] = match.group(1)
        return params_dict
    
    def get_text_after_keyword_from_str(self, text, keyword):
        lines = text.split('\n')
        found = False
        after_lines = []
        for line in lines:
            if found:
                after_lines.append(line)
            if keyword in line:
                found = True
        return '\n'.join(after_lines)

    def process_agent_result(self, res: str, chat: str) -> tuple:
        """
        Process agent result - supports both new JSON format and legacy string format.

        New JSON format:
        {
            "status": "success",
            "message": "...",
            "output_type": "VALUE" | "TABLE" | "PLOT",
            "output_params": {...},
            "final_answer": "...",
            "success": true
        }

        Returns:
            tuple: (answer: str, added: bool) - the answer text and whether content was added
        """
        import sys
        answer = ""
        added = False

        # First, try to parse as JSON (new format)
        try:
            result_data = json.loads(res) if isinstance(res, str) else res

            # Check if this is the new JSON format (has output_type field)
            if isinstance(result_data, dict) and 'output_type' in result_data:
                print(f"[process_agent_result] Processing NEW JSON format", file=sys.stderr, flush=True)

                output_type = result_data.get('output_type', '').upper()
                output_params = result_data.get('output_params', {})
                final_answer = result_data.get('final_answer', '')
                success = result_data.get('success', False)

                print(f"[process_agent_result] output_type={output_type}, success={success}", file=sys.stderr, flush=True)

                if output_type == 'PLOT':
                    # Handle PLOT output
                    data_path = output_params.get('data_path', '')
                    title = output_params.get('title', 'Plot')
                    x_axis_column = output_params.get('x_axis_column', '')
                    y_axis_column = output_params.get('y_axis_column', '')
                    color_column = output_params.get('color_column', '')
                    plot_type = output_params.get('plot_type', 'line')

                    if data_path:
                        plot_name = Path(data_path).name
                        nickname = chat + "_" + "plot"
                        print(f"[process_agent_result] Creating PLOT: {plot_name}, x={x_axis_column}, y={y_axis_column}", file=sys.stderr, flush=True)

                        dataplot_obj = DataPlot(
                            id=self.new_dataplots_id(chat),
                            plot_name=plot_name,
                            column=y_axis_column,
                            xaxis=x_axis_column,
                            color=color_column,
                            title=title,
                            nickname=nickname
                        )
                        self.add_plot_to_list(dataplot_obj, chat)
                        self.add_to_combined_content("plot", dataplot_obj, chat)
                        added = True

                elif output_type == 'TABLE':
                    # Handle TABLE output
                    data_path = output_params.get('data_path', '')
                    title = output_params.get('title', 'Table')
                    columns_list = output_params.get('columns_list', [])

                    if data_path:
                        table_name = Path(data_path).name
                        nickname = chat + "_" + "table"
                        print(f"[process_agent_result] Creating TABLE: {table_name}, title={title}", file=sys.stderr, flush=True)

                        datatable_obj = DataTable(
                            id=self.new_datatables_id(chat),
                            table_name=table_name,
                            title=title,
                            nickname=nickname
                        )
                        self.add_table_to_list(datatable_obj, chat)
                        self.add_to_combined_content("table", datatable_obj, chat)
                        added = True

                elif output_type == 'VALUE':
                    # Handle VALUE output - just use the final_answer
                    value = output_params.get('value', '')
                    unit = output_params.get('unit', '')
                    print(f"[process_agent_result] VALUE result: {value} {unit}", file=sys.stderr, flush=True)
                    added = True  # Mark as added so we don't fall through to legacy handling

                # Use final_answer as the response
                answer = final_answer if final_answer else result_data.get('message', '')
                print(f"[process_agent_result] Final answer: {answer[:200]}...", file=sys.stderr, flush=True)
                return answer, added

        except (json.JSONDecodeError, TypeError):
            # Not JSON, fall through to legacy string-based parsing
            pass

        # Handle standardized tool response format (status/message but no output_type)
        try:
            result_data = json.loads(res) if isinstance(res, str) else res
            if isinstance(result_data, dict) and 'status' in result_data and 'output_type' not in result_data:
                # This is a standardized tool response (success_response/error_response)
                status = result_data.get('status', '')
                message = result_data.get('message', '')
                data = result_data.get('data', {})

                print(f"[process_agent_result] Processing standardized tool response: status={status}", file=sys.stderr, flush=True)

                # Build answer from message and data
                if status == 'success':
                    answer = message
                    # If there's meaningful data, include it
                    if data:
                        if isinstance(data, dict):
                            # Check for specification (macro_strategist output)
                            if 'specification' in data:
                                answer = data['specification']
                            # Check for analysis summary
                            elif 'analysis' in data:
                                answer = f"{message}\n\nAnalysis: {json.dumps(data['analysis'], indent=2)}"
                            else:
                                answer = f"{message}\n\nData: {json.dumps(data, indent=2, default=str)}"
                else:
                    answer = f"Error: {message}"

                print(f"[process_agent_result] Standardized response answer: {answer[:200]}...", file=sys.stderr, flush=True)
                return answer, True
        except (json.JSONDecodeError, TypeError):
            pass

        # Legacy string-based format handling
        print(f"[process_agent_result] Processing LEGACY string format", file=sys.stderr, flush=True)

        if "DATATABLE" in res:
            data_table, name = self.get_params(res, 'DATATABLE', 'NAME')
            nickname = self.current_chat + "_" + "table"
            title = name

            datatable_obj = DataTable(
                id=self.new_datatables_id(),
                table_name=data_table,
                title=title,
                nickname=nickname
            )
            self.add_table_to_list(datatable_obj)
            self.add_to_combined_content("table", datatable_obj, self.current_chat)
            added = True
            answer = self.get_text_after_keyword_from_str(res, "DATATOPLOT")

        if "DATATOPLOT" in res:
            data_toplot, column = self.get_params(res, 'DATATOPLOT')
            xaxis = 'date'
            color = 'etf'
            nickname = self.current_chat + "_" + "plot"
            title = 'ETF Cumulative Performance (%)'

            dataplot_obj = DataPlot(
                id=self.new_dataplots_id(),
                plot_name=data_toplot,
                column=column,
                xaxis=xaxis,
                color=color,
                title=title,
                nickname=nickname
            )
            self.add_plot_to_list(dataplot_obj)
            self.add_to_combined_content("plot", dataplot_obj, self.current_chat)
            added = True
            answer = self.get_text_after_keyword_from_str(res, "DATATOPLOT")

        if "PAPER_COMPLETED" in res:
            answer = extract_tag_content(res, "final_answer")
            added = True
            print(f"[PAPER_COMPLETED] Extracted final answer: {answer[:200]}...", file=sys.stderr, flush=True)

        if "DATA_ANALYSIS_TO_PLOT" in res:
            params = ["data_path", "title", "x_axis_column", "y_axis_column", "color_column"]
            params_dict = self.get_params2(res, params=params)
            xaxis = params_dict.get("x_axis_column", "")
            column = params_dict.get("y_axis_column", "")
            color = params_dict.get("color_column", "")
            plot_name = Path(params_dict.get("data_path", "")).name
            title = params_dict.get("title", "")
            nickname = chat + "_" + "plot"

            dataplot_obj = DataPlot(
                id=self.new_dataplots_id(chat),
                plot_name=plot_name,
                column=column,
                xaxis=xaxis,
                color=color,
                title=title,
                nickname=nickname
            )
            answer = extract_tag_content(res, "final_answer")
            self.add_plot_to_list(dataplot_obj, chat)
            self.add_to_combined_content("plot", dataplot_obj, chat)
            added = True

        if "DATA_ANALYSIS_TO_TABLE" in res:
            params = ["data_path", "title", "columns_list"]
            params_dict = self.get_params2(res, params=params)
            nickname = self.current_chat + "_" + "table"
            title = params_dict.get("title", "")
            data_table = Path(params_dict.get("data_path", "")).name

            datatable_obj = DataTable(
                id=self.new_datatables_id(),
                table_name=data_table,
                title=title,
                nickname=nickname
            )
            answer = extract_tag_content(res, "final_answer")
            self.add_table_to_list(datatable_obj)
            self.add_to_combined_content("table", datatable_obj, chat)
            added = True

        # Handle PORTFOLIOTOPLOT (from equity_analyst compute_returns)
        if "PORTFOLIOTOPLOT" in res:
            data_toplot, column = self.get_params(res, first_param='PORTFOLIOTOPLOT')
            xaxis = 'date'
            color = 'portfolio'
            nickname = chat + "_" + "plot"
            title = 'Portfolio'
            print(f"[process_agent_result] PORTFOLIOTOPLOT: {data_toplot}, column: {column}")

            dataplot_obj = DataPlot(
                id=self.new_dataplots_id(chat),
                plot_name=data_toplot,
                column=column,
                xaxis=xaxis,
                color=color,
                title=title,
                nickname=nickname
            )
            nickname = self.add_plot_to_list(dataplot_obj, chat)
            self.add_to_combined_content("plot", dataplot_obj, chat)

            # Also create Portfolio object
            portfolio_obj = Portfolio(
                id=self.new_portfolio_id(),
                portfolio_name=chat,
                nickname=chat,
            )
            self.add_portfolio_to_list(portfolio_obj)

            answer = "portfolio generated:"
            added = True

        # Handle portfolio results (legacy)
        if not added:
            if "csv" in res:
                if "TYPE:FI" not in res:
                    answer = "generated portfolio:"
                    answer_plot, _ = self.add_portfolio_plot(res, chat)
                    answer += answer_plot
                if "TYPE:FI" in res:
                    answer_plot, _ = self.add_portfolio_plot(res, chat)
                    answer += answer_plot
                    answer = replace_expection(answer)

        return answer, added

    def add_table_to_list(self, datatable_obj, chat=None):
    
        self.chats_name_tables[self.current_chat].append(datatable_obj)
        # add plot in db
        with rx.session() as session:
            # Get the chat instance for the chat title and the user
            this_chat = session.exec(
                select(Chats).where(
                    Chats.chat_title == self.current_chat,
                    Chats.user_id == self.user.id
                )
            ).first()
            #this is the object stored in the db
            datatables = DataTables(
                                  id=datatable_obj.id,
                                  table_name=datatable_obj.table_name,
                                  title=datatable_obj.title,
                                  nickname=datatable_obj.nickname,
                                  user_id=self.user.id,
                                  chat_id=this_chat.id,
                                  created_at=datatable_obj.created_at
                                  )

            session.add(datatables)
            session.commit()
            session.refresh(datatables)
            # here i modify nickname to add id of the plot as well to have unique nicknames
            datatable = session.exec(
                select(DataTables).where(
                    (DataTables.id == datatable_obj.id)
                    &
                    (DataTables.user_id == self.user.id)
                    &
                    (DataTables.chat_id == this_chat.id)
                )
            ).first()
            if datatable:
                updated_nickname = datatable.nickname+"_"+str(datatable_obj.id)
                datatable.nickname = updated_nickname
                datatable_obj.nickname = updated_nickname
                session.commit()

            #self.chats_name_tables[self.current_chat].append(datatable_obj)
            #self.add_to_combined_content("table", datatable_obj, self.current_chat)
            return datatables.nickname

    def add_plot_to_list(self, dataplot_obj, current_chat=None):
        # Check if the chat is already initialized
        if not current_chat:
            current_chat = self.current_chat
        if not hasattr(self, 'chats_name_plots'):
            self.chats_name_plots = DEFAULT_CHATS

        if current_chat not in self.chats_name_plots:
            self.chats_name_plots[current_chat] = []

        # Add plot in db
        with rx.session() as session:
            # Get the chat instance for the current chat title and user
            this_chat = session.exec(
                select(Chats).where(
                    Chats.chat_title == current_chat,
                    Chats.user_id == self.user.id
                )
            ).first()

            # Add the plot to the database
            dataplots = DataPlots(
                id=dataplot_obj.id,  # Use the id already set in dataplot_obj
                plot_name=dataplot_obj.plot_name,
                column=dataplot_obj.column,
                xaxis=dataplot_obj.xaxis,
                color=dataplot_obj.color,
                title=dataplot_obj.title,
                nickname=dataplot_obj.nickname,
                user_id=self.user.id,
                chat_id=this_chat.id,
                created_at=dataplot_obj.created_at
            )

            session.add(dataplots)
            session.commit()
            session.refresh(dataplots)

            # Update the nickname in both the database and the passed object
            if dataplots:
                updated_nickname = f"{dataplots.nickname}_{dataplots.id}"
                dataplots.nickname = updated_nickname
                dataplot_obj.nickname = updated_nickname  # Ensure consistency
                session.commit()

            # Add to the current list
            self.chats_name_plots[current_chat].append(dataplot_obj)
            
            #self.add_to_combined_content("plot", dataplot_obj, self.current_chat)
            return dataplots.nickname

    def add_portfolio_to_list(self, portfolio_obj):
        import logging
        print(f"[add_portfolio_to_list] Called with portfolio_obj: {portfolio_obj}")
        # First, check if we need to initialize the portfolios list for this chat
        if not hasattr(self, 'chats_name_portfolios'):
            print("[add_portfolio_to_list] chats_name_portfolios not found, initializing.")
            self.chats_name_portfolios = DEFAULT_CHATS
        
        if self.current_chat not in self.chats_name_portfolios:
            print(f"[add_portfolio_to_list] Initializing portfolios list for chat {self.current_chat}")
            self.chats_name_portfolios[self.current_chat] = []
            
        # add portfolio in db
        with rx.session() as session:
            # Get the chat instance for the chat title and the user
            this_chat = session.exec(
                select(Chats).where(
                    Chats.chat_title == self.current_chat,
                    Chats.user_id == self.user.id
                )
            ).first()
            print(f"[add_portfolio_to_list] Found chat: {this_chat}")
            if not this_chat:
                logging.error(f"[add_portfolio_to_list] No chat found for title={self.current_chat}, user_id={self.user.id}")
                return None
            #this is the object stored in the db
            portfolios = Portfolios(
                id=portfolio_obj.id,
                portfolio_name=portfolio_obj.portfolio_name,
                nickname=portfolio_obj.nickname,
                user_id=self.user.id,
                chat_id=this_chat.id,
                created_at=portfolio_obj.created_at
            )
            print(f"[add_portfolio_to_list] Creating Portfolios object: {portfolios}")
            try:
                session.add(portfolios)
                session.commit()
                session.refresh(portfolios)
                print(f"[add_portfolio_to_list] Portfolio added and refreshed: {portfolios}")
            except Exception as e:
                logging.error(f"[add_portfolio_to_list] Failed to add portfolio: {e}")
                session.rollback()
                return None
            # here i modify nickname to add id of the portfolio as well to have unique nicknames
            try:
                portfolio = session.exec(
                    select(Portfolios).where(
                        (Portfolios.id == portfolio_obj.id) &
                        (Portfolios.user_id == self.user.id) &
                        (Portfolios.chat_id == this_chat.id)
                    )
                ).first()
                print(f"[add_portfolio_to_list] Fetched portfolio after insert: {portfolio}")
                if portfolio:
                    portfolios.nickname += "_" + str(portfolio_obj.id)
                    portfolios.portfolio_name += "_" + str(portfolio_obj.id)
                    portfolio_obj.nickname = portfolios.nickname
                    portfolio_obj.portfolio_name = portfolios.portfolio_name
                    session.commit()
                    print(f"[add_portfolio_to_list] Updated nicknames: {portfolios.nickname}, {portfolios.portfolio_name}")
            except Exception as e:
                logging.error(f"[add_portfolio_to_list] Failed to update nickname: {e}")
                session.rollback()
            #add to current list
            self.chats_name_portfolios[self.current_chat].append(portfolio_obj)
            print(f"[add_portfolio_to_list] Appended portfolio_obj to chat list: {portfolio_obj}")
            return portfolios.nickname

    def search_last_tag(self):
        with rx.session() as session:
            # Get the chat instance for the chat title and the user
            this_qas = session.exec(
                select(QAs).join(Chats).where(
                    Chats.chat_title == self.current_chat,
                    Chats.user_id == self.user.id
                )
            ).all()
            alias = module_name = None
            pattern = r"@([\w]+)\.([\w]+)"
            for qas in this_qas:
                match = re.search(pattern, qas.question)
                if match:
                    alias = match.group(1)
                    module_name = match.group(2)
        return alias, module_name

    def new_portfolio_id(self, current_chat=None):
        """Get the next portfolio ID for the current chat and user."""
        if not current_chat:
            current_chat = self.current_chat
        with rx.session() as session:
            # Get the chat instance for the chat title and the user
            this_chat = session.exec(
                select(Chats).where(
                    Chats.chat_title == current_chat,
                    Chats.user_id == self.user.id
                )
            ).first()
            
            if not this_chat:
                return 1
                
            # Get the last portfolio ID for this chat
            last_portfolio = session.exec(
                select(Portfolios)
                .where(
                    Portfolios.chat_id == this_chat.id,
                    Portfolios.user_id == self.user.id
                )
                .order_by(Portfolios.id.desc())
            ).first()
            
            if last_portfolio:
                print("last portfolio id:", last_portfolio.id)
                return last_portfolio.id + 1
            else:
                return 1

    def new_dataplots_id(self, current_chat=None) -> int:
        """Get the next dataplot ID for the current user and chat."""
        if not current_chat:
            current_chat = self.current_chat
        with rx.session() as session:
            # Get the chat instance for the current chat title and user
            this_chat = session.exec(
                select(Chats).where(
                    Chats.chat_title == current_chat,
                    Chats.user_id == self.user.id
                )
            ).first()

            if not this_chat:
                return 1

            # Query the maximum ID for the given user_id and chat_id
            max_id = session.exec(
                select(DataPlots)
                .where(
                    DataPlots.chat_id == this_chat.id,
                    DataPlots.user_id == self.user.id
                )
                .order_by(DataPlots.id.desc())
            ).first()

            # Extract the `id` from the result and return the next ID
            return (max_id.id if max_id else 0) + 1

    def new_datatables_id(self, current_chat=None) -> int:
        """Get the next datatable ID for the current user and chat."""
        if not current_chat:
            current_chat = self.current_chat
        with rx.session() as session:
            # Get the chat instance for the current chat title and user
            this_chat = session.exec(
                select(Chats).where(
                    Chats.chat_title == current_chat,
                    Chats.user_id == self.user.id
                )
            ).first()

            if not this_chat:
                return 1

            # Query the maximum ID for the given user_id and chat_id
            max_id = session.exec(
                select(DataTables)
                .where(
                    DataTables.chat_id == this_chat.id,
                    DataTables.user_id == self.user.id
                )
                .order_by(DataTables.id.desc())
            ).first()

            # Extract the `id` from the result and return the next ID
            return (max_id.id if max_id else 0) + 1

    async def lc_bot_process_question(self):#, question: str):
        """Get the response from the API.

        Args:
            form_data: A dict with the current question.
        """
        question = self.question
        # Clear the input field.
        self.question = ""
        if not question:
            return
        question = question.replace("\n", "<br>")
        # Add the question to the list of questions.
        qa = QA(question=question, answer="", id=-1)
        self.chats_list[self.current_chat].append(qa)
        self.add_to_combined_content("message", qa, self.current_chat)
        
        with rx.session() as session:
            # Get the chat instance - first try chats owned by this user
            this_chat = session.exec(
                select(Chats).where(
                    Chats.chat_title == self.current_chat,
                    Chats.user_id == self.user.id
                )
            ).first()

            # If not found, this might be a shared chat - check by chat_id if available
            is_shared_chat = False
            if this_chat is None and hasattr(self, 'current_chat_id') and self.current_chat_id:
                # This is a shared chat - lookup by ID and verify permission
                this_chat = session.exec(
                    select(Chats).where(Chats.id == self.current_chat_id)
                ).first()
                if this_chat:
                    # Verify user has write permission via PostgreSQL RBAC
                    try:
                        with get_connection(read_only=True) as conn:
                            # Resource ID for chats uses format: "chat_{chat_id}"
                            resource_id = f"chat_{this_chat.id}"
                            has_write = check_permission(conn, self.user.username, resource_id, 'write')
                            if not has_write:
                                print(f"[SHARED CHAT] User {self.user.username} lacks write permission for chat {this_chat.id}")
                                this_chat = None  # Deny access
                            else:
                                is_shared_chat = True
                                print(f"[SHARED CHAT] User {self.user.username} has write permission for chat {this_chat.id}")
                    except Exception as e:
                        print(f"[SHARED CHAT] Permission check failed: {e}")
                        this_chat = None  # Fail closed - deny access on error

            if this_chat is None:
                # No valid chat found - user doesn't own it and doesn't have permission
                print(f"[ERROR] No valid chat found for '{self.current_chat}' (user: {self.user.username})")
                self.processing = False
                return

            qas = QAs(question=question,
                      answer='',
                      user_id=self.user.id,  # Author is always the current user
                      chat_id=this_chat.id
                      )

            session.add(qas)
            session.commit()
            session.refresh(qas)
            qa.id = qas.id
            # Clear the input and start the processing.
            self.processing = True
            yield
        yield State.set_plots_frontend()
        self.combined_content = self.combined_content
        self.chats_list = self.chats_list
        yield

        # Check if we're in "comment" mode - just save the message without sending to backend
        if self.message_routing == "comment":
            print(f"[lc_bot_process_question] Comment mode - message saved locally only")
            # Set an empty answer to indicate it's a comment
            qa.answer = ""
            self.chats_list[self.current_chat][-1] = qa
            with rx.session() as session:
                qas_record = session.exec(select(QAs).where(QAs.id == qa.id)).first()
                if qas_record:
                    qas_record.answer = ""
                    session.commit()
            self.processing = False
            yield
            return

        # if using FB_front_end

        # pattern = r"@([\w]+)\.([\w]+)"
        # match = re.search(pattern, question)
        # if match:
        #     alias = match.group(1)
        #     module_name = match.group(2)
        #     self.endpoint = f"@{alias}.{module_name}"
        # else:
        #     if "@" not in self.endpoint :
        #         alias, module_name = self.search_last_tag()
        #         if alias and module_name:
        #             self.endpoint = f"@{alias}.{module_name}"
        #answer_text = await bot.run_text(qa.question, self.user.username)
        last_portfolio_id = self.new_portfolio_id()
        last_dataplot_id = self.new_dataplots_id()
        last_datatable_id = self.new_datatables_id()
        # Ensure answer_text is not None before concatenation
        print(f"[lc_bot_process_question] Routing mode: {self.message_routing}, current_chat: {self.current_chat}")
        text = self.combined_content_totext().replace("<br>", "\n")
        #text=qa.question.replace("<br>", "\n")

        # If routing mode is "agent" and an agent container is selected, route the message to that agent
        if self.message_routing == "agent" and self.selected_container_id and self.current_session_id:
            import json as json_module
            import sys
            # Build the agent call command JSON
            # Use selected_container_id (instance_id) for container lookup, current_session_id for job tracking
            # Include user_dir and out_filename for equity_analyst to generate unique portfolio filenames
            # out_filename format: {current_chat}_{portfolio_id}_{timestamp} ensures unique filenames per chat+portfolio
            # 3-digit timestamp suffix handles rapid consecutive agent calls before DB is updated
            import time
            timestamp_suffix = int(time.time() * 1000) % 1000  # 3 digits from millisecond timestamp
            out_filename = f"{self.current_chat}_{last_portfolio_id}_{timestamp_suffix:03d}"
            agent_call_json = {
                "command_type": "call",
                "container_uuid": self.selected_container_id,  # CRITICAL: Use instance_id, not session_id
                "instructions": question.replace("<br>", "\n"),  # Use the raw question, not combined content
                "job_id": self.current_session_id,  # Use session_id from DB
                "user_dir": self.user.username,  # Pass user_dir for equity_analyst
                "out_filename": out_filename  # Unique filename suffix for portfolios/returns
            }
            text = f"@finbuddy.agents {json_module.dumps(agent_call_json)}"
            print(f"[lc_bot_process_question] Routing to selected agent: {self.selected_container_name} (session_id: {self.current_session_id})", file=sys.stderr, flush=True)
            print(f"[lc_bot_process_question] Current chat (will be chat_id in RabbitMQ): '{self.current_chat}'", file=sys.stderr, flush=True)

        print("sending to agent from state line 2216: "+text)
        answer_text = await bot.FB_super_agent( #FB_front_end
            text=text,
            #self.endpoint,
            user_dir=self.user.username,
            current_chat=f"{self.current_chat}",
            last_portfolio_id=f"{last_portfolio_id}",
            last_dataplot_id=f"{last_dataplot_id}",
            last_datatable_id=f"{last_datatable_id}",
            state={"jwt_token": self.jwt_token}
            )
        if answer_text is not None:
            if isinstance(answer_text, list):
                answer_text = ''.join([item[1] for item in answer_text])
            #this is specific to check jobs in queue
            print("RECEIVED TEXT:\n", answer_text)
            if "QUEUE:" in answer_text:
                job_id = answer_text.split("QUEUE:")[1]
                self.job_ids.append(job_id)
                self.job_ids_chats.append(self.current_chat)
                answer_text = answer_text.split("QUEUE")[0]
                yield State.start_progress2
            #these following two have to be merged together
            #DATATOPLOT is from etf
            #PORTFOLIOTOPLOT is from portfolio returns
            if "DATATABLE" in answer_text:
                data_table, name = self.get_params(answer_text, 'DATATABLE' ,'NAME')
                nickname = self.current_chat+"_"+"table"
                title=name

                datatable_obj = DataTable(
                    id=self.new_datatables_id(),
                    table_name=data_table,
                    title=title,
                    nickname=nickname
                )
                nickname = self.add_table_to_list(datatable_obj)
                self.add_to_combined_content("table", datatable_obj, self.current_chat)
                #answer_text = process_table(answer_text)
                yield State.set_plots_frontend()
            if "DATATOPLOT" in answer_text:
                data_toplot, column = self.get_params(answer_text)
                xaxis = 'date'
                color = 'etf'
                nickname = self.current_chat + "_" + "plot"
                title = 'ETF Cumulative Performance (%)'
                print("added data plot with params: plotname", data_toplot, ",xaxis:", xaxis, ",column:", column, ",color:", color, ",title:", title)

                dataplot_obj = DataPlot(
                    id=self.new_dataplots_id(),
                    plot_name=data_toplot,
                    column=column,
                    xaxis=xaxis,
                    color=color,
                    title=title,
                    nickname=nickname
                )
                nickname = self.add_plot_to_list(dataplot_obj)
                self.add_to_combined_content("plot", dataplot_obj, self.current_chat)
                yield State.set_plots_frontend()
            #this is from data analysis
            if "DATA_ANALYSIS_TO_PLOT" in answer_text:
                params = ["data_path", "title", "x_axis_column", "y_axis_column", "color_column"]
                params_dict = self.get_params2(answer_text, params=params)
                xaxis = params_dict["x_axis_column"]
                column = params_dict["y_axis_column"]
                color = params_dict.get("color_column","")
                plot_name = Path(params_dict["data_path"]).name
                title = params_dict["title"]
                nickname = self.current_chat + "_" + "plot"
                print("added data plot with params: plotname", plot_name, "xaxis:", xaxis, "column:", column, "color:", color, "title:", title)
                dataplot_obj = DataPlot(
                    id=self.new_dataplots_id(),
                    plot_name=plot_name,
                    column=column,
                    xaxis=xaxis,
                    color=color,
                    title=title,
                    nickname=nickname
                )
                answer_text = extract_tag_content(answer_text, "final_answer")
                nickname = self.add_plot_to_list(dataplot_obj)
                print("-----------ADDED TO LIST PLOT -----------")
                self.add_to_combined_content("plot", dataplot_obj, self.current_chat)
                print("-----------LIST COMBINED: -----------")
                for content in self.combined_name[self.current_chat]:
                    print(content[0], content[2])
                yield State.set_plots_frontend()
            #this is from data analysis
            if "DATA_ANALYSIS_TO_TABLE" in answer_text:
                params=["data_path", "title","columns_list"]
                params_dict = self.get_params2(answer_text, params=params)
                nickname = self.current_chat+"_"+"table"
                title = params_dict["title"]
                data_table = Path(params_dict["data_path"]).name

                datatable_obj = DataTable(
                    id=self.new_datatables_id(),
                    table_name=data_table,
                    title=title,
                    nickname=nickname
                )
                answer_text = extract_tag_content(answer_text, "final_answer")
                nickname = self.add_table_to_list(datatable_obj)
                #self.add_to_combined_content("table", datatable_obj, self.current_chat)
                yield State.set_plots_frontend()
            #this is from portfolio 
            if "PORTFOLIOTOPLOT" in answer_text:
                #need to add both the plot and portfolios to lists
                #answer_text, dataplot_obj = self.add_portfolio_plot(answer_text)
                data_toplot, column = self.get_params(answer_text, first_param='PORTFOLIOTOPLOT')
                xaxis = 'date'
                color = 'portfolio'
                nickname = self.current_chat + "_" + "plot"
                title = 'Portfolio '#'Cumulative Performance (%)'
                print("added data plot with params: plotname", data_toplot, ",xaxis:", xaxis, ",column:", column, ",color:", color, ",title:", title)

                dataplot_obj = DataPlot(
                    id=self.new_dataplots_id(),
                    plot_name=data_toplot,
                    column=column,
                    xaxis=xaxis,
                    color=color,
                    title=title,
                    nickname=nickname
                )
                print("before add combinedcontent")
                nickname = self.add_plot_to_list(dataplot_obj)
                print("after adding plot to list")
                self.add_to_combined_content("plot", dataplot_obj, self.current_chat)
                print("time to add portfolio now")
                nickname = self.current_chat
                portfolio_obj = Portfolio(
                    id=self.new_portfolio_id(),
                    portfolio_name=nickname,
                    nickname=nickname,
                )
                print(f"[lc_bot_process_question] Calling add_portfolio_to_list with portfolio_obj: {portfolio_obj}")
                nickname = self.add_portfolio_to_list(portfolio_obj)
                print(f"[lc_bot_process_question] add_portfolio_to_list returned nickname: {nickname}")
                answer_text = "portfolio generated:"
                yield State.set_plots_frontend()
            #answer_text = answer_text.replace("\n", "<br>")
            #if there are table i need not to change \n into <br> by now there is only one case of INFOTABLE possible
            answer_text = replace_expection(answer_text)
            self.chats_list[self.current_chat][-1].answer += answer_text
            #TODO find last chat in combined_name and add answer_text
            
            # Print the matched names
            with rx.session() as session:
                id = self.chats_list[self.current_chat][-1].id
                if id>0:
                    #update answer
                    this_qa = session.exec(select(QAs).where(QAs.id == id)).first()
                    this_qa.answer = answer_text
                    #update plot if any

                    session.commit()

        else:
            # Handle the case where answer_text is None, perhaps log it or assign a default value
            # For example, assigning an empty string if answer_text is None
            answer_text = "sorry some bad incovenience happenning right now...try again"
            self.chats_list[self.current_chat][-1].answer += answer_text
            #TODO find last chat in combined_name and add answer_text     
        self.combined_content = self.combined_content
        self.chats_list = self.chats_list
        yield

    # async def openai_process_question(self, question: str):
    #     """Get the response from the API.

    #     Args:
    #         form_data: A dict with the current question.
    #     """

    #     # Add the question to the list of questions.
    #     qa = QA(question=question, answer="")
    #     self.chats_list[self.current_chat].append(qa)
        
    #     # Add to combined content
    #     self.add_to_combined_content("message", qa)

    #     # Clear the input and start the processing.
    #     self.processing = True
    #     yield

    #     # Build the messages.
    #     messages = [
    #         {
    #             "role": "system",
    #             "content": "You are a friendly chatbot named Reflex. Respond in markdown.",
    #         }
    #     ]
    #     for qa in self.chats_list[self.current_chat]:
    #         messages.append({"role": "user", "content": qa.question})
    #         messages.append({"role": "assistant", "content": qa.answer})

    #     # Remove the last mock answer.
    #     messages = messages[:-1]

    #     # Start a new session to answer the question.
    #     session = OpenAI().chat.completions.create(
    #         model=os.getenv("OPENAI_MODEL", "gpt-3.5-turbo-1106"),
    #         messages=messages,
    #         stream=True,
    #     )

    #     # Stream the results, yielding after every word.
    #     for item in session:
    #         if hasattr(item.choices[0].delta, "content"):
    #             answer_text = item.choices[0].delta.content
    #             # Ensure answer_text is not None before concatenation
    #             if answer_text is not None:
    #                 self.chats_list[self.current_chat][-1].answer += answer_text
    #             else:
    #                 # Handle the case where answer_text is None, perhaps log it or assign a default value
    #                 # For example, assigning an empty string if answer_text is None
    #                 answer_text = ""
    #                 self.chats_list[self.current_chat][-1].answer += answer_text
    #             self.chats_list = self.chats_list
    #             yield


    async def process_question(self, form_data: dict[str, str]):
        # Get the question from the form
        question = form_data["question"]
        self.question=""
        # Check if the question is empty
        if question is None or question == "":
            return
        if self.user is None:
            return
        self.question=question
        model = State.lc_bot_process_question


        yield model
        #async for value in model(question):
        #    yield value


    # def get_params(self, answer_text, first_param='DATATOPLOT', second_param='COLUMN'):
    #     datatoplot_pattern = re.compile(rf'{first_param}:\s*([A-Za-z0-9_\.]+)')
    #     column_pattern = re.compile(rf'{second_param}:\s*([A-Za-z0-9_]+)')
    #     # Find the first match
    #     # get column name
    #     column_match = column_pattern.search(answer_text)
    #     column = column_match.group(1)
    #     # get plot_name
    #     data_match = datatoplot_pattern.search(answer_text)
    #     data_toplot = data_match.group(1)
    #     #normalise name this is return df
    #     #data_toplot = "_".join(data_toplot.split("_")[:2])+"_return.csv"
    #     return data_toplot, column
    
    # def get_params2(self, answer_text="", params=["DATA_PATH", "TITLE", "X_AXIS_COLUMN", "Y_AXIS_COLUMN", "COLOR_COLUMN"]):
    #     params_dict = {}
    #     for param in params:
    #         pattern = re.compile(rf'"{param}"\s*:\s*"([^"]*)"')
    #         match = pattern.search(answer_text)
    #         if match:
    #             params_dict[param] = match.group(1)
    #     return params_dict

    def combined_content_totext(self, chat_name=None):
        if chat_name is None:
            chat_name = self.current_chat
        message = "this is an history of chat messages between users and you (finbuddy), includes messages, tables or plots generated. Previous messages are the history (if any). The last text from user at the end is the last request from the user and the one you need to answer. PRevious message are for reference if needed"
        if chat_name not in self.combined_name:
            return message
        for content_type, content, _ in self.combined_name[chat_name]:
            if content_type == "message":
                message += "User: " + content.question + "\n" + "finbuddy:"+content.answer + "\n"
            elif content_type == "table":
                message += "Table: title:" + content.title + "\n"
            elif content_type == "plot":
                message += "Plot: title:" + content.title + "\n"
            message += "-----------\n"
        return message

    def add_to_combined_content(self, content_type: str, content: Any, chat_name: str = None):
        """Add content to the combined list with a timestamp.
        
        Args:
            content_type: The type of content ("message", "table", or "plot")
            content: The actual content object
            chat_name: The chat to add the content to (defaults to current_chat)
        """
        if chat_name is None:
            chat_name = self.current_chat
            
        if chat_name not in self.combined_name:
            self.combined_name[chat_name] = []
            
        # Add the content with current timestamp
        self.combined_name[chat_name].append((content_type, content, time.time()))
        # Update the state to trigger a refresh
        #self.combined_content = self.combined_content
        
        # # When adding a message, also make sure it's in the chats_list for compatibility
        # if content_type == "message" and isinstance(content, QA):
        #     if chat_name not in self.chats_list:
        #         self.chats_list[chat_name] = []
        #     if content not in self.chats_list[chat_name]:
        #         self.chats_list[chat_name].append(content)
        #         self.chats_list = self.chats_list  # Trigger reactivity

        # # When adding a table, also make sure it's in the chats_data_tables for compatibility
        # elif content_type == "table":
        #     if chat_name not in self.chats_data_tables:
        #         self.chats_data_tables[chat_name] = []
        #     self.chats_data_tables[chat_name].append(content)
        #     self.chats_data_tables = self.chats_data_tables  # Trigger reactivity
            
        # # When adding a plot, also make sure it's in the chats_data_plots for compatibility
        # elif content_type == "plot":
        #     if chat_name not in self.chats_data_plots:
        #         self.chats_data_plots[chat_name] = []
        #     self.chats_data_plots[chat_name].append(content)
        #     self.chats_data_plots = self.chats_data_plots  # Trigger reactivity

    def add_portfolio_plot(self, answer_text, current_chat=None):
        """this is used in the job timer start_progress 
        to add portfolio plot and portfolio
        """
        if not current_chat:
            current_chat = self.current_chat

        data_toplot, column = self.get_params(answer_text, first_param='PORTFOLIOTOPLOT')
        xaxis = 'date'
        color = 'portfolio'
        nickname = current_chat + "_" + "plot"
        title = 'Portfolio '#'Cumulative Performance (%)'
        print("added data plot with params: plotname", data_toplot, ",xaxis:", xaxis, ",column:", column, ",color:", color, ",title:", title)

        dataplot_obj = DataPlot(
            id=self.new_dataplots_id(current_chat),
            plot_name=data_toplot,
            column=column,
            xaxis=xaxis,
            color=color,
            title=title,
            nickname=nickname
        )
        print("before add combinedcontent")
        nickname = self.add_plot_to_list(dataplot_obj, current_chat)
        print("after adding plot to list")
        self.add_to_combined_content("plot", dataplot_obj, current_chat)
        print("time to add portfolio now")
        nickname = self.current_chat
        portfolio_obj = Portfolio(
            id=self.new_portfolio_id(),
            portfolio_name=nickname,
            nickname=nickname,
        )
        print(f"[lc_bot_process_question] Calling add_portfolio_to_list with portfolio_obj: {portfolio_obj}")
        nickname = self.add_portfolio_to_list(portfolio_obj)
        print(f"[lc_bot_process_question] add_portfolio_to_list returned nickname: {nickname}")

        

        #add couponds plot
        if "FI" in answer_text:
            title = 'coupon chart '
            column = "cum_return_interest"
            dataplot_obj = DataPlot(
                id=self.new_dataplots_id(current_chat),
                plot_name=data_toplot+ " "+title,
                column=column,
                xaxis=xaxis,
                color=color,
                title=title,
                nickname=nickname
            )
            nickname = self.add_plot_to_list(dataplot_obj, current_chat)
            self.add_to_combined_content("plot", dataplot_obj, current_chat)
        portfolio_name = "portfolio_"+"_".join(data_toplot.split(".")[0].split("_")[1:])
        if "FI" not in answer_text:
            answer_text = ""#f"<br> you can start monitoring portfolio live with:<br> @finbuddy.live put live portfolio: {portfolio_name}"
            rx.set_value("question",
                         f"@finbuddy.live put live portfolio: {portfolio_name} ")
        else:
            answer_text ="<br> Generated new portfolio"
        return  answer_text, dataplot_obj


    @rx.event
    async def load_default_stats_data(self):
        """Load default stats data on page load, ensuring hydration and portfolio availability."""
        print("load_default_stats_data: Event triggered.")
        
        if not self.is_hydrated or not self.user:
            print(f"load_default_stats_data: Aborting. Hydrated: {self.is_hydrated}, User available: {self.user is not None}")
            return

        if not hasattr(self, 'portfolios') or not self.portfolios:
            print("load_default_stats_data: Portfolios not found, attempting to load them now.")
            await self.set_portfolios()

        if not hasattr(self, 'portfolios') or not self.portfolios:
            print("load_default_stats_data: Failed to load any portfolios for the user.")
            return

        portfolio_to_load = self.current_portfolio_name
        
        if not portfolio_to_load:
            first_portfolio = self.portfolios[0]
            first_portfolio_name = first_portfolio['value'] if isinstance(first_portfolio, dict) else first_portfolio
            print(f"load_default_stats_data: No portfolio selected. Falling back to first available: {first_portfolio_name}")
            self.current_portfolio_name = first_portfolio_name
            portfolio_to_load = first_portfolio_name

        if portfolio_to_load:
            print(f"load_default_stats_data: Loading stats for portfolio: {portfolio_to_load}")
            yield await self.set_statsportfolio(portfolio_to_load)
        else:
            print("load_default_stats_data: Could not determine a portfolio to load.")

    # Agent Diagram Builder State
    agent_boxes: List[Dict[str, Any]] = []
    tool_boxes: List[Dict[str, Any]] = []
    datasource_boxes: List[Dict[str, Any]] = []
    connections: List[Dict[str, Any]] = []
    generated_diagram_json: str = ""
    agent_container_uuid: str = ""  # Store the UUID of the created agent container
    agent_call_instructions: str = ""  # Instructions for calling the agent
    agent_call_result: str = ""  # Result from calling the agent
    
    def ensure_chart_session_id(self):
        """Ensure agent_container_uuid is set for chart session. Called when chart page loads."""
        import uuid as uuid_mod
        if not self.agent_container_uuid:
            self.agent_container_uuid = str(uuid_mod.uuid4())
            print(f"[ensure_chart_session_id] Generated new session ID: {self.agent_container_uuid}", file=sys.stderr, flush=True)
        else:
            print(f"[ensure_chart_session_id] Using existing session ID: {self.agent_container_uuid}", file=sys.stderr, flush=True)
    _pending_agent_result: str = ""  # Pending result from RabbitMQ (set by background task)
    _pending_chat_updates: List[Dict[str, Any]] = []  # Pending chat updates from RabbitMQ consumer
    test_run_instructions: str = ""  # Instructions for test run without container
    test_run_result: str = ""  # Result from test run

    # Dynamic agents and tools from database
    db_agents: List[Dict[str, Any]] = []  # List of agents from DB
    db_tools: List[Dict[str, Any]] = []  # List of tools from DB
    db_agents_loaded: bool = False  # Flag to track if agents have been loaded
    db_datasources: List[Dict[str, Any]] = []  # List of datasources from registry
    db_datasources_loaded: bool = False  # Flag to track if datasources have been loaded

    # Data Onboarding state variables (defaults for equity_db testing)
    onboarding_dataset_name: str = "equity_db"
    onboarding_description: str = "Equity database with stock data"
    onboarding_data_type: str = "database"  # database, csv, parquet, api
    onboarding_db_type: str = "DuckDB"  # DuckDB, PostgreSQL, MySQL, SQLite
    onboarding_access_mode: str = "File"  # File, TCP/IP, HTTP
    onboarding_path: str = "/home/riccardo247/sp500/equities/gold/equity.duckdb"
    onboarding_host: str = ""
    onboarding_port: str = ""
    onboarding_username: str = ""
    onboarding_password: str = ""
    onboarding_api_endpoint: str = ""
    onboarding_api_key: str = ""
    onboarding_auth_type: str = ""
    onboarding_file_type: str = ""  # CSV, Parquet, JSON
    onboarding_status: str = "idle"  # idle, processing, success, error
    onboarding_message: str = ""
    # S3 storage options
    onboarding_storage_location: str = "disk"  # disk, s3
    onboarding_s3_bucket: str = ""
    onboarding_s3_region: str = "us-east-1"
    onboarding_s3_path: str = ""  # Path within the bucket
    onboarding_s3_upload: bool = True  # Whether to upload local file to S3 (if False, just register the S3 path without uploading)

    # Text Indexing state variables
    text_index_dataset_name: str = ""
    text_index_source_dir: str = ""
    text_index_description: str = ""
    text_index_chunk_size: str = "500"
    text_index_chunk_overlap: str = "50"
    text_index_recursive: bool = True
    text_index_status: str = "idle"  # idle, processing, success, error
    text_index_message: str = ""

    # Page Builder state variables
    page_builder_name: str = ""
    page_builder_description: str = ""
    page_builder_chat_input: str = ""
    page_builder_json: str = '{"modules": []}'
    page_builder_save_status: str = ""  # "success", "error", or ""
    page_builder_save_message: str = ""
    page_builder_live_view: bool = False  # Toggle between canvas and live preview
    gui_modules: List[Dict[str, Any]] = []  # All GUI modules from DB
    gui_modules_loaded: bool = False
    saved_page_layouts: List[Dict[str, Any]] = []  # List of saved page layouts

    # Notifications page state - data query triggers and notifications
    data_triggers: List[Dict[str, Any]] = []  # List of user's data query triggers
    data_triggers_loaded: bool = False
    selected_trigger_id: str = ""  # Currently selected trigger's query_id
    trigger_notifications: List[Dict[str, Any]] = []  # Notifications for selected trigger

    # News feed state - top bar unread notifications display
    unread_notifications: List[Dict[str, Any]] = []  # Recent unread notifications for news feed
    news_feed_dropdown_open: bool = False  # Whether the news feed dropdown is open

    # Agents Management page state - 5 column layout
    mgmt_agents_list: List[Dict[str, Any]] = []  # All agents with permissions
    mgmt_selected_agent_id: str = ""  # Selected agent ID
    mgmt_selected_agent_name: str = ""  # Selected agent display name
    mgmt_containers_list: List[Dict[str, Any]] = []  # Containers for selected agent
    mgmt_selected_container_id: str = ""  # Selected container ID
    mgmt_sessions_list: List[Dict[str, Any]] = []  # Sessions for selected container
    mgmt_selected_session_id: str = ""  # Selected session ID
    mgmt_triggers_list: List[Dict[str, Any]] = []  # Triggers for selected session
    mgmt_portfolios_list: List[Dict[str, Any]] = []  # Portfolios linked to selected session

    # MCP Discovery Search page state
    mcp_search_query: str = ""  # Semantic search query
    mcp_search_type_filter: str = ""  # Filter by type: 'agent', 'mcp_server', or '' for all
    mcp_search_category_filter: str = ""  # Filter by category
    mcp_search_results: List[Dict[str, Any]] = []  # Search results
    mcp_search_loading: bool = False  # Loading state
    mcp_selected_result_id: str = ""  # Currently selected result for details view

    # Main page view toggle (chat vs custom page)
    show_page_view: bool = False  # Toggle between chat view and page view on main page
    # Active page JSON - empty by default, loaded from agent's linked GUI page when selected
    active_page_json: str = '{"modules": []}'

    # Dynamic Page State - for agent-driven interface rendering
    dynamic_page_json: str = '{"modules": []}'  # Current layout JSON from agent
    dynamic_page_session_id: str = ""  # Session ID for WebSocket routing
    dynamic_page_connected: bool = False  # WebSocket connection status
    dynamic_page_inputs: Dict[str, Any] = {}  # User inputs keyed by module_id
    dynamic_page_outputs: Dict[str, str] = {}  # Output values keyed by module_id

    # Icon mapping for agents (fallback for agents without icon in config)
    _agent_icons: Dict[str, str] = {
        'Research Agent': '🔬',
        'Papers Agent': '🔬',
        'Web RifRaf': '🌐',
        'Web Summary': '🌐',
        'Equity Analyst': '📊',
        'FI Analyst': '💵',
        'Asset Allocation': '⚖️',
        'Portfolio Manager': '📈',
        'Super PM': '🏆',
        'Test DB Agent': '🧪',
    }

    @rx.var
    def sidebar_agents(self) -> List[Dict[str, str]]:
        """Return agents formatted for sidebar display with icons."""
        result = []
        for agent in self.db_agents:
            display_name = agent.get('display_name', 'Unknown')
            # Try to get icon from config_json first, then fallback mapping
            config = agent.get('config_json', {})
            icon = config.get('icon', self._agent_icons.get(display_name, '🤖'))
            result.append({
                'display_name': display_name,
                'icon': icon
            })
        return result

    @rx.var
    def sidebar_tools(self) -> List[Dict[str, str]]:
        """Return tools formatted for sidebar display."""
        result = []
        for tool in self.db_tools:
            name = tool.get('name', 'Unknown')
            display_name = tool.get('display_name', name)
            result.append({
                'name': name,
                'display_name': display_name
            })
        return result

    @rx.var
    def sidebar_datasources(self) -> List[Dict[str, str]]:
        """Return datasources formatted for sidebar display."""
        # Icon mapping for datasource types
        type_icons = {
            'db': '🗄️',
            'duckdb': '🦆',
            'mysql': '🐬',
            'postgres': '🐘',
            'csv': '📊',
            'parquet': '📦',
            'json': '📋',
            'text': '📄',
            'files': '📁',
        }
        result = []
        for ds in self.db_datasources:
            name = ds.get('dataset_name', 'Unknown')
            ds_type = ds.get('database_type') or ds.get('dataset_type', 'db')
            icon = type_icons.get(ds_type, '💾')
            tables = ds.get('tables_count', 0)
            rows = ds.get('total_rows', 0)
            result.append({
                'name': name,
                'display_name': name,
                'icon': icon,
                'type': ds_type,
                'tables': str(tables),
                'rows': str(rows),
            })
        return result

    @rx.var
    def gui_modules_input(self) -> List[Dict[str, Any]]:
        """Return GUI modules filtered by input category."""
        return [m for m in self.gui_modules if m.get('category') == 'input']

    @rx.var
    def gui_modules_control(self) -> List[Dict[str, Any]]:
        """Return GUI modules filtered by control category."""
        return [m for m in self.gui_modules if m.get('category') == 'control']

    @rx.var
    def gui_modules_display(self) -> List[Dict[str, Any]]:
        """Return GUI modules filtered by display category."""
        return [m for m in self.gui_modules if m.get('category') == 'display']

    # Computed properties for selected trigger
    @rx.var
    def selected_trigger_request(self) -> str:
        """Get the natural language request of the selected trigger."""
        for t in self.data_triggers:
            if t.get('query_id') == self.selected_trigger_id:
                return t.get('natural_language_request', '')
        return ''

    @rx.var
    def selected_trigger_datasets(self) -> str:
        """Get the dataset names of the selected trigger."""
        for t in self.data_triggers:
            if t.get('query_id') == self.selected_trigger_id:
                datasets = t.get('dataset_names', [])
                if isinstance(datasets, list):
                    return ', '.join(datasets)
                return str(datasets)
        return ''

    @rx.var
    def selected_trigger_run_count(self) -> int:
        """Get the run count of the selected trigger."""
        for t in self.data_triggers:
            if t.get('query_id') == self.selected_trigger_id:
                return t.get('run_count', 0)
        return 0

    # News feed computed properties
    @rx.var
    def unread_count(self) -> int:
        """Count of unread notifications for badge display."""
        return len(self.unread_notifications)

    @rx.var
    def has_unread_notifications(self) -> bool:
        """Whether there are any unread notifications."""
        return len(self.unread_notifications) > 0

    @rx.var
    def sidebar_gui_pages(self) -> List[Dict[str, str]]:
        """Return GUI pages formatted for sidebar display in agent builder."""
        result = []
        for page in self.saved_page_layouts:
            name = page.get('name', 'Unknown')
            description = page.get('description', '')
            is_published = page.get('is_published', False)
            result.append({
                'name': name,
                'display_name': name,
                'description': description[:50] + '...' if len(description) > 50 else description,
                'icon': '📱' if is_published else '📄',
                'is_published': 'true' if is_published else 'false',
            })
        return result

    # GC Container state
    gc_deploying: bool = False  # True when GC deployment is in progress
    gc_service_url: str = ""  # URL of the deployed GC Cloud Run service
    gc_container_type: str = ""  # "local" or "gc" to track which type of container is active

    # Running containers state (for navbar selector)
    running_containers: List[Dict[str, str]] = []  # List of running container instances (all values as strings for Reflex)
    has_running_containers: bool = False  # Whether there are any running containers (for UI conditional)
    selected_container_id: str = ""  # Currently selected container ID
    selected_container_name: str = ""  # Display name of selected container
    container_linked: bool = False  # Whether container is linked/connected (deprecated, use message_routing)
    # Message routing mode: "finbuddy" (left), "comment" (center), "agent" (right)
    message_routing: str = "finbuddy"  # Default to sending messages to Finbuddy backend
    current_session_id: str = ""  # Current session_id for agent-chat-user combination (displayed in navbar)
    available_sessions: List[Dict[str, Any]] = []  # List of all sessions for current agent-chat-user (newest first)
    # Per-chat settings storage - remembers agent selection, GUI state per chat
    chat_settings: Dict[str, Dict[str, Any]] = {}
    _raw_diagram_json: str = ""  # Store the actual JSON separately from display text
    # Dynamic agent parameters (stored as JSON string)
    agent_parameters_json: str = "{}"  # JSON string of parameter name -> value mapping
    current_agent_params_schema: str = "[]"  # JSON array of parameter definitions from PROMPT_PARAMETERS
    agent_params_list: List[Dict[str, str]] = []  # List of {name, value, description} for UI rendering
    
    def update_agent_parameter(self, param_name: str, value: str):
        """Update a specific agent parameter value."""
        import json
        import sys
        try:
            params = json.loads(self.agent_parameters_json) if self.agent_parameters_json else {}
            params[param_name] = value
            self.agent_parameters_json = json.dumps(params)
            
            # Also update the list for UI
            for param in self.agent_params_list:
                if param['name'] == param_name:
                    param['value'] = value
                    break
            
            print(f"[update_agent_parameter] Updated {param_name} = {value}", file=sys.stderr, flush=True)
            print(f"[update_agent_parameter] Current params: {self.agent_parameters_json}", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"Error updating parameter {param_name}: {e}", file=sys.stderr, flush=True)
    
    def load_agent_parameters_schema(self, agent_module: str):
        """Load PROMPT_PARAMETERS from agent module and set default values."""
        import json
        import importlib
        import sys
        
        try:
            # Map agent names to modules
            module_path = f"db_light.agents.mcp_server_data_exploration.src.mcp_server_ds.{agent_module}"
            print(f"Loading parameters from: {module_path}", file=sys.stderr, flush=True)
            
            agent_mod = importlib.import_module(module_path)
            
            if hasattr(agent_mod, 'PROMPT_PARAMETERS'):
                params_schema = agent_mod.PROMPT_PARAMETERS
                self.current_agent_params_schema = json.dumps(params_schema)
                
                # Initialize default values for each parameter
                # AUTO-GENERATED PARAMETERS that should NOT be in UI or agent_parameters_json:
                # - user_id, session_id: come from function parameters
                # - job_id, output_directory: auto-generated by run_agent_once_no_container
                auto_generated_params = ['user_id', 'session_id', 'job_id', 'output_directory']
                auto_generated_sources = ['user_id', 'session_id']

                default_values = {}
                for param in params_schema:
                    param_name = param.get('name')
                    param_source = param.get('source', '')

                    # Skip parameters that come from instructions
                    if param_source == 'instructions' or param_name in ['topic', 'instructions']:
                        continue  # Don't add to additional_params

                    # Skip auto-generated parameters
                    if param_source in auto_generated_sources or param_name in auto_generated_params:
                        continue

                    # Set sensible defaults for additional_params
                    if param_name == 'user_dir':
                        default_values[param_name] = 'demo5'
                    elif param_name == 'out_filename':
                        default_values[param_name] = 'test_output'
                    elif param_name == 'csv_path':
                        default_values[param_name] = ''
                    else:
                        default_values[param_name] = ''

                self.agent_parameters_json = json.dumps(default_values)

                # Build list for UI rendering (exclude 'topic', 'instructions', and auto-generated params)
                self.agent_params_list = [
                    {
                        'name': p['name'],
                        'value': default_values.get(p['name'], ''),
                        'description': p.get('description', '')
                    }
                    for p in params_schema
                    if p['name'] not in ['topic', 'instructions'] + auto_generated_params
                ]
                
                print(f"Loaded {len(params_schema)} parameters: {[p['name'] for p in params_schema]}", file=sys.stderr, flush=True)
                print(f"UI params list: {self.agent_params_list}", file=sys.stderr, flush=True)
            else:
                print(f"No PROMPT_PARAMETERS found in {module_path}", file=sys.stderr, flush=True)
                self.current_agent_params_schema = "[]"
                self.agent_parameters_json = "{}"
                self.agent_params_list = []
        except Exception as e:
            print(f"Error loading agent parameters: {e}", file=sys.stderr, flush=True)
            self.current_agent_params_schema = "[]"
            self.agent_parameters_json = "{}"
            self.agent_params_list = []
    
    def populate_test_instructions(self, agent_name: str):
        """Populate test instructions based on agent type.
        First tries to load from database, falls back to static mapping.
        """
        import sys
        import requests
        print(f"\n{'='*60}", file=sys.stderr, flush=True)
        print(f"[populate_test_instructions] CALLED with agent_name: {agent_name}", file=sys.stderr, flush=True)

        # Fallback static mappings
        instructions_map = {
            'Research Agent': "Analyze AAPL stock from 2023-01-01 to 2023-12-31 and create a comprehensive report with price trends and key metrics",
            'Web Summary': "Summarize this article: https://example.com/article",
            'Web RifRaf': "Summarize this article: https://example.com/article",
            'Equity Analyst': "Create a portfolio with SP500 stocks from 2020, exclude bottom 20% by ESG score, rebalance monthly",
            'FI Analyst': "backtest a USA bonds ladder maximum duration 10 years starting from 2015-06-12",
            'Asset Allocation': "Allocate 60/40 weights to Buddy and 11",
            'Portfolio Manager': "Backtest a 60% equity, 40% fixed income portfolio. For equity: Long only, filter on SP500, exclude 20% of tickers with bottom ESG score. For fixed income: Keep gov bonds maximum 10 years duration. Then allocate weights 60/40 to the 2 portfolios.",
            'Super PM': "Create a balanced portfolio with 60% equities (SP500, momentum strategy) and 40% bonds (10-year duration ladder)"
        }

        agent_module_map = {
            'Research Agent': 'papers.papers_agent',
            'Web Summary': 'web_rifraf.web_rifraf_agent',
            'Web RifRaf': 'web_rifraf.web_rifraf_agent',
            'Equity Analyst': 'equity_analyst.equity_agent',
            'FI Analyst': 'FI_analyst.FI_agent',
            'Asset Allocation': 'asset_allocation.asset_allocation_agent',
            'Portfolio Manager': 'portfolio_manager.portfolio_manager_agent',
            'Super PM': 'super_PM.super_PM_agent',
            'Chart Analyst': 'chart_agent.chart_agent'
        }

        agent_module = ''
        instruction_text = ''

        # Try to load from database API first
        try:
            response = requests.get(f"http://localhost:8008/api/agents/by-name/{agent_name}", timeout=5)
            if response.status_code == 200:
                data = response.json()
                agent_data = data.get('agent', {})
                config = agent_data.get('config_json', {})

                # Get agent module from DB
                agent_module = agent_data.get('agent_module', '')

                # Get instructions examples from config
                instructions_examples = config.get('instructions_examples', [])
                if instructions_examples and len(instructions_examples) > 0:
                    instruction_text = instructions_examples[0]
                    print(f"[populate_test_instructions] Loaded instructions from DB", file=sys.stderr, flush=True)

        except Exception as e:
            print(f"[populate_test_instructions] Could not load from DB: {e}", file=sys.stderr, flush=True)

        # Fall back to static mapping if not loaded from DB
        if not instruction_text:
            instruction_text = instructions_map.get(agent_name, "")
            print(f"[populate_test_instructions] Using static fallback instructions", file=sys.stderr, flush=True)

        if not agent_module:
            agent_module = agent_module_map.get(agent_name, '')
            print(f"[populate_test_instructions] Using static fallback module", file=sys.stderr, flush=True)

        print(f"[populate_test_instructions] Setting instructions to: {instruction_text[:50]}...", file=sys.stderr, flush=True)
        self.test_run_instructions = instruction_text

        # Also load the agent's parameters schema
        if agent_module:
            self.load_agent_parameters_schema(agent_module)

        print(f"[populate_test_instructions] State updated. Current value: {self.test_run_instructions[:50]}...", file=sys.stderr, flush=True)
        print(f"[populate_test_instructions] Parameters schema: {self.current_agent_params_schema}", file=sys.stderr, flush=True)
        print(f"[populate_test_instructions] Parameters values: {self.agent_parameters_json}", file=sys.stderr, flush=True)
        print(f"{'='*60}\n", file=sys.stderr, flush=True)
    
    def set_generated_diagram_json(self, value: str):
        """Custom setter with logging for diagram JSON."""
        import sys
        print(f"\n{'='*60}", file=sys.stderr, flush=True)
        print(f"[set_generated_diagram_json] CALLED!", file=sys.stderr, flush=True)
        print(f"[set_generated_diagram_json] Value type: {type(value)}", file=sys.stderr, flush=True)
        print(f"[set_generated_diagram_json] Value length: {len(value) if value else 0}", file=sys.stderr, flush=True)
        print(f"[set_generated_diagram_json] First 200 chars: {value[:200] if value else 'EMPTY'}", file=sys.stderr, flush=True)
        print(f"{'='*60}\n", file=sys.stderr, flush=True)
        self.generated_diagram_json = value
        print(f"[set_generated_diagram_json] State variable updated successfully", file=sys.stderr, flush=True)
    
    def load_json_from_storage(self, json_data: str):
        """
        Load JSON from localStorage and store it in state.
        Called by the Generate JSON button with the actual diagram JSON.
        """
        import sys
        print(f"[load_json_from_storage] Method called with data length: {len(json_data) if json_data else 0}", file=sys.stderr, flush=True)
        # Store the actual JSON data in both display and raw storage
        self.generated_diagram_json = json_data
        self._raw_diagram_json = json_data  # Keep a clean copy for GC deployment
        print(f"[load_json_from_storage] Stored JSON in state, length: {len(self.generated_diagram_json)}", file=sys.stderr, flush=True)
        print(f"[load_json_from_storage] JSON preview: {json_data[:200] if json_data else 'EMPTY'}", file=sys.stderr, flush=True)
    
    def clear_diagram_json(self):
        """Clear the diagram JSON from state for testing."""
        import sys
        print(f"[clear_diagram_json] Clearing JSON from state", file=sys.stderr, flush=True)
        self.generated_diagram_json = ""
        self._raw_diagram_json = ""  # Clear raw JSON too
        self.agent_container_uuid = ""
        self.agent_call_result = ""
        # Clear GC state as well
        self.gc_deploying = False
        self.gc_service_url = ""
        self.gc_container_type = ""
        print(f"[clear_diagram_json] State cleared", file=sys.stderr, flush=True)

    @rx.event
    def load_running_containers(self):
        """Load running containers for the current user from the database via API."""
        import sys
        import requests

        print(f"[load_running_containers] CALLED - starting (via API)...", file=sys.stderr, flush=True)
        try:
            # Use API endpoint to get instances (same pattern as load_agents_from_db)
            # Include JWT token for user-specific permissions
            headers = self._get_auth_headers()
            response = requests.get("http://localhost:8008/api/instances", headers=headers, timeout=5)
            print(f"[load_running_containers] API response status: {response.status_code}", file=sys.stderr, flush=True)

            if response.status_code == 200:
                data = response.json()
                instances = data.get("instances", [])
                print(f"[load_running_containers] Got {len(instances)} instances from API", file=sys.stderr, flush=True)

                # Format for UI display (API already enriches with agent names and gui_page)
                containers = []
                for inst in instances:
                    # Extract container_uuid from config_json (this is the session UUID used for agent calls)
                    config_json = inst.get('config_json', {})
                    container_uuid = config_json.get('container_uuid', '')
                    print(f"[load_running_containers] Instance {inst.get('id', '')}: config_json={config_json}, container_uuid={container_uuid}", file=sys.stderr, flush=True)
                    # Ensure all values are strings for Reflex frontend compatibility
                    containers.append({
                        'id': str(inst.get('id', '')),
                        'name': str(inst.get('name', 'Unknown Agent')),
                        'status': str(inst.get('status', 'unknown')),
                        'address': str(inst.get('address', '')),
                        'port': str(inst.get('port', 0)),
                        'instance_type': str(inst.get('instance_type', 'local')),
                        'container_id': str(inst.get('container_id', '')),
                        'container_uuid': str(container_uuid),  # The session UUID for agent calls
                        'gui_page': str(inst.get('gui_page', '')),  # Linked GUI page name
                    })

                print(f"[load_running_containers] Containers list with UUIDs: {containers}", file=sys.stderr, flush=True)
                self.running_containers = containers
                self.has_running_containers = len(containers) > 0
                print(f"[load_running_containers] Loaded {len(containers)} running containers, has_running_containers={self.has_running_containers}", file=sys.stderr, flush=True)
            else:
                print(f"[load_running_containers] API error: {response.status_code} - {response.text}", file=sys.stderr, flush=True)
                self.running_containers = []
                self.has_running_containers = False

        except requests.exceptions.RequestException as e:
            print(f"[load_running_containers] Request error: {e}", file=sys.stderr, flush=True)
            self.running_containers = []
            self.has_running_containers = False
        except Exception as e:
            print(f"[load_running_containers] Error: {e}", file=sys.stderr, flush=True)
            import traceback
            traceback.print_exc()
            self.running_containers = []
            self.has_running_containers = False

    @rx.event
    def select_container(self, container_id: str):
        """Select a container from the running containers list."""
        import sys
        print(f"[select_container] Selecting container: {container_id}", file=sys.stderr, flush=True)

        # Find the container in the list
        for container in self.running_containers:
            if container.get('id') == container_id:
                self.selected_container_id = container_id
                self.selected_container_name = container.get('name', 'Unknown')
                self.gc_container_type = container.get('instance_type', 'local')
                # For GC containers, address is the full HTTPS URL; for local, build http://host:port
                if self.gc_container_type == 'gc':
                    self.gc_service_url = container.get('address', '')
                elif container.get('address') and container.get('port'):
                    self.gc_service_url = f"http://{container['address']}:{container['port']}"
                # Auto-link when selecting a container and switch routing to agent
                self.container_linked = True
                self.message_routing = "agent"

                # CRITICAL: agent_container_uuid must be the instance_id for backend lookup
                # session_id is separate and used for job tracking
                # container_id is the instance_id from agent_instances table
                self.agent_container_uuid = container_id  # This is the instance_id
                
                # Get or create session_id from database for this agent-chat-user combination
                if self.current_chat and self.user:
                    session_id = self.get_or_create_session_id(
                        agent_name=self.selected_container_name,
                        chat_title=self.current_chat,
                        user_id=self.user.id
                    )
                    if session_id:
                        self.current_session_id = session_id
                        print(f"[select_container] Using session_id from DB: {session_id}", file=sys.stderr, flush=True)
                        print(f"[select_container] Using instance_id for container_uuid: {container_id}", file=sys.stderr, flush=True)
                    else:
                        # Fallback to using instance_id as session_id
                        self.current_session_id = container_id
                        print(f"[select_container] Using fallback - instance_id as session_id: {container_id}", file=sys.stderr, flush=True)
                    # Load all available sessions for this agent-chat-user
                    self.load_available_sessions()
                else:
                    # No chat/user context, use instance_id as session_id
                    self.current_session_id = container_id
                    self.available_sessions = []
                    print(f"[select_container] No chat/user context, using instance_id: {container_id}", file=sys.stderr, flush=True)

                # Load the agent's linked GUI page if available
                gui_page = container.get('gui_page', '')
                if gui_page:
                    try:
                        from db_light.duckdb_models.page_layouts_db import get_layout
                        layout = get_layout(gui_page)
                        if layout:
                            self.active_page_json = layout.layout_json
                            print(f"[select_container] Loaded GUI page '{gui_page}' for agent", file=sys.stderr, flush=True)
                        else:
                            # GUI page name exists but layout not found - show empty
                            self.active_page_json = '{"modules": []}'
                            print(f"[select_container] GUI page '{gui_page}' not found in database", file=sys.stderr, flush=True)
                    except Exception as e:
                        print(f"[select_container] Error loading GUI page: {e}", file=sys.stderr, flush=True)
                        self.active_page_json = '{"modules": []}'
                else:
                    # No GUI page linked to this agent - show empty view
                    self.active_page_json = '{"modules": []}'
                    print(f"[select_container] No GUI page linked to agent", file=sys.stderr, flush=True)

                print(f"[select_container] Selected: {self.selected_container_name} (session_id: {self.current_session_id}), linked: {self.container_linked}", file=sys.stderr, flush=True)
                return

        # Container not found - clear selection
        self.selected_container_id = ""
        self.selected_container_name = ""
        self.active_page_json = '{"modules": []}'
        print(f"[select_container] Container {container_id} not found", file=sys.stderr, flush=True)

    @rx.event
    def clear_container_selection(self):
        """Clear the current container selection."""
        self.selected_container_id = ""
        self.selected_container_name = ""
        self.container_linked = False
        self.current_session_id = ""

    def get_or_create_session_id(self, agent_name: str, chat_title: str, user_id: int) -> str:
        """Get existing session_id or create new one for agent-chat-user combination.
        Returns the most recent session ordered by updated_at."""
        import uuid as uuid_mod
        import sys
        
        with rx.session() as session:
            # Get the chat instance
            this_chat = session.exec(
                select(Chats).where(
                    Chats.chat_title == chat_title,
                    Chats.user_id == user_id
                )
            ).first()
            
            if not this_chat:
                print(f"[get_or_create_session_id] Chat '{chat_title}' not found for user {user_id}", file=sys.stderr, flush=True)
                return ""
            
            # Get the most recent session for this agent-chat-user combination
            # Order by updated_at descending to get the latest
            agent_session = session.exec(
                select(AgentSessions)
                .where(
                    AgentSessions.agent_name == agent_name,
                    AgentSessions.chat_id == this_chat.id,
                    AgentSessions.user_id == user_id
                )
                .order_by(AgentSessions.updated_at.desc())
            ).first()
            
            if agent_session:
                # Session exists, return the most recent one
                print(f"[get_or_create_session_id] Found existing session (most recent): {agent_session.session_id}", file=sys.stderr, flush=True)
                return agent_session.session_id
            else:
                # Create new session
                new_session_id = str(uuid_mod.uuid4())
                agent_session = AgentSessions(
                    user_id=user_id,
                    chat_id=this_chat.id,
                    agent_name=agent_name,
                    session_id=new_session_id
                )
                session.add(agent_session)
                session.commit()
                session.refresh(agent_session)
                print(f"[get_or_create_session_id] Created new session: {new_session_id}", file=sys.stderr, flush=True)
                return new_session_id

    @rx.event
    def create_new_agent_session(self):
        """Create a new session_id for current agent-chat-user combination.
        Always creates a new record to allow multiple sessions."""
        import uuid as uuid_mod
        import sys

        if not self.selected_container_name or not self.current_chat or not self.user:
            print("[create_new_agent_session] Missing required data", file=sys.stderr, flush=True)
            return

        with rx.session() as session:
            # Get the chat instance
            this_chat = session.exec(
                select(Chats).where(
                    Chats.chat_title == self.current_chat,
                    Chats.user_id == self.user.id
                )
            ).first()

            if not this_chat:
                print(f"[create_new_agent_session] Chat '{self.current_chat}' not found", file=sys.stderr, flush=True)
                return

            # Generate new session_id
            new_session_id = str(uuid_mod.uuid4())

            # Always create a new record to support multiple sessions
            agent_session = AgentSessions(
                user_id=self.user.id,
                chat_id=this_chat.id,
                agent_name=self.selected_container_name,
                session_id=new_session_id
            )
            session.add(agent_session)
            print(f"[create_new_agent_session] Created new session: {new_session_id}", file=sys.stderr, flush=True)

            session.commit()
            session.refresh(agent_session)

            # Update state variables
            self.current_session_id = new_session_id
            self.agent_container_uuid = new_session_id

            # Reload available sessions list
            self._load_available_sessions_internal(session, this_chat.id)

    def _load_available_sessions_internal(self, db_session, chat_id: int):
        """Internal helper to load all sessions for current agent-chat-user.
        Called within an existing database session context."""
        import sys
        from datetime import datetime

        if not self.selected_container_name or not self.user:
            self.available_sessions = []
            return

        # Get all sessions for this agent-chat-user, ordered by updated_at descending (newest first)
        sessions = db_session.exec(
            select(AgentSessions)
            .where(
                AgentSessions.agent_name == self.selected_container_name,
                AgentSessions.chat_id == chat_id,
                AgentSessions.user_id == self.user.id
            )
            .order_by(AgentSessions.updated_at.desc())
        ).all()

        self.available_sessions = [
            {
                "session_id": s.session_id,
                "created_at": datetime.fromtimestamp(s.created_at).strftime("%Y-%m-%d %H:%M") if s.created_at else "",
                "updated_at": datetime.fromtimestamp(s.updated_at).strftime("%Y-%m-%d %H:%M") if s.updated_at else "",
            }
            for s in sessions
        ]
        print(f"[_load_available_sessions_internal] Loaded {len(self.available_sessions)} sessions", file=sys.stderr, flush=True)

    @rx.event
    def load_available_sessions(self):
        """Load all available sessions for the current agent-chat-user combination."""
        import sys

        if not self.selected_container_name or not self.current_chat or not self.user:
            self.available_sessions = []
            return

        with rx.session() as session:
            # Get the chat instance
            this_chat = session.exec(
                select(Chats).where(
                    Chats.chat_title == self.current_chat,
                    Chats.user_id == self.user.id
                )
            ).first()

            if not this_chat:
                self.available_sessions = []
                return

            self._load_available_sessions_internal(session, this_chat.id)

    @rx.event
    def select_session(self, session_id: str):
        """Select a specific session from the available sessions list."""
        import sys

        self.current_session_id = session_id
        self.agent_container_uuid = session_id
        print(f"[select_session] Selected session: {session_id}", file=sys.stderr, flush=True)

    @rx.event
    def toggle_container_link(self):
        """Toggle the container link status (connected/disconnected).

        When linked (green), messages will be routed to the selected agent.
        When unlinked (red), messages will NOT be routed to the agent.
        """
        import sys
        self.container_linked = not self.container_linked
        print(f"[toggle_container_link] Container linked toggled to: {self.container_linked}", file=sys.stderr, flush=True)

    @rx.event
    def set_message_routing(self, mode: str):
        """Set the message routing mode.

        Args:
            mode: "finbuddy" (send to backend), "comment" (just add to chat), or "agent" (send to selected agent)
        """
        import sys
        if mode in ["finbuddy", "comment", "agent"]:
            self.message_routing = mode
            # Also update container_linked for backwards compatibility
            self.container_linked = (mode == "agent")
            print(f"[set_message_routing] Mode set to: {mode}", file=sys.stderr, flush=True)

    @rx.var
    def routing_is_finbuddy(self) -> bool:
        """Check if routing mode is finbuddy."""
        return self.message_routing == "finbuddy"

    @rx.var
    def routing_is_comment(self) -> bool:
        """Check if routing mode is comment."""
        return self.message_routing == "comment"

    @rx.var
    def routing_is_agent(self) -> bool:
        """Check if routing mode is agent."""
        return self.message_routing == "agent"

    # Available options
    available_datasources: List[str] = ["equity", "FI", "forex", "crypto"]
    available_tools: List[str] = ["stock_metrics", "price_analyzer", "sentiment_analyzer", "risk_calculator", "portfolio_optimizer"]

    def _get_auth_headers(self) -> dict:
        """Get authorization headers with JWT token for API requests.

        Note: rx.LocalStorage values may not be available during server-side event handlers,
        so we generate a fresh token from the user object if jwt_token is empty.
        """
        import sys
        print(f"[_get_auth_headers] jwt_token={self.jwt_token[:20] if self.jwt_token else 'None'}..., user={self.user}", file=sys.stderr, flush=True)

        # First try using the stored jwt_token (from LocalStorage)
        if self.jwt_token:
            print(f"[_get_auth_headers] Using jwt_token from LocalStorage", file=sys.stderr, flush=True)
            return {"Authorization": f"Bearer {self.jwt_token}"}

        # Fallback: generate a fresh token if we have a logged-in user
        # This handles cases where LocalStorage hasn't synced yet
        if self.user and hasattr(self.user, 'username') and self.user.username:
            from db_light.auth.jwt_utils import create_access_token
            token = create_access_token(user_id=self.user.username)
            print(f"[_get_auth_headers] Generated fresh token for user {self.user.username}", file=sys.stderr, flush=True)
            return {"Authorization": f"Bearer {token}"}

        print(f"[_get_auth_headers] No auth available!", file=sys.stderr, flush=True)
        return {}

    def load_agents_from_db(self):
        """Load agents and tools from the database API."""
        import sys
        import requests

        print(f"[load_agents_from_db] Loading agents and tools from database...", file=sys.stderr, flush=True)

        # Get auth headers with JWT token
        headers = self._get_auth_headers()

        try:
            # Load agents
            agents_response = requests.get("http://localhost:8008/api/agents", headers=headers, timeout=5)
            if agents_response.status_code == 200:
                agents_data = agents_response.json()
                self.db_agents = agents_data.get("agents", [])
                print(f"[load_agents_from_db] Loaded {len(self.db_agents)} agents from DB", file=sys.stderr, flush=True)
            else:
                print(f"[load_agents_from_db] Failed to load agents: {agents_response.status_code}", file=sys.stderr, flush=True)

            # Load tools
            tools_response = requests.get("http://localhost:8008/api/tools", headers=headers, timeout=5)
            if tools_response.status_code == 200:
                tools_data = tools_response.json()
                self.db_tools = tools_data.get("tools", [])
                print(f"[load_agents_from_db] Loaded {len(self.db_tools)} tools from DB", file=sys.stderr, flush=True)
            else:
                print(f"[load_agents_from_db] Failed to load tools: {tools_response.status_code}", file=sys.stderr, flush=True)

            self.db_agents_loaded = True

            # Also load datasources
            self.load_datasources_from_db()

            # Also load GUI pages for agent builder sidebar
            self.load_saved_page_layouts()

        except requests.exceptions.RequestException as e:
            print(f"[load_agents_from_db] Error loading from API: {e}", file=sys.stderr, flush=True)
            # Fall back to empty lists - UI will use static fallback
            self.db_agents = []
            self.db_tools = []
            self.db_agents_loaded = False

    def load_datasources_from_db(self):
        """Load datasources from the dataset registry API."""
        import sys
        import requests

        print(f"[load_datasources_from_db] Loading datasources from registry...", file=sys.stderr, flush=True)

        try:
            response = requests.get("http://localhost:8008/api/datasources", timeout=5)
            if response.status_code == 200:
                data = response.json()
                self.db_datasources = data.get("datasources", [])
                print(f"[load_datasources_from_db] Loaded {len(self.db_datasources)} datasources", file=sys.stderr, flush=True)
            else:
                print(f"[load_datasources_from_db] Failed to load: {response.status_code}", file=sys.stderr, flush=True)

            self.db_datasources_loaded = True

        except requests.exceptions.RequestException as e:
            print(f"[load_datasources_from_db] Error loading from API: {e}", file=sys.stderr, flush=True)
            self.db_datasources = []
            self.db_datasources_loaded = False

    def reset_onboarding_form(self):
        """Reset all onboarding form fields to default values."""
        self.onboarding_dataset_name = ""
        self.onboarding_description = ""
        self.onboarding_data_type = ""
        self.onboarding_db_type = ""
        self.onboarding_access_mode = ""
        self.onboarding_path = ""
        self.onboarding_host = ""
        self.onboarding_port = ""
        self.onboarding_username = ""
        self.onboarding_password = ""
        self.onboarding_api_endpoint = ""
        self.onboarding_api_key = ""
        self.onboarding_auth_type = ""
        self.onboarding_file_type = ""
        self.onboarding_status = "idle"
        self.onboarding_message = ""
        # S3 fields
        self.onboarding_storage_location = "disk"
        self.onboarding_s3_bucket = ""
        self.onboarding_s3_region = "us-east-1"
        self.onboarding_s3_path = ""
        self.onboarding_s3_upload = True  # Whether to upload local file to S3

    async def start_data_onboarding(self):
        """Start the data onboarding process by calling the FastAPI endpoint."""
        import sys
        import httpx

        # Validate required fields
        if not self.onboarding_dataset_name:
            self.onboarding_status = "error"
            self.onboarding_message = "Dataset name is required"
            return

        if not self.onboarding_data_type:
            self.onboarding_status = "error"
            self.onboarding_message = "Please select a data source type"
            return

        self.onboarding_status = "processing"
        self.onboarding_message = ""

        # Build request payload based on data type
        payload = {
            "dataset_name": self.onboarding_dataset_name,
            "description": self.onboarding_description,
            "data_type": self.onboarding_data_type,
            "storage_location": self.onboarding_storage_location,
        }

        # Add S3 fields if storage location is S3
        if self.onboarding_storage_location == "s3":
            # S3 bucket only required if upload is ON
            if self.onboarding_s3_upload and not self.onboarding_s3_bucket:
                self.onboarding_status = "error"
                self.onboarding_message = "S3 bucket name is required"
                return
            payload["s3_bucket"] = self.onboarding_s3_bucket
            payload["s3_region"] = self.onboarding_s3_region or "us-east-1"
            payload["s3_upload"] = self.onboarding_s3_upload
            payload["s3_path"] = self.onboarding_s3_path

        if self.onboarding_data_type == "database":
            if not self.onboarding_db_type:
                self.onboarding_status = "error"
                self.onboarding_message = "Please select a database type"
                return
            payload["database_type"] = self.onboarding_db_type.lower()
            payload["access_mode"] = self.onboarding_access_mode.lower() if self.onboarding_access_mode else "file"

            if self.onboarding_access_mode == "File":
                if not self.onboarding_path:
                    self.onboarding_status = "error"
                    self.onboarding_message = "Database file path is required"
                    return
                payload["path"] = self.onboarding_path
            else:
                payload["host"] = self.onboarding_host
                payload["port"] = int(self.onboarding_port) if self.onboarding_port else None
                payload["username"] = self.onboarding_username
                payload["password"] = self.onboarding_password

        elif self.onboarding_data_type in ["csv", "parquet"]:
            if not self.onboarding_path:
                self.onboarding_status = "error"
                self.onboarding_message = "File path is required"
                return
            payload["path"] = self.onboarding_path
            payload["file_type"] = self.onboarding_file_type.lower() if self.onboarding_file_type else self.onboarding_data_type

        elif self.onboarding_data_type == "api":
            if not self.onboarding_api_endpoint:
                self.onboarding_status = "error"
                self.onboarding_message = "API endpoint URL is required"
                return
            payload["api_endpoint"] = self.onboarding_api_endpoint
            payload["api_key"] = self.onboarding_api_key
            payload["auth_type"] = self.onboarding_auth_type

        print(f"[start_data_onboarding] Sending payload: {payload}", file=sys.stderr, flush=True)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:8008/api/onboard_dataset",
                    json=payload,
                    timeout=120.0  # 2 minutes timeout for large datasets
                )

                if response.status_code == 200:
                    result = response.json()
                    self.onboarding_status = "success"
                    self.onboarding_message = f"Dataset '{self.onboarding_dataset_name}' onboarded successfully! ID: {result.get('dataset_id', 'N/A')}"
                    # Reload datasources to include the new one
                    self.load_datasources_from_db()
                else:
                    error_detail = response.json().get("detail", response.text)
                    self.onboarding_status = "error"
                    self.onboarding_message = f"Failed to onboard dataset: {error_detail}"

        except httpx.TimeoutException:
            self.onboarding_status = "error"
            self.onboarding_message = "Request timed out. The dataset may be too large."
        except Exception as e:
            print(f"[start_data_onboarding] Error: {e}", file=sys.stderr, flush=True)
            self.onboarding_status = "error"
            self.onboarding_message = f"Error: {str(e)}"

    def reset_text_index_form(self):
        """Reset all text indexing form fields to default values."""
        self.text_index_dataset_name = ""
        self.text_index_source_dir = ""
        self.text_index_description = ""
        self.text_index_chunk_size = "500"
        self.text_index_chunk_overlap = "50"
        self.text_index_recursive = True
        self.text_index_status = "idle"
        self.text_index_message = ""

    async def start_text_indexing(self):
        """Start the text indexing process by calling the FastAPI endpoint."""
        import sys
        import httpx

        # Validate required fields
        if not self.text_index_dataset_name:
            self.text_index_status = "error"
            self.text_index_message = "Dataset name is required"
            return

        if not self.text_index_source_dir:
            self.text_index_status = "error"
            self.text_index_message = "Source directory is required"
            return

        self.text_index_status = "processing"
        self.text_index_message = ""

        # Build request payload
        payload = {
            "dataset_name": self.text_index_dataset_name,
            "source_dir": self.text_index_source_dir,
            "description": self.text_index_description,
            "chunk_size": int(self.text_index_chunk_size) if self.text_index_chunk_size else 500,
            "chunk_overlap": int(self.text_index_chunk_overlap) if self.text_index_chunk_overlap else 50,
            "recursive": self.text_index_recursive,
        }

        print(f"[start_text_indexing] Sending payload: {payload}", file=sys.stderr, flush=True)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:8008/api/index_text",
                    json=payload,
                    timeout=300.0  # 5 minutes timeout for large datasets with embeddings
                )

                if response.status_code == 200:
                    result = response.json()
                    self.text_index_status = "success"
                    total_chunks = result.get('total_chunks', 0)
                    embedded_chunks = result.get('embedded_chunks', 0)
                    self.text_index_message = f"Dataset '{self.text_index_dataset_name}' indexed successfully! Total chunks: {total_chunks}, Embedded: {embedded_chunks}"
                    # Reload datasources to include the new one
                    self.load_datasources_from_db()
                else:
                    error_detail = response.json().get("detail", response.text)
                    self.text_index_status = "error"
                    self.text_index_message = f"Failed to index text: {error_detail}"

        except httpx.TimeoutException:
            self.text_index_status = "error"
            self.text_index_message = "Request timed out. The dataset may be too large."
        except Exception as e:
            print(f"[start_text_indexing] Error: {e}", file=sys.stderr, flush=True)
            self.text_index_status = "error"
            self.text_index_message = f"Error: {str(e)}"

    def add_agent_box(self):
        """Add a new agent box to the canvas."""
        new_id = f"agent_{len(self.agent_boxes) + 1}"
        # Stagger positions so boxes don't overlap
        offset = len(self.agent_boxes) * 50
        new_box = {
            "id": new_id,
            "type": "agent",
            "name": f"Agent {len(self.agent_boxes) + 1}",
            "x": 50 + offset,
            "y": 50 + offset
        }
        self.agent_boxes.append(new_box)
        print(f"Added agent box: {new_box}")
        print(f"Total agent boxes: {len(self.agent_boxes)}")
    
    def add_tool_box(self, tool_name: str):
        """Add a new tool box to the canvas."""
        new_id = f"tool_{len(self.tool_boxes) + 1}"
        # Stagger positions so boxes don't overlap
        offset = len(self.tool_boxes) * 50
        self.tool_boxes.append({
            "id": new_id,
            "type": "tool",
            "name": tool_name,
            "x": 350 + offset,
            "y": 50 + offset
        })
    
    def add_datasource_box(self, datasource_name: str):
        """Add a new datasource box to the canvas."""
        new_id = f"datasource_{len(self.datasource_boxes) + 1}"
        # Stagger positions so boxes don't overlap
        offset = len(self.datasource_boxes) * 50
        self.datasource_boxes.append({
            "id": new_id,
            "type": "datasource",
            "name": datasource_name,
            "x": 650 + offset,
            "y": 50 + offset
        })
    
    # Helper methods for specific tools and data sources
    def add_stock_metrics(self):
        self.add_tool_box("stock_metrics")
    
    def add_price_analyzer(self):
        self.add_tool_box("price_analyzer")
    
    def add_sentiment_analyzer(self):
        self.add_tool_box("sentiment_analyzer")
    
    def add_risk_calculator(self):
        self.add_tool_box("risk_calculator")
    
    def add_portfolio_optimizer(self):
        self.add_tool_box("portfolio_optimizer")
    
    def add_equity_datasource(self):
        self.add_datasource_box("equity")
    
    def add_fi_datasource(self):
        self.add_datasource_box("FI")
    
    def add_forex_datasource(self):
        self.add_datasource_box("forex")
    
    def add_crypto_datasource(self):
        self.add_datasource_box("crypto")
    
    def add_connection(self, from_id: str, to_id: str):
        """Add a connection between two boxes."""
        self.connections.append({
            "from": from_id,
            "to": to_id
        })
    
    def update_box_position(self, box_id: str, x: int, y: int):
        """Update the position of a box."""
        # Find and update in agent_boxes
        for box in self.agent_boxes:
            if box["id"] == box_id:
                box["x"] = x
                box["y"] = y
                return
        # Find and update in tool_boxes
        for box in self.tool_boxes:
            if box["id"] == box_id:
                box["x"] = x
                box["y"] = y
                return
        # Find and update in datasource_boxes
        for box in self.datasource_boxes:
            if box["id"] == box_id:
                box["x"] = x
                box["y"] = y
                return
    
    def check_diagram_json_ready(self):
        """Check if diagram JSON is ready in state."""
        has_json = bool(self.generated_diagram_json and len(self.generated_diagram_json) > 0)
        print(f"[check_diagram_json_ready] Has JSON: {has_json}, Length: {len(self.generated_diagram_json) if self.generated_diagram_json else 0}")
        return has_json
    
    async def generate_agent_from_diagram(self, json_str: str = ""):
        """
        Generate agent container from diagram JSON.
        This is called when the Create button is clicked in the agent builder.
        Reads JSON from localStorage via client-side cookie.
        """
        import json
        import sys
        
        # Check if user is logged in
        if self.user is None:
            self.generated_diagram_json = "Error: User not logged in"
            yield
            return
            
        try:
            # The JSON is in localStorage and has been loaded into self.generated_diagram_json
            # Use the actual diagram JSON from the UI
            diagram_json = self.generated_diagram_json
            
            # Validate that we have JSON from the UI
            if not diagram_json or len(diagram_json) == 0:
                error_msg = "❌ Error: No diagram JSON found. Please click 'Generate JSON' first."
                print(f"[generate_agent_from_diagram] {error_msg}", file=sys.stderr, flush=True)
                self.generated_diagram_json = error_msg
                yield
                return
            
            print(f"[generate_agent_from_diagram] ✓ Using diagram JSON from GUI, length: {len(diagram_json)}", file=sys.stderr, flush=True)
            
            print(f"\n[generate_agent_from_diagram] Starting...", file=sys.stderr)
            print(f"[generate_agent_from_diagram] diagram_json length: {len(diagram_json) if diagram_json else 0}", file=sys.stderr)
            
            # Debug logging
            print(f"[generate_agent_from_diagram] diagram_json type: {type(diagram_json)}", file=sys.stderr, flush=True)
            print(f"[generate_agent_from_diagram] diagram_json length: {len(diagram_json) if diagram_json else 0}", file=sys.stderr, flush=True)
            print(f"[generate_agent_from_diagram] diagram_json repr: {repr(diagram_json[:200]) if diagram_json else 'EMPTY'}", file=sys.stderr, flush=True)
            print(f"[generate_agent_from_diagram] diagram_json bytes: {diagram_json[:50].encode() if diagram_json else b'EMPTY'}", file=sys.stderr, flush=True)
            
            # Check if empty or None
            if diagram_json is None:
                self.generated_diagram_json = "Error: diagram_json is None"
                yield
                return
            
            if len(diagram_json) == 0:
                self.generated_diagram_json = "Error: diagram_json is empty (length 0)"
                yield
                return
            
            if diagram_json.strip() == "":
                self.generated_diagram_json = "Error: diagram_json is only whitespace"
                yield
                return
            
            # Parse the diagram JSON
            try:
                diagram_data = json.loads(diagram_json)
            except json.JSONDecodeError as e:
                error_msg = f"JSON Parse Error: {str(e)}\n\nReceived data (first 500 chars):\n{diagram_json[:500]}\n\nFull data:\n{diagram_json}"
                print(error_msg, file=sys.stderr, flush=True)
                self.generated_diagram_json = error_msg
                yield
                return
            
            # Add command_type to the JSON
            diagram_data["command_type"] = "generate"
            
            # Convert back to JSON string for agent_manager
            json_text = json.dumps(diagram_data)
            
            # Prepare the command with @finbuddy.agents prefix
            command = f"@finbuddy.agents {json_text}"
            
            # Use the bot instance (already initialized at top of file)
            
            # Update state to show processing
            self.generated_diagram_json = "Generating agent container...\n\n" + diagram_json
            yield
            
            # Call FB_super_agent with the command
            answer_text = await bot.FB_super_agent(
                text=command,
                user_dir=self.user.username,
                current_chat="agent_builder",
                last_portfolio_id="1",
                last_dataplot_id="1",
                last_datatable_id="1"
            )
            
            # Store the result - keep it short to avoid WebSocket issues
            if answer_text:
                # Extract just the essential info from the response
                result_lines = answer_text.split('\n')[:5]  # First 5 lines only
                result_summary = '\n'.join(result_lines)
                
                # Try to extract the UUID from the response (format: "QUEUE:uuid")
                import re
                uuid_match = re.search(r'QUEUE:([a-f0-9-]+)', answer_text)
                if uuid_match:
                    self.agent_container_uuid = uuid_match.group(1)
                    self.gc_container_type = "local"  # Mark as local container
                    self.generated_diagram_json = f"✅ Local Container Created!\n\nUUID: {self.agent_container_uuid}\n\n{result_summary}\n\n(Use Call/Stop buttons below)"
                else:
                    self.gc_container_type = "local"  # Mark as local container
                    self.generated_diagram_json = f"✅ Local Container Created!\n\n{result_summary}\n\n(Check logs for full details)"

                # Refresh agents and running containers list to show newly created container in sidebar
                self.load_agents_from_db()
                self.load_running_containers()
            else:
                self.generated_diagram_json = "❌ Error: No response from agent generation"

            yield
            
        except Exception as e:
            import traceback
            error_msg = f"❌ Error: {str(e)}"
            # Limit error message length to avoid WebSocket issues
            if len(error_msg) > 500:
                error_msg = error_msg[:500] + "...\n(See backend logs for full error)"
            self.generated_diagram_json = error_msg
            yield
    
    def generate_diagram(self):
        """Generate the diagram configuration as JSON."""
        diagram_config = {
            "agents": self.agent_boxes,
            "tools": self.tool_boxes,
            "datasources": self.datasource_boxes,
            "connections": self.connections
        }
        self.generated_diagram_json = json.dumps(diagram_config, indent=2)
        print("Generated Diagram:")
        print(self.generated_diagram_json)
    
    async def call_agent_container(self):
        """Call an existing agent container with instructions."""
        import json
        import uuid
        import sys

        # Check if user is logged in
        if self.user is None:
            self.agent_call_result = "❌ Error: User not logged in"
            yield
            return

        # Check if we have a container UUID
        if not self.agent_container_uuid:
            self.agent_call_result = "❌ Error: No agent container UUID. Create an agent first."
            yield
            return

        # Check if we have instructions
        if not self.agent_call_instructions:
            self.agent_call_result = "❌ Error: Please enter instructions for the agent"
            yield
            return

        try:
            # Check if this is a GC container
            if self.gc_container_type == "gc" and self.gc_service_url:
                # Call GC Cloud Run service directly
                self.agent_call_result = "☁️ Calling GC Cloud Run agent..."
                yield

                import aiohttp
                import uuid as uuid_mod

                # Use current_session_id if already set, otherwise generate new
                # This ensures frontend chart and agent use the SAME session ID
                if self.current_session_id:
                    session_id = self.current_session_id
                    print(f"[call_agent_container] GC: Using existing current_session_id: {session_id}", file=sys.stderr, flush=True)
                else:
                    session_id = str(uuid_mod.uuid4())
                    self.current_session_id = session_id
                    print(f"[call_agent_container] GC: Generated new session_id: {session_id}", file=sys.stderr, flush=True)

                # Build additional_params with job_id, output_directory, and chat_id
                # chat_id is CRITICAL for AMQP messages to appear in chat UI
                chat_id_str = str(self.current_chat_id) if self.current_chat_id else ""
                if not chat_id_str:
                    print(f"[call_agent_container] WARNING: chat_id is empty! current_chat_id={self.current_chat_id}, current_chat='{self.current_chat}'", file=sys.stderr, flush=True)
                    print(f"[call_agent_container] Agent messages may not appear in chat UI without a valid chat_id!", file=sys.stderr, flush=True)
                additional_params = {
                    "job_id": session_id,
                    "output_directory": f"/home/riccardo247/sp500/shareit/{self.user.username}/shareit_{session_id}",
                    "chat_id": chat_id_str
                }
                print(f"[call_agent_container] GC: container={self.selected_container_id}, session={session_id}, chat_id={chat_id_str}", file=sys.stderr, flush=True)

                # Add connected datasource info if available (for data_analyst agent)
                if self.db_datasources and len(self.db_datasources) > 0:
                    ds = self.db_datasources[0]  # Use first available datasource
                    additional_params['dataset_name'] = ds.get('dataset_name')
                    additional_params['dataset_path'] = ds.get('path') or ds.get('dataset_path')
                    additional_params['dataset_schema'] = ds.get('prompt_minimal') or ds.get('prompt_full') or ds.get('description', '')
                    print(f"[call_agent_container] Added datasource to GC params: {ds.get('dataset_name')}", file=sys.stderr, flush=True)

                payload = {
                    "instructions": self.agent_call_instructions,
                    "user_id": self.user.username,
                    "session_id": session_id,
                    "additional_params": additional_params
                }
                
                print(f"\n{'='*80}", file=sys.stderr, flush=True)
                print(f"[AGENT CALL] Calling Cloud Run agent", file=sys.stderr, flush=True)
                print(f"[AGENT CALL] URL: {self.gc_service_url}/execute", file=sys.stderr, flush=True)
                print(f"[AGENT CALL] Session ID: {session_id}", file=sys.stderr, flush=True)
                print(f"[AGENT CALL] Instructions: {self.agent_call_instructions[:100]}...", file=sys.stderr, flush=True)
                print(f"{'='*80}\n", file=sys.stderr, flush=True)

                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.gc_service_url}/execute",
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=300)  # 5 min timeout
                    ) as response:
                        if response.status == 200:
                            result = await response.json()
                            result_text = result.get("result", str(result))
                            if len(result_text) > 1000:
                                result_text = result_text[:1000] + "..."
                            self.agent_call_result = f"✅ GC Agent Response:\n\n{result_text}"
                        else:
                            error_text = await response.text()
                            self.agent_call_result = f"❌ GC Error ({response.status}):\n\n{error_text[:500]}"
            else:
                # Call local container via existing mechanism
                self.agent_call_result = "🐳 Calling local container agent..."
                yield

                # Ensure CloudAMQP queue exists before calling agent
                # This is critical for receiving progress messages
                if USE_CLOUDAMQP and FASTSTREAM_AVAILABLE and CLOUDAMQP_URL:
                    try:
                        from faststream.rabbit import RabbitBroker, RabbitExchange, RabbitQueue, ExchangeType

                        user_id = self.user.username
                        queue_name = f"user_{user_id}_queue"
                        routing_key = f"user.{user_id}.job.*"

                        jobs_exchange = RabbitExchange(
                            name="jobs_exchange",
                            type=ExchangeType.TOPIC,
                            durable=True
                        )

                        user_queue = RabbitQueue(
                            name=queue_name,
                            durable=True,
                            routing_key=routing_key
                        )

                        broker = RabbitBroker(CLOUDAMQP_URL)
                        await broker.connect()
                        await broker.declare_exchange(jobs_exchange)
                        # CRITICAL: Bind queue to exchange with routing key pattern
                        # declare_queue alone doesn't bind - we need to explicitly bind
                        declared_queue = await broker.declare_queue(user_queue)
                        # Use exchange name string for binding
                        await declared_queue.bind("jobs_exchange", routing_key)
                        await broker.close()

                        print(f"[Agent Builder] Ensured CloudAMQP queue '{queue_name}' exists")
                        self.agent_call_result = "🐳 Queue ready, calling agent..."
                        yield

                        # Also ensure consumer is running to receive messages
                        await self.ensure_rabbitmq_consumer()
                    except Exception as queue_err:
                        print(f"[Agent Builder] Could not ensure queue exists: {queue_err}")

                # Build the command JSON
                # container_uuid = instance_id for database lookup
                # job_id = session_id for tracking
                # chat_id is CRITICAL for AMQP messages to appear in chat UI
                chat_id_str = str(self.current_chat_id) if self.current_chat_id else ""
                if not chat_id_str:
                    print(f"[call_agent_container] WARNING: chat_id is empty! current_chat_id={self.current_chat_id}, current_chat='{self.current_chat}'", file=sys.stderr, flush=True)
                    print(f"[call_agent_container] Agent messages may not appear in chat UI without a valid chat_id!", file=sys.stderr, flush=True)
                command_json = {
                    "command_type": "call",
                    "container_uuid": self.selected_container_id,  # instance_id for backend lookup
                    "instructions": self.agent_call_instructions,
                    "job_id": self.current_session_id,  # session UUID for tracking
                    "chat_id": chat_id_str
                }
                print(f"[call_agent_container] Local: container_uuid={self.selected_container_id}, job_id={self.current_session_id}, chat_id={chat_id_str}", file=sys.stderr, flush=True)
                print(f"[call_agent_container] JWT token present: {bool(self.jwt_token)}, length: {len(self.jwt_token) if self.jwt_token else 0}", file=sys.stderr, flush=True)

                json_text = json.dumps(command_json)
                command = f"@finbuddy.agents {json_text}"

                # Call FB_super_agent with JWT token for authentication
                answer_text = await bot.FB_super_agent(
                    text=command,
                    user_dir=self.user.username,
                    current_chat="agent_builder",
                    last_portfolio_id="1",
                    last_dataplot_id="1",
                    last_datatable_id="1",
                    state={"jwt_token": self.jwt_token}
                )

                # Store the result
                if answer_text:
                    result_lines = answer_text.split('\n')[:10]  # First 10 lines
                    result_summary = '\n'.join(result_lines)
                    self.agent_call_result = f"✅ Agent Response:\n\n{result_summary}"
                else:
                    self.agent_call_result = "❌ Error: No response from agent"

            yield

        except Exception as e:
            error_msg = f"❌ Error calling agent: {str(e)}"
            if len(error_msg) > 500:
                error_msg = error_msg[:500] + "..."
            self.agent_call_result = error_msg
            yield
    
    async def stop_agent_container(self):
        """Stop an existing agent container."""
        import json
        import asyncio
        import os
        import sys
        from pathlib import Path

        # Check if user is logged in
        if self.user is None:
            self.agent_call_result = "❌ Error: User not logged in"
            yield
            return

        # Check if we have a container UUID
        if not self.agent_container_uuid:
            self.agent_call_result = "❌ Error: No agent container UUID. Create an agent first."
            yield
            return

        try:
            # Check if this is a GC container
            if self.gc_container_type == "gc" and self.gc_service_url:
                self.agent_call_result = "☁️ Deleting GC Cloud Run service..."
                yield

                # Get service name and instance_id from database config_json (more reliable than URL parsing)
                service_name = None
                instance_id_to_delete = None
                try:
                    from YourIndexingAI.agents_data.agents_db import get_running_instances
                    user_id = getattr(self, 'user_email', 'demo5') or 'demo5'
                    instances = get_running_instances(user_id)
                    for inst in instances:
                        if inst.get('instance_type') == 'gc':
                            # Check if address matches or service_url in config matches
                            inst_address = str(inst.get('address', ''))
                            config = inst.get('config_json', {})
                            if isinstance(config, str):
                                config = json.loads(config)
                            config_service_url = config.get('service_url', '')

                            if self.gc_service_url and (self.gc_service_url in inst_address or self.gc_service_url == config_service_url):
                                service_name = config.get('service_name')
                                instance_id_to_delete = inst.get('id')
                                print(f"[stop_agent_container] Found service_name from DB: {service_name}, instance_id: {instance_id_to_delete}", file=sys.stderr, flush=True)
                                break
                except Exception as db_err:
                    print(f"[stop_agent_container] Could not get service_name from DB: {db_err}", file=sys.stderr, flush=True)

                # Fallback: extract from URL if not in DB
                if not service_name:
                    import re
                    # Match new Cloud Run URL pattern: https://SERVICE_NAME-NUMBERS.REGION.run.app
                    # Example: https://finbuddy-web-rifraf-2afa1a8f-1012901907036.us-central1.run.app
                    url_match = re.search(r'https://([a-zA-Z0-9-]+)-\d+\.[a-z0-9-]+\.run\.app', self.gc_service_url)
                    if url_match:
                        service_name = url_match.group(1)
                    else:
                        # Try older pattern: https://SERVICE_NAME-xxx-uc.a.run.app
                        url_match = re.search(r'https://([a-zA-Z0-9-]+)-[a-zA-Z0-9]+-uc\.a\.run\.app', self.gc_service_url)
                        if url_match:
                            service_name = url_match.group(1)
                        else:
                            # Last resort: extract everything before the first number-dash sequence
                            url_match = re.search(r'https://([a-zA-Z0-9-]+)', self.gc_service_url)
                            service_name = url_match.group(1) if url_match else "finbuddy-agent"
                    print(f"[stop_agent_container] Extracted service_name from URL: {service_name}", file=sys.stderr, flush=True)

                # Set environment variables for gcloud
                env = os.environ.copy()
                env["PATH"] = f"{os.path.expanduser('~')}/google-cloud-sdk/bin:" + env.get("PATH", "")

                # Delete the Cloud Run service
                cmd = [
                    "gcloud", "run", "services", "delete", service_name,
                    "--region", "us-central1",
                    "--project", "finbuddy1",
                    "--quiet"
                ]

                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    env=env
                )

                stdout, _ = await process.communicate()
                output = stdout.decode('utf-8') if stdout else ""

                if process.returncode == 0:
                    self.agent_call_result = f"✅ GC Cloud Run service '{service_name}' deleted successfully"

                    # Delete the instance from database
                    try:
                        from YourIndexingAI.agents_data.agents_db import delete_instance

                        if instance_id_to_delete:
                            delete_instance(instance_id_to_delete)
                            print(f"[stop_agent_container] Deleted GC instance {instance_id_to_delete} from DB", file=sys.stderr, flush=True)
                        else:
                            print(f"[stop_agent_container] Warning: No instance_id found to delete from DB", file=sys.stderr, flush=True)
                    except Exception as db_err:
                        print(f"[stop_agent_container] Warning: Failed to delete GC instance from DB: {db_err}", file=sys.stderr, flush=True)
                else:
                    self.agent_call_result = f"⚠️ Service '{service_name}' may already be deleted or error:\n{output[:300]}"

                # Clear GC state
                self.agent_container_uuid = ""
                self.gc_service_url = ""
                self.gc_container_type = ""
            else:
                # Stop local container via existing mechanism
                self.agent_call_result = "🐳 Stopping local container..."
                yield

                # Build the command JSON
                command_json = {
                    "command_type": "stop",
                    "container_uuid": self.agent_container_uuid
                }

                json_text = json.dumps(command_json)
                command = f"@finbuddy.agents {json_text}"

                # Call FB_super_agent
                answer_text = await bot.FB_super_agent(
                    text=command,
                    user_dir=self.user.username,
                    current_chat="agent_builder",
                    last_portfolio_id="1",
                    last_dataplot_id="1",
                    last_datatable_id="1"
                )

                # Store the result
                if answer_text:
                    self.agent_call_result = f"✅ {answer_text}"
                    # Clear the UUID since container is stopped
                    self.agent_container_uuid = ""
                    self.gc_container_type = ""
                else:
                    self.agent_call_result = "❌ Error: No response from stop command"

            yield

        except Exception as e:
            error_msg = f"❌ Error stopping agent: {str(e)}"
            if len(error_msg) > 500:
                error_msg = error_msg[:500] + "..."
            self.agent_call_result = error_msg
            yield

    def _build_gc_containers(self, image_uri: str, filtered_env_vars: dict, use_cloudflared: bool, db_tunnel_host: str) -> list:
        """
        Build the containers list for Cloud Run service YAML.

        Args:
            image_uri: The agent container image URI
            filtered_env_vars: Environment variables for the agent
            use_cloudflared: Whether to add cloudflared sidecar for PostgreSQL
            db_tunnel_host: The Cloudflare tunnel hostname for PostgreSQL (e.g., db.finbuddygroup.com)

        Returns:
            List of container definitions for Cloud Run
        """
        containers = [
            # Agent container (always present)
            {
                "name": "agent",
                "image": image_uri,
                "ports": [{"name": "http1", "containerPort": 8080}],
                "env": [{"name": k, "value": str(v)} for k, v in filtered_env_vars.items()],
                "resources": {
                    "limits": {
                        "cpu": "2",
                        "memory": "2Gi"
                    },
                    "requests": {
                        "cpu": "1",
                        "memory": "1Gi"
                    }
                }
            }
        ]

        # Add cloudflared sidecar only if DB_TUNNEL_HOST is configured
        if use_cloudflared:
            containers.append({
                "name": "cloudflared",
                "image": "cloudflare/cloudflared:latest",
                "args": [
                    "access",
                    "tcp",
                    "--hostname",
                    db_tunnel_host,
                    "--url",
                    "0.0.0.0:5432"
                ],
                "resources": {
                    "limits": {
                        "cpu": "200m",
                        "memory": "256Mi"
                    },
                    "requests": {
                        "cpu": "50m",
                        "memory": "64Mi"
                    }
                }
            })

        return containers

    async def deploy_gc_container(self):
        """
        Deploy agent container to Google Cloud Run.
        Uses per-agent build pattern (like local containers) - builds fresh image per agent.
        """
        import json
        import subprocess
        import asyncio
        import tempfile
        import os
        import sys
        import shutil
        from pathlib import Path

        # Check if user is logged in
        if self.user is None:
            self.generated_diagram_json = "❌ Error: User not logged in"
            yield
            return

        # Check if we have diagram JSON - use the raw copy
        if not self._raw_diagram_json:
            self.generated_diagram_json = "❌ Error: No diagram JSON found. Please click 'Generate JSON' first."
            yield
            return

        try:
            # Save the raw JSON before we overwrite the display variable
            diagram_json = self._raw_diagram_json

            # Set deploying state
            self.gc_deploying = True
            self.generated_diagram_json = "☁️ Deploying to Google Cloud Run...\n\n⏳ This may take several minutes.\n"
            yield

            # Parse the diagram JSON from the saved raw copy
            config_data = None
            try:
                config_data = json.loads(diagram_json)
            except json.JSONDecodeError as e:
                self.gc_deploying = False
                self.generated_diagram_json = f"❌ Error: Invalid JSON format: {str(e)}"
                yield
                return

            if not config_data:
                self.gc_deploying = False
                self.generated_diagram_json = "❌ Error: Empty diagram JSON. Please click 'Generate JSON' first to create valid configuration."
                yield
                return

            # Extract agent info from diagram
            # Handle both NEW format (entities array) and OLD format (separate agents/tools keys)
            entities = config_data.get("entities", [])
            print(f"[deploy_gc_container] DEBUG: entities count = {len(entities)}", file=sys.stderr, flush=True)
            print(f"[deploy_gc_container] DEBUG: entities = {entities}", file=sys.stderr, flush=True)
            if entities:
                # NEW FORMAT: entities array with type field
                agents = [e for e in entities if e.get("type") == "agent"]
                tools_list = [e for e in entities if e.get("type") == "tool"]
                print(f"[deploy_gc_container] NEW FORMAT: {len(agents)} agents, {len(tools_list)} tools", file=sys.stderr, flush=True)
                print(f"[deploy_gc_container] DEBUG: tools_list = {tools_list}", file=sys.stderr, flush=True)
            else:
                # OLD FORMAT: separate agents/tools keys from generate_diagram()
                agents = config_data.get("agents", [])
                tools_list = config_data.get("tools", [])
                print(f"[deploy_gc_container] Using OLD format: {len(agents)} agents, {len(tools_list)} tools", file=sys.stderr, flush=True)

            if not agents:
                self.gc_deploying = False
                self.generated_diagram_json = "❌ Error: No agents found in diagram. Please add at least one agent."
                yield
                return

            # Get first agent for now (or main superagent)
            main_agent = agents[0]
            agent_name = main_agent.get("name", "DynamicAgent")
            agent_module = main_agent.get("agent_module") or main_agent.get("module")
            
            # If agent_module is still None/empty, try to load from database
            if not agent_module:
                print(f"[deploy_gc_container] agent_module is null, looking up from DB for agent: {agent_name}", file=sys.stderr, flush=True)
                try:
                    response = requests.get(f"http://localhost:8008/api/agents/by-name/{agent_name}", timeout=5)
                    if response.status_code == 200:
                        data = response.json()
                        agent_data = data.get('agent', {})
                        agent_module = agent_data.get('agent_module', '')
                        print(f"[deploy_gc_container] Loaded agent_module from DB: {agent_module}", file=sys.stderr, flush=True)
                except Exception as e:
                    print(f"[deploy_gc_container] Could not load agent_module from DB: {e}", file=sys.stderr, flush=True)
            
            # Final fallback to agent_module_map
            if not agent_module:
                agent_module_map = {
                    'Research Agent': 'papers.papers_agent',
                    'Web Summary': 'web_rifraf.web_rifraf_agent',
                    'Equity Analyst': 'equity_analyst.equity_agent',
                    'FI Analyst': 'FI_analyst.FI_agent',
                    'Asset Allocation': 'asset_allocation.asset_allocation_agent',
                    'Portfolio Manager': 'portfolio_manager.portfolio_manager_agent',
                    'Super PM': 'super_PM.super_PM_agent',
                    'Chart Analyst': 'chart_agent.chart_agent'
                }
                agent_module = agent_module_map.get(agent_name, 'web_rifraf.web_rifraf_agent')
                print(f"[deploy_gc_container] Using fallback agent_module from map: {agent_module}", file=sys.stderr, flush=True)
            
            print(f"[deploy_gc_container] Final agent_module: {agent_module}", file=sys.stderr, flush=True)

            # =================================================================
            # SUPERAGENT DETECTION: Parse connections to find subagents
            # =================================================================
            connections = config_data.get("connections", [])
            print(f"[deploy_gc_container] Found {len(connections)} connections in diagram", file=sys.stderr, flush=True)

            def find_all_subagents_recursive_gc(source_agent_name, depth=0):
                """Recursively find all subagents (direct and nested) for GC deployment."""
                found_subagents = []
                agent_conns = [c for c in connections if c.get("source_id") == source_agent_name and c.get("connection_type") == "agent"]

                for conn in agent_conns:
                    subagent_name = conn.get("target_id")
                    subagent_entity = next((e for e in entities if e.get("name") == subagent_name and e.get("type") == "agent"), None)
                    if subagent_entity:
                        # Get tools for this subagent
                        subagent_tool_connections = [c for c in connections if c.get("source_id") == subagent_name and c.get("connection_type") == "tool"]
                        subagent_tools = [c.get("target_id", "").split("_", 1)[-1] for c in subagent_tool_connections]

                        # Check if this subagent has its own subagents (nested)
                        nested_subagents_list = find_all_subagents_recursive_gc(subagent_name, depth + 1)

                        found_subagents.append({
                            "name": subagent_name,
                            "module": subagent_entity.get("agent_module", ""),
                            "port": conn.get("port", 18300 + depth * 100 + len(found_subagents)),
                            "mcp_server_name": conn.get("mcp_server_name", f"{subagent_name.lower().replace(' ', '_')}_srv"),
                            "mcp_tool_name": conn.get("mcp_tool_name", f"{subagent_name.lower().replace(' ', '_')}_tool"),
                            "tools": subagent_tools,
                            "nested_subagents": nested_subagents_list,
                            "parent": source_agent_name,
                            "depth": depth
                        })

                        # Add nested subagents to the flat list (for server startup)
                        found_subagents.extend(nested_subagents_list)

                return found_subagents

            # Check if main agent has agent-to-agent connections (superagent)
            agent_connections = [c for c in connections if c.get("source_id") == agent_name and c.get("connection_type") == "agent"]
            subagents = []
            if agent_connections:
                subagents = find_all_subagents_recursive_gc(agent_name)
                # Sort by depth (deepest first) to ensure bottom-up server startup
                subagents.sort(key=lambda x: x.get('depth', 0), reverse=True)
                print(f"[deploy_gc_container] SUPERAGENT MODE: Found {len(subagents)} subagents", file=sys.stderr, flush=True)
                for sa in subagents:
                    print(f"[deploy_gc_container]   - {sa['name']} (port {sa['port']}, depth {sa['depth']}, tools: {sa['tools']})", file=sys.stderr, flush=True)

            superagent_mode = len(subagents) > 0
            print(f"[deploy_gc_container] superagent_mode = {superagent_mode}", file=sys.stderr, flush=True)

            # Build tools list from diagram
            gc_tools = []
            db_tool_mapping = {}

            # Load tools from DB first
            try:
                from YourIndexingAI.agents_data.agents_db import get_all_tools
                db_tools = get_all_tools()
                for t in db_tools:
                    db_tool_mapping[t['name']] = {
                        "api_module": t['api_module'],
                        "api_function": t['api_function']
                    }
                print(f"[deploy_gc_container] Loaded {len(db_tool_mapping)} tools from DB", file=sys.stderr, flush=True)
            except Exception as e:
                print(f"[deploy_gc_container] Could not load tools from DB: {e}", file=sys.stderr, flush=True)

            # ALWAYS also load from Python modules (merging, not replacing)
            # This ensures tools defined in agent modules (like interface_agent) are available
            try:
                from db_light.duckdb_models.agent_tools_loader import build_tool_mappings_from_all_agents
                module_tool_mapping = build_tool_mappings_from_all_agents()
                # Merge: module tools fill in gaps not covered by DB
                for tool_name, tool_info in module_tool_mapping.items():
                    if tool_name not in db_tool_mapping:
                        db_tool_mapping[tool_name] = tool_info
                print(f"[deploy_gc_container] After merging with agent modules: {len(db_tool_mapping)} total tools", file=sys.stderr, flush=True)
            except Exception as e:
                print(f"[deploy_gc_container] Could not load tool mappings from agents: {e}", file=sys.stderr, flush=True)

            print(f"[deploy_gc_container] DEBUG: db_tool_mapping keys = {list(db_tool_mapping.keys())}", file=sys.stderr, flush=True)
            for tool in tools_list:
                tool_name = tool.get("name", "")
                print(f"[deploy_gc_container] DEBUG: Checking tool '{tool_name}' in db_tool_mapping...", file=sys.stderr, flush=True)
                if tool_name in db_tool_mapping:
                    gc_tools.append({
                        "name": tool_name,
                        **db_tool_mapping[tool_name]
                    })
                    print(f"[deploy_gc_container] DEBUG: ✓ Tool '{tool_name}' FOUND: {db_tool_mapping[tool_name]}", file=sys.stderr, flush=True)
                else:
                    print(f"[deploy_gc_container] Warning: Tool '{tool_name}' NOT found in mappings", file=sys.stderr, flush=True)

            print(f"[deploy_gc_container] DEBUG: gc_tools count = {len(gc_tools)}", file=sys.stderr, flush=True)
            print(f"[deploy_gc_container] DEBUG: gc_tools = {gc_tools}", file=sys.stderr, flush=True)

            # NO FALLBACKS - tools MUST come from the diagram canvas
            if not gc_tools:
                self.gc_deploying = False
                self.generated_diagram_json = f"❌ Error: No tools found in diagram for agent '{agent_name}'. Add tools to the canvas and connect them to the agent."
                yield
                return

            # Generate unique service name
            import uuid as uuid_mod
            import re as re_mod

            agent_slug = re_mod.sub(r'[^a-z0-9-]', '', agent_name.lower().replace(' ', '-'))[:20]
            short_uuid = str(uuid_mod.uuid4())[:8]
            gc_service_name = f"finbuddy-{agent_slug}-{short_uuid}"[:63]
            gc_image_name = gc_service_name  # Image name matches service name

            print(f"[deploy_gc_container] Generated unique service/image name: {gc_service_name}", file=sys.stderr, flush=True)

            # =================================================================
            # STEP 1: Prepare build context (like local container build)
            # =================================================================
            self.generated_diagram_json = f"☁️ Step 1/4: Preparing build context...\n\nAgent: {agent_name}\nTools: {', '.join([t['name'] for t in gc_tools])}\n"
            yield

            # Get project root and template directory
            project_root = Path(__file__).parent.parent
            template_dir = project_root / "db_light" / "agents" / "mcp_server_data_exploration" / "src" / "mcp_server_ds"

            # Create temp build directory
            build_dir = Path(tempfile.mkdtemp(prefix=f"gc_build_{agent_slug}_"))
            print(f"[deploy_gc_container] Build directory: {build_dir}", file=sys.stderr, flush=True)

            try:
                # Check if fast Dockerfile exists (uses pre-built base image)
                # Fast build: ~1-2 min vs ~10 min for full build
                dockerfile_fast = project_root / "cloud_deploy" / "Dockerfile.cloud.agent.fast"
                dockerfile_slow = project_root / "cloud_deploy" / "Dockerfile.cloud.agent"

                if dockerfile_fast.exists():
                    # Use fast Dockerfile (no need for pyproject.toml - deps are in base image)
                    shutil.copy(dockerfile_fast, build_dir / "Dockerfile.agent_server")
                    print(f"[deploy_gc_container] Using FAST Dockerfile (pre-built base image)", file=sys.stderr, flush=True)
                else:
                    # Fallback to slow Dockerfile (installs all deps)
                    # Copy pyproject.cloud.toml as pyproject.toml
                    pyproject_src = project_root / "cloud_deploy" / "pyproject.cloud.toml"
                    shutil.copy(pyproject_src, build_dir / "pyproject.toml")
                    print(f"[deploy_gc_container] Copied pyproject.cloud.toml", file=sys.stderr, flush=True)

                    shutil.copy(dockerfile_slow, build_dir / "Dockerfile.agent_server")
                    print(f"[deploy_gc_container] Using SLOW Dockerfile (full dependency install)", file=sys.stderr, flush=True)

                # Copy cloudbuild.yaml (use fast config if fast Dockerfile exists)
                cloudbuild_fast = project_root / "cloud_deploy" / "cloudbuild.agent.fast.yaml"
                cloudbuild_slow = project_root / "cloud_deploy" / "cloudbuild.agent.yaml"

                if dockerfile_fast.exists() and cloudbuild_fast.exists():
                    shutil.copy(cloudbuild_fast, build_dir / "cloudbuild.yaml")
                    print(f"[deploy_gc_container] Using FAST cloudbuild config (with caching)", file=sys.stderr, flush=True)
                else:
                    shutil.copy(cloudbuild_slow, build_dir / "cloudbuild.yaml")
                    print(f"[deploy_gc_container] Using standard cloudbuild config", file=sys.stderr, flush=True)

                # Copy template files
                for item in ['server_template.py', 'agent_template.py', 'websocket_socks5_patch.py', 'example_api.py', 'unified_response.py']:
                    src = template_dir / item
                    if src.exists():
                        shutil.copy(src, build_dir / item)
                        print(f"[deploy_gc_container] Copied {item}", file=sys.stderr, flush=True)
                    else:
                        print(f"[deploy_gc_container] WARNING: {item} not found at {src}", file=sys.stderr, flush=True)
                
                # CRITICAL: Explicitly verify websocket_socks5_patch.py was copied
                websocket_patch_dst = build_dir / "websocket_socks5_patch.py"
                if not websocket_patch_dst.exists():
                    print(f"[deploy_gc_container] ERROR: websocket_socks5_patch.py NOT in build directory!", file=sys.stderr, flush=True)
                    print(f"[deploy_gc_container] Attempting explicit copy...", file=sys.stderr, flush=True)
                    websocket_patch_src = template_dir / "websocket_socks5_patch.py"
                    if websocket_patch_src.exists():
                        shutil.copy(websocket_patch_src, websocket_patch_dst)
                        print(f"[deploy_gc_container] Explicit copy succeeded", file=sys.stderr, flush=True)
                    else:
                        print(f"[deploy_gc_container] FATAL: Source file does not exist at {websocket_patch_src}", file=sys.stderr, flush=True)
                else:
                    print(f"[deploy_gc_container] ✓ Verified websocket_socks5_patch.py in build directory", file=sys.stderr, flush=True)

                # Copy all tool directories (papers/, web_rifraf/, etc.)
                # Create empty dirs for missing ones (Docker COPY requires directories to exist)
                tool_dirs = ['papers', 'web_rifraf', 'equity_analyst', 'FI_analyst', 'asset_allocation', 'portfolio_manager', 'super_pm', 'data_analyst', 'chart_agent']
                for tool_dir in tool_dirs:
                    src = template_dir / tool_dir
                    dst = build_dir / tool_dir
                    if src.exists():
                        shutil.copytree(src, dst, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
                        print(f"[deploy_gc_container] Copied {tool_dir}/", file=sys.stderr, flush=True)
                    else:
                        # Create empty directory with __init__.py so Docker COPY works
                        dst.mkdir(parents=True, exist_ok=True)
                        (dst / "__init__.py").write_text("# Placeholder\n")
                        print(f"[deploy_gc_container] Created empty {tool_dir}/", file=sys.stderr, flush=True)

                # Copy YourIndexingAI module
                yourindexingai_src = project_root / "YourIndexingAI"
                if yourindexingai_src.exists():
                    shutil.copytree(yourindexingai_src, build_dir / "YourIndexingAI",
                                   ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.git'))
                    print(f"[deploy_gc_container] Copied YourIndexingAI/", file=sys.stderr, flush=True)

                # Copy db_light/message_queue for messaging support
                db_light_src = project_root / "db_light" / "message_queue"
                if db_light_src.exists():
                    db_light_dst = build_dir / "db_light" / "message_queue"
                    db_light_dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(db_light_src, db_light_dst, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
                    # Create __init__.py for db_light package
                    (db_light_dst.parent / "__init__.py").write_text("# db_light package\n")
                    print(f"[deploy_gc_container] Copied db_light/message_queue/", file=sys.stderr, flush=True)

                # Copy db_light/data_onboarding for dataset registry support (data_analyst tools)
                data_onboarding_src = project_root / "db_light" / "data_onboarding"
                if data_onboarding_src.exists():
                    data_onboarding_dst = build_dir / "db_light" / "data_onboarding"
                    shutil.copytree(data_onboarding_src, data_onboarding_dst, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
                    print(f"[deploy_gc_container] Copied db_light/data_onboarding/", file=sys.stderr, flush=True)

                # Copy permission_db/postgres for PostgreSQL connection support
                # Required by trading_agent/position_manager and other tools that access the database
                permission_db_src = project_root / "permission_db"
                if permission_db_src.exists():
                    permission_db_dst = build_dir / "permission_db"
                    shutil.copytree(permission_db_src, permission_db_dst, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.md', 'docker-compose*', '*.sh'))
                    print(f"[deploy_gc_container] Copied permission_db/", file=sys.stderr, flush=True)

                # Check for GUI page entity (like local container does)
                gui_page_name = None
                gui_entity = next((e for e in entities if e.get("type") == "gui"), None)
                if gui_entity:
                    gui_page_name = gui_entity.get("name", "")
                    print(f"[deploy_gc_container] Found GUI entity: {gui_page_name}", file=sys.stderr, flush=True)

                # Generate start_cloud.sh (similar to local start.sh)
                tools_json = json.dumps(gc_tools)

                # Build environment variable exports for start.sh
                env_exports = f'''# Cloud Run sets PORT env var
export AGENT_PORT=${{PORT:-8080}}
export MCP_PORT=8222

# Agent configuration
export AGENT_NAME="{agent_name}"
export AGENT_MODULE="{agent_module}"
export AGENT_MODEL="{main_agent.get("model", "gpt-4o")}"
export MAX_ITERATIONS=50
export SUPERAGENT_MODE="{str(superagent_mode).lower()}"
export TOOLS_LIST='{tools_json}'

# Infrastructure configuration (matching local container)
export RUNNING_IN_DOCKER="true"
export PYTHONPATH="/app:/app/db_light:/app/db_light/agents/mcp_server_data_exploration/src/mcp_server_ds"

# Redis configuration (will be set via Cloud Run env vars)
export REDIS_HOST="${{REDIS_HOST:-redis}}"
export REDIS_PORT="${{REDIS_PORT:-6379}}"

# S3 configuration
export S3_CUSTOM_DOMAIN="${{S3_CUSTOM_DOMAIN:-papers.finbuddygroup.com}}"

# Storage configuration
export STORAGE_CONFIG_JSON="${{STORAGE_CONFIG_JSON:-/app/YourIndexingAI/config.json}}"

# Backend WebSocket connection (will be configured via sidecar later)
export BACKEND_HOST="${{BACKEND_HOST:-localhost}}"
export BACKEND_PORT="${{BACKEND_PORT:-8008}}"
'''

                # Add GUI_PAGE if present
                if gui_page_name:
                    env_exports += f'\n# GUI Page configuration\nexport GUI_PAGE="{gui_page_name}"\n'

                # =================================================================
                # BUILD START SCRIPT BASED ON SUPERAGENT MODE
                # =================================================================
                if superagent_mode and subagents:
                    # SUPERAGENT MODE: Start subagents first, then main agent
                    print(f"[deploy_gc_container] Generating SUPERAGENT start_cloud.sh with {len(subagents)} subagents", file=sys.stderr, flush=True)

                    # Build subagent startup commands
                    subagent_startup_commands = ""
                    subagent_pids = []

                    for idx, sa in enumerate(subagents):
                        sa_name = sa['name']
                        sa_port = sa['port']
                        sa_module = sa['module']
                        sa_tools = sa['tools']
                        sa_mcp_tool_name = sa['mcp_tool_name']
                        has_nested = len(sa.get('nested_subagents', [])) > 0

                        # Build tools list for this subagent
                        sa_tools_list = []
                        for tool_name in sa_tools:
                            if tool_name in db_tool_mapping:
                                tool_mapping = db_tool_mapping[tool_name].copy()

                                # Context-aware tool resolution (same as local test run)
                                if tool_name == "input_transform":
                                    if sa_name == "FI Analyst":
                                        tool_mapping = {"api_module": "FI_analyst.FI_input_transform", "api_function": "input_transform"}
                                    elif sa_name == "Equity Analyst":
                                        tool_mapping = {"api_module": "equity_analyst.equity_input_transform", "api_function": "input_transform"}

                                sa_tools_list.append({
                                    "name": tool_name,
                                    **tool_mapping
                                })
                        sa_tools_json = json.dumps(sa_tools_list).replace('"', '\\"')

                        pid_var = f"SUBAGENT_{idx}_PID"
                        subagent_pids.append(pid_var)

                        if has_nested:
                            # Middle agent with nested subagents - use agent_template in MCP server mode
                            nested_list = sa['nested_subagents']
                            nested_mcp_config = {'servers': {}}
                            for nested in nested_list:
                                nested_server_name = nested['mcp_server_name']
                                nested_port = nested['port']
                                nested_mcp_config['servers'][nested_server_name] = {
                                    'url': f"http://localhost:{nested_port}/sse/",
                                    'tools': []
                                }
                            nested_mcp_config_json = json.dumps(nested_mcp_config).replace('"', '\\"')

                            subagent_startup_commands += f'''
echo "[$(date)] Starting MIDDLE AGENT: {sa_name} on port {sa_port}..."
python agent_template.py \\
    --mode mcp_server \\
    --port {sa_port} \\
    --mcp-tool-name "{sa_mcp_tool_name}" \\
    --agent-name "{sa_name}" \\
    --agent-module "{sa_module}" \\
    --model "$AGENT_MODEL" \\
    --max-iterations 50 \\
    --superagent-mode \\
    --mcp-servers-config "{nested_mcp_config_json}" &
{pid_var}=$!
echo "[$(date)] {sa_name} started with PID: ${pid_var}"
'''
                        else:
                            # Leaf agent - use server_template for simple tool wrapping
                            subagent_startup_commands += f'''
echo "[$(date)] Starting SUBAGENT: {sa_name} on port {sa_port}..."
python server_template.py \\
    --port {sa_port} \\
    --tools-list "{sa_tools_json}" \\
    --transport sse &
{pid_var}=$!
echo "[$(date)] {sa_name} started with PID: ${pid_var}"
'''

                    # Build MCP_SERVERS_CONFIG for main superagent
                    # Match local behavior: include all subagents (direct + nested)
                    # This allows main agent to connect to all subagents in the hierarchy
                    mcp_servers_config = {'servers': {}}
                    for sa in subagents:
                        server_name = sa['mcp_server_name']
                        mcp_servers_config['servers'][server_name] = {
                            'url': f"http://localhost:{sa['port']}/sse/",
                            'tools': []
                        }
                    mcp_servers_config_json = json.dumps(mcp_servers_config).replace('"', '\\"')

                    start_sh_content = f'''#!/bin/bash
set -e

echo "========================================="
echo "Starting Cloud SUPERAGENT Container"
echo "========================================="
echo "Main Agent: {agent_name}"
echo "Module: {agent_module}"
echo "Model: {main_agent.get("model", "gpt-4o")}"
echo "Agent Port: ${{PORT:-8080}}"
echo "Subagents: {len(subagents)}"
echo "========================================="

{env_exports}

# =================================================================
# STEP 1: Start all subagent processes (deepest first)
# =================================================================
echo "[$(date)] Starting {len(subagents)} subagent processes..."
{subagent_startup_commands}

# Wait for subagents to initialize
echo "[$(date)] Waiting 10 seconds for subagents to initialize..."
sleep 10

# =================================================================
# STEP 2: Start main agent's MCP server (if it has direct tools)
# =================================================================
'''
                    # Only start main MCP server if main agent has direct tools
                    if gc_tools:
                        start_sh_content += f'''
echo "[$(date)] Starting main agent MCP Server on port $MCP_PORT..."
python server_template.py \\
    --port $MCP_PORT \\
    --tools-list "$TOOLS_LIST" \\
    --transport sse &
MCP_PID=$!
echo "[$(date)] MCP Server started with PID: $MCP_PID"
sleep 3
'''

                    start_sh_content += f'''
# =================================================================
# STEP 3: Start main SUPERAGENT (connects to all subagents)
# =================================================================
echo "[$(date)] Starting main SUPERAGENT on port $AGENT_PORT..."
export MCP_SERVERS_CONFIG="{mcp_servers_config_json}"

python agent_template.py \\
    --port $AGENT_PORT \\
    --model $AGENT_MODEL \\
    --max-iterations $MAX_ITERATIONS \\
    --agent-name "$AGENT_NAME" \\
    --agent-module $AGENT_MODULE \\
    --superagent-mode \\
    --mcp-servers-config "$MCP_SERVERS_CONFIG" &

AGENT_PID=$!
echo "[$(date)] Main Agent started with PID: $AGENT_PID"

# Wait for agent to be ready (it has /health endpoint)
echo "[$(date)] Waiting for Agent health check..."
MAX_ATTEMPTS=90
ATTEMPT=0
until curl -f http://localhost:$AGENT_PORT/health > /dev/null 2>&1; do
    ATTEMPT=$((ATTEMPT + 1))
    if [ $ATTEMPT -ge $MAX_ATTEMPTS ]; then
        echo "[$(date)] ERROR: Agent failed to start within timeout"
        exit 1
    fi
    if [ $((ATTEMPT % 10)) -eq 0 ]; then
        echo "[$(date)] Still waiting... (attempt $ATTEMPT/$MAX_ATTEMPTS)"
    fi
    sleep 1
done

echo "[$(date)] ✓ Superagent is ready and responding on port $AGENT_PORT!"
echo "[$(date)] ✓ Container startup complete"

# Keep all processes running and monitor them
wait -n
EXIT_CODE=$?
echo "[$(date)] ERROR: A process exited with code $EXIT_CODE"
exit $EXIT_CODE
'''
                else:
                    # SINGLE AGENT MODE: Original behavior
                    print(f"[deploy_gc_container] Generating SINGLE AGENT start_cloud.sh", file=sys.stderr, flush=True)

                    start_sh_content = f'''#!/bin/bash
set -e

echo "========================================="
echo "Starting Cloud Agent Container"
echo "========================================="
echo "Agent: {agent_name}"
echo "Module: {agent_module}"
echo "Model: {main_agent.get("model", "gpt-4o")}"
echo "Agent Port: ${{PORT:-8080}}"
echo "========================================="

{env_exports}

echo "[$(date)] Starting MCP Server on port $MCP_PORT..."
python server_template.py \\
    --port $MCP_PORT \\
    --tools-list "$TOOLS_LIST" \\
    --transport sse &

MCP_PID=$!
echo "[$(date)] MCP Server started with PID: $MCP_PID"

# Start Agent immediately (it will retry MCP connection)
echo "[$(date)] Starting Agent on port $AGENT_PORT..."
python agent_template.py \\
    --port $AGENT_PORT \\
    --mcp-server-name generic-mcp-server \\
    --mcp-server-url http://localhost:$MCP_PORT/sse/ \\
    --model $AGENT_MODEL \\
    --max-iterations $MAX_ITERATIONS \\
    --agent-name "$AGENT_NAME" \\
    --agent-module $AGENT_MODULE \\
    --tools-info "$TOOLS_LIST" &

AGENT_PID=$!
echo "[$(date)] Agent started with PID: $AGENT_PID"

# Wait for agent to be ready (it has /health endpoint)
echo "[$(date)] Waiting for Agent health check..."
MAX_ATTEMPTS=60
ATTEMPT=0
until curl -f http://localhost:$AGENT_PORT/health > /dev/null 2>&1; do
    ATTEMPT=$((ATTEMPT + 1))
    if [ $ATTEMPT -ge $MAX_ATTEMPTS ]; then
        echo "[$(date)] ERROR: Agent failed to start within timeout"
        echo "=== MCP Server Log ==="
        tail -50 /tmp/mcp_server.log
        echo "=== Agent Log ==="
        tail -50 /tmp/agent.log
        exit 1
    fi
    if [ $((ATTEMPT % 10)) -eq 0 ]; then
        echo "[$(date)] Still waiting... (attempt $ATTEMPT/$MAX_ATTEMPTS)"
    fi
    sleep 1
done

echo "[$(date)] ✓ Agent is ready and responding on port $AGENT_PORT!"
echo "[$(date)] ✓ Container startup complete"

# Keep both processes running and monitor them
wait -n
EXIT_CODE=$?
echo "[$(date)] ERROR: A process exited with code $EXIT_CODE"
exit $EXIT_CODE
'''
                start_sh_path = build_dir / "start_cloud.sh"
                start_sh_path.write_text(start_sh_content)
                os.chmod(start_sh_path, 0o755)
                print(f"[deploy_gc_container] Created start_cloud.sh", file=sys.stderr, flush=True)

                # =================================================================
                # STEP 2: Submit build to Google Cloud Build
                # =================================================================
                self.generated_diagram_json = f"☁️ Step 2/4: Building container on Google Cloud Build...\n\nThis may take 5-10 minutes...\n\nImage: {gc_image_name}\n"
                yield

                env = os.environ.copy()
                env["PATH"] = f"{os.path.expanduser('~')}/google-cloud-sdk/bin:" + env.get("PATH", "")

                # Run gcloud builds submit
                build_cmd = [
                    "gcloud", "builds", "submit",
                    "--config", "cloudbuild.yaml",
                    f"--substitutions=_IMAGE_NAME={gc_image_name},_IMAGE_TAG=latest",
                    "--project", "finbuddy1",
                    "."
                ]

                print(f"[deploy_gc_container] Running: {' '.join(build_cmd)}", file=sys.stderr, flush=True)

                build_process = await asyncio.create_subprocess_exec(
                    *build_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    env=env,
                    cwd=str(build_dir)
                )

                build_stdout, _ = await build_process.communicate()
                build_output = build_stdout.decode('utf-8') if build_stdout else ""

                if build_process.returncode != 0:
                    self.gc_deploying = False
                    error_output = build_output[-1500:] if len(build_output) > 1500 else build_output
                    self.generated_diagram_json = f"❌ Cloud Build Failed!\n\nExit code: {build_process.returncode}\n\nOutput:\n{error_output}"
                    yield
                    return

                print(f"[deploy_gc_container] Cloud Build completed successfully", file=sys.stderr, flush=True)

                # =================================================================
                # STEP 3: Deploy to Cloud Run
                # =================================================================
                self.generated_diagram_json = f"☁️ Step 3/4: Deploying to Cloud Run...\n\nService: {gc_service_name}\n"
                yield

                # Load secrets from .env
                env_file = project_root / ".env"
                secrets = {}
                if env_file.exists():
                    with open(env_file) as f:
                        for line in f:
                            if '=' in line and not line.startswith('#'):
                                key, _, value = line.strip().partition('=')
                                secrets[key] = value.strip('"').strip("'")
                
                # Debug: Check key configuration
                db_tunnel_host = secrets.get('DB_TUNNEL_HOST', '')
                if db_tunnel_host:
                    print(f"[deploy_gc_container] ✅ DB_TUNNEL_HOST loaded: {db_tunnel_host}", file=sys.stderr, flush=True)
                else:
                    print(f"[deploy_gc_container] ℹ️ DB_TUNNEL_HOST not set - cloudflared sidecar will NOT be added", file=sys.stderr, flush=True)

                # Build env vars for Cloud Run (matching local container environment)
                # Use dict to build env vars, then convert to proper format
                env_vars_dict = {
                    'OPENAI_API_KEY': secrets.get('OPENAI_API_KEY', ''),
                    'OPENROUTER_API_KEY': secrets.get('OPENROUTER_API_KEY', ''),
                    # AWS credentials for S3 uploads
                    'AWS_ACCESS_KEY_ID': secrets.get('AWS_ACCESS_KEY_ID', ''),
                    'AWS_SECRET_ACCESS_KEY': secrets.get('AWS_SECRET_ACCESS_KEY', ''),
                    # Infrastructure configuration (NEW - matching local container)
                    'RUNNING_IN_DOCKER': 'true',
                    'PYTHONPATH': '/app:/app/db_light:/app/db_light/agents/mcp_server_data_exploration/src/mcp_server_ds',
                    # Redis configuration (NEW - for session storage)
                    'REDIS_HOST': secrets.get('REDIS_HOST', 'redis'),
                    'REDIS_PORT': secrets.get('REDIS_PORT', '6379'),
                    'REDIS_USERNAME': secrets.get('REDIS_USERNAME', ''),
                    'REDIS_PASSWORD': secrets.get('REDIS_PASSWORD', ''),
                    # S3 configuration (NEW - for public URLs)
                    'S3_CUSTOM_DOMAIN': 'papers.finbuddygroup.com',
                    # Storage configuration (NEW - for config.json path)
                    'STORAGE_CONFIG_JSON': '/app/YourIndexingAI/config.json',
                    # Backend WebSocket connection
                    # For Tailscale: BACKEND_HOST=100.113.123.27, BACKEND_PORT=8008, BACKEND_USE_SSL=false
                    # For Cloudflare: BACKEND_HOST=xyz.trycloudflare.com, BACKEND_USE_SSL=true
                    'BACKEND_HOST': secrets.get('BACKEND_HOST', '100.113.123.27'),
                    'BACKEND_PORT': secrets.get('BACKEND_PORT', '8008'),
                    'BACKEND_USE_SSL': secrets.get('BACKEND_USE_SSL', 'false'),
                }
                
                # SMTP configuration for email sending
                if secrets.get('SMTP_SERVER'):
                    env_vars_dict.update({
                        'SMTP_SERVER': secrets.get('SMTP_SERVER', ''),
                        'SMTP_PORT': secrets.get('SMTP_PORT', '465'),
                        'SMTP_USERNAME': secrets.get('SMTP_USERNAME', ''),
                        'SMTP_PASSWORD': secrets.get('SMTP_PASSWORD', ''),
                        'SMTP_FROM_EMAIL': secrets.get('SMTP_FROM_EMAIL', ''),
                        'SMTP_USE_TLS': secrets.get('SMTP_USE_TLS', 'false'),
                    })
                
                # CloudAMQP for messaging
                if secrets.get('CLOUDAMQP_URL'):
                    env_vars_dict['CLOUDAMQP_URL'] = secrets.get('CLOUDAMQP_URL', '')

                # PostgreSQL database configuration (for agents that need DB access)
                # Note: DB_HOST is set to 127.0.0.1 because cloudflared sidecar creates local proxy
                # The actual tunnel hostname is in DB_TUNNEL_HOST (used by cloudflared sidecar)
                if secrets.get('DB_TUNNEL_HOST'):
                    env_vars_dict.update({
                        'DB_HOST': '127.0.0.1',  # Connect to local cloudflared proxy
                        'DB_PORT': secrets.get('DB_PORT', '5432'),
                        'DB_NAME': secrets.get('DB_NAME', 'finbuddy_db'),
                        'DB_USER': secrets.get('DB_USER', 'finbuddy_app'),
                        'DB_PASSWORD': secrets.get('DB_PASSWORD', ''),
                    })

                # GUI Page configuration (NEW - if GUI entity exists)
                if gui_page_name:
                    env_vars_dict['GUI_PAGE'] = gui_page_name

                # =================================================================
                # Build Cloud Run service YAML with agent (+ optional cloudflared sidecar)
                # =================================================================
                import yaml

                # Filter out empty values
                filtered_env_vars = {k: v for k, v in env_vars_dict.items() if v}

                skipped_vars = [k for k, v in env_vars_dict.items() if not v]
                if skipped_vars:
                    print(f"[deploy_gc_container] Skipping empty env vars: {', '.join(skipped_vars)}", file=sys.stderr, flush=True)

                # Check if cloudflared sidecar is needed (for PostgreSQL access)
                use_cloudflared = bool(secrets.get('DB_TUNNEL_HOST'))

                if use_cloudflared:
                    print(f"[deploy_gc_container] Building Cloud Run service YAML with cloudflared sidecar (for PostgreSQL)", file=sys.stderr, flush=True)
                else:
                    print(f"[deploy_gc_container] Building Cloud Run service YAML (no sidecar)", file=sys.stderr, flush=True)
                
                image_uri = f"us-central1-docker.pkg.dev/finbuddy1/finbuddy/{gc_image_name}:latest"
                
                # Build Cloud Run service YAML with multi-container support
                cloud_run_service = {
                    "apiVersion": "serving.knative.dev/v1",
                    "kind": "Service",
                    "metadata": {
                        "name": gc_service_name,
                        "labels": {
                            "app": "finbuddy",
                            "component": "agent"
                        },
                        "annotations": {
                            "run.googleapis.com/ingress": "all"
                        }
                    },
                    "spec": {
                        "template": {
                            "metadata": {
                                "annotations": {
                                    "run.googleapis.com/execution-environment": "gen2",
                                    "run.googleapis.com/cpu-throttling": "false",
                                    "autoscaling.knative.dev/minScale": "1"
                                }
                            },
                            "spec": {
                                "containers": self._build_gc_containers(
                                    image_uri=image_uri,
                                    filtered_env_vars=filtered_env_vars,
                                    use_cloudflared=use_cloudflared,
                                    db_tunnel_host=secrets.get('DB_TUNNEL_HOST', 'db.finbuddygroup.com')
                                ),
                                "volumes": [],
                                "containerConcurrency": 10,
                                "timeoutSeconds": 300
                            }
                        }
                    }
                }
                
                # Write service YAML to file
                service_yaml_file = build_dir / "cloud-run-service.yaml"
                with open(service_yaml_file, 'w') as f:
                    yaml.dump(cloud_run_service, f)
                
                print(f"[deploy_gc_container] Created Cloud Run service YAML with {len(filtered_env_vars)} env vars", file=sys.stderr, flush=True)
                
                # Deploy using gcloud run services replace (supports multi-container)
                deploy_cmd = [
                    "gcloud", "run", "services", "replace", str(service_yaml_file),
                    "--project", "finbuddy1",
                    "--region", "us-central1"
                ]
                
                # Set IAM policy to allow unauthenticated access after deployment
                # This is done via a separate command since YAML doesn't support IAM policy
                iam_cmd = [
                    "gcloud", "run", "services", "add-iam-policy-binding", gc_service_name,
                    "--member", "allUsers",
                    "--role", "roles/run.invoker",
                    "--project", "finbuddy1",
                    "--region", "us-central1"
                ]

                sidecar_info = "with cloudflared sidecar" if use_cloudflared else "without sidecar"
                print(f"[deploy_gc_container] Running deploy command ({sidecar_info})...", file=sys.stderr, flush=True)

                deploy_process = await asyncio.create_subprocess_exec(
                    *deploy_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    env=env
                )

                deploy_stdout, _ = await deploy_process.communicate()
                deploy_output = deploy_stdout.decode('utf-8') if deploy_stdout else ""

                if deploy_process.returncode != 0:
                    self.gc_deploying = False
                    # Show more of the error output to see the actual error, not just help text
                    error_output = deploy_output[-2000:] if len(deploy_output) > 2000 else deploy_output
                    # Try to extract the actual error message (before the help text)
                    error_lines = error_output.split('\n')
                    actual_error = []
                    for line in error_lines:
                        if 'ERROR:' in line or 'error:' in line.lower():
                            actual_error.append(line)
                        if line.strip().startswith('usage:') or line.strip().startswith('Usage:'):
                            break  # Stop before help text
                    
                    if actual_error:
                        error_msg = '\n'.join(actual_error[:10])
                    else:
                        error_msg = error_output[:1000]
                    
                    self.generated_diagram_json = f"❌ Cloud Run Deploy Failed!\n\nExit code: {deploy_process.returncode}\n\nError:\n{error_msg}\n\nFull output length: {len(deploy_output)} chars"
                    yield
                    return

                # Set IAM policy to allow unauthenticated access
                print(f"[deploy_gc_container] Setting IAM policy to allow unauthenticated access...", file=sys.stderr, flush=True)
                iam_process = await asyncio.create_subprocess_exec(
                    *iam_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    env=env
                )
                iam_stdout, _ = await iam_process.communicate()
                if iam_process.returncode != 0:
                    print(f"[deploy_gc_container] Warning: Failed to set IAM policy: {iam_stdout.decode('utf-8') if iam_stdout else 'Unknown error'}", file=sys.stderr, flush=True)
                else:
                    print(f"[deploy_gc_container] IAM policy set successfully - service allows unauthenticated access", file=sys.stderr, flush=True)

                # Extract service URL
                import re
                url_match = re.search(r'(https://[a-zA-Z0-9-]+[^\s]+\.run\.app)', deploy_output)
                if url_match:
                    self.gc_service_url = url_match.group(1)
                else:
                    # Try to get URL from gcloud
                    url_cmd = ["gcloud", "run", "services", "describe", gc_service_name,
                              "--region", "us-central1", "--project", "finbuddy1",
                              "--format", "value(status.url)"]
                    url_process = await asyncio.create_subprocess_exec(
                        *url_cmd, stdout=asyncio.subprocess.PIPE, env=env)
                    url_stdout, _ = await url_process.communicate()
                    self.gc_service_url = url_stdout.decode('utf-8').strip() if url_stdout else ""

                # =================================================================
                # STEP 4: Register and complete
                # =================================================================
                self.gc_container_type = "gc"
                gc_container_uuid = str(uuid_mod.uuid4())
                self.agent_container_uuid = gc_container_uuid
                self.gc_deploying = False

                # Register in database
                try:
                    from YourIndexingAI.agents_data.agents_db import create_instance, update_instance_status, get_agent_by_display_name, update_agent

                    # Use self.user.username to match the user_id used in call_agent_container_async lookup
                    user_id = self.user.username 
                    agent_db_record = get_agent_by_display_name(agent_name)
                    agent_db_id = agent_db_record.get('id') if agent_db_record else f"dynamic:{agent_name}"

                    # Build config_json with all relevant info
                    config_json = {
                        "container_uuid": gc_container_uuid,
                        "service_url": self.gc_service_url,
                        "service_name": gc_service_name,
                        "image_name": gc_image_name,
                        "agent_module": agent_module,
                        "display_name": agent_name,
                        "tools": [t['name'] for t in gc_tools],
                        "superagent_mode": superagent_mode
                    }
                    
                    # Add GUI page if present (matching local container)
                    if gui_page_name:
                        config_json["gui_page"] = gui_page_name
                        print(f"[deploy_gc_container] Added gui_page to config: {gui_page_name}", file=sys.stderr, flush=True)
                        
                        # Also update agent's config_json in database (matching local container)
                        if agent_db_record:
                            current_config = agent_db_record.get('config_json', {})
                            current_config['gui_page'] = gui_page_name
                            update_agent(agent_db_id, config_json=current_config)
                            print(f"[deploy_gc_container] Updated agent DB record with gui_page", file=sys.stderr, flush=True)

                    instance_id = create_instance(
                        agent_id=agent_db_id,
                        user_id=user_id,
                        instance_type="gc",
                        address=self.gc_service_url,
                        port=443,
                        container_id=gc_container_uuid[:12],
                        config_json=config_json
                    )
                    update_instance_status(instance_id, "running")
                    print(f"[deploy_gc_container] Registered GC instance in DB: {instance_id}", file=sys.stderr, flush=True)
                except Exception as db_err:
                    print(f"[deploy_gc_container] Warning: Failed to register in DB: {db_err}", file=sys.stderr, flush=True)

                # Success message
                success_msg = f"✅ GC Container Deployed Successfully!\n\n"
                success_msg += f"🌐 Service URL: {self.gc_service_url}\n"
                success_msg += f"📛 Service Name: {gc_service_name}\n"
                success_msg += f"🖼️ Image: {gc_image_name}\n\n"
                success_msg += f"Agent: {agent_name}\n"
                success_msg += f"Tools: {', '.join([t['name'] for t in gc_tools])}\n"
                if gui_page_name:
                    success_msg += f"GUI Page: {gui_page_name}\n"
                success_msg += "\n(Use Call/Stop buttons below to interact)"

                self.generated_diagram_json = success_msg
                yield

            finally:
                # Clean up build directory
                try:
                    shutil.rmtree(build_dir)
                    print(f"[deploy_gc_container] Cleaned up build directory", file=sys.stderr, flush=True)
                except Exception as cleanup_err:
                    print(f"[deploy_gc_container] Warning: Failed to cleanup: {cleanup_err}", file=sys.stderr, flush=True)

        except Exception as e:
            import traceback
            self.gc_deploying = False
            error_msg = f"❌ Error deploying to GC: {str(e)}\n\n{traceback.format_exc()}"
            if len(error_msg) > 1000:
                error_msg = error_msg[:1000] + "..."
            self.generated_diagram_json = error_msg
            yield

    async def run_agent_once_no_container(self):
        """
        Run agent + server template once without creating a container.
        This is for testing the code before containerization.
        """
        import json
        import subprocess
        import asyncio
        import tempfile
        import os
        import sys
        from pathlib import Path
        
        # Check if user is logged in
        if self.user is None:
            self.test_run_result = "❌ Error: User not logged in"
            yield
            return
        
        # Auto-generate diagram JSON if not present
        if not self.generated_diagram_json:
            self.test_run_result = "🔄 Generating diagram JSON first...\n"
            yield
            # Call the generate method (it's an async generator, so we iterate through it)
            async for _ in self.generate_agent_from_diagram():
                pass
            
            # Check if generation succeeded
            if not self.generated_diagram_json:
                self.test_run_result = "❌ Error: Failed to generate diagram JSON. Please add agents to the canvas first."
                yield
                return
            
            self.test_run_result += "✓ Diagram JSON generated successfully\n\n"
            yield
        
        # Check if we have instructions
        if not self.test_run_instructions:
            self.test_run_result = "❌ Error: Please enter test instructions"
            yield
            return
        
        try:
            import requests
            
            self.test_run_result = "🔄 Starting test run...\n"
            yield
            
            # Parse diagram JSON to get agent configuration
            diagram_data = json.loads(self.generated_diagram_json)
            
            # Handle NEW format (entities/connections) or OLD format (agent_template)
            entities = diagram_data.get("entities", [])
            if entities:
                # NEW FORMAT: Find the main agent (mode=fastapi)
                main_agent = next((e for e in entities if e.get("type") == "agent" and e.get("mode") == "fastapi"), None)
                if not main_agent:
                    # If no fastapi agent, use first agent
                    main_agent = next((e for e in entities if e.get("type") == "agent"), None)
                
                if not main_agent:
                    self.test_run_result = "❌ Error: No agent found in diagram JSON"
                    yield
                    return
                
                agent_name = main_agent.get("name", "test_agent")
                agent_module = main_agent.get("agent_module", "")

                # Extract connected datasources (for data_analyst agent)
                connected_datasources = main_agent.get("connected_datasources", [])
                if connected_datasources:
                    print(f"[run_agent_once_no_container] Found {len(connected_datasources)} connected datasources for agent {agent_name}", file=sys.stderr, flush=True)
                    for ds in connected_datasources:
                        print(f"  - Datasource: {ds.get('dataset_name')} at {ds.get('dataset_path')}", file=sys.stderr, flush=True)

                # Get connections
                connections = diagram_data.get("connections", [])
                
                # Check if this is a superagent (has agent-to-agent connections)
                # RECURSIVE: Find ALL subagents including nested ones (for 3-level chains)
                def find_all_subagents_recursive(source_agent_name, depth=0):
                    """Recursively find all subagents (direct and nested)"""
                    found_subagents = []
                    agent_conns = [c for c in connections if c.get("source_id") == source_agent_name and c.get("connection_type") == "agent"]

                    for conn in agent_conns:
                        subagent_name = conn.get("target_id")
                        subagent_entity = next((e for e in entities if e.get("name") == subagent_name and e.get("type") == "agent"), None)
                        if subagent_entity:
                            # Get tools for this subagent
                            subagent_tool_connections = [c for c in connections if c.get("source_id") == subagent_name and c.get("connection_type") == "tool"]
                            subagent_tools = [c.get("target_id", "").split("_", 1)[-1] for c in subagent_tool_connections]

                            # Check if this subagent has its own subagents (nested)
                            nested_subagents_list = find_all_subagents_recursive(subagent_name, depth + 1)

                            found_subagents.append({
                                "name": subagent_name,
                                "module": subagent_entity.get("agent_module", ""),
                                "port": conn.get("port", 18300),
                                "mcp_server_name": conn.get("mcp_server_name", ""),
                                "mcp_tool_name": conn.get("mcp_tool_name", ""),
                                "tools": subagent_tools,
                                "nested_subagents": nested_subagents_list,  # Store nested subagents
                                "parent": source_agent_name,  # Track parent for debugging
                                "depth": depth  # Track depth for sorting
                            })

                            # Add nested subagents to the flat list (for server startup)
                            found_subagents.extend(nested_subagents_list)

                    return found_subagents

                agent_connections = [c for c in connections if c.get("source_id") == agent_name and c.get("connection_type") == "agent"]
                subagents = []
                if agent_connections:
                    # This is a superagent! Find all subagents recursively
                    subagents = find_all_subagents_recursive(agent_name)

                    # Sort by depth (deepest first) to ensure bottom-up server startup
                    subagents.sort(key=lambda x: x.get('depth', 0), reverse=True)
                
                # Get tools connected directly to main agent
                tool_connections = [c for c in connections if c.get("source_id") == agent_name and c.get("connection_type") == "tool"]
                tools = [c.get("target_id", "").split("_", 1)[-1] for c in tool_connections]  # Remove agent prefix
            else:
                # OLD FORMAT: agent_template
                agent_template_data = diagram_data.get("agent_template", [])
                if not agent_template_data or len(agent_template_data) == 0:
                    self.test_run_result = "❌ Error: No agent template in diagram JSON"
                    yield
                    return
                
                agent_config = agent_template_data[0]
                agent_name = agent_config.get("name", "test_agent")
                tools = agent_config.get("tools", [])
            
            self.test_run_result += f"📋 Agent: {agent_name}\n"
            if 'subagents' in locals() and subagents:
                self.test_run_result += f"🔗 Superagent with {len(subagents)} subagents:\n"
                for sa in subagents:
                    self.test_run_result += f"   • {sa['name']} (port {sa['port']}, {len(sa['tools'])} tools)\n"
            self.test_run_result += f"🔧 Direct Tools: {', '.join(tools) if tools else 'none'}\n\n"
            yield
            
            # Determine paths - use local paths since we're not in container
            template_dir = Path(__file__).parent.parent / "db_light" / "agents" / "mcp_server_data_exploration" / "src" / "mcp_server_ds"
            
            if not template_dir.exists():
                self.test_run_result += f"❌ Error: Template directory not found: {template_dir}\n"
                yield
                return
            
            agent_template_path = template_dir / "agent_template.py"
            server_template_path = template_dir / "server_template.py"
            
            if not agent_template_path.exists():
                self.test_run_result += f"❌ Error: agent_template.py not found\n"
                yield
                return
            
            if not server_template_path.exists():
                self.test_run_result += f"❌ Error: server_template.py not found\n"
                yield
                return
            
            self.test_run_result += "✅ Template files found\n\n"
            yield
            
            # Get tool mappings dynamically from all agent modules (loads from database)
            from db_light.duckdb_models.agent_tools_loader import build_tool_mappings_from_all_agents, get_agent_mappings_from_db
            TOOL_MAPPINGS = build_tool_mappings_from_all_agents()

            # Get agent module from database - NO STATIC FALLBACK
            if 'agent_module' not in locals() or not agent_module:
                agent_mappings = get_agent_mappings_from_db()
                if agent_name in agent_mappings:
                    agent_module = agent_mappings[agent_name]
                    print(f"[run_agent_once_no_container] Loaded agent_module from DB: {agent_module}", file=sys.stderr, flush=True)
                else:
                    error_msg = f"Agent '{agent_name}' not found in database. Available: {list(agent_mappings.keys())}"
                    print(f"[run_agent_once_no_container] ERROR: {error_msg}", file=sys.stderr, flush=True)
                    self.test_run_result += f"❌ {error_msg}\n"
                    yield
                    return
            
            # Build tools list
            tools_list = []
            for tool_name in tools:
                if tool_name in TOOL_MAPPINGS:
                    tool_mapping = TOOL_MAPPINGS[tool_name]
                    
                    # Context-aware tool resolution for input_transform
                    # Both Equity and FI analysts use input_transform but with different modules
                    if tool_name == "input_transform":
                        if agent_name == "FI Analyst" or agent_module == "FI_analyst.FI_agent":
                            tool_mapping = {
                                "api_module": "FI_analyst.FI_input_transform",
                                "api_function": "input_transform"
                            }
                        elif agent_name == "Equity Analyst" or agent_module == "equity_analyst.equity_agent":
                            tool_mapping = {
                                "api_module": "equity_analyst.equity_input_transform",
                                "api_function": "input_transform"
                            }
                    
                    tools_list.append({
                        "name": tool_name,
                        "api_module": tool_mapping["api_module"],
                        "api_function": tool_mapping["api_function"]
                    })
            
            if not tools_list:
                # Default tool
                tools_list = [{
                    "name": "stock_metrics",
                    "api_module": "example_api",
                    "api_function": "calculate_stock_metrics"
                }]
            
            tools_info = json.dumps(tools_list)
            
            self.test_run_result += f"🔧 Tools configured: {len(tools_list)} tool(s)\n"
            yield
            
            # Use available ports for local testing
            mcp_port = 18222  # Different from Docker ports to avoid conflicts
            agent_port = 18000
            
            # Get OpenAI API key from environment
            openai_key = os.environ.get('OPENAI_API_KEY', '')
            if not openai_key:
                self.test_run_result += "❌ Error: OPENAI_API_KEY not found in environment\n"
                yield
                return
            
            # CRITICAL: Set PYTHONPATH to include finbuddy root so YourIndexingAI module can be imported
            finbuddy_root = Path(__file__).parent.parent  # /home/riccardo247/YourIndexingAI/finbuddy
            current_pythonpath = os.environ.get('PYTHONPATH', '')
            new_pythonpath = f"{finbuddy_root}:{template_dir}:{current_pythonpath}" if current_pythonpath else f"{finbuddy_root}:{template_dir}"
            
            # Path to config.json for YourIndexingAI module
            config_json_path = finbuddy_root / "YourIndexingAI" / "config.json"
            
            # Optional: Create log files for debugging
            import tempfile
            log_dir = Path(tempfile.gettempdir()) / "finbuddy_test_run"
            log_dir.mkdir(exist_ok=True)
            
            # Track all started processes for cleanup
            started_processes = []
            
            # If this is a superagent, start subagent MCP servers first
            if 'subagents' in locals() and subagents:
                self.test_run_result += f"\n🚀 Starting {len(subagents)} subagent MCP servers...\n"
                self.test_run_result += f"🧹 Cleaning up any existing processes on ports...\n"
                yield
                
                # Kill any existing processes on the ports we need
                import subprocess as sp
                for subagent in subagents:
                    port = subagent['port']
                    try:
                        # Find and kill process using this port
                        result = sp.run(['lsof', '-ti', f':{port}'], capture_output=True, text=True)
                        if result.stdout.strip():
                            pids = result.stdout.strip().split('\n')
                            for pid in pids:
                                try:
                                    sp.run(['kill', '-9', pid], check=False)
                                    self.test_run_result += f"   Killed old process on port {port} (PID: {pid})\n"
                                except:
                                    pass
                    except:
                        pass
                
                yield
                
                for subagent in subagents:
                    sa_name = subagent['name']
                    sa_port = subagent['port']
                    sa_tools = subagent['tools']
                    
                    # Build tools list for subagent
                    sa_tools_list = []
                    for tool_name in sa_tools:
                        if tool_name in TOOL_MAPPINGS:
                            tool_mapping = TOOL_MAPPINGS[tool_name].copy()
                            
                            # Context-aware tool resolution
                            if tool_name == "input_transform":
                                if sa_name == "FI Analyst":
                                    tool_mapping = {"api_module": "FI_analyst.FI_input_transform", "api_function": "input_transform"}
                                elif sa_name == "Equity Analyst":
                                    tool_mapping = {"api_module": "equity_analyst.equity_input_transform", "api_function": "input_transform"}
                            
                            sa_tools_list.append({
                                "name": tool_name,
                                "api_module": tool_mapping["api_module"],
                                "api_function": tool_mapping["api_function"]
                            })
                    
                    sa_tools_info = json.dumps(sa_tools_list)
                    
                    # Start subagent MCP server
                    self.test_run_result += f"   Starting {sa_name} on port {sa_port}...\n"
                    yield
                    
                    sa_module = subagent['module']  # Get agent module from subagent config
                    
                    sa_env = os.environ.copy()
                    sa_env.update({
                        'MCP_PORT': str(sa_port),
                        'TOOLS_LIST': sa_tools_info,
                        'AGENT_MODULE': sa_module,  # Pass agent module so server loads correct prompt
                        'OPENAI_API_KEY': openai_key,
                        'REDIS_HOST': 'localhost',
                        'REDIS_PORT': '6379',
                        'RUNNING_IN_DOCKER': 'false',
                        'PYTHONPATH': new_pythonpath,
                        'STORAGE_CONFIG_JSON': str(config_json_path),
                        'S3_CUSTOM_DOMAIN': 'papers.finbuddygroup.com'
                    })

                    # If this subagent has nested subagents, enable SUPERAGENT_MODE and build MCP config
                    if subagent.get('nested_subagents'):
                        nested_list = subagent['nested_subagents']
                        self.test_run_result += f"      (This is a middle agent with {len(nested_list)} nested subagents - enabling SUPERAGENT_MODE)\n"
                        yield

                        # Build MCP_SERVERS_CONFIG for this middle agent
                        mcp_servers_config = {'servers': {}}
                        for nested in nested_list:
                            nested_server_name = nested['mcp_server_name']
                            nested_port = nested['port']
                            nested_tool_name = nested['mcp_tool_name']

                            mcp_servers_config['servers'][nested_server_name] = {
                                'url': f"http://localhost:{nested_port}/sse/",
                                'tools': [{
                                    'name': nested_tool_name,
                                    'description': f"Execute {nested['name']} agent",
                                    'schema': {}
                                }]
                            }

                        sa_env['SUPERAGENT_MODE'] = 'true'
                        sa_env['MCP_SERVERS_CONFIG'] = json.dumps(mcp_servers_config)
                        self.test_run_result += f"      MCP config: {len(mcp_servers_config['servers'])} nested servers\n"
                        yield
                    
                    sa_log = log_dir / f"subagent_{sa_name.replace(' ', '_')}_{sa_port}.log"
                    sa_log_file = open(sa_log, 'w')

                    # Middle agents (with nested subagents) need agent_template for superagent mode
                    # Leaf agents use server_template for simple tool wrapping
                    if subagent.get('nested_subagents'):
                        # Middle agent: Use agent_template.py in MCP server mode
                        sa_env['AGENT_MODE'] = 'mcp_server'  # Run as MCP server
                        sa_env['AGENT_PORT'] = str(sa_port)
                        sa_env['MCP_TOOL_NAME'] = subagent['mcp_tool_name']
                        sa_env['AGENT_MODEL'] = 'gpt-4o'  # Use full model for middle agents
                        sa_env['MAX_ITERATIONS'] = '50'  # Allow sufficient iterations

                        sa_process = subprocess.Popen(
                            ['python', str(agent_template_path)],
                            env=sa_env,
                            stdout=sa_log_file,
                            stderr=subprocess.STDOUT,
                            text=True,
                            cwd=str(template_dir)
                        )
                    else:
                        # Leaf agent: Use server_template.py for tool wrapping
                        sa_process = subprocess.Popen(
                            ['python', str(server_template_path),
                             '--port', str(sa_port),
                             '--tools-list', sa_tools_info,
                             '--transport', 'sse'],
                            env=sa_env,
                            stdout=sa_log_file,
                            stderr=subprocess.STDOUT,
                            text=True,
                            cwd=str(template_dir)
                        )
                    
                    started_processes.append((sa_process, sa_log_file, sa_name))
                    
                    # Wait longer for MCP server to fully initialize
                    await asyncio.sleep(10)
                    
                    if sa_process.poll() is not None:
                        sa_log_file.close()  # Close file before reading
                        self.test_run_result += f"   ❌ {sa_name} failed to start (exit code: {sa_process.returncode})\n"
                        # Read log to see what went wrong
                        try:
                            with open(sa_log, 'r') as f:
                                log_content = f.read()
                                if log_content:
                                    self.test_run_result += f"   Last 500 chars of log:\n{log_content[-500:]}\n"
                        except Exception as e:
                            self.test_run_result += f"   Could not read log: {e}\n"
                    else:
                        # Try to verify server is responding
                        try:
                            health_check = requests.get(f'http://localhost:{sa_port}/health', timeout=2)
                            if health_check.status_code == 200:
                                self.test_run_result += f"   ✅ {sa_name} started and healthy (PID: {sa_process.pid})\n"
                            else:
                                self.test_run_result += f"   ⚠️ {sa_name} started but health check failed (PID: {sa_process.pid})\n"
                        except:
                            self.test_run_result += f"   ✅ {sa_name} started (PID: {sa_process.pid}, health check unavailable)\n"
                    yield
                
                self.test_run_result += f"\n✅ All subagent servers started\n"
                self.test_run_result += f"⏳ Waiting for servers to fully initialize...\n\n"
                yield
                
                # Give extra time for all servers to be fully ready
                await asyncio.sleep(10)
            
            # Start main agent's MCP server (if it has direct tools)
            server_process = None
            server_log_file = None
            if tools:
                self.test_run_result += f"\n🚀 Starting main agent MCP server on port {mcp_port}...\n"
                yield
                
                server_env = os.environ.copy()
                server_env.update({
                    'MCP_PORT': str(mcp_port),
                    'TOOLS_LIST': tools_info,
                    'OPENAI_API_KEY': openai_key,
                    'REDIS_HOST': 'localhost',
                    'REDIS_PORT': '6379',
                    'RUNNING_IN_DOCKER': 'false',
                    'PYTHONPATH': new_pythonpath,
                    'STORAGE_CONFIG_JSON': str(config_json_path),
                    'S3_CUSTOM_DOMAIN': 'papers.finbuddygroup.com'
                })
                
                server_log = log_dir / f"server_{mcp_port}.log"
                server_log_file = open(server_log, 'w')
                
                server_process = subprocess.Popen(
                    ['python', str(server_template_path), '--port', str(mcp_port), '--tools-list', tools_info, '--transport', 'sse'],
                    env=server_env,
                    stdout=server_log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=str(template_dir)
                )
                
                started_processes.append((server_process, server_log_file, "main_server"))
                await asyncio.sleep(3)
                
                if server_process.poll() is not None:
                    self.test_run_result += f"❌ Main server failed to start\n"
                    yield
                    return
                else:
                    self.test_run_result += f"✅ Main MCP server started (PID: {server_process.pid})\n\n"
                    yield
            else:
                # Superagent with no direct tools - skip MCP server
                self.test_run_result += f"\n📋 Superagent mode - no direct MCP server needed\n\n"
                mcp_port = None
                yield
            
            # Start agent
            self.test_run_result += f"🤖 Starting agent on port {agent_port}...\n"
            yield
            
            # Prepare agent configuration
            agent_log = log_dir / f"agent_{agent_port}.log"
            agent_env = os.environ.copy()
            agent_env.update({
                'AGENT_PORT': str(agent_port),
                'AGENT_MODEL': 'gpt-4o',
                'MAX_ITERATIONS': '50',
                'AGENT_NAME': agent_name,
                'AGENT_MODULE': agent_module,
                'OPENAI_API_KEY': openai_key,
                'RUNNING_IN_DOCKER': 'false',
                'PYTHONPATH': new_pythonpath,
                'STORAGE_CONFIG_JSON': str(config_json_path),
                'S3_CUSTOM_DOMAIN': 'papers.finbuddygroup.com'
            })

            # Pass connected datasources to agent via environment variable
            if 'connected_datasources' in locals() and connected_datasources:
                agent_env['CONNECTED_DATASOURCES'] = json.dumps(connected_datasources)
                self.test_run_result += f"📊 Connected Datasources: {len(connected_datasources)}\n"
                for ds in connected_datasources:
                    self.test_run_result += f"   • {ds.get('dataset_name')} ({ds.get('dataset_type')})\n"
                yield
            
            # Build agent command based on mode (superagent or single agent)
            agent_cmd = ['python', str(agent_template_path),
                         '--port', str(agent_port),
                         '--model', 'gpt-4o',
                         '--max-iterations', '50',
                         '--agent-name', agent_name,
                         '--agent-module', agent_module]
            
            if 'subagents' in locals() and subagents:
                # SUPERAGENT MODE: Build MCP_SERVERS_CONFIG
                mcp_servers_config = {"servers": {}}
                for subagent in subagents:
                    server_name = subagent['mcp_server_name']
                    mcp_servers_config["servers"][server_name] = {
                        "url": f"http://localhost:{subagent['port']}/sse/",
                        "tools": []  # Tools will be auto-discovered
                    }
                
                mcp_servers_config_json = json.dumps(mcp_servers_config)
                agent_env['SUPERAGENT_MODE'] = 'true'
                agent_env['MCP_SERVERS_CONFIG'] = mcp_servers_config_json
                # Note: --superagent-mode is a boolean flag, don't pass a value
                agent_cmd.extend(['--superagent-mode', '--mcp-servers-config', mcp_servers_config_json])
                
                self.test_run_result += f"🔗 Configured superagent with {len(subagents)} MCP servers\n"
                yield
            else:
                # SINGLE AGENT MODE: Use single MCP server
                mcp_server_name = "generic-mcp-server"
                agent_env['MCP_SERVER_NAME'] = mcp_server_name
                agent_env['MCP_SERVER_URL'] = f'http://localhost:{mcp_port}/sse/'
                agent_env['TOOLS_INFO'] = tools_info
                agent_cmd.extend(['--mcp-server-name', mcp_server_name,
                                 '--mcp-server-url', f'http://localhost:{mcp_port}/sse/',
                                 '--tools-info', tools_info])
                
                self.test_run_result += f"🔧 Configured single agent mode\n"
                yield
            
            # Run agent with instructions (blocking call with timeout)
            self.test_run_result += f"📝 Executing instructions: {self.test_run_instructions[:100]}...\n\n"
            yield
            
            try:
                # Open agent log file
                agent_log_file = open(agent_log, 'w')
                
                # Use a timeout to prevent hanging
                agent_process = subprocess.Popen(
                    agent_cmd,
                    env=agent_env,
                    stdout=agent_log_file,
                    stderr=subprocess.STDOUT,  # Combine stderr with stdout
                    text=True,
                    cwd=str(template_dir)
                )
                
                # Wait for agent to start (give it a few seconds)
                await asyncio.sleep(5)
                
                # Check if agent process is still running
                if agent_process.poll() is not None:
                    agent_log_file.close()  # Close file before reading
                    self.test_run_result += f"❌ Agent failed to start\n"
                    # Read log file
                    try:
                        with open(agent_log, 'r') as f:
                            log_content = f.read()
                            self.test_run_result += f"Agent log:\n{log_content[-1000:]}\n"  # Last 1000 chars
                    except Exception as e:
                        self.test_run_result += f"Could not read agent log: {e}\n"
                    yield
                    return
                
                self.test_run_result += f"✅ Agent started (PID: {agent_process.pid})\n"
                yield
                
                # Now make a request to the agent
                # Generate session/job ID for this test run
                import uuid
                test_session_id = str(uuid.uuid4())  # Full UUID for job_id
                test_user_id = self.user.username if self.user else "test_user"
                
                # CRITICAL: Use EXACT same path structure as production
                # Import the user_path helper and main_shareit_dir from YourIndexingAI
                from YourIndexingAI.modules.modules_utils import user_path
                from YourIndexingAI import main_shareit_dir
                
                # Construct output directory using same pattern as agent_papers.py
                output_dir = user_path(test_user_id, main_shareit_dir) / f"shareit_{test_session_id}"
                test_output_dir = str(output_dir)
                
                # Create output directory
                import os
                os.makedirs(test_output_dir, exist_ok=True)
                
                self.test_run_result += f"📁 Output directory: {test_output_dir}\n"
                yield
                
                try:
                    # Parse dynamic parameters from JSON
                    import json
                    import sys
                    agent_params = json.loads(self.agent_parameters_json) if self.agent_parameters_json else {}
                    
                    print(f"\n{'='*60}", file=sys.stderr, flush=True)
                    print(f"[run_agent_once_no_container] Sending request to agent", file=sys.stderr, flush=True)
                    print(f"[run_agent_once_no_container] Agent params from UI: {agent_params}", file=sys.stderr, flush=True)
                    
                    # Build additional_params with dynamic agent parameters
                    additional_params = {
                        'job_id': test_session_id,
                        'output_directory': test_output_dir
                    }
                    # Add all agent-specific parameters
                    additional_params.update(agent_params)

                    # Add connected datasource info to additional_params (for data_analyst agent)
                    if 'connected_datasources' in locals() and connected_datasources and len(connected_datasources) > 0:
                        ds = connected_datasources[0]  # Use first connected datasource
                        additional_params['dataset_name'] = ds.get('dataset_name')
                        additional_params['dataset_path'] = ds.get('path') or ds.get('dataset_path')
                        additional_params['dataset_schema'] = ds.get('prompt_minimal') or ds.get('prompt_full') or ds.get('description', '')
                        print(f"[run_agent_once_no_container] Added datasource to params: {ds.get('dataset_name')}", file=sys.stderr, flush=True)

                    print(f"[run_agent_once_no_container] Final additional_params: {additional_params}", file=sys.stderr, flush=True)
                    print(f"{'='*60}\n", file=sys.stderr, flush=True)
                    
                    response = requests.post(
                        f'http://localhost:{agent_port}/execute',
                        json={
                            'instructions': self.test_run_instructions,
                            'session_id': test_session_id,
                            'user_id': test_user_id,
                            'additional_params': additional_params
                        },
                        timeout=300  # 5 minutes for complex analysis tasks
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        self.test_run_result += "✅ Agent execution completed!\n\n"
                        self.test_run_result += f"Result:\n{json.dumps(result, indent=2)[:1000]}\n"
                    else:
                        self.test_run_result += f"❌ Agent returned status {response.status_code}\n"
                        self.test_run_result += f"Response: {response.text[:500]}\n"
                except requests.exceptions.Timeout:
                    self.test_run_result += "⏱️ Agent execution timed out (300s limit)\n"
                except requests.exceptions.ConnectionError as conn_err:
                    self.test_run_result += f"❌ Connection error - agent may not have started properly: {str(conn_err)[:200]}\n"
                except Exception as req_err:
                    self.test_run_result += f"❌ Request error: {str(req_err)}\n"
                
            finally:
                # Clean up processes
                self.test_run_result += "\n🧹 Cleaning up processes...\n"
                yield
                
                # Kill agent process
                try:
                    agent_process.terminate()
                    agent_process.wait(timeout=5)
                except:
                    try:
                        agent_process.kill()
                    except:
                        pass
                
                # Kill all started processes (subagents and main server)
                for proc, log_file, name in started_processes:
                    try:
                        proc.terminate()
                        proc.wait(timeout=5)
                        self.test_run_result += f"   Stopped {name}\n"
                    except:
                        try:
                            proc.kill()
                        except:
                            pass
                    try:
                        log_file.close()
                    except:
                        pass
                
                # Close agent log file
                try:
                    agent_log_file.close()
                except:
                    pass
                
                self.test_run_result += f"✅ Test run completed\n"
                self.test_run_result += f"📋 Full logs available at:\n"
                self.test_run_result += f"   Agent: {agent_log}\n"
                if 'subagents' in locals() and subagents:
                    for subagent in subagents:
                        sa_log = log_dir / f"subagent_{subagent['name'].replace(' ', '_')}_{subagent['port']}.log"
                        self.test_run_result += f"   {subagent['name']}: {sa_log}\n"
                yield
            
        except json.JSONDecodeError as e:
            self.test_run_result = f"❌ JSON Parse Error: {str(e)}"
            yield
        except Exception as e:
            import traceback
            error_msg = f"❌ Error: {str(e)}\n\nTraceback:\n{traceback.format_exc()[:1000]}"
            self.test_run_result = error_msg
            yield

    # ==================== Page Builder Methods ====================

    def load_gui_modules(self):
        """Load GUI modules from database for page builder."""
        import sys

        # Always load saved page layouts (they may have changed)
        self.load_saved_page_layouts()

        # Also load agents if not already loaded
        if not self.db_agents_loaded:
            self.load_agents_from_db()

        # Always reload GUI modules from database to pick up changes
        try:
            from db_light.duckdb_models.gui_modules_db import get_modules_for_sidebar
            modules = get_modules_for_sidebar()
            self.gui_modules = modules
            self.gui_modules_loaded = True
            print(f"[load_gui_modules] Loaded {len(modules)} GUI modules", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"[load_gui_modules] Error: {e}", file=sys.stderr, flush=True)
            self.gui_modules = []

    # ==================== Notifications Page Methods ====================

    def load_data_triggers(self):
        """Load data query triggers for the current user from PostgreSQL."""
        import sys
        from permission_db.postgres.connection import get_connection

        if not self.user:
            print("[load_data_triggers] No user logged in", file=sys.stderr, flush=True)
            self.data_triggers = []
            return

        try:
            with get_connection(read_only=True) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT query_id::text, natural_language_request, duckdb_sql,
                               dataset_names, query_type, is_active, notify_type,
                               notify_target, created_at, last_run_at, run_count
                        FROM data_queries
                        WHERE owner_id = %s
                        ORDER BY created_at DESC
                    """, (self.user.username,))
                    rows = cur.fetchall()

            triggers = []
            for row in rows:
                # Format dataset_names as comma-separated string for display
                datasets = row[3] if row[3] else []
                if isinstance(datasets, list):
                    dataset_str = ', '.join(datasets)
                else:
                    dataset_str = str(datasets)

                triggers.append({
                    'query_id': row[0],
                    'natural_language_request': row[1] or '',
                    'duckdb_sql': row[2] or '',
                    'dataset_names': dataset_str,
                    'query_type': row[4] or 'trigger',
                    'is_active': row[5] if row[5] is not None else True,
                    'notify_type': row[6] or '',
                    'notify_target': row[7] or '',
                    'created_at': str(row[8]) if row[8] else '',
                    'last_run_at': str(row[9]) if row[9] else '',
                    'run_count': row[10] or 0,
                })

            self.data_triggers = triggers
            self.data_triggers_loaded = True
            print(f"[load_data_triggers] Loaded {len(triggers)} triggers for user {self.user.username}", file=sys.stderr, flush=True)

        except Exception as e:
            print(f"[load_data_triggers] Error: {e}", file=sys.stderr, flush=True)
            import traceback
            traceback.print_exc()
            self.data_triggers = []

    def select_trigger(self, trigger_id: str):
        """Select a trigger and load its notifications."""
        import sys
        self.selected_trigger_id = trigger_id
        print(f"[select_trigger] Selected trigger: {trigger_id}", file=sys.stderr, flush=True)
        self.load_trigger_notifications()

    def load_trigger_notifications(self):
        """Load notifications for the selected trigger (polling from DB)."""
        import sys
        from permission_db.postgres.connection import get_connection

        if not self.selected_trigger_id:
            self.trigger_notifications = []
            return

        try:
            with get_connection(read_only=True) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT id, query_id::text, message, row_count, created_at, data_json
                        FROM notifications
                        WHERE query_id::text = %s
                        ORDER BY created_at DESC
                        LIMIT 50
                    """, (self.selected_trigger_id,))
                    rows = cur.fetchall()

            notifications = []
            for row in rows:
                notifications.append({
                    'id': row[0],
                    'query_id': row[1],
                    'message': row[2] or 'Query executed',
                    'row_count': row[3] or 0,
                    'created_at': str(row[4]) if row[4] else '',
                    'data_json': row[5] or '',
                })

            self.trigger_notifications = notifications
            print(f"[load_trigger_notifications] Loaded {len(notifications)} notifications", file=sys.stderr, flush=True)

        except Exception as e:
            # If notifications table doesn't exist yet, return empty
            print(f"[load_trigger_notifications] Error (table may not exist yet): {e}", file=sys.stderr, flush=True)
            self.trigger_notifications = []

    def view_notification_data(self, notification_id: int):
        """View the data for a specific notification."""
        import sys
        print(f"[view_notification_data] Viewing notification: {notification_id}", file=sys.stderr, flush=True)
        # TODO: Open a modal or redirect to view the data
        pass

    # ==================== News Feed Methods (Top Bar Notifications) ====================

    def load_unread_notifications(self):
        """Load unread notifications for current user from PostgreSQL for the news feed."""
        import sys
        from permission_db.postgres.connection import get_connection

        if not self.user:
            print("[load_unread_notifications] No user logged in", file=sys.stderr, flush=True)
            self.unread_notifications = []
            return

        try:
            with get_connection(read_only=True) as conn:
                with conn.cursor() as cur:
                    # Join notifications with data_queries to get owner_id and trigger info
                    cur.execute("""
                        SELECT n.id, n.message, n.row_count, n.created_at, n.dataset_name,
                               dq.natural_language_request, n.query_id::text
                        FROM notifications n
                        JOIN data_queries dq ON n.query_id = dq.query_id
                        WHERE dq.owner_id = %s AND n.is_read = FALSE
                        ORDER BY n.created_at DESC
                        LIMIT 10
                    """, (self.user.username,))
                    rows = cur.fetchall()

            notifications = []
            for row in rows:
                notifications.append({
                    'id': row[0],
                    'message': row[1] or 'Query executed',
                    'row_count': row[2] or 0,
                    'created_at': str(row[3]) if row[3] else '',
                    'dataset_name': row[4] or '',
                    'trigger_request': row[5] or '',
                    'query_id': row[6] or '',
                })

            self.unread_notifications = notifications
            print(f"[load_unread_notifications] Loaded {len(notifications)} unread notifications for user {self.user.username}", file=sys.stderr, flush=True)

        except Exception as e:
            print(f"[load_unread_notifications] Error: {e}", file=sys.stderr, flush=True)
            import traceback
            traceback.print_exc()
            self.unread_notifications = []

    def mark_notification_read(self, notification_id: int):
        """Mark a single notification as read."""
        import sys
        from permission_db.postgres.connection import get_connection

        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE notifications SET is_read = TRUE WHERE id = %s
                    """, (notification_id,))
                conn.commit()

            # Remove from unread list
            self.unread_notifications = [n for n in self.unread_notifications if n['id'] != notification_id]
            print(f"[mark_notification_read] Marked notification {notification_id} as read", file=sys.stderr, flush=True)

        except Exception as e:
            print(f"[mark_notification_read] Error: {e}", file=sys.stderr, flush=True)

    def mark_all_notifications_read(self):
        """Mark all unread notifications as read for the current user."""
        import sys
        from permission_db.postgres.connection import get_connection

        if not self.user:
            return

        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    # Mark all notifications as read for triggers owned by this user
                    cur.execute("""
                        UPDATE notifications n
                        SET is_read = TRUE
                        FROM data_queries dq
                        WHERE n.query_id = dq.query_id
                          AND dq.owner_id = %s
                          AND n.is_read = FALSE
                    """, (self.user.username,))
                conn.commit()

            self.unread_notifications = []
            print(f"[mark_all_notifications_read] Marked all notifications as read for {self.user.username}", file=sys.stderr, flush=True)

        except Exception as e:
            print(f"[mark_all_notifications_read] Error: {e}", file=sys.stderr, flush=True)

    def toggle_news_feed_dropdown(self, is_open: bool = None):
        """Toggle or set the news feed dropdown open state."""
        if is_open is not None:
            self.news_feed_dropdown_open = is_open
        else:
            self.news_feed_dropdown_open = not self.news_feed_dropdown_open
        # Reload notifications when opening
        if self.news_feed_dropdown_open:
            self.load_unread_notifications()

    # ==================== Agents Management Page Methods ====================

    @rx.event
    def load_agents_management_data(self):
        """Load all agents with permissions for the agents management page."""
        import sys
        from permission_db.postgres.connection import get_connection

        if not self.user:
            print("[load_agents_management_data] No user logged in", file=sys.stderr, flush=True)
            self.mgmt_agents_list = []
            return

        try:
            with get_connection(read_only=True) as conn:
                with conn.cursor() as cur:
                    # Get agents the user owns or has access to via permissions
                    cur.execute("""
                        SELECT DISTINCT a.id, a.name, a.display_name, a.description,
                               a.user_id,
                               CASE
                                   WHEN a.user_id = %s THEN 'owner'
                                   WHEN rp.permission_level IS NOT NULL THEN rp.permission_level
                                   ELSE 'read'
                               END as permission
                        FROM agents a
                        LEFT JOIN resources r ON r.resource_id = a.id AND r.resource_type = 'agent'
                        LEFT JOIN resource_permissions rp ON rp.resource_id = a.id
                            AND rp.entity_type = 'user' AND rp.entity_id = %s
                        WHERE a.user_id = %s
                           OR rp.entity_id = %s
                           OR r.visibility = 'public'
                        ORDER BY a.display_name
                    """, (self.user.username, self.user.username, self.user.username, self.user.username))
                    rows = cur.fetchall()

            agents = []
            for row in rows:
                agents.append({
                    'id': str(row[0]) if row[0] else '',
                    'name': str(row[1]) if row[1] else '',
                    'display_name': str(row[2]) if row[2] else '',
                    'description': str(row[3]) if row[3] else '',
                    'owner_id': str(row[4]) if row[4] else '',
                    'permission': str(row[5]) if row[5] else 'read',
                })

            self.mgmt_agents_list = agents
            print(f"[load_agents_management_data] Loaded {len(agents)} agents", file=sys.stderr, flush=True)

        except Exception as e:
            print(f"[load_agents_management_data] Error: {e}", file=sys.stderr, flush=True)
            import traceback
            traceback.print_exc()
            self.mgmt_agents_list = []

    @rx.event
    def select_mgmt_agent(self, agent_id: str):
        """Select an agent and load its containers."""
        import sys
        from permission_db.postgres.connection import get_connection

        self.mgmt_selected_agent_id = agent_id
        self.mgmt_selected_container_id = ""
        self.mgmt_selected_session_id = ""
        self.mgmt_sessions_list = []
        self.mgmt_triggers_list = []
        self.mgmt_portfolios_list = []

        # Get agent display name
        for agent in self.mgmt_agents_list:
            if agent.get('id') == agent_id:
                self.mgmt_selected_agent_name = agent.get('display_name', '')
                break

        print(f"[select_mgmt_agent] Selected agent: {agent_id}", file=sys.stderr, flush=True)

        try:
            with get_connection(read_only=True) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT id, instance_type, status, address, port, container_id,
                               platform, created_at, started_at
                        FROM agent_instances
                        WHERE agent_id = %s
                        ORDER BY created_at DESC
                    """, (agent_id,))
                    rows = cur.fetchall()

            containers = []
            for row in rows:
                # Format created_at to remove microseconds (YYYY-MM-DD HH:MM:SS)
                created_at_str = ''
                if row[7]:
                    created_at_str = str(row[7]).split('.')[0] if '.' in str(row[7]) else str(row[7])

                containers.append({
                    'id': str(row[0]) if row[0] else '',
                    'instance_type': str(row[1]) if row[1] else '',
                    'status': str(row[2]) if row[2] else 'stopped',
                    'address': str(row[3]) if row[3] else '',
                    'port': str(row[4]) if row[4] else '',
                    'container_id': str(row[5]) if row[5] else '',
                    'platform': str(row[6]) if row[6] else '',
                    'created_at': created_at_str,
                    'started_at': str(row[8]) if row[8] else '',
                })

            self.mgmt_containers_list = containers
            print(f"[select_mgmt_agent] Loaded {len(containers)} containers", file=sys.stderr, flush=True)

        except Exception as e:
            print(f"[select_mgmt_agent] Error loading containers: {e}", file=sys.stderr, flush=True)
            self.mgmt_containers_list = []

    @rx.event
    def select_mgmt_container(self, container_id: str):
        """Select a container and load its sessions."""
        import sys
        import time

        self.mgmt_selected_container_id = container_id
        self.mgmt_selected_session_id = ""
        self.mgmt_triggers_list = []
        self.mgmt_portfolios_list = []

        print(f"[select_mgmt_container] Selected container: {container_id}", file=sys.stderr, flush=True)

        if not self.user:
            self.mgmt_sessions_list = []
            return

        # Get agent name for the selected container
        agent_name = self.mgmt_selected_agent_name

        try:
            # Query AgentSessions from Reflex database
            with rx.session() as session:
                from sqlmodel import select
                sessions_data = session.exec(
                    select(AgentSessions)
                    .where(AgentSessions.agent_name == agent_name)
                    .where(AgentSessions.user_id == self.user.id)
                    .order_by(AgentSessions.updated_at.desc())
                ).all()

            sessions = []
            for sess in sessions_data:
                # Get chat title
                chat_title = ""
                with rx.session() as db_session:
                    chat = db_session.exec(
                        select(Chats).where(Chats.id == sess.chat_id)
                    ).first()
                    if chat:
                        chat_title = chat.chat_title

                # Format timestamp
                created_str = ""
                if sess.created_at:
                    from datetime import datetime
                    created_str = datetime.fromtimestamp(sess.created_at).strftime("%Y-%m-%d %H:%M")

                sessions.append({
                    'session_id': str(sess.session_id) if sess.session_id else '',
                    'chat_id': str(sess.chat_id) if sess.chat_id else '',
                    'chat_title': chat_title,
                    'agent_name': str(sess.agent_name) if sess.agent_name else '',
                    'created_at': created_str,
                })

            self.mgmt_sessions_list = sessions
            print(f"[select_mgmt_container] Loaded {len(sessions)} sessions", file=sys.stderr, flush=True)

        except Exception as e:
            print(f"[select_mgmt_container] Error loading sessions: {e}", file=sys.stderr, flush=True)
            import traceback
            traceback.print_exc()
            self.mgmt_sessions_list = []

    @rx.event
    async def delete_mgmt_container(self, container_id: str):
        """Delete a container instance via API."""
        import sys
        import requests

        print(f"[delete_mgmt_container] Deleting container: {container_id}", file=sys.stderr, flush=True)

        if not self.user:
            print(f"[delete_mgmt_container] Error: User not logged in", file=sys.stderr, flush=True)
            return

        try:
            # Call DELETE API
            headers = self._get_auth_headers()
            response = requests.delete(
                f"http://localhost:8008/agents/{container_id}",
                headers=headers,
                timeout=30
            )

            if response.status_code == 200:
                print(f"[delete_mgmt_container] Successfully deleted container {container_id}", file=sys.stderr, flush=True)

                # Clear selection if we deleted the selected container
                if self.mgmt_selected_container_id == container_id:
                    self.mgmt_selected_container_id = ""
                    self.mgmt_sessions_list = []
                    self.mgmt_triggers_list = []
                    self.mgmt_portfolios_list = []

                # Refresh containers list
                if self.mgmt_selected_agent_id:
                    self.select_mgmt_agent(self.mgmt_selected_agent_id)

                # Also refresh navbar running containers
                self.load_running_containers()
            else:
                print(f"[delete_mgmt_container] Error: {response.status_code} - {response.text}", file=sys.stderr, flush=True)

        except Exception as e:
            print(f"[delete_mgmt_container] Error: {e}", file=sys.stderr, flush=True)
            import traceback
            traceback.print_exc()

    @rx.event
    def select_mgmt_session(self, session_id: str):
        """Select a session and load its triggers."""
        import sys
        from permission_db.postgres.connection import get_connection

        self.mgmt_selected_session_id = session_id
        print(f"[select_mgmt_session] Selected session: {session_id}", file=sys.stderr, flush=True)

        try:
            with get_connection(read_only=True) as conn:
                with conn.cursor() as cur:
                    # Get triggers linked to this session_id
                    cur.execute("""
                        SELECT query_id::text, natural_language_request, duckdb_sql,
                               dataset_names, query_type, is_active, notify_type,
                               notify_target, created_at, last_run_at, run_count
                        FROM data_queries
                        WHERE session_id = %s
                        ORDER BY created_at DESC
                    """, (session_id,))
                    rows = cur.fetchall()

            triggers = []
            for row in rows:
                # Format dataset_names as comma-separated string for display
                datasets = row[3] if row[3] else []
                if isinstance(datasets, list):
                    dataset_str = ', '.join(datasets)
                else:
                    dataset_str = str(datasets)

                triggers.append({
                    'query_id': str(row[0]) if row[0] else '',
                    'natural_language_request': str(row[1]) if row[1] else '',
                    'duckdb_sql': str(row[2]) if row[2] else '',
                    'dataset_names': dataset_str,
                    'query_type': str(row[4]) if row[4] else 'trigger',
                    'is_active': row[5] if row[5] is not None else True,
                    'notify_type': str(row[6]) if row[6] else '',
                    'notify_target': str(row[7]) if row[7] else '',
                    'created_at': str(row[8]) if row[8] else '',
                    'last_run_at': str(row[9]) if row[9] else '',
                    'run_count': row[10] or 0,
                })

            self.mgmt_triggers_list = triggers
            print(f"[select_mgmt_session] Loaded {len(triggers)} triggers", file=sys.stderr, flush=True)

        except Exception as e:
            print(f"[select_mgmt_session] Error loading triggers: {e}", file=sys.stderr, flush=True)
            import traceback
            traceback.print_exc()
            self.mgmt_triggers_list = []

        # Load portfolios linked to this session via AgentSessions -> chat_id -> Portfolios
        self._load_portfolios_for_session(session_id)

    def _load_portfolios_for_session(self, session_id: str):
        """Load portfolios linked to the session via chat_id."""
        import sys
        from sqlmodel import select

        try:
            # First get the chat_id from AgentSessions
            with rx.session() as db_session:
                from finbuddy.data_models.db_users import AgentSessions, Portfolios, Chats

                # Get the agent session to find the chat_id
                agent_session = db_session.exec(
                    select(AgentSessions).where(AgentSessions.session_id == session_id)
                ).first()

                if not agent_session:
                    print(f"[_load_portfolios_for_session] No agent session found for {session_id}", file=sys.stderr, flush=True)
                    self.mgmt_portfolios_list = []
                    return

                chat_id = agent_session.chat_id
                print(f"[_load_portfolios_for_session] Found chat_id: {chat_id}", file=sys.stderr, flush=True)

                # Get portfolios linked to this chat
                portfolios_query = select(Portfolios).where(Portfolios.chat_id == chat_id)
                portfolios = db_session.exec(portfolios_query).all()

                # Get the chat title for display
                chat = db_session.exec(select(Chats).where(Chats.id == chat_id)).first()
                chat_title = chat.chat_title if chat else "Unknown"

                portfolio_list = []
                for p in portfolios:
                    # Format created_at timestamp
                    import time
                    created_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(p.created_at)) if p.created_at else ''

                    portfolio_list.append({
                        'id': p.id,
                        'portfolio_name': p.portfolio_name,
                        'nickname': p.nickname,
                        'chat_id': p.chat_id,
                        'chat_title': chat_title,
                        'created_at': created_str,
                    })

                self.mgmt_portfolios_list = portfolio_list
                print(f"[_load_portfolios_for_session] Loaded {len(portfolio_list)} portfolios", file=sys.stderr, flush=True)

        except Exception as e:
            print(f"[_load_portfolios_for_session] Error: {e}", file=sys.stderr, flush=True)
            import traceback
            traceback.print_exc()
            self.mgmt_portfolios_list = []

    def save_page_layout(self):
        """Save the current page layout to database (legacy method)."""
        self.save_page_layout_with_json(self.page_builder_json)

    def save_page_layout_with_json(self, json_from_js: str):
        """Save the current page layout to database with JSON from JavaScript."""
        import sys

        # Store the JSON from JavaScript
        if json_from_js:
            self.page_builder_json = json_from_js

        # Validate page name
        if not self.page_builder_name.strip():
            self.page_builder_save_status = "error"
            self.page_builder_save_message = "Page name is required"
            return

        print(f"[save_page_layout] Name: {self.page_builder_name}", file=sys.stderr, flush=True)
        print(f"[save_page_layout] JSON: {self.page_builder_json}", file=sys.stderr, flush=True)

        try:
            from db_light.duckdb_models.page_layouts_db import save_layout, PageLayout

            layout = PageLayout(
                page_name=self.page_builder_name.strip(),
                description=self.page_builder_description.strip(),
                layout_json=self.page_builder_json,
                is_published=False
            )

            layout_id = save_layout(layout)
            print(f"[save_page_layout] Saved layout with ID: {layout_id}", file=sys.stderr, flush=True)

            self.page_builder_save_status = "success"
            self.page_builder_save_message = f"Page '{self.page_builder_name}' saved successfully!"

            # Reload the list of saved layouts
            self.load_saved_page_layouts()

        except Exception as e:
            print(f"[save_page_layout] Error: {e}", file=sys.stderr, flush=True)
            self.page_builder_save_status = "error"
            self.page_builder_save_message = f"Failed to save: {str(e)}"

    def load_saved_page_layouts(self):
        """Load list of saved page layouts from database."""
        import sys
        try:
            from db_light.duckdb_models.page_layouts_db import list_layouts
            layouts = list_layouts()
            self.saved_page_layouts = [
                {
                    "id": l.layout_id,
                    "name": l.page_name,
                    "description": l.description,
                    "is_published": l.is_published,
                    "updated_at": l.updated_at
                }
                for l in layouts
            ]
            print(f"[load_saved_page_layouts] Loaded {len(self.saved_page_layouts)} layouts", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"[load_saved_page_layouts] Error: {e}", file=sys.stderr, flush=True)
            self.saved_page_layouts = []

    def load_page_layout(self, page_name: str):
        """Load a specific page layout into the builder and populate canvas."""
        import sys
        import json
        try:
            from db_light.duckdb_models.page_layouts_db import get_layout
            layout = get_layout(page_name)
            if layout:
                self.page_builder_name = layout.page_name
                self.page_builder_description = layout.description or ""
                self.page_builder_json = layout.layout_json
                # Turn off live view to show canvas
                self.page_builder_live_view = False
                print(f"[load_page_layout] Loaded layout: {page_name}, JSON: {layout.layout_json[:100]}...", file=sys.stderr, flush=True)
                # Return script to load modules into JS canvas
                # Use JSON.stringify to safely escape the JSON string
                escaped_json = json.dumps(layout.layout_json)
                return rx.call_script(f"window.loadPageModules && window.loadPageModules({escaped_json})")
            else:
                print(f"[load_page_layout] Layout not found: {page_name}", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"[load_page_layout] Error: {e}", file=sys.stderr, flush=True)

    def clear_page_builder_status(self):
        """Clear the save status message."""
        self.page_builder_save_status = ""
        self.page_builder_save_message = ""

    def send_page_builder_chat(self):
        """Send chat message for AI-assisted page building."""
        import sys
        if not self.page_builder_chat_input.strip():
            return
        print(f"[send_page_builder_chat] Message: {self.page_builder_chat_input}", file=sys.stderr, flush=True)
        # TODO: Integrate with AI agent for page building assistance
        self.page_builder_chat_input = ""

    def set_page_builder_name(self, value: str):
        """Set the page builder name."""
        self.page_builder_name = value

    def set_page_builder_description(self, value: str):
        """Set the page builder description."""
        self.page_builder_description = value

    def set_page_builder_chat_input(self, value: str):
        """Set the page builder chat input."""
        self.page_builder_chat_input = value

    def set_page_builder_json(self, value):
        """Set the page builder JSON (called from JavaScript).

        Value can be either a string directly or an event dict with target.value
        """
        if isinstance(value, dict):
            # Event from rx.el.input
            self.page_builder_json = value.get("target", {}).get("value", '{"modules": []}')
        else:
            # Direct string value
            self.page_builder_json = value

    def toggle_page_builder_live_view(self, value: bool):
        """Toggle live view mode."""
        self.page_builder_live_view = value

    def toggle_live_view_with_json(self, json_from_js: str):
        """Toggle live view and update JSON from JavaScript canvas."""
        # First update the JSON from JavaScript
        if json_from_js:
            self.page_builder_json = json_from_js
        # Then toggle the live view
        self.page_builder_live_view = not self.page_builder_live_view
        # Hide or show canvas modules based on the new state
        if self.page_builder_live_view:
            # Entering live view - hide canvas modules
            return rx.call_script("window.hideCanvasModules && window.hideCanvasModules()")
        else:
            # Exiting live view - show canvas modules
            return rx.call_script("window.showCanvasModules && window.showCanvasModules()")

    @rx.var
    def page_builder_modules_list(self) -> List[Dict[str, Any]]:
        """Parse the page builder JSON and return modules list."""
        import json
        try:
            data = json.loads(self.page_builder_json)
            return data.get("modules", [])
        except (json.JSONDecodeError, TypeError):
            return []

    def toggle_page_view(self):
        """Toggle between chat view and page view on main page."""
        self.show_page_view = not self.show_page_view

    @rx.var
    def active_page_modules_list(self) -> List[Dict[str, Any]]:
        """Parse the active page JSON and return modules list for main page view."""
        import json
        try:
            data = json.loads(self.active_page_json)
            return data.get("modules", [])
        except (json.JSONDecodeError, TypeError):
            return []

    # =========================================================================
    # DYNAMIC PAGE METHODS - Agent-driven interface rendering
    # =========================================================================

    @rx.var
    def dynamic_page_modules_list(self) -> List[Dict[str, Any]]:
        """Parse the dynamic page JSON and return modules list."""
        import json
        try:
            data = json.loads(self.dynamic_page_json)
            return data.get("modules", [])
        except (json.JSONDecodeError, TypeError):
            return []

    @rx.var
    def dynamic_inputs_json(self) -> str:
        """Return dynamic inputs as JSON string for display."""
        import json
        return json.dumps(self.dynamic_page_inputs, indent=2)

    @rx.var
    def dynamic_outputs_json(self) -> str:
        """Return dynamic outputs as JSON string for display."""
        import json
        return json.dumps(self.dynamic_page_outputs, indent=2)

    @rx.var
    def dynamic_output1_value(self) -> str:
        """Get the output value for output1 module (for display)."""
        return self.dynamic_page_outputs.get("output1", "Output will appear here...")

    def set_dynamic_input(self, module_id: str, value: Any):
        """Store user input from a dynamic module."""
        self.dynamic_page_inputs[module_id] = value

    def get_dynamic_output(self, module_id: str) -> str:
        """Get output value for a dynamic module."""
        return self.dynamic_page_outputs.get(module_id, "")

    def update_dynamic_layout(self, layout_json: str):
        """Update the dynamic page layout from agent message."""
        print(f"[Dynamic Page] Updating layout, length: {len(layout_json) if layout_json else 0}")
        if layout_json:
            self.dynamic_page_json = layout_json
            # Also update active_page_json so the GUI view (active_page_view) reflects the change
            self.active_page_json = layout_json
            # Reset inputs/outputs when new layout is loaded
            self.dynamic_page_inputs = {}
            self.dynamic_page_outputs["output1"] = "Waiting for input..."

    def update_dynamic_output(self, module_id: str, value: str):
        """Update an output module's value."""
        self.dynamic_page_outputs[module_id] = value

    def update_dynamic_output_from_js(self, json_data: str):
        """Update an output module from JavaScript callback (receives JSON string)."""
        import json
        try:
            data = json.loads(json_data) if json_data else {}
            module_id = data.get("module_id", "")
            value = data.get("value", "")
            if module_id:
                self.dynamic_page_outputs[module_id] = value
                print(f"[Dynamic Page] Output updated: {module_id} = {value}")
        except Exception as e:
            print(f"[Dynamic Page] Error parsing output update: {e}")

    def send_dynamic_input(self):
        """Send collected inputs back to the agent via WebSocket."""
        import json
        print(f"[Dynamic Page] Sending inputs: {json.dumps(self.dynamic_page_inputs)}")

        # Call JavaScript function to send inputs via WebSocket
        # The JavaScript function will include the correlation_id if there's a pending request
        return rx.call_script(
            f"window.sendDynamicInput({json.dumps(self.dynamic_page_inputs)})"
        )

    def reconnect_dynamic_page(self):
        """Reconnect the dynamic page WebSocket."""
        print(f"[Dynamic Page] Reconnect requested")
        return rx.call_script("window.reconnectDynamicPage && window.reconnectDynamicPage()")

    def set_dynamic_ws_status(self, connected: bool):
        """Set WebSocket connection status (called from JavaScript)."""
        self.dynamic_page_connected = connected
        print(f"[Dynamic Page] WebSocket status: {connected}")

    def clear_dynamic_layout(self):
        """Clear the dynamic page layout."""
        self.dynamic_page_json = '{"modules": []}'
        self.dynamic_page_inputs = {}
        self.dynamic_page_outputs = {}

    def load_sample_dynamic_layout(self):
        """Load a sample layout for testing."""
        import json
        sample = {
            "modules": [
                {
                    "id": "input1",
                    "type": "input_box",
                    "x": 50,
                    "y": 50,
                    "width": 300,
                    "height": 60,
                    "config": {"placeholder": "Enter your query..."}
                },
                {
                    "id": "send_btn",
                    "type": "button",
                    "x": 360,
                    "y": 50,
                    "width": 100,
                    "height": 60,
                    "config": {"label": "Send"}
                },
                {
                    "id": "output1",
                    "type": "text_output",
                    "x": 50,
                    "y": 130,
                    "width": 410,
                    "height": 200,
                    "config": {}
                },
                {
                    "id": "label1",
                    "type": "label",
                    "x": 50,
                    "y": 20,
                    "width": 200,
                    "height": 30,
                    "config": {"text": "Dynamic Interface Demo"}
                }
            ]
        }
        self.dynamic_page_json = json.dumps(sample)
        self.dynamic_page_inputs = {}
        self.dynamic_page_outputs["output1"] = "Waiting for response..."

    def load_sample_layout_2(self):
        """Load second sample layout with menu and switch."""
        import json
        sample = {
            "modules": [
                {
                    "id": "label1",
                    "type": "label",
                    "x": 50,
                    "y": 20,
                    "width": 300,
                    "height": 30,
                    "config": {"text": "Menu & Switch Demo"}
                },
                {
                    "id": "menu1",
                    "type": "menu",
                    "x": 50,
                    "y": 60,
                    "width": 200,
                    "height": 60,
                    "config": {}
                },
                {
                    "id": "switch1",
                    "type": "switch",
                    "x": 270,
                    "y": 60,
                    "width": 150,
                    "height": 60,
                    "config": {}
                },
                {
                    "id": "send_btn",
                    "type": "button",
                    "x": 50,
                    "y": 140,
                    "width": 100,
                    "height": 50,
                    "config": {"label": "Send"}
                },
                {
                    "id": "output1",
                    "type": "text_output",
                    "x": 50,
                    "y": 210,
                    "width": 370,
                    "height": 150,
                    "config": {}
                }
            ]
        }
        self.dynamic_page_json = json.dumps(sample)
        self.dynamic_page_inputs = {}
        self.dynamic_page_outputs["output1"] = "Select menu item and toggle switch, then click Send"

    # =========================================================================
    # MCP Discovery Search Methods
    # =========================================================================

    @rx.event
    def set_mcp_search_query(self, query: str):
        """Set the search query for MCP discovery."""
        self.mcp_search_query = query

    @rx.event
    def set_mcp_search_type_filter(self, type_filter: str):
        """Set the type filter for search (agent, mcp_server, or empty for all)."""
        self.mcp_search_type_filter = type_filter

    @rx.event
    def handle_mcp_type_filter_change(self, value: str):
        """Handle type filter select change - convert 'all' to empty string."""
        self.mcp_search_type_filter = "" if value == "all" else value

    @rx.event
    def set_mcp_search_category_filter(self, category: str):
        """Set the category filter for search."""
        self.mcp_search_category_filter = category

    @rx.event
    def handle_mcp_category_filter_change(self, value: str):
        """Handle category filter select change - convert 'all' to empty string."""
        self.mcp_search_category_filter = "" if value == "all" else value

    @rx.event
    def clear_mcp_search(self):
        """Clear all search filters and results."""
        self.mcp_search_query = ""
        self.mcp_search_type_filter = ""
        self.mcp_search_category_filter = ""
        self.mcp_search_results = []
        self.mcp_selected_result_id = ""

    @rx.event
    def select_mcp_result(self, result_id: str):
        """Select a result for detail view."""
        self.mcp_selected_result_id = result_id

    @rx.var
    def mcp_selected_result(self) -> Dict[str, Any]:
        """Get the currently selected search result details."""
        for result in self.mcp_search_results:
            if result.get('id') == self.mcp_selected_result_id:
                return result
        return {}

    @rx.var
    def mcp_selected_similarity_display(self) -> str:
        """Get formatted similarity score for display."""
        result = self.mcp_selected_result
        if not result:
            return ""
        distance = result.get('distance', 0)
        if distance > 0:
            similarity = (1 - distance) * 100
            return f"{similarity:.1f}%"
        return ""

    @rx.var
    def mcp_selected_has_distance(self) -> bool:
        """Check if selected result has a distance value > 0."""
        result = self.mcp_selected_result
        if not result:
            return False
        return result.get('distance', 0) > 0

    @rx.var
    def mcp_selected_has_category(self) -> bool:
        """Check if selected result has a non-empty category."""
        result = self.mcp_selected_result
        if not result:
            return False
        return bool(result.get('category', ''))

    @rx.var
    def mcp_selected_is_agent(self) -> bool:
        """Check if selected result is an agent type."""
        result = self.mcp_selected_result
        if not result:
            return False
        return result.get('type', '') == 'agent'

    @rx.event
    def load_mcp_search_data(self):
        """Initialize MCP search page - no initial load needed."""
        import sys
        print("[load_mcp_search_data] Page loaded", file=sys.stderr, flush=True)
        # Clear previous search state on page load
        self.mcp_search_results = []
        self.mcp_selected_result_id = ""
        self.mcp_search_loading = False

    @rx.event
    async def search_mcp_registry(self):
        """Execute search against MCP discovery registry API."""
        import sys
        import httpx

        if not self.mcp_search_query.strip():
            self.mcp_search_results = []
            return

        self.mcp_search_loading = True
        yield

        try:
            # Use the JWT token for API authentication
            token = self.jwt_token
            if not token:
                print("[search_mcp_registry] No JWT token available", file=sys.stderr, flush=True)
                self.mcp_search_results = []
                self.mcp_search_loading = False
                return

            # Build search request
            search_request = {
                "query": self.mcp_search_query,
                "k": 20  # Return up to 20 results
            }

            # Add optional filters
            if self.mcp_search_type_filter:
                search_request["type_filter"] = self.mcp_search_type_filter
            if self.mcp_search_category_filter:
                search_request["category_filter"] = self.mcp_search_category_filter

            # Call the MCP discovery API
            api_base = os.getenv("API_BASE_URL", "http://localhost:8008")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{api_base}/api/mcp/search",
                    json=search_request,
                    headers={"Authorization": f"Bearer {token}"}
                )

            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])
                # Convert to list of dicts for Reflex state
                self.mcp_search_results = [
                    {
                        "id": str(r.get("id", "")),
                        "type": str(r.get("type", "")),
                        "name": str(r.get("name", "")),
                        "display_name": str(r.get("display_name", "")),
                        "description": str(r.get("description", "")),
                        "category": str(r.get("category", "")),
                        "distance": float(r.get("distance", 0)) if r.get("distance") else 0.0,
                    }
                    for r in results
                ]
                print(f"[search_mcp_registry] Found {len(self.mcp_search_results)} results", file=sys.stderr, flush=True)
            else:
                print(f"[search_mcp_registry] API error: {response.status_code} - {response.text}", file=sys.stderr, flush=True)
                self.mcp_search_results = []

        except Exception as e:
            print(f"[search_mcp_registry] Error: {e}", file=sys.stderr, flush=True)
            import traceback
            traceback.print_exc()
            self.mcp_search_results = []

        self.mcp_search_loading = False


CDN = ("https://unpkg.com/lightweight-charts@4.1.1/dist/"
       "lightweight-charts.standalone.production.js")
def lightweight_chart_component() -> rx.Component:
    init_js = """
(function() {
    const chartElementId = 'lw-chart';
    let chartInstance = null;
    let seriesInstance = null;
    let scriptInitializationDone = false;

    function initializeChartIfNeeded() {
        if (scriptInitializationDone) return true;

        if (typeof LightweightCharts === 'undefined' || !window.LightweightCharts) {
            return false; 
        }

        const el = document.getElementById(chartElementId);
        if (!el) {
            return false; 
        }

        chartInstance = LightweightCharts.createChart(el, {
            width: el.clientWidth,
            height: 300,
            autoSize: true,
            layout: { background: { color: 'transparent' }, textColor: '#333' },
            grid:   { vertLines: { color: '#f0f0f0' }, horzLines: { color: '#f0f0f0' } },
        });
        seriesInstance = chartInstance.addLineSeries({ color: '#4a90e2', lineWidth: 2 });

        if (window.ResizeObserver) {
            new ResizeObserver(entries => {
                if (!entries || !entries.length || !chartInstance) { return; }
                const entry = entries[0];
                if (entry.contentRect && entry.contentRect.width > 0) {
                    chartInstance.applyOptions({ width: entry.contentRect.width });
                }
            }).observe(el);
        } else {
        }

        if (!window.dragZoomInitializedLightweight) {
            const chartContainerForZoom = document.getElementById('lw-chart-container');
            const selectionBand = document.getElementById('lw-selection-band');
            let isDragging = false;
            let dragStartLogical = null;

            if (chartContainerForZoom && selectionBand && chartInstance) {
                chartContainerForZoom.addEventListener('mousedown', (event) => {
                    if (event.button !== 0 || !chartInstance) return;
                    
                    const rect = chartContainerForZoom.getBoundingClientRect();
                    const x = event.clientX - rect.left;
                    
                    dragStartLogical = chartInstance.timeScale().coordinateToLogical(x);
                    if (dragStartLogical === null) { 
                        return; 
                    }
                    isDragging = true; 

                    selectionBand.style.left = x + 'px';
                    selectionBand.style.top = '0px';
                    selectionBand.style.width = '0px';
                    selectionBand.style.height = chartContainerForZoom.clientHeight + 'px';
                    selectionBand.style.display = 'block';

                    chartInstance.applyOptions({ 
                        handleScroll: { pressedMouseMove: false, horzTouchDrag: false, vertTouchDrag: false }, 
                        handleScale: { mouseWheel: false, pinch: false } 
                    });
                });

                document.addEventListener('mousemove', (event) => {
                    if (!isDragging || !chartInstance) return;
                    const rect = chartContainerForZoom.getBoundingClientRect();
                    const currentX = event.clientX - rect.left;
                    
                    const initialX = parseFloat(selectionBand.style.left);
                    const width = Math.abs(currentX - initialX);
                    const newLeft = Math.min(currentX, initialX);

                    selectionBand.style.left = newLeft + 'px';
                    selectionBand.style.width = width + 'px';
                });

                document.addEventListener('mouseup', (event) => {
                    if (!isDragging || !chartInstance) return;
                    
                    isDragging = false;
                    selectionBand.style.display = 'none';

                    const rect = chartContainerForZoom.getBoundingClientRect();
                    const x = event.clientX - rect.left;
                    const dragEndLogical = chartInstance.timeScale().coordinateToLogical(x);

                    if (dragStartLogical !== null && dragEndLogical !== null && dragStartLogical !== dragEndLogical) {
                        const from = Math.min(dragStartLogical, dragEndLogical);
                        const to = Math.max(dragStartLogical, dragEndLogical);
                        if (from !== to) { 
                           chartInstance.timeScale().setVisibleLogicalRange({ from, to });
                        }
                    }
                    
                    chartInstance.applyOptions({ 
                        handleScroll: { pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: true }, 
                        handleScale: { mouseWheel: true, pinch: true } 
                    });
                });

                chartContainerForZoom.addEventListener('dblclick', () => {
                    if (chartInstance) {
                        chartInstance.timeScale().fitContent();
                    }
                });
                window.dragZoomInitializedLightweight = true;
            }
        }
        
        scriptInitializationDone = true;
        return true;
    }

    function renderData(data) {
        if (!initializeChartIfNeeded()) {
            if (data && (!Array.isArray(data) || data.length > 0)) {
                setTimeout(() => renderData(data), 100);
            }
            return;
        }
        
        if (data && seriesInstance) {
            seriesInstance.setData(data);
            if (data.length > 0) {
                 chartInstance.timeScale().fitContent();
            }
        } else if (seriesInstance) {
            seriesInstance.setData([]);
        }
    }

    if (!Object.getOwnPropertyDescriptor(window, 'lightweightChartState')) {
        let _internalState = null; 
        Object.defineProperty(window, 'lightweightChartState', {
            configurable: true, 
            set: function(v) {
                _internalState = v;
                renderData(v); 
            },
            get: function() {
                return _internalState;
            }
        });
    } else {
    }

    // Attempt an initial draw in case data was set before this script ran (less likely with defer)
    // or if the initial state of State.eq_performance_lightweight_json is already populated.
})();
    """

    trigger_script = lambda: (
        rx.script(f"window.lightweightChartState = {State.eq_performance_lightweight_json};",
                  strategy="afterInteractive")
    )

    return rx.fragment(
        rx.box(
            rx.box(id="lw-chart", width="100%", height="100%"),
            rx.box(
                id="lw-selection-band",
                position="absolute",
                display="none",
                bg="rgba(0, 123, 255, 0.2)",
                border="1px solid rgba(0, 123, 255, 0.5)",
                z_index="10",
                top="0",
                left="0",
                width="0px",
                height="100%"
            ),
            id="lw-chart-container",
            position="relative",
            width="100%",
            height="300px"
        ),
        rx.script(src=CDN, strategy="afterInteractive"),
        rx.script(init_js, strategy="afterInteractive"),
        rx.cond(State.eq_performance_lightweight_json,
                trigger_script(),
                rx.script("window.lightweightChartState = null;", strategy="afterInteractive"))
    )

def lightweight_chart_component_fi() -> rx.Component:
    init_js = """
(function() {
    const chartElementId = 'lw-chart';
    let chartInstance = null;
    let seriesInstance = null;
    let scriptInitializationDone = false;

    function initializeChartIfNeeded() {
        if (scriptInitializationDone) return true;

        if (typeof LightweightCharts === 'undefined' || !window.LightweightCharts) {
            return false; 
        }

        const el = document.getElementById(chartElementId);
        if (!el) {
            return false; 
        }

        chartInstance = LightweightCharts.createChart(el, {
            width: el.clientWidth,
            height: 300,
            autoSize: true,
            layout: { background: { color: 'transparent' }, textColor: '#333' },
            grid:   { vertLines: { color: '#f0f0f0' }, horzLines: { color: '#f0f0f0' } },
        });
        seriesInstance = chartInstance.addLineSeries({ color: '#4a90e2', lineWidth: 2 });

        if (window.ResizeObserver) {
            new ResizeObserver(entries => {
                if (!entries || !entries.length || !chartInstance) { return; }
                const entry = entries[0];
                if (entry.contentRect && entry.contentRect.width > 0) {
                    chartInstance.applyOptions({ width: entry.contentRect.width });
                }
            }).observe(el);
        } else {
        }

        if (!window.dragZoomInitializedLightweight) {
            const chartContainerForZoom = document.getElementById('lw-chart-container');
            const selectionBand = document.getElementById('lw-selection-band');
            let isDragging = false;
            let dragStartLogical = null;

            if (chartContainerForZoom && selectionBand && chartInstance) {
                chartContainerForZoom.addEventListener('mousedown', (event) => {
                    if (event.button !== 0 || !chartInstance) return;
                    
                    const rect = chartContainerForZoom.getBoundingClientRect();
                    const x = event.clientX - rect.left;
                    
                    dragStartLogical = chartInstance.timeScale().coordinateToLogical(x);
                    if (dragStartLogical === null) { 
                        return; 
                    }
                    isDragging = true; 

                    selectionBand.style.left = x + 'px';
                    selectionBand.style.top = '0px';
                    selectionBand.style.width = '0px';
                    selectionBand.style.height = chartContainerForZoom.clientHeight + 'px';
                    selectionBand.style.display = 'block';

                    chartInstance.applyOptions({ 
                        handleScroll: { pressedMouseMove: false, horzTouchDrag: false, vertTouchDrag: false }, 
                        handleScale: { mouseWheel: false, pinch: false } 
                    });
                });

                document.addEventListener('mousemove', (event) => {
                    if (!isDragging || !chartInstance) return;
                    const rect = chartContainerForZoom.getBoundingClientRect();
                    const currentX = event.clientX - rect.left;
                    
                    const initialX = parseFloat(selectionBand.style.left);
                    const width = Math.abs(currentX - initialX);
                    const newLeft = Math.min(currentX, initialX);

                    selectionBand.style.left = newLeft + 'px';
                    selectionBand.style.width = width + 'px';
                });

                document.addEventListener('mouseup', (event) => {
                    if (!isDragging || !chartInstance) return;
                    
                    isDragging = false;
                    selectionBand.style.display = 'none';

                    const rect = chartContainerForZoom.getBoundingClientRect();
                    const x = event.clientX - rect.left;
                    const dragEndLogical = chartInstance.timeScale().coordinateToLogical(x);

                    if (dragStartLogical !== null && dragEndLogical !== null && dragStartLogical !== dragEndLogical) {
                        const from = Math.min(dragStartLogical, dragEndLogical);
                        const to = Math.max(dragStartLogical, dragEndLogical);
                        if (from !== to) { 
                           chartInstance.timeScale().setVisibleLogicalRange({ from, to });
                        }
                    }
                    
                    chartInstance.applyOptions({ 
                        handleScroll: { pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: true }, 
                        handleScale: { mouseWheel: true, pinch: true } 
                    });
                });

                chartContainerForZoom.addEventListener('dblclick', () => {
                    if (chartInstance) {
                        chartInstance.timeScale().fitContent();
                    }
                });
                window.dragZoomInitializedLightweight = true;
            }
        }
        
        scriptInitializationDone = true;
        return true;
    }

    function renderData(data) {
        if (!initializeChartIfNeeded()) {
            if (data && (!Array.isArray(data) || data.length > 0)) {
                setTimeout(() => renderData(data), 100);
            }
            return;
        }
        
        if (data && seriesInstance) {
            seriesInstance.setData(data);
            if (data.length > 0) {
                 chartInstance.timeScale().fitContent();
            }
        } else if (seriesInstance) {
            seriesInstance.setData([]);
        }
    }

    if (!Object.getOwnPropertyDescriptor(window, 'lightweightChartState')) {
        let _internalState = null; 
        Object.defineProperty(window, 'lightweightChartState', {
            configurable: true, 
            set: function(v) {
                _internalState = v;
                renderData(v); 
            },
            get: function() {
                return _internalState;
            }
        });
    } else {
    }

    // Attempt an initial draw in case data was set before this script ran (less likely with defer)
    // or if the initial state of State.eq_performance_lightweight_json is already populated.
})();
    """

    trigger_script = lambda: (
        rx.script(f"window.lightweightChartState = {State.fi_performance_lightweight_json};",
                  strategy="afterInteractive")
    )

    return rx.fragment(
        rx.box(
            rx.box(id="lw-chart", width="100%", height="100%"),
            rx.box(
                id="lw-selection-band",
                position="absolute",
                display="none",
                bg="rgba(0, 123, 255, 0.2)",
                border="1px solid rgba(0, 123, 255, 0.5)",
                z_index="10",
                top="0",
                left="0",
                width="0px",
                height="100%"
            ),
            id="lw-chart-container",
            position="relative",
            width="100%",
            height="300px"
        ),
        rx.script(src=CDN, strategy="afterInteractive"),
        rx.script(init_js, strategy="afterInteractive"),
        rx.cond(State.fi_performance_lightweight_json,
                trigger_script(),
                rx.script("window.lightweightChartState = null;", strategy="afterInteractive"))
    )

def gauge_component():
    gauge_module=f"""
    <svg width="400" height="200" viewBox="0 0 200 100">
        <defs>
            <linearGradient id="riskGradient" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stop-color="#4CAF50" />   <!-- Green -->
                <stop offset="33%" stop-color="#FFEB3B" />  <!-- Yellow -->
                <stop offset="66%" stop-color="#FF9800" />  <!-- Orange -->
                <stop offset="100%" stop-color="#F44336" /> <!-- Red -->
            </linearGradient>
        </defs>
    
        <!-- Background arc -->
        <path d="M10,100 A90,90 0 0 1 190,100" fill="none" stroke="#eee" stroke-width="15" />
    
        <!-- Foreground arc with gradient -->
        <path d="M10,100 A90,90 0 0 1 190,100" fill="none" stroke="url(#riskGradient)" stroke-width="15"
            stroke-dasharray="{State.dash_value_rx} 282.74" stroke-linecap="round" />
    
        <!-- Arrow (rotates based on risk level) -->
        <g transform="rotate({-90 + State.dash_arrow_rx}, 100, 100)">
            <path d="M100,30 L95,50 L105,50 Z" fill="#ff3e3e" />
            <circle cx="100" cy="100" r="5" fill="#ff3e3e" />
        </g>  
    
        <!-- Text in the center -->
        <text x="100" y="90" font-size="18" text-anchor="middle" fill="#333">{State.std_annual_rx}%</text>
    </svg>
    """
    return rx.html(gauge_module)

def user_info(tokeninfo: dict) -> rx.Component:
    return rx.hstack(
        rx.box(
            rx.avatar(
                name=tokeninfo.get("name") or "Ananymous",
                source=tokeninfo.get("picture") or None
            ),
            width="auto",
            margin_right="0.5em",
        ),
        rx.vstack(
            rx.text(tokeninfo.get("name") or "Anonymous", font_weight="bold", text_align="left"),
            rx.text(tokeninfo.get("email") or "anonymous@example.com", font_size="0.8em", text_align="left"),
            align_items="start",
            spacing="0",
            width="auto",
        ),
        align_items="center",
        width="auto",
    )


def login() -> rx.Component:
    return rx.vstack(
        GoogleLogin.create(on_success=State.on_success),
    )


def require_google_login(page) -> rx.Component:
    @functools.wraps(page)
    def _auth_wrapper() -> rx.Component:
        return GoogleOAuthProvider.create(
            rx.cond(
                State.is_hydrated,
                rx.cond(State.token_is_valid, page(), login()),
                rx.spinner(),
            ),
            client_id=CLIENT_ID,
        )
    return _auth_wrapper