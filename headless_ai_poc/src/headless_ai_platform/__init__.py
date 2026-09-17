"""Headless capability boundary around the layered agent platform (Part 2).

Experiences (Slack, Web, CLI, REST, events) talk to a versioned capability contract. The contract talks to Part 2's
public facade, `agent_platform.service.PlatformService`, and nothing else in Part 2's engine.
"""

SCHEMA_VERSION = "1.0"
