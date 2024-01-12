from typing import Sequence
from aqt import mw

ENABLED_FOR_DECKS = "enabled_for_decks"

tag = mw.addonManager.addonFromModule(__name__)

def load_config():
    return mw.addonManager.getConfig(tag)

def load_default_config():
    return mw.addonManager.addonConfigDefaults(tag)

def get_current_deck() -> int:
    return mw.col.decks.get_current_id()


DEFAULT_CONFIG = {
    "enabled_for_decks": {}
}

class Config:
    def __init__(self):
        self.load()

    def load(self):
        self.data = load_config() or load_default_config()

    def save(self):
        mw.addonManager.writeConfig(tag, self.data)

    @property
    def enabled_for_deck_ids(self) -> Sequence[str]:
        return [deck_id for deck_id, enabled in self.data[ENABLED_FOR_DECKS].items() if enabled is True]

    @property
    def enabled_for_current_deck(self):
        return str(get_current_deck()) in self.enabled_for_deck_ids

    @enabled_for_current_deck.setter
    def enabled_for_current_deck(self, value):
        self.data[ENABLED_FOR_DECKS][str(get_current_deck())] = value
        self.save()


def config_change(function):
    mw.addonManager.setConfigUpdatedAction(__name__, lambda *_: function())
    
