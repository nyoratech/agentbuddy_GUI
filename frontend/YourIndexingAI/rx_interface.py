"""
Shim for the full project's YourIndexingAI.rx_interface.

The real module wires the frontend to the whole agent/storage backend. Here we
provide just the surface the original `finbuddy` UI imports, backed by the
minimal mock backend:

  * init_bot() returns a MockBot whose FB_super_agent() POSTs the message to the
    mock backend's /api/chat, which enqueues a background job and returns a
    job_id. We hand back "...QUEUE:{job_id}" so the ORIGINAL state.py flow (start
    progress, then let the RabbitMQ consumer fill in the answer on completion)
    runs unchanged.
  * the storage-listing helpers return safe empties — the mock backend generates
    no portfolios/plots, but the UI still renders them if data ever appears.
"""
import os
import logging

import httpx

logger = logging.getLogger("finbuddy.shim.rx_interface")


def _backend_url() -> str:
    explicit = os.getenv("BACKEND_URL")
    if explicit:
        return explicit.rstrip("/")
    if os.getenv("RUNNING_IN_DOCKER", "false").lower() == "true":
        return "http://backend:8008"
    return "http://localhost:8008"


def _use_async() -> bool:
    """Async mode = background job + live RabbitMQ notifications (needs a broker).
    Sync mode (default) = inline answer, no broker needed."""
    return os.getenv("USE_ASYNC_JOBS", "false").lower() == "true"


class MockBot:
    """Stand-in for ConversationBot2 — routes chat to the mock backend.

    * sync mode (default): POST /api/chat_sync, return the answer directly.
    * async mode: POST /api/chat, return "QUEUE:{job_id}" so the original UI
      shows an acknowledgement and the RabbitMQ consumer fills in the answer.
    """

    async def FB_super_agent(self, text="", user_dir="", current_chat="",
                             last_portfolio_id="1", last_dataplot_id="1",
                             last_datatable_id="1", backend=False, state=None, **kwargs):
        state = state or {}
        jwt_token = state.get("jwt_token", "")
        headers = {"Authorization": f"Bearer {jwt_token}"} if jwt_token else {}
        payload = {"chat_id": current_chat or "default", "question": text}
        path = "/api/chat" if _use_async() else "/api/chat_sync"
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(f"{_backend_url()}{path}", json=payload, headers=headers)
            if resp.status_code != 200:
                return f"Backend error ({resp.status_code}). Please try again."
            data = resp.json()
            if _use_async():
                # Acknowledgement now; the RabbitMQ consumer delivers the answer.
                return f"Working on your request… QUEUE:{data['job_id']}"
            return data.get("answer", "")
        except Exception as exc:
            logger.warning("MockBot backend call failed: %s", exc)
            return f"Could not reach backend: {exc}"

    def run_text(self, *args, **kwargs):
        return "(mock) This minimal build routes chat through the background-job backend."


def init_bot():
    return MockBot()


# --------------------------------------------------------------------------- #
# Storage helpers — safe empties (no portfolios/plots exist in the mock build)  #
# --------------------------------------------------------------------------- #
def list_saved_portfolios(user_dir: str):
    return []


def list_all_portfolios(user_dir: str):
    return []


def list_saved_plots(user_dir: str):
    return []


def read_live_portfolio(portfolio_name, user_dir: str):
    return None, None


def read_portfolio(portfolio_name, user_dir: str, portfolio_type="equity"):
    return None, None, None


def load_images_from_directory(user_dir: str):
    return []


def load_datas_from_directory(file_names, user_dir: str):
    return {}


def load_files_from_directory(user_dir: str):
    return [], []


def pool_jobids(job_ids, user_dir: str):
    return {}


def add_user(username: str):
    return True
