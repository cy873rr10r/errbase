"""
seed.py — the starter "community error graph".

These are common errors every Arch/Nix/CachyOS/dev hits. Seeding them means a
user's FIRST encounter with an error still gets an answer — demonstrating the
network effect without needing real users yet.

Keep these real and verifiable — judges may recognize them.
"""

# Each fix is a single, atomic command — no `&&` chains or subshells. Cognee's
# entity extraction fragments multi-command fixes into many small nodes, which
# clutters the Mindmap graph view. One error -> one fix -> one clean edge.
SEED_CARDS = [
    {
        "error": "port 8000 already in use",
        "fix": "fuser -k 8000/tcp",
        "system": "Linux",
        "cmd": "uvicorn app:app",
    },
    {
        "error": "docker daemon is not running",
        "fix": "sudo systemctl start docker",
        "system": "docker",
        "cmd": "docker ps",
    },
    {
        "error": "npm permission denied global install",
        "fix": "sudo chown -R $USER /usr/local/lib/node_modules",
        "system": "node",
        "cmd": "npm install -g",
    },
    {
        "error": "pip externally managed environment",
        "fix": "pip install --break-system-packages",
        "system": "python",
        "cmd": "pip install",
    },
    {
        "error": "permission denied running script",
        "fix": "chmod +x script.sh",
        "system": "Linux",
        "cmd": "./script.sh",
    },
    {
        "error": "pacman keyring signature error",
        "fix": "sudo pacman-key --refresh-keys",
        "system": "Arch",
        "cmd": "sudo pacman -Syu",
    },
    {
        "error": "nixos rebuild collision between attribute names",
        "fix": "nix-collect-garbage -d",
        "system": "NixOS",
        "cmd": "sudo nixos-rebuild switch",
    },
    {
        "error": "git push authentication failed",
        "fix": "git remote set-url origin git@github.com:USER/REPO.git",
        "system": "git",
        "cmd": "git push",
    },
    {
        "error": "git pull refusing to merge unrelated histories",
        "fix": "git pull --allow-unrelated-histories",
        "system": "git",
        "cmd": "git pull",
    },
    {
        "error": "hyprland socket permission denied",
        "fix": "systemctl --user restart hyprland",
        "system": "Hyprland",
        "cmd": "hyprctl reload",
    },
]
