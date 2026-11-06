"""Settings load defaults.toml, then overlay <environment>.toml section by section."""
import tomllib


def load(environment):
    with open("config/defaults.toml", "rb") as f:
        merged = tomllib.load(f)
    with open(f"config/{environment}.toml", "rb") as f:
        for section, values in tomllib.load(f).items():
            merged.setdefault(section, {}).update(values)
    return merged
