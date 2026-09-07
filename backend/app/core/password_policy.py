"""
MODULE: Password strength policy.

Enforced whenever a user sets their own password (self-service Change Password).
Not applied to admin-generated temporary passwords (access requests, password
resets), which are always random and already meet these rules by construction.
"""
import re


MIN_LENGTH = 8


def validate_password_strength(password: str) -> list[str]:
    """Returns a list of unmet requirements. An empty list means the password is acceptable."""
    problems = []
    if len(password) < MIN_LENGTH:
        problems.append(f"be at least {MIN_LENGTH} characters long")
    if not re.search(r"[A-Za-z]", password):
        problems.append("include at least one letter")
    if not re.search(r"[0-9]", password):
        problems.append("include at least one number")
    if not re.search(r"[^A-Za-z0-9]", password):
        problems.append("include at least one special character (e.g. ! @ # $ % &)")
    return problems
