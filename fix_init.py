with open("app/services/background_worker.py", "r") as f:
    content = f.read()

# Replace __init__ definition to accept provider
old_init = """    def __init__(
        self,
        worker_id: str = "worker-1",
        base_backoff_seconds: int = 2,
        max_retries: int = 3,
        stale_timeout_minutes: int = 15
    ):"""

new_init = """    def __init__(
        self,
        worker_id: str = "worker-1",
        base_backoff_seconds: int = 2,
        max_retries: int = 3,
        stale_timeout_minutes: int = 15,
        provider = None
    ):
        self.provider = provider"""

if old_init in content:
    content = content.replace(old_init, new_init, 1)
    with open("app/services/background_worker.py", "w") as f:
        f.write(content)
    print("Updated BackgroundWorker.__init__ to accept provider.")
else:
    print("Could not find old __init__ signature.")
