from dataclasses import dataclass, asdict
import json
import os

CONFIG_FILE_NAME = "shmirot_config.json"

@dataclass
class ScoringConfig:
    # Bonuses (Negative values reduce score, which is good)
    SIMULTANEOUS_BONUS: int = 200
    CONSECUTIVE_BONUS_PER_HOUR: int = 20
    
    # Penalties (Positive values increase score, which is bad)
    CONSECUTIVE_PENALTY_EXPONENT: float = 2.0
    CONSECUTIVE_PENALTY_MULTIPLIER: int = 500
    REST_PENALTY: int = 1000
    ACTIVITY_WINDOW_PENALTY: int = 1000
    HARD_HOUR_PENALTY_BASE: int = 50
    SAME_DAY_PENALTY: int = 50
    
    @staticmethod
    def load() -> 'ScoringConfig':
        if os.path.exists(CONFIG_FILE_NAME):
            try:
                with open(CONFIG_FILE_NAME, 'r') as f:
                    data = json.load(f)
                return ScoringConfig(**data)
            except Exception:
                return ScoringConfig() # Fallback to defaults
        return ScoringConfig()

    def save(self):
        try:
            with open(CONFIG_FILE_NAME, 'w') as f:
                json.dump(asdict(self), f, indent=4)
        except Exception as e:
            print(f"Failed to save config: {e}")

# Global instance
config = ScoringConfig.load()
