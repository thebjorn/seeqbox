"""A keyless staged-content guard, intended for a local pre-commit hook."""

from pathlib import Path
import re
import subprocess

from .errors import SeeqboxError
from .files import read_json


def check_staged(vault: str | Path, workdir: str | Path,
                 *, cwd: str | Path = ".") -> int:
    """Reject staged working data and unexpected/plaintext files inside the vault.

    This is an accident guard, not a proof of encryption or a general DLP scanner.
    """
    def git(*args):
        result = subprocess.run(["git", "-C", str(cwd), *args],
                                capture_output=True, check=False)
        if result.returncode:
            raise SeeqboxError("Git could not inspect the index.")
        return result.stdout
    root = Path(git("rev-parse", "--show-toplevel").decode().strip()).resolve()
    if Path(vault).resolve() == root or Path(workdir).resolve() == root:
        raise SeeqboxError("Vault and workdir must be subdirectories, not the repository root.")
    try:
        vault_prefix = Path(vault).resolve().relative_to(root).as_posix() + "/"
        work_prefix = Path(workdir).resolve().relative_to(root).as_posix() + "/"
    except ValueError:
        raise SeeqboxError("Vault and workdir must be inside the Git repository.") from None
    names = git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
    checked = 0
    for raw in names.split(b"\0"):
        if not raw:
            continue
        name = raw.decode("utf-8")
        if name.casefold().startswith(work_prefix.casefold()):
            raise SeeqboxError("Plaintext working data is staged. Unstage it before committing.")
        if not name.casefold().startswith(vault_prefix.casefold()):
            continue
        relative = name[len(vault_prefix):]
        mode = git("ls-files", "--stage", "--", name).split(b" ", 1)[0]
        if mode != b"100644":
            raise SeeqboxError("Vault files must be regular non-executable files.")
        if relative in {"format.json", "recipients.txt", ".gitignore"}:
            content = git("show", ":" + name)
            if b"AGE-SECRET-KEY-" in content or b"PRIVATE KEY" in content:
                raise SeeqboxError("A private key is staged in vault configuration.")
            if relative == "format.json":
                config = read_json(content)
                if (set(config) != {"format", "version", "vault_id"}
                        or config["format"] != "seeqbox" or config["version"] != 1
                        or not re.fullmatch(r"[0-9a-f]{32}", str(config["vault_id"]))):
                    raise SeeqboxError("Unexpected public vault configuration.")
            elif relative == "recipients.txt":
                try:
                    recipients = content.decode("ascii").splitlines()
                except UnicodeError:
                    raise SeeqboxError("Invalid public recipient list.") from None
                if not recipients or any(not re.fullmatch(r"age1[a-z0-9]+", r) for r in recipients):
                    raise SeeqboxError("Staged recipients must contain only native age public keys.")
            elif content.replace(b"\r\n", b"\n") != b"/.write-lock\n/.seeqbox-*.tmp\n/objects/.seeqbox-*.tmp\n":
                raise SeeqboxError("Unexpected vault ignore rules.")
        elif relative == "manifest.age" or re.fullmatch(r"objects/[0-9a-f]{32}\.age", relative):
            if not git("show", ":" + name).startswith(b"age-encryption.org/v1\n"):
                raise SeeqboxError("Staged vault object does not have an age header.")
        else:
            raise SeeqboxError("An unexpected file is staged inside the vault.")
        checked += 1
    return checked
