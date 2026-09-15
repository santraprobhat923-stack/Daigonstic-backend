from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class ProviderResult:
    def __init__(self, success: bool, error: Optional[str] = None):
        self.success = success
        self.error = error

class BaseNotificationProvider(ABC):
    @abstractmethod
    def send(self, recipient: str, channel: str, message: str) -> ProviderResult:
        pass

class MockNotificationProvider(BaseNotificationProvider):
    MODE_SUCCESS = "SUCCESS"
    MODE_TEMPORARY_FAILURE = "TEMPORARY_FAILURE"
    MODE_PERMANENT_FAILURE = "PERMANENT_FAILURE"

    def __init__(self, mode: str = MODE_SUCCESS):
        self.mode = mode
        self.history: List[Dict[str, Any]] = []

    def set_mode(self, mode: str):
        self.mode = mode

    def send(self, recipient: str, channel: str, message: str) -> ProviderResult:
        entry = {
            "recipient": recipient,
            "channel": channel,
            "message": message,
            "mode": self.mode
        }
        self.history.append(entry)

        if self.mode == self.MODE_SUCCESS:
            return ProviderResult(success=True)
        elif self.mode == self.MODE_TEMPORARY_FAILURE:
            return ProviderResult(success=False, error="Provider network timeout (temporary)")
        elif self.mode == self.MODE_PERMANENT_FAILURE:
            return ProviderResult(success=False, error="Invalid recipient address (permanent)")
        else:
            return ProviderResult(success=False, error="Unknown provider error")
