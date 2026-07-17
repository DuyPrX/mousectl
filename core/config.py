import os
import json
from pathlib import Path

# Respect REAL_HOME if set (e.g. by systemd service or our launcher)
real_home = os.environ.get('REAL_HOME')
if not real_home:
    # Try to find the real user's home if we are running under sudo
    sudo_user = os.environ.get('SUDO_USER')
    if sudo_user:
        import pwd
        try:
            real_home = pwd.getpwnam(sudo_user).pw_dir
        except Exception:
            pass

if real_home:
    CONFIG_PATH = Path(real_home) / '.config' / 'mousectl' / 'config.json'
else:
    CONFIG_PATH = Path.home() / '.config' / 'mousectl' / 'config.json'

DEFAULT_CONFIG = {
    'fan_curve': [(30,30),(45,40),(60,55),(70,70),(80,85),(90,100)],
    'fan_curve_active': False,
    'fan_lock_duty': None,
    'undervolt': {
        'core': 0.0, 'cache': 0.0, 'gpu': 0.0,
        'uncore': 0.0, 'analogio': 0.0, 'apply_on_boot': False
    },
    'power': {
        'long': 15, 'short': 25, 'profile': 'balanced', 
        'ratios': [0, 0, 0, 0], 'apply_on_boot': False
    },
    'profiles': {},
    'active_profile': "",
}

def load_config() -> dict:
    try:
        print(f"[INFO] Loading config from: {CONFIG_PATH}")
        if CONFIG_PATH.exists():
            data = json.loads(CONFIG_PATH.read_text())
            cfg = json.loads(json.dumps(DEFAULT_CONFIG)) # Deep copy
            for k, v in data.items():
                if isinstance(v, dict) and k in cfg and isinstance(cfg[k], dict):
                    cfg[k].update(v)
                else:
                    cfg[k] = v
            return cfg
    except Exception:
        pass
    return json.loads(json.dumps(DEFAULT_CONFIG))

def save_config(cfg: dict):
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    except Exception:
        pass

def reset_config() -> dict:
    """Delete saved config and return a clean default. All boot-persistence flags off."""
    try:
        if CONFIG_PATH.exists():
            CONFIG_PATH.unlink()
    except Exception:
        pass
    return json.loads(json.dumps(DEFAULT_CONFIG))
