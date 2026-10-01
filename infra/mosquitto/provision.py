"""Create local-only Mosquitto credentials without committing working passwords."""

import argparse
import os
import re
import secrets
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
USERS = ("device-demo-001", "gateway-demo-001", "health")


def ensure_admin_password(directory: Path) -> None:
    """Create the broker control password once, readable by broker/backend group."""
    directory = directory.resolve()
    path = directory / "admin.password"
    if path.exists():
        return
    if not (directory / "passwd").is_file():
        raise RuntimeError(
            f"Mosquitto password file does not exist: {directory / 'passwd'}"
        )
    if shutil.which("docker") is None:
        raise RuntimeError("Docker is required to set MQTT admin file permissions")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(secrets.token_urlsafe(32) + "\n")
        path.chmod(0o640)
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--mount",
                f"type=bind,source={directory},target=/auth",
                "--entrypoint",
                "chown",
                broker_image(),
                "1883:1883",
                "/auth/admin.password",
            ],
            capture_output=True,
            check=False,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError("Could not set MQTT admin file group to 1883")
    except Exception:
        path.unlink(missing_ok=True)
        raise


def broker_image() -> str:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    match = re.search(r"^\s+image: (eclipse-mosquitto:\S+)$", compose, re.MULTILINE)
    if match is None:
        raise RuntimeError("Cannot find the pinned Mosquitto image in compose.yaml")
    return match.group(1)


def provision(directory: Path) -> None:
    """Provision once; refusing an existing directory prevents silent rotation."""
    if shutil.which("docker") is None:
        raise RuntimeError("Docker is required to hash local MQTT passwords")

    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    directory.chmod(0o755)  # The broker's uid 1883 must traverse the bind mount.
    password_file = directory / "passwd"
    passwords = {user: secrets.token_urlsafe(32) for user in USERS}
    try:
        password_file.write_text(
            "".join(f"{user}:{password}\n" for user, password in passwords.items()),
            encoding="utf-8",
            newline="\n",
        )
        password_file.chmod(0o600)
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--mount",
                f"type=bind,source={directory},target=/auth",
                "--entrypoint",
                "mosquitto_passwd",
                broker_image(),
                "-U",
                "/auth/passwd",
            ],
            capture_output=True,
            check=False,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError("Mosquitto password hashing failed; check Docker")
        hashed = password_file.read_text(encoding="utf-8")
        if any(password in hashed for password in passwords.values()):
            raise RuntimeError("Mosquitto did not replace plaintext passwords")

        # These two files are broker-readable through the read-only bind mount.
        password_file.chmod(0o644)
        for user, password in passwords.items():
            path = directory / f"{user}.password"
            path.write_text(password + "\n", encoding="utf-8", newline="\n")
            path.chmod(0o600)
        ensure_admin_password(directory)
    except Exception:
        for path in directory.iterdir():
            if path.is_file():
                path.unlink()
        directory.rmdir()
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "secrets" / "mosquitto",
        help="Ignored local auth directory (default: secrets/mosquitto)",
    )
    parser.add_argument(
        "--ensure-admin",
        action="store_true",
        help="Add the MQTT control password to an existing auth directory",
    )
    args = parser.parse_args()
    try:
        if args.ensure_admin:
            ensure_admin_password(args.output_dir)
        else:
            provision(args.output_dir)
    except FileExistsError as error:
        raise SystemExit(
            f"Credential directory already exists: {args.output_dir}. "
            "Keep it for existing clients or move it aside before rotating."
        ) from error
    except (RuntimeError, subprocess.TimeoutExpired, OSError) as error:
        raise SystemExit(str(error)) from error
    if args.ensure_admin:
        print(f"MQTT control password is ready in {args.output_dir}")
    else:
        print(
            f"Created local MQTT credentials in {args.output_dir} for {', '.join(USERS)}"
        )


if __name__ == "__main__":
    main()
