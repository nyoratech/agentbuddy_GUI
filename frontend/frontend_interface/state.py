"""
Application state for the minimal FinBuddy interface.

Responsibilities (this is the "core" kept from the full app):
  * authentication (login / signup against the FastAPI backend, JWT in
    browser LocalStorage so a refresh keeps you logged in),
  * chat: send a question -> backend enqueues a background job -> we show a
    placeholder assistant bubble tied to that job_id,
  * a long-lived RabbitMQ consumer (background task) that receives progress +
    completion notifications and updates the matching bubble live,
  * a notifications feed of everything the backend has pushed.

Everything the consumer needs runs server-side inside the Reflex backend.
"""
import asyncio
import datetime as dt
import json
import logging
from typing import List

import aio_pika
import httpx
import reflex as rx

from .config import backend_url, rabbitmq_url, JOBS_EXCHANGE

logger = logging.getLogger("finbuddy.frontend")


class Msg(rx.Base):
    """A single chat message."""
    role: str          # "user" | "assistant"
    content: str
    job_id: str = ""
    status: str = ""   # assistant only: "queued" | "in_progress" | "completed"


class Notif(rx.Base):
    """An item in the notifications feed."""
    text: str
    status: str
    job_id: str
    time: str


class State(rx.State):
    # --- auth (persisted in the browser) --------------------------------- #
    jwt_token: str = rx.LocalStorage("")
    user_id: str = rx.LocalStorage("")

    # --- login/signup form ---------------------------------------------- #
    username_input: str = ""
    password_input: str = ""
    auth_error: str = ""

    # --- chat ------------------------------------------------------------ #
    chat_id: str = "default"
    messages: List[Msg] = []
    question: str = ""

    # --- notifications --------------------------------------------------- #
    notifications: List[Notif] = []

    # backend-only flag (leading underscore => not serialized to the client)
    _consumer_started: bool = False

    # ------------------------------------------------------------------ #
    # Derived                                                             #
    # ------------------------------------------------------------------ #
    @rx.var
    def is_authenticated(self) -> bool:
        return bool(self.jwt_token)

    @rx.var
    def processing(self) -> bool:
        return any(m.status in ("queued", "in_progress") for m in self.messages)

    @rx.var
    def unread_count(self) -> int:
        return len(self.notifications)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.jwt_token}"}

    # ------------------------------------------------------------------ #
    # Auth handlers                                                       #
    # ------------------------------------------------------------------ #
    async def _auth_request(self, path: str):
        self.auth_error = ""
        if not self.username_input or not self.password_input:
            self.auth_error = "Enter a username and password."
            return
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{backend_url()}{path}",
                    json={"username": self.username_input, "password": self.password_input},
                )
            if resp.status_code == 200:
                data = resp.json()
                self.jwt_token = data["access_token"]
                self.user_id = data["user_id"]
                self.password_input = ""
                return rx.redirect("/")
            self.auth_error = resp.json().get("detail", f"Request failed ({resp.status_code}).")
        except Exception as exc:  # backend down, etc.
            self.auth_error = f"Cannot reach backend: {exc}"

    async def do_login(self):
        return await self._auth_request("/api/auth/login")

    async def do_signup(self):
        return await self._auth_request("/api/auth/signup")

    def logout(self):
        self.jwt_token = ""
        self.user_id = ""
        self.messages = []
        self.notifications = []
        self._consumer_started = False
        return rx.redirect("/login")

    # ------------------------------------------------------------------ #
    # Page load                                                           #
    # ------------------------------------------------------------------ #
    async def on_load_index(self):
        """Guard the main page, restore history and start the consumer."""
        if not self.jwt_token:
            return rx.redirect("/login")
        await self._load_history()
        if not self._consumer_started:
            return State.rabbitmq_consumer

    async def _load_history(self):
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{backend_url()}/api/history",
                    params={"chat_id": self.chat_id},
                    headers=self._headers(),
                )
            if resp.status_code == 200:
                self.messages = [
                    Msg(role=m["role"], content=m["content"], status="completed" if m["role"] == "assistant" else "")
                    for m in resp.json().get("messages", [])
                ]
            elif resp.status_code == 401:
                return self.logout()
        except Exception as exc:
            logger.warning("Could not load history: %s", exc)

    # ------------------------------------------------------------------ #
    # Chat                                                                #
    # ------------------------------------------------------------------ #
    async def send_message(self, form_data: dict):
        question = (form_data.get("question") or "").strip()
        self.question = ""
        if not question or not self.jwt_token:
            return
        self.messages.append(Msg(role="user", content=question))
        yield  # render the user's message immediately

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{backend_url()}/api/chat",
                    json={"chat_id": self.chat_id, "question": question},
                    headers=self._headers(),
                )
            if resp.status_code == 401:
                yield self.logout()
                return
            if resp.status_code != 200:
                self.messages.append(Msg(role="assistant", content=f"⚠️ Backend error ({resp.status_code}).", status="completed"))
                return
            job_id = resp.json()["job_id"]
            # Placeholder bubble the RabbitMQ consumer will fill in live.
            self.messages.append(
                Msg(role="assistant", content="⏳ _queued…_", job_id=job_id, status="queued")
            )
        except Exception as exc:
            self.messages.append(Msg(role="assistant", content=f"⚠️ Cannot reach backend: {exc}", status="completed"))

    # ------------------------------------------------------------------ #
    # Notification handling                                               #
    # ------------------------------------------------------------------ #
    def _apply_notification(self, data: dict):
        job_id = data.get("job_id", "")
        status = data.get("status", "")
        result = data.get("result", "")
        now = dt.datetime.now().strftime("%H:%M:%S")

        # 1) prepend to the notifications feed
        self.notifications = [Notif(text=result, status=status, job_id=job_id, time=now)] + self.notifications

        # 2) update the assistant bubble bound to this job
        for m in self.messages:
            if m.role == "assistant" and m.job_id == job_id:
                if status == "completed":
                    m.content = result
                    m.status = "completed"
                else:
                    m.content = f"⏳ {result}"
                    m.status = "in_progress"
        self.messages = self.messages  # trigger re-render

    @rx.event(background=True)
    async def rabbitmq_consumer(self):
        """Long-lived consumer for user.{user_id}.job.* notifications."""
        async with self:
            if self._consumer_started or not self.user_id:
                return
            self._consumer_started = True
            user_id = self.user_id

        queue_name = f"frontend_{user_id}"
        routing_key = f"user.{user_id}.job.*"
        logger.info("Starting RabbitMQ consumer: queue=%s routing_key=%s", queue_name, routing_key)

        while True:
            try:
                connection = await aio_pika.connect_robust(rabbitmq_url())
                async with connection:
                    channel = await connection.channel()
                    exchange = await channel.declare_exchange(
                        JOBS_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
                    )
                    queue = await channel.declare_queue(queue_name, durable=False, auto_delete=True)
                    await queue.bind(exchange, routing_key)
                    logger.info("RabbitMQ consumer connected, waiting for notifications…")

                    async with queue.iterator() as it:
                        async for message in it:
                            async with message.process():
                                try:
                                    data = json.loads(message.body.decode())
                                except Exception:
                                    continue
                                async with self:
                                    if not self._consumer_started:
                                        return
                                    self._apply_notification(data)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("RabbitMQ consumer error (%s); reconnecting in 3s", exc)
                await asyncio.sleep(3)
                async with self:
                    if not self._consumer_started:
                        return

    def clear_notifications(self):
        self.notifications = []
