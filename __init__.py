# Reschedules siblings so that they always appear together.
# Useful for language learning decks

from typing import List
from dataclasses import dataclass
from typing import Sequence
from anki.decks import DeckManager
from typing import Sequence, Callable

from anki.cards import Card
from anki.consts import REVLOG_RESCHED
from aqt import mw, gui_hooks
from aqt.utils import tooltip
from aqt.qt import QAction


from .configuration import (
    Config,
    config_change,
)

moved_cards = []  # Cards moved
done_cards = []  # Cards marked correct
synchronized_pairs = set() # Notes synced


def get_siblings(card: Card) -> Sequence[Card]:
    card_ids = card.col.db.list("select id from cards where nid=? and id!=?",
                                card.nid, card.id)
    return [mw.col.get_card(card_id) for card_id in card_ids]

def move_siblings(siblings: Sequence[Card]):
    card = mw.reviewer.card

    for sibling in siblings:
        # Move non-new siblings not previously moved or currently in review
        if sibling.id not in moved_cards and sibling.queue != 0 and sibling.due > mw.col.sched.today:
            sibling.due = mw.col.sched.today
            moved_cards.append(sibling.id)
            sibling.flush()


# Sync's all notes, useful for cross-saves
def sync_deck():
    current_deck = mw.col.decks.current()["name"]

    # List of learning notes
    learning_notes = mw.col.find_notes(f'deck:"{current_deck}" is:learn')
   
    for note_id in learning_notes:
        note = mw.col.getNote(note_id)
        
        # Skip suspended, buried, and solo cards
        note_cards = note.cards()
        if len(note_cards) == 1 or any(card.queue < 0 for card in note.cards()): 
            continue
      
        min_queue = min(card.queue for card in note_cards)
        max_left = max(card.left for card in note_cards)
        min_due = float('inf')

        # Reverted learn cards are due in 1969.. 
        for card in note_cards:
            if 946684800 < card.due < min_due:
                min_due = card.due
         
        # Sync siblings
        for card in note.cards():
            card.queue = card.type = min_queue
            card.left = max_left
            card.due = min_due
            card.flush()

    # Repeat for review cards
    review_notes = mw.col.find_notes(f'deck:"{current_deck}" is:review')

    for note_id in review_notes:
        note = mw.col.getNote(note_id)

        note_cards = note.cards()
        if len(note_cards) == 1  or any(card.queue < 0 for card in note.cards()): 
            continue

        min_ivl = min(card.queue for card in note_cards)
        min_due = min(card.left for card in note_cards)

        for card in note.cards():
            card.ivl = min_ivl
            card.due = min_due
    
    mw.reset()


def get_learning_interval(card):
    if card.type == 1:
        col = card.col

        # Retrieve deck configuration
        deck_conf_id = card.did
        deck_manager = DeckManager(col)
        deck_config = deck_manager.config_dict_for_deck_id(deck_conf_id)

        # Learning intervals
        lapse_delays = deck_config['new']['delays']

        # Steps saved: remaining learning phase steps
        current_step_index = len(lapse_delays) - card.left
        
        # Constraints check
        if 0 <= current_step_index < len(lapse_delays):
            current_step_time = int(lapse_delays[current_step_index])
            return current_step_time

    return len(lapse_delays) # Default: Restart learning phrase

    
def sync_siblings(card: Card, siblings: Sequence[Card]):
    
    for sibling in siblings:

        card_pair = frozenset({card.id, sibling.id})
        if card_pair not in synchronized_pairs and card.id in done_cards and sibling.id in done_cards:
            
            # Ensures that both cards graduate together
            if card.queue == 1 and sibling.queue == 2:
                sibling.type = sibling.queue = 1
                sibling.left = card.left
                sibling.due = card.due
            elif card.queue == 2 and sibling.queue == 1:
                card.type = card.queue = 1
                card.left = sibling.left
                card.due = sibling.due
            # Ensures review/learn cards stay on the same scheduling cycle
            elif card.queue != 0 and card.queue == sibling.queue and card.due != sibling.due:
                max_step = max(card.left, sibling.left)
                card.left = sibling.left = max_step

                min_ivl = min(card.ivl, sibling.ivl)
                card.ivl = sibling.ivl = min_ivl
                
                next_due = min(card.due, sibling.due)
                card.due = sibling.due = next_due

            card.flush()
            sibling.flush()
            synchronized_pairs.add(card_pair)

@gui_hooks.reviewer_did_answer_card.append
def reviewer_did_answer_card(reviewer: "Reviewer", card: Card, ease: int) -> None:
    # Card Answered Correctly
    if ease != 1:
        done_cards.append(card.id)
        siblings = get_siblings(card)
        card.flush()
        sync_siblings(card, siblings)
        

# Clear records on review wrap up
@gui_hooks.reviewer_will_end.append
def reviewer_will_end() -> None:
    moved_cards.clear()
    done_cards.clear()
    synchronized_pairs.clear()
   
# First action
@gui_hooks.reviewer_did_show_answer.append
def reviewer_did_show_answer(card: Card):
    if not config.enabled_for_current_deck:
        return

    siblings = get_siblings(card)
    moved_cards.append(card.id)
    move_siblings(siblings)



config = Config()
config.load()

def checkable(title: str, on_click: Callable[[bool], None]) -> QAction:
    action = QAction(title, mw, checkable=True)  # noqa
    action.triggered.connect(on_click)  # noqa
    return action

def set_enabled_for_this_deck(checked):
    config.enabled_for_current_deck = checked

sync_enabled_for_deck = checkable(
    title="Enable sibling synching for this deck",
    on_click=set_enabled_for_this_deck
)
    
mw.form.menuTools.addSeparator()

menu = mw.form.menuTools.addMenu("Sync Siblings")
menu.addAction(sync_enabled_for_deck)

sync = QAction("&Sync Siblings", mw)
sync.triggered.connect(sync_deck)
menu.addAction(sync)

def adjust_menu():
    if mw.col is not None:
        sync_enabled_for_deck.setEnabled(mw.state in ["overview", "review"])
        sync_enabled_for_deck.setChecked(config.enabled_for_current_deck)
        sync.setEnabled(mw.state in ["overview", "review"])

@gui_hooks.state_did_change.append
def state_did_change(_next_state, _previous_state):
    adjust_menu()

@config_change
def configuration_changed():
    config.load()
    adjust_menu()