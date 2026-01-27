"""TickTick API client with OAuth token management."""

import time
import webbrowser
from dataclasses import dataclass
from datetime import date

import requests

from .config import Config, Tokens, load_config

API_BASE = "https://api.ticktick.com/open/v1"
OAUTH_AUTHORIZE_URL = "https://ticktick.com/oauth/authorize"
OAUTH_TOKEN_URL = "https://ticktick.com/oauth/token"
REDIRECT_URI = "http://localhost:8080/callback"


class AuthenticationError(Exception):
    """Raised when authentication fails."""

    pass


@dataclass
class Task:
    """A TickTick task."""

    id: str
    title: str
    priority: int
    due_date: date | None
    project_id: str
    project_name: str = ""

    @classmethod
    def from_api(cls, data: dict, project_name: str = "") -> "Task":
        due = None
        if data.get("dueDate"):
            due = date.fromisoformat(data["dueDate"].split("T")[0])
        return cls(
            id=data["id"],
            title=data["title"],
            priority=data.get("priority", 0),
            due_date=due,
            project_id=data.get("projectId", ""),
            project_name=project_name,
        )


class TickTickClient:
    """Client for TickTick API with automatic token refresh."""

    def __init__(self, config: Config | None = None, tokens: Tokens | None = None):
        self.config = config or load_config()
        self.tokens = tokens or Tokens.load()
        self._session = requests.Session()

    def _ensure_valid_token(self) -> None:
        """Refresh token if expired or expiring soon."""
        if not self.tokens.access_token:
            raise AuthenticationError("No access token. Run 'friday auth' first.")

        # Refresh if expiring within 5 minutes
        if self.tokens.expires_at and time.time() >= self.tokens.expires_at - 300:
            self._refresh_token()

    def _refresh_token(self) -> None:
        """Refresh the access token."""
        if not self.tokens.refresh_token:
            raise AuthenticationError("No refresh token. Run 'friday auth' first.")

        resp = self._session.post(
            OAUTH_TOKEN_URL,
            data={
                "client_id": self.config.ticktick_client_id,
                "client_secret": self.config.ticktick_client_secret,
                "refresh_token": self.tokens.refresh_token,
                "grant_type": "refresh_token",
            },
        )

        if resp.status_code != 200:
            raise AuthenticationError(f"Token refresh failed: {resp.text}")

        data = resp.json()
        self.tokens.access_token = data["access_token"]
        if "refresh_token" in data:
            self.tokens.refresh_token = data["refresh_token"]
        self.tokens.expires_at = int(time.time()) + data.get("expires_in", 3600)
        self.tokens.save()

    def _api_request(self, endpoint: str) -> dict | list:
        """Make authenticated API request."""
        self._ensure_valid_token()
        resp = self._session.get(
            f"{API_BASE}{endpoint}",
            headers={"Authorization": f"Bearer {self.tokens.access_token}"},
        )
        resp.raise_for_status()
        return resp.json()

    def get_projects(self) -> list[dict]:
        """Get all projects."""
        return self._api_request("/project")

    def get_project_tasks(self, project_id: str) -> list[dict]:
        """Get tasks for a project."""
        data = self._api_request(f"/project/{project_id}/data")
        return data.get("tasks", [])

    def get_all_tasks(self) -> list[Task]:
        """Get all tasks from all projects."""
        tasks = []
        projects = self.get_projects()
        project_names = {p["id"]: p["name"] for p in projects}

        for project in projects:
            project_tasks = self.get_project_tasks(project["id"])
            for task_data in project_tasks:
                tasks.append(Task.from_api(task_data, project_names.get(project["id"], "")))

        return tasks

    def get_priority_tasks(self, as_of: date | None = None) -> list[Task]:
        """Get tasks that are due today/overdue or high priority."""
        as_of = as_of or date.today()
        tasks = self.get_all_tasks()

        priority_tasks = [
            t
            for t in tasks
            if (t.due_date and t.due_date <= as_of) or t.priority >= 3
        ]

        # Sort by priority descending
        return sorted(priority_tasks, key=lambda t: t.priority, reverse=True)

    def get_inbox_tasks(self) -> list[Task]:
        """Get tasks from the Inbox project."""
        projects = self.get_projects()
        inbox = next((p for p in projects if p["name"].lower() == "inbox"), None)
        if not inbox:
            return []

        tasks = self.get_project_tasks(inbox["id"])
        return [Task.from_api(t, "Inbox") for t in tasks]


def authorize(config: Config | None = None) -> Tokens:
    """Run OAuth authorization flow."""
    config = config or load_config()

    if not config.ticktick_client_id or not config.ticktick_client_secret:
        raise AuthenticationError(
            "Missing TickTick credentials. Add them to config/friday.conf"
        )

    auth_url = (
        f"{OAUTH_AUTHORIZE_URL}"
        f"?client_id={config.ticktick_client_id}"
        f"&scope=tasks:read%20tasks:write"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
    )

    print("Opening browser for TickTick authorization...")
    webbrowser.open(auth_url)

    print("\nAfter authorizing, you'll be redirected to a page that won't load.")
    print("Copy the 'code' parameter from the URL.\n")

    code = input("Paste the code here: ").strip()
    if not code:
        raise AuthenticationError("No code provided")

    print("Exchanging code for tokens...")
    resp = requests.post(
        OAUTH_TOKEN_URL,
        data={
            "client_id": config.ticktick_client_id,
            "client_secret": config.ticktick_client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        },
    )

    if resp.status_code != 200:
        raise AuthenticationError(f"Token exchange failed: {resp.text}")

    data = resp.json()
    tokens = Tokens(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token", ""),
        expires_at=int(time.time()) + data.get("expires_in", 3600),
    )
    tokens.save()

    print("Authentication successful!")
    return tokens
