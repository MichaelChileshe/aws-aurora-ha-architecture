"""Tiny wrapper so every kit script calls the AWS CLI the same way and fails loudly."""
import json, os, subprocess, sys

# The repo folder (where env.sh lives). env.sh exports WORKDIR; fall back to the parent of scripts/.
ROOT = os.environ.get("WORKDIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def aws(*args):
    """Run `aws <args> --output json` and return parsed JSON (or {} for empty output)."""
    cmd = ["aws", *args, "--output", "json"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit(f"\nFAILED: aws {' '.join(args[:2])}\n{res.stderr.strip()}\n")
    return json.loads(res.stdout) if res.stdout.strip() else {}


def env(name):
    """Read a saved value from the environment, with a clear message if it is missing."""
    val = os.environ.get(name, "")
    if not val:
        sys.exit(f"\nMISSING: ${name} is not set. Run:  source ./env.sh  (from the repo folder)\n")
    return val


def save(name, value):
    """Same as the save() shell function: export for this run + append to env.sh."""
    os.environ[name] = value
    path = os.path.join(ROOT, "env.sh")
    with open(path, "a") as f:
        f.write(f'export {name}="{value}"\n')
    print(f"saved {name}={value}")


def use_profile(profile):
    """Run every following AWS CLI call as a named profile (e.g. the finance account)."""
    if profile:
        os.environ["AWS_PROFILE"] = profile
