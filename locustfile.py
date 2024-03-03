"""
Load generator for the Jitterbug experiment.

Sends equal traffic to /static/data and /jitter/data endpoints,
picking id uniformly from 0..999.

Designed for ~10k req/s total when run with multiple workers.
"""

import random

from locust import FastHttpUser, constant_throughput, task

NUM_IDS = 1000


class JitterbugUser(FastHttpUser):
    """
    Each user targets ~7 req/s; with 1500 users that's ~10.5k req/s target.
    Split across 2 endpoints = ~5k req/s each.
    """

    wait_time = constant_throughput(7)

    @task
    def hit_static(self):
        item_id = random.randint(0, NUM_IDS - 1)
        self.client.get(f"/static/data?id={item_id}", name="/static/data?id=[id]")

    @task
    def hit_jitter(self):
        item_id = random.randint(0, NUM_IDS - 1)
        self.client.get(f"/jitter/data?id={item_id}", name="/jitter/data?id=[id]")
