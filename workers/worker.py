import os
import sys
import subprocess
import time
import signal
import redis

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379")
MODEL_PATH = os.environ.get("MODEL_PATH")
WORKER_PORT = os.environ.get("WORKER_PORT")

API_ACCESSIBLE_HOSTNAME = os.environ.get("API_ACCESSIBLE_HOSTNAME")
API_ACCESSIBLE_PORT = os.environ.get("API_ACCESSIBLE_PORT")


class LlamaCppWorker:
    def __init__(self):
        if not all([MODEL_PATH, WORKER_PORT, API_ACCESSIBLE_HOSTNAME, API_ACCESSIBLE_PORT]):
            print("Error: Missing one or more required environment variables", file=sys.stderr)
            sys.exit(1)

        self.worker_url = f"http://{API_ACCESSIBLE_HOSTNAME}:{API_ACCESSIBLE_PORT}"
        self.redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        self.llama_process = None

    def _wait_for_redis(self):
        print("Connecting to Redis...")
        while True:
            try:
                self.redis_client.ping()
                print("Successfully connected to Redis.")
                return
            except redis.exceptions.ConnectionError:
                print("Waiting for Redis...")
                time.sleep(2)

    def _register_with_redis(self):
        print(f"Registering host-accessible worker URL: {self.worker_url}")
        self.redis_client.lpush("idle_workers", self.worker_url)
        print("Worker registered successfully.")

    def _deregister_from_redis(self):
        print(f"Deregistering worker: {self.worker_url}")
        self.redis_client.lrem("idle_workers", 0, self.worker_url)
        self.redis_client.lrem("busy_workers", 0, self.worker_url)
        print("Worker deregistered.")

    def start_llama_server(self):
        command = [
            "llama-server",
            "-m", MODEL_PATH,
            "--host", "0.0.0.0",
            "--port", WORKER_PORT,
            "-c", "4096",
            "--threads", "4",
            "--mlock",
            "--cont-batching",
            "--batch-size", "512",
        ]
        
        print(f"Starting llama-server internally on port {WORKER_PORT}")
        self.llama_process = subprocess.Popen(
            command, 
            stdout=sys.stdout, 
            stderr=sys.stderr
        )

    def run(self):
        def handle_shutdown(signum, frame):
            print(f"Received signal {signum}. Shutting down gracefully.")
            self._deregister_from_redis()
            if self.llama_process:
                self.llama_process.terminate()
            sys.exit(0)

        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)
        
        self._wait_for_redis()
        self.start_llama_server()

        time.sleep(10)
        self._register_with_redis()

        try:
            self.llama_process.wait()
            print("llama-server process exited unexpectedly.", file=sys.stderr)
        finally:
            self._deregister_from_redis()
            sys.exit(1)

if __name__ == "__main__":
    worker = LlamaCppWorker()
    worker.run()