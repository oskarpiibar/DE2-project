import ray
import socket
import time

# Connect to Ray cluster
ray.init(address="auto")

@ray.remote
def worker_task(x):
    hostname = socket.gethostname()
    time.sleep(2)  # simulate work
    return f"Task {x} executed on {hostname}"

# Submit tasks
futures = [worker_task.remote(i) for i in range(10)]

# Get results
results = ray.get(futures)

print("\nResults:")
for r in results:
    print(r)