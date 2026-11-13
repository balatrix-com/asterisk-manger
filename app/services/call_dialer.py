"""In-memory, single-call Asterisk dialer driven by AMI channel events."""

from __future__ import annotations

import ipaddress
import re
import select
import socket
import threading
import time
import uuid
from dataclasses import dataclass


NUMBER = re.compile(r"^\+?[0-9]{3,20}$")
ENDPOINT = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


@dataclass(frozen=True)
class Target:
    number: str
    server_ip: str
    server_port: int

    @classmethod
    def parse(cls, data: dict) -> "Target":
        number = str(data.get("number", "")).strip()
        server_ip = str(data.get("server_ip", "")).strip()
        try:
            address = ipaddress.ip_address(server_ip)
            server_port = int(data.get("server_port"))
        except (TypeError, ValueError) as exc:
            raise ValueError("Enter a valid server IP and port") from exc
        if not NUMBER.fullmatch(number):
            raise ValueError("Number must contain 3–20 digits, optionally starting with +")
        if address.version != 4 or not 1 <= server_port <= 65535:
            raise ValueError("Use an IPv4 server and port 1–65535")
        return cls(number, server_ip, server_port)


class AMIClient:
    def __init__(self, host: str, port: int):
        self.sock = socket.create_connection((host, port), timeout=5)
        self.sock.setblocking(False)
        self.buffer = b""
        self.send_lock = threading.Lock()
        self._read_greeting()

    def _read_greeting(self) -> None:
        deadline = time.monotonic() + 5
        while b"\n" not in self.buffer:
            if time.monotonic() > deadline:
                raise TimeoutError("AMI greeting timed out")
            self._receive(0.2)
        greeting, self.buffer = self.buffer.split(b"\n", 1)
        if not greeting.startswith(b"Asterisk Call Manager/"):
            raise ConnectionError("Unexpected AMI greeting")

    def send(self, fields: dict[str, str]) -> None:
        if any("\r" in value or "\n" in value for value in fields.values()):
            raise ValueError("Invalid AMI field")
        payload = "".join(f"{key}: {value}\r\n" for key, value in fields.items()) + "\r\n"
        with self.send_lock:
            self.sock.sendall(payload.encode("utf-8"))

    def _receive(self, timeout: float) -> None:
        ready, _, _ = select.select([self.sock], [], [], timeout)
        if ready:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("AMI connection closed")
            self.buffer += chunk
            if len(self.buffer) > 1048576:
                raise ConnectionError("AMI response too large")

    def read(self, timeout: float = 0.2) -> dict[str, str] | None:
        self._receive(timeout)
        marker = b"\r\n\r\n"
        if marker not in self.buffer:
            return None
        raw, self.buffer = self.buffer.split(marker, 1)
        result = {}
        for line in raw.decode("utf-8", "replace").split("\r\n"):
            if ": " in line:
                key, value = line.split(": ", 1)
                result[key] = value
        return result

    def login(self, username: str, secret: str) -> None:
        self.send({"Action": "Login", "Username": username, "Secret": secret, "Events": "call"})
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            message = self.read()
            if message and message.get("Response"):
                if message["Response"] == "Success":
                    return
                raise PermissionError("AMI login failed")
        raise TimeoutError("AMI login timed out")

    def close(self) -> None:
        self.sock.close()


class CallDialer:
    def __init__(self, settings, retry_seconds: float = 5):
        self.settings = settings
        self.retry_seconds = retry_seconds
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.target: Target | None = None
        self.state = "Stopped"
        self.detail = "Ready"
        self.attempt = 0
        self.active_uniqueid: str | None = None

    def snapshot(self) -> dict:
        with self.lock:
            target = self.target
            return {"state": self.state, "detail": self.detail,
                    "running": bool(target is not None and self.worker and self.worker.is_alive() and not self.stop_event.is_set()),
                    "has_target": target is not None,
                    "number": target.number if target else None,
                    "server_ip": target.server_ip if target else None,
                    "server_port": target.server_port if target else None,
                    "attempt": self.attempt}

    def start(self, target: Target) -> dict:
        if not self.settings.ami_username or not self.settings.ami_secret:
            raise RuntimeError("AMI credentials are not configured")
        if not ENDPOINT.fullmatch(self.settings.dialer_endpoint):
            raise RuntimeError("DIALER_ENDPOINT is not configured")
        with self.lock:
            if self.target is not None or self.worker and self.worker.is_alive():
                raise RuntimeError("A dialer test is already active or stopping")
            self.target = target
            self.stop_event.clear()
            self.state = "Calling"
            self.detail = "Starting call"
            self.attempt = 0
            self.active_uniqueid = None
            self.worker = threading.Thread(target=self._run, daemon=True, name="asterisk-dialer")
            self.worker.start()
            return self.snapshot()

    def stop(self) -> dict:
        with self.lock:
            self.stop_event.set()
            worker = self.worker
            self.state = "Stopping"
            self.detail = "Hanging up test call"
        if worker and worker is not threading.current_thread():
            worker.join(timeout=40)
        with self.lock:
            if worker and worker.is_alive():
                raise RuntimeError("Hangup has not been confirmed; check the Asterisk channel")
            unique_id = self.active_uniqueid
        if unique_id:
            self._recover_hangup(unique_id)
        with self.lock:
            self.target = None
            self.state = "Stopped"
            self.detail = "Ready"
            self.attempt = 0
            return self.snapshot()

    def _set(self, state: str, detail: str) -> None:
        with self.lock:
            if not self.stop_event.is_set():
                self.state, self.detail = state, detail

    def _run(self) -> None:
        while not self.stop_event.is_set():
            with self.lock:
                target = self.target
                self.attempt += 1
                self.state, self.detail = "Calling", f"Attempt {self.attempt}: dialing"
            if target is None:
                break
            try:
                self._one_call(target)
            except (OSError, TimeoutError, PermissionError, ConnectionError) as exc:
                self._set("Error", f"AMI error: {exc}")
                break  # Unknown channel state: never risk a duplicate call.
            if not self.stop_event.is_set():
                self.stop_event.wait(self.retry_seconds)

    def _one_call(self, target: Target) -> None:
        client = AMIClient(self.settings.ami_host, self.settings.ami_port)
        try:
            client.login(self.settings.ami_username, self.settings.ami_secret)
            if self.stop_event.is_set():
                return
            action_id = uuid.uuid4().hex
            unique_id = f"dialer-{action_id}"
            channel = f"PJSIP/{self.settings.dialer_endpoint}/sip:{target.number}@{target.server_ip}:{target.server_port}"
            with self.lock:
                self.active_uniqueid = unique_id
            client.send({"Action": "Originate", "ActionID": action_id,
                         "Channel": channel, "ChannelId": unique_id,
                         "Application": "Echo", "Timeout": "30000", "Async": "true"})
            channel_name = None
            hangup_sent = False
            deadline = time.monotonic() + 35
            answered = False
            while True:
                message = client.read()
                if message:
                    event = message.get("Event")
                    if message.get("Response") == "Error" and message.get("ActionID") == action_id:
                        self._set("Disconnected", message.get("Message", "Originate rejected"))
                        with self.lock:self.active_uniqueid = None
                        return
                    if event == "Newchannel" and message.get("Uniqueid") == unique_id:
                        channel_name = message.get("Channel")
                    elif event == "Newstate" and message.get("Uniqueid") == unique_id:
                        if message.get("ChannelStateDesc") == "Up":
                            answered = True
                            self._set("Connected", "Call answered; waiting for hangup")
                        elif message.get("ChannelStateDesc") in {"Ring", "Ringing"}:
                            self._set("Calling", "Remote side is ringing")
                    elif event == "OriginateResponse" and message.get("ActionID") == action_id:
                        if message.get("Response") == "Failure":
                            self._set("Disconnected", "Call was rejected or unanswered")
                            if not channel_name:
                                with self.lock:self.active_uniqueid = None
                                return
                    elif event == "Hangup" and message.get("Uniqueid") == unique_id:
                        self._set("Disconnected", "Call ended")
                        with self.lock:self.active_uniqueid = None
                        return
                if self.stop_event.is_set() and channel_name and not hangup_sent:
                    client.send({"Action": "Hangup", "Channel": channel_name})
                    hangup_sent = True
                    deadline = time.monotonic() + 10
                if (not answered or hangup_sent) and time.monotonic() > deadline:
                    raise TimeoutError("No call completion or hangup confirmation")
        finally:
            client.close()

    def _recover_hangup(self, unique_id: str) -> None:
        """Find the exact test channel after an AMI disconnect, then hang it up."""
        client = AMIClient(self.settings.ami_host, self.settings.ami_port)
        try:
            client.login(self.settings.ami_username, self.settings.ami_secret)
            client.send({"Action": "Status", "ActionID": unique_id})
            deadline = time.monotonic() + 10
            channel = None
            while time.monotonic() < deadline:
                message = client.read()
                if not message:
                    continue
                if message.get("Event") == "Status" and message.get("Uniqueid") == unique_id:
                    channel = message.get("Channel")
                if message.get("Response") == "Error":
                    raise RuntimeError(message.get("Message", "AMI status failed"))
                if message.get("Event") == "StatusComplete":
                    break
            else:
                raise TimeoutError("Could not verify the test channel")
            if channel:
                client.send({"Action": "Hangup", "Channel": channel})
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    message = client.read()
                    if message and message.get("Event") == "Hangup" and message.get("Uniqueid") == unique_id:
                        break
                else:
                    raise TimeoutError("Could not confirm test call hangup")
            with self.lock:self.active_uniqueid = None
        finally:
            client.close()
