"""Fetch layer: robots, rate-limit, cache, content-addressed snapshots.

API-first; page fetching is enrichment (D-013). Every fetch is content-hashed over
*normalised* content so an unchanged page hits cache even when volatile chrome
changes (cost §3b-i). Nothing here defeats a login or a bot-wall (D-039).
"""
