"""Command line interface with explicit plaintext output destinations."""

import argparse
import json
import os
from pathlib import Path
import sys

from . import __version__
from .age import Age, FileIdentity, SeeqretIdentity
from .errors import SeeqboxError
from .files import atomic_write, bounded_read
from .git import check_staged
from .vault import Vault
from .workspace import seal, unlock


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="seeqbox", description="Encrypted, versionable data for your applications.")
    root.add_argument("--version", action="version", version=__version__)
    root.add_argument("--vault", type=Path, default=Path("vault"), help="encrypted vault directory (default: vault)")
    root.add_argument("--identity", "-i", type=Path, action="append", help="age identity file; repeat for multiple keys")
    root.add_argument("--age", default="age", help="trusted age executable (default: age on PATH)")
    root.add_argument("--seeqret-key", help="read native age identity text from this seeqret key")
    root.add_argument("--seeqret-app", default="seeqbox")
    root.add_argument("--seeqret-env", default="local")
    sub = root.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="initialize an empty vault using public recipients")
    init.add_argument("--recipient", "-r", action="append", required=True)
    put = sub.add_parser("put", help="encrypt a file as a named object")
    put.add_argument("name")
    put.add_argument("file", type=Path)
    put.add_argument("--metadata-file", type=Path, help="JSON object (kept encrypted)")
    get = sub.add_parser("get", help="decrypt one object to an explicit file")
    get.add_argument("name")
    get.add_argument("--output", "-o", type=Path, required=True)
    sub.add_parser("list", help="print decrypted object names and metadata as JSON")
    sub.add_parser("verify", help="authenticate all referenced objects")
    delete = sub.add_parser("delete", help="remove an entry; history remains")
    delete.add_argument("name")
    load = sub.add_parser("unlock", help="restore a working directory without overwriting local edits")
    load.add_argument("directory", type=Path)
    save = sub.add_parser("seal", help="encrypt a working directory, refusing stale copies")
    save.add_argument("directory", type=Path)
    save.add_argument("--prune", action="store_true", help="remove entries whose local files were deleted")
    rotate = sub.add_parser("recipients", help="re-encrypt current contents for a replacement recipient list")
    rotate.add_argument("--recipient", "-r", action="append", required=True)
    guard = sub.add_parser("check-staged", help="reject plaintext workdir and malformed vault files in Git's index")
    guard.add_argument("--workdir", type=Path, default=Path("data"))
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "check-staged":
            count = check_staged(args.vault, args.workdir)
            print(f"Checked {count} staged vault files.")
            return 0
        engine = Age(args.age)
        if args.command == "init":
            Vault.create(args.vault, args.recipient, age=engine)
            print("Vault initialized. Keep private keys and plaintext working data out of Git.")
            return 0
        if args.seeqret_key and args.identity:
            raise SeeqboxError("Choose either identity files or a seeqret key.")
        if args.seeqret_key:
            identity = SeeqretIdentity(args.seeqret_key, args.seeqret_app, args.seeqret_env)
        else:
            paths = args.identity or ([Path(os.environ["SEEQBOX_IDENTITY"])]
                                      if os.environ.get("SEEQBOX_IDENTITY") else [])
            if not paths:
                raise SeeqboxError("Use --identity, SEEQBOX_IDENTITY, or --seeqret-key.")
            identity = FileIdentity(*paths)
            if any(args.vault.resolve() == p or args.vault.resolve() in p.parents for p in identity.paths):
                raise SeeqboxError("Identity files must be outside the encrypted vault.")
        vault = Vault(args.vault, identity, age=engine)
        if args.command == "put":
            metadata = None
            if args.metadata_file:
                from .files import read_json
                metadata = read_json(bounded_read(args.metadata_file))
            changed = vault.put(args.name, bounded_read(args.file), metadata)
            print("Stored object." if changed else "Object unchanged.")
        elif args.command == "get":
            target = args.output.absolute()
            if args.vault.resolve() == target.resolve() or args.vault.resolve() in target.resolve().parents:
                raise SeeqboxError("Plaintext output must be outside the encrypted vault.")
            if target.exists() or target.is_symlink():
                raise SeeqboxError("Output already exists; choose a new path.")
            atomic_write(target, vault.get(args.name))
            print("Object decrypted to the requested file.")
        elif args.command == "list":
            print(json.dumps(vault.list(), indent=2, ensure_ascii=True))
        elif args.command == "verify":
            print(f"Verified {vault.verify()} objects.")
        elif args.command == "delete":
            vault.delete(args.name)
            print("Entry removed. Historical ciphertext remains.")
        elif args.command == "seal":
            print(f"Sealed {seal(vault, args.directory, prune=args.prune)} changes.")
        elif args.command == "unlock":
            print(f"Restored {unlock(vault, args.directory)} objects.")
        elif args.command == "recipients":
            vault.rotate(args.recipient)
            print("Current contents re-encrypted. Old keys can still decrypt history.")
        return 0
    except (SeeqboxError, OSError) as exc:
        # OSError filenames can contain private record names; omit those details.
        message = str(exc) if isinstance(exc, SeeqboxError) else "Filesystem operation failed."
        print(f"seeqbox: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
