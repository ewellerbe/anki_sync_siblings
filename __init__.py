# Reschedules siblings so that they always appear together
# Useful for language learning decks (functions like Wanikani)

from typing import Sequence
from typing import Sequence, Callable

from anki.cards import Card
from aqt import mw, gui_hooks
from aqt.qt import QAction

from .configuration import (
    Config,
    config_change,
)

moved_notes = [] # Cards moved
done_cards = []  # Cards marked correct
initial_sync = False

def get_siblings(card: Card) -> Sequence[Card]:
    card_ids = card.col.db.list("select id from cards where nid=? and id!=?",
                                card.nid, card.id)
    return [mw.col.get_card(card_id) for card_id in card_ids]


def move_cards_before_review(card: Card, siblings: Sequence[Card]):
    moved_notes.append(card.nid)
    for sibling in siblings:
        sibling.due = mw.col.sched.today
        sibling.flush()


def sync_deck():
    current_deck = mw.col.decks.current()["name"]
    notes = mw.col.find_notes(f'deck:"{current_deck}" is:learn OR is:review')

    for note_id in notes:
        note = mw.col.getNote(note_id)
    
        note_cards = note.cards()
        if len(note_cards) == 1 or any(card.queue < 0 for card in note.cards()):
            continue

        card_to_replicate = note_cards[0]
        for sibling in note_cards:
            if card_to_replicate.type == sibling.type:
                if card_to_replicate.type == 1: # Learn Card
                    card_to_replicate =  max([card_to_replicate, sibling], key=lambda card: card.left)
                elif card_to_replicate.type == 2: # Review Card
                    card_to_replicate =  min([card_to_replicate, sibling], key=lambda card: card.ivl)
            else:
                card_to_replicate =  min([card_to_replicate, sibling], key=lambda card: card.type)
     
        for child in note_cards:
            child.queue = child.type = card_to_replicate.type
            child.ivl = card_to_replicate.ivl
            child.left = card_to_replicate.left
            child.due = card_to_replicate.due
            child.flush()

        mw.reset()


def sync_siblings(card:Card, siblings: Sequence[Card]):
    all_cards_done = True
    card_to_replicate = card

    for sibling in siblings:
        if sibling.id not in done_cards:
            all_cards_done = False

            if card_to_replicate.type == sibling.type:
                if card_to_replicate.type == 1: # Learn Card
                    card_to_replicate =  max([card_to_replicate, sibling], key=lambda card: card.left)
                elif card_to_replicate.type == 2: # Review Card
                    card_to_replicate =  min([card_to_replicate, sibling], key=lambda card: card.ivl)
            else:
                card_to_replicate =  min([card_to_replicate, sibling], key=lambda card: card.type)

    children = siblings + [card] # Add the original card first
    if all_cards_done:
        for child in children:
            child.queue = child.type = card_to_replicate.type
            child.ivl = card_to_replicate.ivl
            child.left = card_to_replicate.left
            child.due = card_to_replicate.due
            child.flush()

@gui_hooks.reviewer_did_answer_card.append
def reviewer_did_answer_card(reviewer: "Reviewer", card: Card, ease: int) -> None:
    if not config.enabled_for_current_deck:
        return

    if ease != 1:
        done_cards.append(card.id)
        siblings = get_siblings(card)
        sync_siblings(card, siblings)



@gui_hooks.reviewer_did_show_question.append
def reviewer_did_show_question(card: Card):
    global initial_sync

    if not config.enabled_for_current_deck or initial_sync:
        return

    current_deck = mw.col.decks.current()["name"]
    due_cards = mw.col.find_cards(f'deck:"{current_deck}" is:due')

    initial_sync = True
    for due_card in due_cards:
        due_card = mw.col.getCard(due_card)
        if due_card.nid not in moved_notes:
            siblings = get_siblings(due_card)
            move_cards_before_review(due_card, siblings)

    mw.reset()
    

# Clear records on review wrap up
@gui_hooks.reviewer_will_end.append
def reviewer_will_end() -> None:
    global initial_sync
    initial_sync = False
    moved_notes.clear()
    done_cards.clear()

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
