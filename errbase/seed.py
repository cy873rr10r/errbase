"""
seed.py — the starter "community error graph".

These are common errors every Arch/Nix/CachyOS/dev hits. Seeding them means a
user's FIRST encounter with an error still gets an answer — demonstrating the
network effect without needing real users yet.

Keep these real and verifiable — judges may recognize them.
"""

SEED_CARDS = [
    {
        "error": "permission denied on /run/user/1000/hyprland-0 socket",
        "fix": "rm -f /run/user/$(id -u)/hyprland-*.lock && systemctl --user restart hyprland",
        "system": "CachyOS",
        "cmd": "hyprctl reload",
    },
    {
        "error": "error: failed to commit transaction (conflicting files) pacman",
        "fix": "sudo pacman -S --overwrite '*' <package>",
        "system": "Arch",
        "cmd": "sudo pacman -Syu",
    },
    {
        "error": "error: GPGME error: No data signature keyring pacman",
        "fix": "sudo pacman-key --refresh-keys && sudo pacman -Sy archlinux-keyring",
        "system": "Arch",
        "cmd": "sudo pacman -Syu",
    },
    {
        "error": "error: collision between attribute names nixos rebuild",
        "fix": "nix-collect-garbage -d && sudo nixos-rebuild switch",
        "system": "NixOS",
        "cmd": "sudo nixos-rebuild switch",
    },
    {
        "error": "error: experimental Nix feature 'nix-command' is disabled",
        "fix": "echo 'experimental-features = nix-command flakes' >> ~/.config/nix/nix.conf",
        "system": "NixOS",
        "cmd": "nix build",
    },
    {
        "error": "fatal: refusing to merge unrelated histories git pull",
        "fix": "git pull origin main --allow-unrelated-histories",
        "system": "git",
        "cmd": "git pull",
    },
    {
        "error": "fatal: Authentication failed for github https remote",
        "fix": "git remote set-url origin git@github.com:USER/REPO.git",
        "system": "git",
        "cmd": "git push",
    },
    {
        "error": "Cannot connect to the Docker daemon at unix:///var/run/docker.sock",
        "fix": "sudo systemctl start docker && sudo usermod -aG docker $USER",
        "system": "docker",
        "cmd": "docker ps",
    },
    {
        "error": "docker: Error response from daemon port is already allocated",
        "fix": "docker ps -q | xargs -r docker stop && docker container prune -f",
        "system": "docker",
        "cmd": "docker compose up",
    },
    {
        "error": "npm ERR! code EACCES permission denied npm global install",
        "fix": "npm config set prefix ~/.npm-global && export PATH=~/.npm-global/bin:$PATH",
        "system": "node",
        "cmd": "npm i -g",
    },
    {
        "error": "ModuleNotFoundError: No module named pip externally managed environment",
        "fix": "pip install --break-system-packages <package>",
        "system": "python",
        "cmd": "pip install",
    },
    {
        "error": "error: externally-managed-environment pip install",
        "fix": "python -m venv .venv && source .venv/bin/activate && pip install <package>",
        "system": "python",
        "cmd": "pip install",
    },
    {
        "error": "bind: address already in use port 8000",
        "fix": "fuser -k 8000/tcp",
        "system": "Linux",
        "cmd": "uvicorn app:app",
    },
    {
        "error": "nvidia driver mismatch failed to initialize NVML",
        "fix": "sudo modprobe -r nvidia_uvm && sudo modprobe nvidia_uvm",
        "system": "CachyOS",
        "cmd": "nvidia-smi",
    },
    {
        "error": "wayland could not connect to display hyprland",
        "fix": "export WAYLAND_DISPLAY=wayland-1 && export XDG_RUNTIME_DIR=/run/user/$(id -u)",
        "system": "Hyprland",
        "cmd": "<gui app>",
    },
]
