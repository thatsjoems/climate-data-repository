"""
MODULE: Password strength policy.

Enforced whenever a person sets a password: self-service Change Password, an administrator creating an account, the first administrator made from the
command line, and a password set from the server (scripts/reset_password.py). Temporary passwords made by the application are random and are checked
against the strictest rule, so they always pass.

The rules, and why:
* LENGTH depends on who the account belongs to. The Bank's own staff (BOT analysts and System Administrators) can see sector-wide data or manage every
  account, so they need at least 12 characters. Institution users keep 8. An unknown role gets the stricter rule.
* A LETTER, A DIGIT AND A SPECIAL CHARACTER, as before.
* NOT A COMMON PASSWORD. "Admin1234!" and "P@ssw0rd2026" meet the letter, digit and symbol rule and are among the first guesses anyone makes. A password is
  refused when, with look-alike characters undone (0 for o, 1 for i, 3 for e, 4 for a, 5 for s, 7 for t, @ for a, $ for s) and everything but letters
  removed, it is a well-known password or word with only a few digits or symbols added, or when it is made of very few different characters.
* NOT CONTAINING THE USERNAME (when it is at least 4 characters).
A long phrase of unrelated words is the best choice and always passes: "lantern-river-orange-road-72".
"""
import re
import secrets
import string

MIN_LENGTH = 8              # institution users
STAFF_MIN_LENGTH = 12       # the Bank's own staff: BOT analysts and System Administrators

_LOOK_ALIKES = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})
_MAX_DECORATION = 8         # digits and symbols that may be added to a common word before it stops being "just that word"

# Lower-case letters only. A password is refused when its letters (after undoing look-alikes) are exactly one of these, or one of these with "my", "the" or "new" in
# front or "user" behind.
_COMMON_BASES = frozenset("""
password passwd passw0rd pass pwd secret secrets admin administrator root user username guest test testing tester temp temporary default login logon master
welcome letmein changeme change qwerty qwertyuiop asdfghjkl zxcvbnm abc abcd abcdef abcdefgh abcdefghijkl iloveyou monkey dragon football baseball soccer sunshine
princess shadow superman batman trustno hello hello123 summer winter spring autumn secure security system server computer internet office company
tanzania dodoma dar daressalaam zanzibar bot bank banks bankoftanzania cdr climate climatedata climaterepository repository data database finance financial
nenosiri siri karibu jambo asante mimi pesa benki
""".split())
_COMMON_WHOLE = frozenset({"123456789012", "1q2w3e4r5t6y", "qwertyuiop12", "qwertyuiop123", "123456789abc", "1234567890ab", "passwordpassword", "qwertyqwerty",
                           "asdfghjkl123", "zxcvbnm12345", "abcdefghij12"})


def min_length_for(role) -> int:
    """The minimum length for an account of this role (a RoleEnum or its name). Anything unknown gets the stricter rule."""
    value = getattr(role, "value", role)
    return MIN_LENGTH if value == "INSTITUTION_USER" else STAFF_MIN_LENGTH


def _is_common(password: str) -> bool:
    lowered = password.lower()
    if re.sub(r"[^a-z0-9]", "", lowered) in _COMMON_WHOLE:
        return True
    # Cut the digits and symbols added in front or behind ("Admin1234!" -> "admin"), THEN undo look-alikes inside what is left ("p@ssw0rd" -> "password").
    # (Undoing them first would turn the added digits into letters and hide the word.)
    core = re.sub(r"^[^a-z]+|[^a-z]+$", "", lowered)
    decoration = len(lowered) - len(core)
    base = re.sub(r"[^a-z]", "", core.translate(_LOOK_ALIKES))
    if base:
        candidates = {base}
        for prefix in ("my", "the", "new"):
            if base.startswith(prefix):
                candidates.add(base[len(prefix):])
        if base.endswith("user"):
            candidates.add(base[:-4])
        if candidates & _COMMON_BASES and decoration <= _MAX_DECORATION:
            return True
    return len(set(lowered)) <= 4         # "aaaaaaaa1!", "1212121212!a"


def validate_password_strength(password: str, role=None, username: str | None = None) -> list[str]:
    """Returns a list of unmet requirements. An empty list means the password is acceptable."""
    password = password or ""
    problems = []
    minimum = min_length_for(role)
    if len(password) < minimum:
        problems.append(f"be at least {minimum} characters long")
    if not re.search(r"[A-Za-z]", password):
        problems.append("include at least one letter")
    if not re.search(r"[0-9]", password):
        problems.append("include at least one number")
    if not re.search(r"[^A-Za-z0-9]", password):
        problems.append("include at least one special character (e.g. ! @ # $ % &)")
    if password and _is_common(password):
        problems.append("not be a common password, or a common word with a few digits or symbols added (for example Admin1234! or P@ssw0rd2026): "
                        "a phrase of several unrelated words is best")
    if username and len(username) >= 4 and username.lower() in password.lower():
        problems.append("not contain your username")
    return problems


def generate_secure_temp_password(length: int = 12) -> str:
    """
    Cryptographically secure random password (uses `secrets`, never `random`),
    guaranteed to satisfy validate_password_strength() for ANY role (it is checked against the strictest rule):
    at least one letter, one digit, and one special character, and 12 or more characters.
    """
    length = max(length, STAFF_MIN_LENGTH)
    alphabet = string.ascii_letters + string.digits + "!@#$%&*"

    while True:
        candidate = "".join(secrets.choice(alphabet) for _ in range(length))
        if not validate_password_strength(candidate):
            return candidate
