"""
auth.py - Project Access Verification and Security Gate
Ensures unauthorized users or clone instances must provide the valid access password.
"""
import os
import sys
import hashlib
import getpass

# Authorized SHA-256 password hash
# Storing the cryptographic hash prevents the plaintext password from being visible on GitHub.
EXPECTED_PASSWORD_HASH = "625004342db8173882ba98bcbf6b9e26b68f9b2fee266a1f538994e06bde11de"

_ACCESS_VERIFIED = False


def check_password(candidate: str) -> bool:
    """Verifies whether the candidate password matches the expected SHA-256 hash."""
    if not candidate:
        return False
    candidate_hash = hashlib.sha256(candidate.strip().encode("utf-8")).hexdigest()
    return candidate_hash == EXPECTED_PASSWORD_HASH


def is_running_tests() -> bool:
    """Detects if the process is being invoked as part of an automated test suite."""
    if "unittest" in sys.modules or "pytest" in sys.modules:
        return True
    for arg in sys.argv:
        arg_lower = os.path.basename(arg).lower()
        if "test" in arg_lower or arg_lower.endswith(".pytest"):
            return True
    return False


def verify_project_access(max_attempts: int = 3, skip_if_testing: bool = False) -> bool:
    """
    Prompts the user for the project access password before allowing execution.
    Exits the process immediately if authentication fails.
    """
    global _ACCESS_VERIFIED

    # If already verified in the current runtime session, skip
    if _ACCESS_VERIFIED:
        return True

    # If invoked during test execution and skip_if_testing is set, allow bypass
    if skip_if_testing and is_running_tests():
        _ACCESS_VERIFIED = True
        return True

    # 1. Check if configured in environment variables (e.g. in local .env)
    env_password = os.getenv("PROJECT_PASSWORD")
    if env_password and check_password(env_password):
        _ACCESS_VERIFIED = True
        return True

    # 2. Check CLI argument (--password <pwd>)
    if "--password" in sys.argv:
        try:
            idx = sys.argv.index("--password")
            if idx + 1 < len(sys.argv):
                cli_pwd = sys.argv[idx + 1]
                if check_password(cli_pwd):
                    _ACCESS_VERIFIED = True
                    sys.argv.pop(idx + 1)
                    sys.argv.pop(idx)
                    return True
        except Exception:
            pass

    # 3. Interactive prompt in terminal
    print("\n" + "=" * 60)
    print(" [AUTH] SKILLRACK AUTOMATION - ACCESS VERIFICATION")
    print("=" * 60)
    print(" This project is protected. Please enter the password to run.")
    print("=" * 60)

    attempts = 0
    while attempts < max_attempts:
        attempts += 1
        try:
            try:
                if sys.stdin.isatty():
                    candidate = getpass.getpass(prompt="Enter Password: ")
                else:
                    candidate = sys.stdin.readline().strip()
            except Exception:
                candidate = input("Enter Password: ")

            if check_password(candidate):
                _ACCESS_VERIFIED = True
                print("[AUTH] Access Granted. Starting project...\n")
                return True
            else:
                remaining = max_attempts - attempts
                if remaining > 0:
                    print(f"[AUTH] Incorrect password. {remaining} attempt(s) remaining.\n")
                else:
                    print("[AUTH] Access Denied: Maximum attempts exceeded.")
                    sys.exit(1)

        except (KeyboardInterrupt, EOFError):
            print("\n[AUTH] Authentication aborted by user. Exiting.")
            sys.exit(1)

    sys.exit(1)


if __name__ == "__main__":
    verify_project_access()
